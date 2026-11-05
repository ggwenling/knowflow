# 欠引用修复第三次独立复审

- Reviewer: Codex 6.1 Sol High（独立只读审阅，未参与实现）
- Branch: `grok`
- HEAD: `b7dced852b2c609d401df4125d6770ea31b4b804`（实跑 `git rev-parse HEAD`）
- 对照：[第二次复审](2026-11-05-sol-under-citation-repair-rereview2.md)，审阅 `4ac425c..b7dced8` 差异及同步/SSE 共用调用链。
- Verdict: **APPROVED**

默认关闭已切断前次 P1 的默认产品发布路径；前次年份加背景精确负例在显式开启时也已拒答。P2-1/P2-2 仍关闭，未发现新的 P0/P1。显式开启后的相关性判断仍有启发式局限，以下记为非阻断 P2，符合本次允许默认 off 后批准的标准。

## 必核项

| 项目 | 独立核验结果 |
| --- | --- |
| 1. 开关默认值 | **通过**。`answering.py:112` 仅接受显式开启值 `on/true/1/yes`，忽略首尾空白及大小写；unset、空串、纯空白、未知值均为 false，`off/false/0/no` 也为 false。辅助函数独立验证 17 组输入；服务实例和真实 finalize 路径另作矩阵验证，未强制覆盖 `_repair_enabled`。 |
| 2. 默认下历次负例 | **通过**。原始零重叠、共享“公司”、共享缓存背景、第二次复审的年份加背景四个精确负例，在 unset、空值、空白、未知值及四个关闭值下，同步/SSE 均保留标准拒答、`has_answer=false`、空 sources、零补问、`repair_attempt=0`、`repair_outcome=not_attempted`。 |
| 3. 显式开启时的闸 | **通过**。数字全覆盖与内容 token 覆盖率 ≥0.5 仍在；新增已识别疑问词前最后一个中文主体短语的 token 全覆盖条件。上述四个精确负例在显式开启时均一次补问后保持拒答，outcome 为 `failed_unrelated`。 |
| 4. 显式开启正例 | **通过**。“2027 年索引何时可检索？”配套含年份的索引资料，同步/SSE 均一次补问成功，outcome 为 `answered`，只发布索引答案和 `src-evidence-1`。unset 时该正例也不补问，符合默认关闭策略。 |
| 5. P2 与 P0/P1 | **通过**。P2-1/P2-2 的独立边界及回落探针全部通过；无新 P0/P1。显式 opt-in 的语义相关性残留见下方 P2，不能据本次批准推导可默认启用。 |

`AnswerService.__init__` 在 `answering.py:543` 读取开关；`:619` 在任何补问调用前检查它。同步路径与 `streaming.py:339` 都使用同一个 `_finalize_generation`，SSE 在最终校验后才发送正文。全仓调用点检查未见生产代码另行强制开启。`.env.example:16` 为 `off`，流式说明、评测说明及 Windows runbook 也已统一默认关闭。

## 精确负例及正例结果

首次 generation 均使用现有 `_ungrounded_generated()`，并独立断言首次结果为标准拒答。除索引正例外，资料 1 沿用 `_two_evidence()` 的索引资料；补问均引用资料 2。

| 场景 | 问题 | 资料 2 / 补问主体 | unset，同步及 SSE | on，同步及 SSE |
| --- | --- | --- | --- | --- |
| 原始零重叠 | 公司 2027 年净利润是多少？ | 原始资料说明缓存默认关闭。 | 拒答，0 次 | 拒答，1 次，failed_unrelated |
| 更早共享公司 | 公司 2027 年净利润是多少？ | 原始资料说明公司缓存默认关闭。 / 公司缓存默认关闭。 | 拒答，0 次 | 拒答，1 次，failed_unrelated |
| 更早共享背景 | 缓存默认关闭时，公司 2027 年净利润是多少？ | 原始资料说明缓存默认关闭。 / 缓存默认关闭。 | 拒答，0 次 | 拒答，1 次，failed_unrelated |
| 前次年份加背景 | 缓存默认关闭时，公司 2027 年净利润是多少？ | 原始资料说明公司 2027 年缓存默认关闭。 / 公司 2027 年缓存默认关闭。 | 拒答，0 次 | 拒答，1 次，failed_unrelated |
| 索引正例 | 2027 年索引何时可检索？ | 资料 1：原始资料说明 2027 年索引 READY 后才可检索。 / 2027 年索引 READY 后才可检索。 | 拒答，0 次 | 成功，1 次，answered |

所有拒答正文均精确等于 `没有足够的资料证据回答这个问题。`，空 sources；所有 SSE 探针均为 `started → delta → sources → completed`，没有错误终态或首版正文泄漏。

独立矩阵共 **156 组通过**：上述五个场景加下方 P2 场景，分别覆盖 13 个开关输入 × 同步/SSE。13 个输入为 unset、`""`、`" \t "`、`sometimes`、`off`、`false`、`0`、`no`、`on`、`" ON "`、`true`、`1`、`yes`。同一场景在各显式开启别名下行为一致，在各关闭/默认输入下均零补问。

另有 7 组直接闸探针通过：覆盖率恰好 0.5 接受、低于 0.5 拒绝、多个数字缺一个拒绝、marker 内数字不计、`12027` 不覆盖 `2027`、空问题内容拒绝、空答案内容拒绝。将缓存摘录直接作为首次 generation 的同步/SSE 对照仍按既有规则接受、零补问，确认新增相关性闸仅位于补问接受分支（`answering.py:643`）。

## P2：显式 opt-in 后仍可能接受背景摘录（已知限制，非阻断）

位置：`answering.py:38` 的疑问词列表、`:100` 的匹配条件、`:108` 的全题覆盖率判断。

第二次复审的精确“是多少”负例已被主体短语检查挡住。但以下自然改写未命中疑问词列表，仍可只凭年份和背景覆盖通过：

```text
问题：缓存默认关闭时，公司 2027 年净利润有多高？
资料 1：原始资料说明索引 READY 后才可检索。
资料 2：原始资料说明公司 2027 年缓存默认关闭。
首次生成：沿用 _ungrounded_generated()，首次校验为标准拒答。
```

```json
{"answer":"公司 2027 年缓存默认关闭[src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-2"]}
```

实测显式 `on` 时同步/SSE 均一次补问、`has_answer=true`、`repair_outcome=answered`，发布上述缓存摘录及一条 source；资料依然没有净利润答案。unset、空值、未知值、显式关闭时均标准拒答且零补问。因此这是原相关性问题在 opt-in 中的残留，按本次审阅标准记为 **P2 已知限制**；原默认开启导致的产品路径 **P1 已关闭**。本结论不要求先解决所有语义改写才能批准默认关闭方案。

## 原 P2 复核

**P2-1 仍关闭。**`citation_verify.py:354,364` 继续限制最终正文长度，`answering.py:632,640` 继续捕获补问契约失败。相对前次，这些 verifier 及 SSE 实现未改动；本次仍实际执行了以下探针：

- 原长度扩张输入 844 code points，补挂后内部正文 18,044；首次生成扩张（off）及补问扩张（on）在同步/SSE 均回落标准拒答，无 error 终态。补问扩张为 `still_ungrounded`。
- 补问结果的 `AnswerResponse` 校验抛 `InvalidMessage`，同步/SSE 保留首次拒答，outcome 为 `failed_contract_validation`。
- fake 补问调用直接抛 `InvalidMessage`，经现有归一得到 `failed_AI_PROCESSING_FAILED`，同步/SSE 同样保留拒答。
- 直接 verifier 的最终长度 **15,999 / 16,000 / 16,001**，`ok` 分别为 **true / true / false**。

上述服务级回落共 8 组通过，长度边界 3 组通过。

**P2-2 仍关闭。**`citation_verify.py:305,371` 继续按原始 marker 出现位置统计保留数量，再从输入总数扣除。独立四组探针：只补挂为 **0**；删除两个原始 marker 并新增一个为 **2**；删除无 claim 独立 marker 为 **1**；同一 ID 两个原始 marker 保留并另补挂为 **0**。未出现负数或新增 marker 抵消删除。

## 验证记录与只读边界

- 聚焦现有 pytest：**78 passed, 79 deselected，4.15s**，退出码 0。范围为 `test_answering.py` 中名称含 repair/reask/prune/citation 的用例，以及 `test_streaming.py` 中六个明确列名的补问/长度/契约回归函数（含参数化）。没有修改现有测试或生产实现。
- 使用现有 `.venv`，`PYTHONDONTWRITEBYTECODE=1`、Python `-B`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；pytest 参数为 `-q -s -p no:logging -p no:cacheprovider -p pytest_asyncio.plugin --noconftest`，通过内存 collection plugin 选择上述用例。未运行会写临时预算文件和 SQLite 账本的全套 autouse fixture，故本次不声称完整套件通过。
- pytest 及额外探针均安装 Python audit hook，拒绝全部 `socket.connect/sendto/getaddrinfo`，并拒绝写模式 `open`、目录创建/删除、文件重命名/删除/链接及 SQLite 连接；使用 FakeRetriever、RepairLlm、ReaskingModel，无 provider transport。**零真实 provider 调用**，无真实模型或 holdout 评测。
- 执行准备时，写入防护阻止了 pytest 默认临时捕获及日志初始化；关闭二者后，一次按行号选择误纳入 provider cancellation 用例，因未加载预算 fixture 而超时（其余 78 项已通过）。改为精确函数名选择后得到上述正式 78 项通过结果；这是审阅 harness 范围修正，非业务修复。
- `git diff --check 4ac425c HEAD` 通过。审阅开始工作树干净，唯一写入为本报告；未创建临时文件、字节码或 pytest cache，未提交或推送。

**最终结论：APPROVED。**
