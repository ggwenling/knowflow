# SSE 消费工程收尾

## 最终工程候选（2026-11-03）

代码目标：`a30394a9042383fafaab9e6ca6c71d64f7b5a156`，基线 `4db75a987028a8f177711bb981a13de0a72bf8e3`。Sol 对精确 SHA 工程审查 **APPROVED**；本轮有限 SSE 工程项已完成，人工消费签收和 PR 合并仍独立待办。

- 统一 HTTP `X-Request-ID`、公开 SSE、内部 AI 请求及问答记录的诊断 ID；覆盖客户端安全 ID、缺省生成 ID、准入失败和幂等冲突。修复前 Java 真实集成测试明确因两个 UUID 不同失败。
- Web 校验版本、帧名与 payload.event、严格序号、请求 ID 及事件阶段；拒绝缺 sources 的 completed、重复 started、sources 后 delta 和当前读取批次内的终态后事件。独立首轮回归在旧实现上复现 8 项失败。合法 sequence=1 的独立 error、零 delta 成功流和 sources 后 error/cancelled 仍可消费。
- completed 后立即结束消费并取消 reader，无须等服务器关闭连接；错误/取消也关闭 reader，不自动重发。独立复审发现的“等待 EOF”及 `has_answer` 与来源数量不一致两项问题已修复并加回归。来源最多 5 项。
- 实时视图消费 `has_answer`，失败/取消清除临时引用，保留已显示的未完成文本和非成功提示。拒答全链路验证标准文本、`has_answer=false`、空来源及成功历史；模型拒答草稿不显示。
- 浏览器真实 Python 28 秒 deadline 验证 `started → delta → error(PROCESSING_TIMEOUT)`、失败 UI、历史 `FAILED/PROCESSING_TIMEOUT` 与空答案/引用；合成模型等待 60 秒后本可合法完成，不直接抛超时。Java 自身 3 秒 deadline 在实际 HTTP 上游/Testcontainers 集成测试中另验 sources 后唯一 timeout error、无 completed 和失败持久化。主动停止保留原 4 秒慢流及无迟到成功/无自动重发检查。

最终候选执行结果：Java **84 tests，0 failures/errors，1 skip**；Windows Python **341 passed**（1 条既有弃用警告）；Web **64 passed**、typecheck/相关 ESLint 通过；Schema **85 structural cases**、OpenAPI **4 passed**。Docker 全栈浏览器 **1/1 passed，场景43.0秒（总44.3秒）**；捕获共享 Schema/顺序校验 text=4、pdf=4、error=3、cancelled=3、timeout=3、refusal=4。隔离项目 `knowflow-e2e-dbccb0ed2a` 容器、网络、卷清零；真实 provider 调用 **0**。

首轮浏览器运行因终态 reader.cancel 后 Chromium `Network.getResponseBody` 不再可读而失败，未冒称通过。测试现为非主动停止流安装只在测试页生效的 response.clone 字节副本，真实 UI 仍消费原流；主动停止不 clone，保留原取消链路。修正后上述最终候选重跑通过。抓包器是六类指定样本的验收器，并非全部合法路径的通用状态机；终态后未来到达的字节由取消连接丢弃，当前批次中的迟到帧则拒绝。

候选已推送 `local`；远端 [PR CI](https://github.com/ggwenling/knowflow/actions/runs/41600122093) 与 [push CI](https://github.com/ggwenling/knowflow/actions/runs/41600113965) 在记录时尚未结束，最终状态以 Actions 及本地交接为准。工程收尾不代替 Java/Python/M 负责人签收，不合并 PR #3，不宣称真实 provider 行为及质量已验收。

## 前一轮限定补验（历史）

代码目标：`802fe48e7d4c689c224c72273a937ac1c8472d73`，基线 `65774c47506ddc0e83ac9b6fd5054a32af590e3b`。Schema SHA-256：`20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`。执行者为 Codex；Luna 服务两次返回 503 后由根代理实施，Sol 独立审阅。

## 修复与验证范围

- 已用解析器和组件回归复现：上游 `cancelled` 被前端误报为 `FAILED`。现以 `AbortError` 传递取消并显示 `CANCELLED`；普通 error 仍显示失败，正常 completed 行为保留。
- 测试专用 AI 入口产生部分 delta 后的 error、上游 cancelled 和可成功完成的慢流。生产服务没有测试触发器，真实 provider 调用为 0。
- 浏览器测试经过 Web proxy、Java、Python、PostgreSQL/MinIO：检查 error/cancelled 的唯一终态、帧内同一 request ID、严格序号、无 sources、UI 非成功状态，以及历史记录的 `FAILED`/`CANCELLED`、空答案/引用和结束时间。
- 主动点击停止后，历史为 `CANCELLED`；超过慢流本可完成的时间后仍无成功结果或答案/引用，没有自动重发，并能从历史重新打开取消记录。主动断连不声称收到了完整 cancelled SSE 帧。
- 捕获校验要求正常流为 `started → delta+ → sources → completed`，本次错误/取消样本为 `started → delta+ → error/cancelled`。它是本次四类捕获的验收器，不是所有合法 SSE 路径的通用状态机。

## 执行证据

- `uv run --project services/ai --frozen pytest services/ai/tests -q`：目标 SHA **338 passed**，1 条既有 Starlette/httpx 弃用警告。
- 在 `apps/web` 执行 Vitest：**46 passed**；`tsc --noEmit` 及本轮改动文件 ESLint 均通过。
- Schema：**85 structural cases**；OpenAPI：**4 passed**。结构检查不代替授权、租约及数据库状态验证。
- 本地 Docker E2E：修复后的中间工作树 **1/1 passed，16.8 秒**；共享 Schema/生命周期校验为 text 4、pdf 4、error 3、cancelled 3 帧。随后 Sol 发现并关闭两项测试缺口：慢流补有效引用并通过真实 AnswerService 校验；新增 sources-before-delta 拒绝用例。最终定向 **15 passed**。
- 目标 SHA 本地 Docker 重跑在构建阶段因 `ghcr.io` 鉴权端点连接失败停止，未执行测试，不能称为目标 SHA 的完整 E2E 通过。前一轮另有 Web 宿主端口暂时不可达，原样重跑后成功。各次隔离 E2E 容器、网络、卷已核对为 0，未清理其他项目服务。
- Sol 对精确 base/target 的代码审阅为 **APPROVED**；两项 P2 发现已修复，无剩余本轮代码阻断。
- 最终目标 [PR CI #20](https://github.com/ggwenling/knowflow/actions/runs/41596593798) 三个 job 均成功：Java **84 tests，0 failures/errors，1 skip**；Linux Python **335 passed，3 skipped，3 warnings**；Schema 85、OpenAPI 4、offline smoke 16；Web 检查与 Docker 全栈 **1/1 passed，14.3 秒**。最终捕获 text/pdf 各4帧、error/cancelled各3帧通过共享 Schema 和顺序校验，CI 隔离容器/网络/卷已清理。Linux 跳过项与本地 Windows 计数不同，不把二者混写为338项Linux通过。

## 消费清单的证据映射（不是签收）

Sol 在目标 SHA 只读核对下列测试。Java `D` 指 `services/api/src/test/java/com/knowflow/api/document/DocumentApiIntegrationTest.java`；Python 测试位于 `services/ai/tests/`。

| 清单项 | 直接测试证据 | 仍需确认的范围 |
| --- | --- | --- |
| Java 1：版本、身份、owner、凭证、租约 | `ApiSecurityIntegrationTest` 内部凭证/旧版本拒绝；`AuthKnowledgeBaseIntegrationTest` owner 隔离；D 的 heartbeat fencing 与 source lease 测试 | 所有端点/配置与授权组合的完整签收 |
| Java 2：幂等、恢复、删除/发布、候选清理 | D 的 `indexBatchWriteIsFencedIdempotentAndConflictDetecting`、completion 原子发布、过期恢复、删除清理与失败更新保留旧索引；`bb25dc1` 隔离恢复报告 | 任意事务中途断连、MinIO 写入故障和全部并发交错 |
| Java 3：问答、deadline/取消、profile、历史 | D 的正常/失败/截断/断连/timeout/迟到完成流测试、锁等待 deadline、两代内容保留与过期来源 null/404；最终候选补 timeout wire、ID 关联及浏览器真实 deadline | 全部刷新/切库与授权并发组合的正式消费签收 |
| Python 1：版本、结构、指纹、profile | `test_service.py` 的共享样例消费、draft10 health、旧/改字节 schema 拒绝、不可执行 runtime profile 拒绝 | 执行环境、审核者、日期及正式消费确认 |
| Python 2：范围、只读、维度、批次、取消、脱敏 | `test_answering.py` 只读查询/越界来源；`test_worker.py` 批次、限制、去重、取消、lease 拒绝；`test_embedding.py` 错维度/错误脱敏；`test_java_client.py` lease receipt | 生产角色权限与真实 provider 的错误/重试行为 |
| Python 3：拒答、SSE、引用映射与失效 | `test_answering.py` 引用/拒答/profile/伪引用；`test_streaming.py` 取消唯一终态、deadline、HTTP disconnect、序列化；D 的来源映射/历史失效与最终全栈拒答补验 | 过期来源的逐项消费签收，以及真实答案支持率与引用准确率 |

较早 `local-backend-e2e-draft10-replay.json` 使用旧 Schema，角色审计仍是 draft.6，不改称目标 SHA 的完整运行验收。恢复报告继续绑定其实际 `bb25dc1` 与隔离环境。

## 验收边界与后续

本记录不代替 Java/Python 消费签收、M/项目负责人签收或正式 Q/M 总体验收。未全面证明所有 deadline、授权、竞态及异常组合；PR #3 仍须负责人签收后才能合并。

前轮遗留的 HTTP/SSE 诊断 ID 关联问题已在最终候选修复，见本文顶部的复现与回归证据。

用户指定 `.env.example` 作为预算信息位置；仅核对变量名与是否有值，未显示凭据值。文件没有供应商硬支出 cap 或超额拒绝证明，因此评测入口保持 fail-closed。用户确认新增私有盲测和生产目标环境仍无更新。
