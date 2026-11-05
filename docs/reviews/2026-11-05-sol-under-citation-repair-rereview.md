# 欠引用修复独立复审

- Reviewer: Codex 6.1 Sol High（独立只读复审，未参与本轮实现）
- Target: `6cedb27 fix(ai): guard citation repairs against unrelated answers`；对照 `e37fb3fb59cfce71002a889fc7c4c3185ca1999d..6cedb27352f24638bdcebf18489a8c9ffc951a4e`
- HEAD: `6cedb27352f24638bdcebf18489a8c9ffc951a4e`（通过 `git rev-parse HEAD` 确认）
- Branch: `grok`
- Verdict: **CHANGES_REQUESTED**

前次报告：[2026-11-05-sol-under-citation-repair.md](2026-11-05-sol-under-citation-repair.md)。已阅读 `git show 6cedb27`、相对 `e37fb3f` 的完整差异及同步/SSE 调用链。范围中另有 `c2e726f`，仅提交前次报告。两个 P2 已解决；原始 P1 精确用例已修复，但共享背景词时仍能把正确拒答变成不回答核心问题的答案，P1 不予关闭。

## P0

未发现。

## P1

### P1-1 未关闭：任意 token 重叠仍可让背景摘录覆盖正确拒答

位置：`services/ai/src/knowflow_ai/answering.py:77`（任意内容 token 交集即通过）；`answering.py:616`（据此接受补问）；`answering.py:84`（补问仍默认开启）。

**原始用例通过。**问题为“公司 2027 年净利润是多少？”，资料及两次生成完全沿用前次 Sol 复现时，同步和 SSE 都返回“没有足够的资料证据回答这个问题。”，`has_answer=false`、空 sources、一次补问，`repair_outcome=failed_unrelated`。没有发布缓存摘录。

**仍然失败的相邻用例。**保持上述问题及 `_ungrounded_generated()` 不变，仅将第二条资料改为“原始资料说明公司缓存默认关闭。”；补问完全照录其中的短句：

```json
{"answer":"公司缓存默认关闭[src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-2"]}
```

资料依然没有任何净利润信息。首次校验仍得到标准拒答；但问题和补问答案共享 `公司` 一个 token，重叠闸通过。实测如下：

| 路径 | 补问开关 | 首次 has_answer | 最终 has_answer | repair_outcome |
| --- | --- | --- | --- | --- |
| 同步 | 关闭 | false | false | not_attempted |
| 同步 | 开启 | false | **true** | **answered** |
| SSE | 关闭 | false | false | not_attempted |
| SSE | 开启 | false | **true** | **answered** |

开启时两条路径都发布“公司缓存默认关闭[src-evidence-2]。”和一条 source；SSE 事件为 `started → delta → sources → completed`。该反例无需利用单 marker 的宽松忠实性规则：补问短句确实完整出现在资料中。

另一个反例不改变原始资料或补问摘录，只把问题写成“缓存默认关闭时，公司 2027 年净利润是多少？”。同步和 SSE 也均从标准拒答变成 `has_answer=true`、`repair_outcome=answered`；重叠全部来自缓存背景，净利润仍无答案。关闭补问则两者均保持拒答。

**影响与判断：**当前保护能识别零词汇重叠，不能保护“有背景重叠、无核心答案”的不可答题。这是前次 P1 所指同一发布路径的残留问题，不另计一个 P1；也不是把既有首次生成的相关性局限当作本次新问题。默认开启时，补问仍会新增错误可发布答案。

**修复要求：**补问接受条件需保护核心所问，不能把任意实体、年份或背景词重叠视为充分条件；至少固化上述两个负例。若本轮无法提供可靠保护，应先默认关闭补问、保留显式 opt-in，完成不可答题回归验证后再开启。只给 `公司` 加停用词不能解决共享其他实体或背景词的同类问题。

可在 `services/ai` 下用现有 fake 在内存复现（不修改业务代码或测试，不调用 provider）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
import asyncio, sys
sys.path.insert(0, 'tests')
from test_answering import (
    FakeRetriever, RepairLlm, _contract, _request,
    _two_evidence, _ungrounded_generated,
)
from test_streaming import ReaskingModel
from knowflow_ai.answering import AnswerService, answer_repair_enabled

async def main():
    assert answer_repair_enabled({}) is True
    request = _request()
    request['question'] = '公司 2027 年净利润是多少？'
    evidence = _two_evidence()
    evidence[1]['text_content'] = '原始资料说明公司缓存默认关闭。'
    first = _ungrounded_generated()
    repaired = {'answer': '公司缓存默认关闭[src-evidence-2]。',
                'has_answer': True, 'source_ids': ['src-evidence-2']}
    for streaming in (False, True):
        calls = []
        model = RepairLlm(first, repaired)
        factory = (lambda: ReaskingModel(first, repaired, calls)) if streaming else (lambda: model)
        service = AnswerService('unused', _contract(),
            retriever=FakeRetriever(evidence), llm_factory=factory)
        service._repair_enabled = True
        initial = service._response_from_generated(request, evidence, first)
        assert initial['has_answer'] is False
        if streaming:
            events = [e async for e in service.stream(request)]
            assert [e['event'] for e in events] == ['started', 'delta', 'sources', 'completed']
            assert events[1]['delta'] == repaired['answer']
            assert events[2]['has_answer'] is True
        else:
            response = await service.answer(request)
            assert response['answer'] == repaired['answer']
            assert response['has_answer'] is True
        assert service.last_diagnostics['repair_outcome'] == 'answered'
        print('SSE' if streaming else 'sync', 'first=false final=true outcome=answered')
asyncio.run(main())
PY
```

## P2

无未关闭的 P2 发现。

### 前次 P2-1：已关闭

`citation_verify.py:354` 对最终 `pruned_answer` 检查 16,000 code points，超限返回 `ok=false`、`reason=answer_too_long_after_prune`；`answering.py:694` 只发布 `ok=true` 的正文，否则使用标准拒答，不会把超长内容送入响应契约或 SSE delta。

前次长度探针复测：输入 **844**，补挂后内部正文 **18,044**，现为不可发布；`pruned_markers=0`。额外检查最终长度 **15,999 / 16,000 / 16,001** 时的 `ok` 分别为 **true / true / false**。首次生成超限且关闭补问时，同步/SSE 均正常输出标准拒答；首次已拒答、补问再返回超长结果时，两者也均保留原拒答，`repair_outcome=still_ungrounded`，没有同步异常或 SSE error。

`answering.py:605,613` 捕获补问阶段的 `InvalidMessage`，结果契约验证失败记录 `failed_contract_validation`，保留首次已验证的拒答及 diagnostics。现有新增测试与额外内存探针均验证同步/SSE 契约拒绝回落。额外让 fake 的补问调用直接抛 `InvalidMessage` 时，`within_deadline` 先归一为 `AI_PROCESSING_FAILED`，最终 `repair_outcome=failed_AI_PROCESSING_FAILED`；同步/SSE 同样正常返回原拒答。这两类失败均不再逃逸为客户端请求错误或流式错误终态。

### 前次 P2-2：已关闭

`citation_verify.py:305,371` 按原始 marker 的 `(start, end)` 位置计数保留项，再用原始 marker 总数减去该数量；新增 marker 不参与减法，同一 ID 的不同出现位置也不会被错误合并。

现有测试与额外探针覆盖：只补挂时 `pruned_markers=0`；删除两个原始 marker 并新增一个时为 **2**；无 claim 的独立 marker 被删时为 **1**；相同 ID 的两个原始 marker 都保留且另补挂时为 **0**。前次长度探针也从负值恢复为 **0**，未见新增 marker 抵消真实删除或产生负数。

## 逐项关闭结论

| 前次事项 | 复审核验 | 关闭结论 |
| --- | --- | --- |
| P1-1 | 原始 Sol 用例同步/SSE 均拒答，outcome 为 failed_unrelated；重叠检查仅位于补问 answered 接受分支 | **未关闭**：共享公司或背景词仍错误接受补问 |
| P2-1 | 最终长度预算生效；补问 InvalidMessage/契约失败在同步/SSE 均保留原拒答 | **已关闭** |
| P2-2 | 按被删原始 marker 计数，新增引用不抵消删除且不产生负数 | **已关闭** |

针对“首次生成路径未变”：相关性重叠闸没有加入 `_evaluate_generated` 或首次生成接受路径。额外将原始缓存摘录直接作为首次生成，同步/SSE 仍按既有行为接受且不补问；此次长度修复则按 P2-1 的要求作用于两条路径共用的 verifier。除此处残留 P1，未发现新的独立 P0/P1。

## 验证记录与边界

完整本地 `services/ai` pytest：**486 passed, 3 skipped, 3 warnings，20.83s**。三个 skip 为 socks 依赖分支及两个 Windows 专用用例；三个 warning 为 TestClient 依赖弃用提示及两次既有本地 PostgreSQL blackhole 测试线程的 `ConnectionResetError`，无失败断言。`git diff --check e37fb3f HEAD` 通过。

使用已有 `.venv`，设置 `PYTHONDONTWRITEBYTECODE=1`、Python `-B`、pytest `-p no:cacheprovider`。全套及额外探针在 Python audit hook 下拒绝非 loopback 的 socket connect/sendto/getaddrinfo；fake、MockTransport、本地协议对端均不调用真实 provider。全套运行入口如下：

```python
import ipaddress, sys
def no_external(event, args):
    if event not in {'socket.connect', 'socket.sendto', 'socket.getaddrinfo'}:
        return
    target = args[0] if event == 'socket.getaddrinfo' else args[-1]
    host = target[0] if isinstance(target, tuple) else target
    if isinstance(host, str):
        if host == 'localhost':
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
    raise RuntimeError('REVIEW_EXTERNAL_NETWORK_DISABLED')
sys.addaudithook(no_external)
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider']))
```

额外内存探针完成原始/共享公司/共享背景三类输入的同步与 SSE、补问开关对照，并核验长度扩张、长度边界、调用异常、结果契约异常和 marker 计数。未做真实模型质量评测，不据单元测试推断不可答题 holdout 指标。业务代码与测试均未修改；唯一写入的仓库文件为本报告。
