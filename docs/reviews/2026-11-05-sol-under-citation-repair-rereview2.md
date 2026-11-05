# 欠引用修复第二次独立复审

- Reviewer: Codex 6.1 Sol High（独立只读审阅，未参与本轮实现）
- Branch: `grok`
- HEAD: `4ac425c3db6f57a2a1ba7036ecc5f4ddec627acf`（实跑 `git rev-parse HEAD`）
- Verdict: **CHANGES_REQUESTED**
- 对照：[前次仍为 CR 的复审](2026-11-05-sol-under-citation-repair-rereview.md)。审阅 `6cedb27..HEAD` 的差异及相关同步/SSE 调用链，并检查中间提交 `0d23763`。当前 HEAD 为文档清理提交，已包含 `2443c5e fix(ai): keep citation repair on with tightened relevance gate`。

默认开启、指定的收紧闸、前次两个精确负例及索引正例均通过核验；P2-1/P2-2 仍关闭。但同一背景重叠问题在背景资料也含年份时仍可复现，原 P1-1 不能关闭。未发现新的独立 P0/P1。

## P1-1 仍未关闭：共享年份和背景词可覆盖正确拒答

位置：`services/ai/src/knowflow_ai/answering.py:87`（数字集合覆盖）、`:92`（全题 token 覆盖率）、`:634`（补问接受分支）。

收紧闸确实落实了“数字全覆盖且内容 token 覆盖 ≥0.5”，但全题覆盖仍可全部来自背景，未要求覆盖核心所问。沿用前次共享缓存背景的问题、首次生成和两条资料结构，仅把缓存资料写成含年份的完整短句：

```text
问题：缓存默认关闭时，公司 2027 年净利润是多少？
资料 1：原始资料说明索引 READY 后才可检索。
资料 2：原始资料说明公司 2027 年缓存默认关闭。
```

第一次 generation 沿用现有 `_ungrounded_generated()`；两条路径均先得到标准拒答。补问只照录资料 2：

```json
{"answer":"公司 2027 年缓存默认关闭[src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-2"]}
```

问题内容 tokens 共 12 个：`2027、公司、关闭、净利、利润、存默、年净、润是、缓存、认关、闭时、默认`。补问覆盖其中 `2027、公司、关闭、存默、缓存、认关、默认`，比例 **7/12 ≈0.5833**；问题数字 `2027` 也完整出现。因此闸通过，但资料和答案均无净利润信息，核心问题仍不可答。

| 路径 | 开关 | 首次 has_answer | 最终 has_answer | 补问次数 | repair_outcome |
| --- | --- | --- | --- | --- | --- |
| 同步 | off | false | false | 0 | not_attempted |
| SSE | off | false | false | 0 | not_attempted |
| 同步 | on | false | **true** | 1 | **answered** |
| SSE | on | false | **true** | 1 | **answered** |
| 同步 | unset | false | **true** | 1 | **answered** |
| SSE | unset | false | **true** | 1 | **answered** |

开启及未设置时均发布上述缓存答案及一条 source。SSE 顺序为 `started → delta → sources → completed`。这是新增补问发布路径将正确拒答变成不回答核心问题的答案，且完整短句确实存在于单条资料中；无需依赖既有单 marker 宽松忠实性规则。关闭补问则保持标准拒答。独立内存探针以“应保留拒答”为断言，四个开启/默认开启路径失败，退出码 1；不是 pytest 套件失败。

**判断与修复要求：**这是前次 P1-1 的残留，不另列新 P1。通过两个精确负例不足以关闭它。保留默认开启时，应保护核心所问的覆盖，而不能仅以年份和全题一半背景词作为充分条件；至少固化本例的同步/SSE、on/off/unset 对照。全题重叠是启发式信号这一文档说明，没有消除已经复现的发布回归。

## 必核项结果

| 项目 | 独立核验结果 |
| --- | --- |
| 1. 默认补问重新开启 | **通过**。`answer_repair_enabled()` 对 unset、空串、空白、未知值返回 true；`on/true/1/yes` 开启，`off/false/0/no` 关闭，strip/lower 生效。构造服务及真实补问路径也验证 unset 开启，不仅检查辅助函数。 |
| 2. 收紧闸及作用范围 | **通过**。去除引用 marker 后，数字集合必须全包含，内容 token 集合交集数/问题 token 数 ≥0.5；空内容拒绝。额外探针验证恰好 0.5 接受、低于 0.5 拒绝、多个数字少一个拒绝、marker 内年份不算覆盖、`12027` 不等于 `2027`。仅补问 `decision=answered` 接受分支调用该闸。将无关缓存摘录直接作为首次生成，同步/SSE 仍沿用既有接受行为，不补问。 |
| 3. 前次两个负例 | **通过精确回归**。共享“公司”和“缓存默认关闭时…净利润”两例，在 on 及 unset 下同步/SSE 均返回标准拒答、`has_answer=false`、空 sources、一次补问、`repair_outcome=failed_unrelated`；off 下不补问并保留拒答。最初零词汇重叠负例也通过。 |
| 4. 正例仍可成功 | **通过**。“2027 年索引何时可检索？”配套资料含“2027 年索引 READY 后才可检索”，在 unset 默认开启时同步/SSE 均一次补问成功，`repair_outcome=answered`，只发布校验后的索引答案及其 source。 |
| 5. P2 与 P0/P1 | P2-1/P2-2 **仍关闭**；未发现新独立 P0/P1，但原 **P1-1 仍未关闭**，见上方年份背景反例，故整体不通过。 |

## P2 复核

**P2-1 仍关闭。**最终正文长度限制仍位于 `citation_verify.py:354,364`。长度扩张探针在首次生成和补问两种情形下，同步/SSE 均返回标准拒答，无 error 终态；补问扩张得到 `still_ungrounded`。直接 verifier 边界 **15,999 / 16,000 / 16,001** 的 `ok` 分别为 **true / true / false**。让补问结果的 `AnswerResponse` 契约校验抛 `InvalidMessage`，同步/SSE 均保留首次拒答，`repair_outcome=failed_contract_validation`。对应异常捕获仍在 `answering.py:622,630`。

**P2-2 仍关闭。**`citation_verify.py:305,371` 以原始 marker 出现位置统计保留数量，再从原始总数中扣除。额外四组探针分别验证：只补挂为 **0**；删除两个原始 marker 并新增一个为 **2**；删除独立 marker 为 **1**；重复 ID 的两个 marker 都保留并另补挂为 **0**。没有负值或新增 marker 抵消删除。

## 验证记录与边界

完整本地 `services/ai` pytest：**506 passed, 3 skipped, 3 warnings，20.37s**。三个 skip 为 socks 依赖分支及两个 Windows 专用用例；warnings 为 TestClient 依赖弃用提示及两次既有 PostgreSQL blackhole 测试线程 `ConnectionResetError`。没有失败断言。`git diff --check 6cedb27 HEAD` 通过。

pytest 使用已有 `.venv`、`PYTHONDONTWRITEBYTECODE=1`、Python `-B`、`-p no:cacheprovider`，通过 Python audit hook 拒绝非 loopback socket connect/sendto/getaddrinfo。额外内存探针使用现有 fake，拒绝所有上述网络操作。**零真实 provider 调用**，未做真实模型或 holdout 质量评测。仓库写入仅本报告，未修改业务代码与测试。

全套运行入口（工作目录 `services/ai`）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
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
PY
```

P1 残留的可复现入口（工作目录同上；预期最后断言失败，列出四个错误发布路径）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
import asyncio, os, sys
def no_network(event, args):
    if event in {'socket.connect', 'socket.sendto', 'socket.getaddrinfo'}:
        raise RuntimeError('REVIEW_NETWORK_DISABLED')
sys.addaudithook(no_network)
sys.path.insert(0, 'tests')
from test_answering import (
    FakeRetriever, RepairLlm, _contract, _request,
    _two_evidence, _ungrounded_generated,
)
from test_streaming import ReaskingModel
from knowflow_ai.answering import AnswerService, REFUSAL

async def main():
    request = _request()
    request['question'] = '缓存默认关闭时，公司 2027 年净利润是多少？'
    evidence = _two_evidence()
    evidence[1]['text_content'] = '原始资料说明公司 2027 年缓存默认关闭。'
    first = _ungrounded_generated()
    repaired = {'answer': '公司 2027 年缓存默认关闭[src-evidence-2]。',
                'has_answer': True, 'source_ids': ['src-evidence-2']}
    failures = []
    for switch in ['off', 'on', None]:
        if switch is None:
            os.environ.pop('KNOWFLOW_ANSWER_REPAIR', None)
        else:
            os.environ['KNOWFLOW_ANSWER_REPAIR'] = switch
        for streaming in [False, True]:
            repairs = []
            model = RepairLlm(first, repaired)
            factory = ((lambda: ReaskingModel(first, repaired, repairs))
                       if streaming else (lambda: model))
            service = AnswerService('unused', _contract(),
                retriever=FakeRetriever(evidence), llm_factory=factory)
            initial = service._response_from_generated(request, evidence, first)
            assert initial['answer'] == REFUSAL and not initial['has_answer']
            if streaming:
                events = [e async for e in service.stream(request)]
                assert [e['event'] for e in events] == [
                    'started', 'delta', 'sources', 'completed']
                answered, answer = events[2]['has_answer'], events[1]['delta']
            else:
                response = await service.answer(request)
                answered, answer = response['has_answer'], response['answer']
            outcome = service.last_diagnostics['repair_outcome']
            print(switch, 'SSE' if streaming else 'sync', answered, outcome, answer)
            if switch == 'off':
                assert not answered and answer == REFUSAL
            elif answered or outcome == 'answered':
                failures.append((switch, 'SSE' if streaming else 'sync'))
    assert not failures, f'P1 canonical refusal overwritten in {failures}'
asyncio.run(main())
PY
```
