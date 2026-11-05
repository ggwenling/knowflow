# 欠引用修复独立审阅

- Reviewer: Codex 6.1 Sol High（独立只读审阅，未参与本轮实现）
- Target range: `101f9b443f515f6c209bae8e7589170c52a0f59c..e37fb3fb59cfce71002a889fc7c4c3185ca1999d`
- HEAD: `e37fb3fb59cfce71002a889fc7c4c3185ca1999d`
- Branch: `grok`
- Verdict: **CHANGES_REQUESTED**

已核对范围只包含 `5b41d67`、`29153b6`、`dbd332c`、`e37fb3f` 四个提交。审阅了完整 diff，并读取调用链、协议及预算边界作为上下文；下面只报告本范围引入的问题。实现说明仅作背景。

## P0

未发现。

## P1

### P1-1 默认开启的补问可将不可答题的正确拒答变成无关摘录答案

位置：`services/ai/src/knowflow_ai/answering.py:568`（只凭第二次 citation decision 接受答案）；`services/ai/src/knowflow_ai/answering.py:43`（未配置时默认开启）；`services/ai/src/knowflow_ai/answering.py:632`（校验引用，不判断是否回答核心问题）。

**复现：**使用现有测试的 `_two_evidence()`，其中资料只有“索引 READY 后才可检索”和“缓存默认关闭”。把问题设为“公司 2027 年净利润是多少？”。第一次 fake generation 返回 `_ungrounded_generated()`，组合断言的两个来源都不能独立覆盖整句，单次校验正确得到标准拒答。第二次返回：

```json
{"answer":"原始资料说明缓存默认关闭[src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-2"]}
```

实际结果：`first_has_answer=false` → `final_has_answer=true`，`repair_calls=1`。第二次答案完全照录原文，仍不回答净利润问题。该探针使用 FakeRetriever/RepairLlm，无 provider 调用。

**影响：**此类输入在基线保持拒答，本改动默认把它改成可发布答案；同步与 SSE 共用接受分支，均受影响。system prompt 虽保留“核心所问”约束，但它不是服务端接受条件，重问提示还鼓励照录短句。实现记录承认该风险并要求启用前验证不可答题指标，当前代码却默认启用，新增测试也没有这一负例。这里并不声称模型每次都会如此生成，而是已证明新的发布路径没有阻止这种回归。

**建议：**补问的发布条件应包含对核心问题可答性的约束，并增加“有相关背景、无核心答案”的回归用例；若本轮无法提供可靠保护，先将补问默认关闭、仅在评测中显式开启，完成独立 holdout 的不可答题回归验证后再启用。不要用引用存在或原文完整包含代替答案相关性。

## P2

### P2-1 补挂引用可突破答案长度上限，并让补问校验异常逃逸

位置：`services/ai/src/knowflow_ai/citation_verify.py:315`（给每个 uncited claim 插入完整 marker）；`services/ai/src/knowflow_ai/answering.py:643`（接受扩张后的正文）；`services/ai/src/knowflow_ai/answering.py:565`（只捕获 ProcessingError）；`services/ai/src/knowflow_ai/answering.py:662`（契约校验）。

**复现：**令已声明来源 ID 为正常 UUID 形式 `src-00000000-0000-0000-0000-000000000001`，来源原文为 `a。`。模型答案为 `a[该ID]。` 后接 400 次 `a。`，`has_answer=true` 且 `source_ids` 只列该 ID。输入正文长 **844** code points，通过生成结果的 16,000 长度检查；修复后正文长 **18,044**，超过 `AnswerResponse.answer.maxLength=16000`。

实际结果：同步 `service.answer()` 抛出 `InvalidMessage('INVALID_MESSAGE')`；SSE 只有 `started → error(AI_PROCESSING_FAILED)`。相同数据调用基线 verifier，只保留首句，长度 **44**，可正常发布。另用先剪空、再返回上述修复答案的 fake model 验证，补问同样抛出 `InvalidMessage`，没有保留已生成的标准拒答。HTTP 同步入口的既有 InvalidMessage handler 会将这类内部生成结果错误映射为 `400 INVALID_REQUEST`。

**影响：**正常范围内的 provider 输出经新增修复后变成协议外结果；provider/资料中的重复短句可触发。只检查模型原始正文长度不足以保护最终正文，且补问“畸形结果保持拒答”的承诺没有覆盖契约校验异常。

**建议：**在修复后的最终正文上执行长度预算，按完整 claim 保留或回落标准拒答；补问的契约校验失败也应归一为受控失败并保持原拒答。补充同步、SSE 和 re-ask 三条路径的长度扩张用例，避免截断 marker 或半句。

### P2-2 pruned_markers 将新增 marker 当作负的剪枝数

位置：`services/ai/src/knowflow_ai/citation_verify.py:365`。

**复现：**

```python
prune_claims("索引可检索[s1]。缓存默认关闭。",
             {"s1": "索引可检索。缓存默认关闭。"})
# repaired_claims == 1, pruned_markers == -1
```

计算使用“输入 marker 总数 − 最终 marker 总数”；新增引用后结果可为负。上面的长度探针返回 `pruned_markers=-400`。

**影响：**日志和 sidecar 的剪枝计数失真；同一答案若既删 marker 又补 marker，两者还会相互抵消，无法据此判断实际剪枝。它不泄漏文本，也不改变预测行 schema，但削弱本次新增观测能力。

**建议：**直接统计原始 marker 中被删除的个数；新增 marker 与删除 marker 分开计数，已有 `repaired_claims` 可保留其自身含义。增加“只补挂”和“删除与补挂同时发生”用例。

## 六项焦点结论

### 1. 补问预算 / guard：通过

`DeepSeekAdapter.generate_repair()` 经 `_generate()` 的同一个 `reserve_provider_call` 入口（`answering.py:209,219`）；`GuardedLlm.generate_repair()` 经 `_reserve("generate", ...)`，真实 adapter 自行预约，fake 由 guard 预约，旧 adapter 回落也位于预约之后（`guarded_adapters.py:124`）。未发现双预约、漏预约或无界重试。服务最多一次补问，要求剩余时间至少 6 秒，以剩余时间减 1 秒限制操作，并受外层 28 秒 deadline 约束。额外 MockTransport 探针验证真实 adapter + guard 两次 HTTP 时预约数依次为 `[1,2]`；预留 7,850,000 microyuan 后，首次生成可执行、补问触发 `BUDGET_SOFT_STOP`，HTTP 次数仍为 1，最终返回标准拒答，`repair_outcome=failed_AI_PROCESSING_FAILED`。预约不退款是既有保守策略，不是双计费。

### 2. 不可答题拒答：部分保留，整体不通过

空 evidence 在同步入口直接标准拒答，SSE 构造 declined generation；均不创建补问。`has_answer=false` 且空 IDs 仍标准拒答、不补问。`has_answer=true` 但空 declared IDs，或正文 marker 集与声明不符，仍在补问前抛 `MODEL_FAILURE`，不会发布；这里沿用的是错误响应，并非统一的标准拒答正文。上述硬边界保持了，但它们不能识别“模型自称可答、资料只有相关背景”；P1-1 已实际复现该路径将正确拒答转为错误可发布答案。

### 3. SSE 流式契约：正常与取消路径通过，失败回落有缺口

`answer_events` 在 `streaming.py:339` await 同一个 `_finalize_generation`，之后才于第 341 行发出正文 `delta`；没有提前泄漏第一版未校验正文。流式第一模型先关闭，补问使用新模型并在 finally 关闭；同步复用原模型。现有成功/仍不合格测试通过，额外阻塞补问取消探针得到 `started → cancelled`，两个模型均关闭，无 delta。超时与 ProcessingError 可回落拒答，CancelledError 继续传播至取消终态。但 P2-1 的 `InvalidMessage` 逃逸会产生 SSE error，并在同步入口变成错误请求响应，不能声称所有补问校验失败都保持拒答。

### 4. 引用忠实性 / prompt-injection：新增绑定规则通过，仍有既有局限

`_verbatim_source` 只遍历答案已声明的 marker IDs，并在 `_normalized`（NFC + 空白折叠）后的单个来源中检查完整 claim 子串；uncited claim 和失配引用栈都不能用两个来源的半句拼接复活（`citation_verify.py:239,281,304`）。服务仍先验证 source IDs 属于本批 scope 内 evidence；未发现新增检索来源、放宽覆盖阈值或把资料指令提升为 system 指令，previous_answer 也在 user JSON 中。多 marker 的完整包含要求未放宽；单 marker 只要求来源非空是基线已有策略，本次继续沿用，不能把所有通过结果描述成严格蕴含验证。完整子串包含本身也不证明相关性或免疫 prompt-injection，P1-1 即可在完全照录时发生。另有 P2-1 的输出扩张问题。

### 5. 观测 sidecar：隐私与 schema 通过，计数不通过

`last_diagnostics` 的当前生产路径仅构造 decision/reason/outcome、布尔值和整数；未发现题面、答案、断言、source_id 或资料原文进入新增 citation diagnostics。`RecordingAnswerService` 将其复制到 capture 信封，collector 再单独写入 diagnostics 文件，预测行结构未增加字段；既有 capture 的 response/trace 本来就有文本，不应与新增 diagnostics 混为一谈。sidecar 另含数据集指纹、question_id 和 outcome，便于关联。当前 HTTP 服务每题新建 AnswerService，未见共享 last_diagnostics 的跨题问题。P2-2 使剪枝计数失真，需修正后才能可靠分析。

### 6. 测试充分性与回归风险：现有测试通过，但不足以批准

新增测试覆盖 reason codes、claim 重挂正负例、一次补问成功/失败/declined/畸形/无时间/关闭、SSE 成功与拒答、fake guard 转发与旧 adapter 回落、sidecar 落盘。完整本地套件结果 **477 passed, 3 skipped, 3 warnings**；聚焦本范围及 provider-budget 的测试为 **208 passed**。三个 skip 分别与 socks 依赖分支、两项 Windows 专用用例有关；本 Linux 环境未验证 Windows。warnings 为两次既有 PostgreSQL blackhole 测试线程的 ConnectionResetError 和 TestClient 依赖弃用提示，没有失败断言。本次新加用例没有覆盖不可答背景摘录、补挂长度扩张、负的 marker 计数；预算真实边界和补问取消虽由额外内存探针验证，建议后续固化成测试。未做真实模型质量评测，不能据单元测试推出 holdout 的不可答题指标不退化。

## 验证方式与边界

所有 pytest 均使用已有 `services/ai/.venv`，`PYTHONDONTWRITEBYTECODE=1`、`python -B`、`-p no:cacheprovider`，不修改业务代码或测试。全套运行在 Python audit hook 下，拒绝非 loopback 的 connect/sendto/getaddrinfo；测试使用 fake、MockTransport 或本地协议对端。额外探针均以内联 Python 运行；真实 adapter 验证使用合成 key、临时合成价格/政策/账本和 MockTransport。零真实 provider 调用，零真实 DeepSeek 预算消耗，无 push。

全套命令（从 `services/ai` 执行）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B - <<'PY'
import sys, ipaddress
def no_external(event, args):
    if event in {'socket.connect', 'socket.sendto', 'socket.getaddrinfo'}:
        target = args[1] if event != 'socket.getaddrinfo' else args[0]
        host = target[0] if isinstance(target, tuple) else target
        if isinstance(host, str):
            if host == 'localhost': return
            try:
                if ipaddress.ip_address(host).is_loopback: return
            except ValueError: pass
        raise RuntimeError('REVIEW_EXTERNAL_NETWORK_DISABLED')
sys.addaudithook(no_external)
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider']))
PY
```

## 交给后续独立实现会话的修复点

1. 保护不可答题的拒答：处理补问结果的核心问题相关性，并在验证完成前采用显式 opt-in；增加背景相关但核心不可答的负例。
2. 对补挂后的最终正文施加协议长度预算，保持完整 claim/marker；归一补问契约校验失败，保留标准拒答，覆盖同步与 SSE。
3. 按实际删除的原始 marker 统计 `pruned_markers`，覆盖新增与删除并存的情况。

本审阅仅写入本报告；未修改实现与测试。上述修复留给后续独立实现会话。
