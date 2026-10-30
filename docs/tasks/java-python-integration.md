# JP-01 Java → Python 开发联调记录

状态：JP-I1 draft.4 的历史证据仍有效；JP2 draft.6 在本机 `local` 工作树完成开发联调和合成后端 E2E，真实模型调用为 0。当前候选 Schema 尚待 Q 审阅/M 消费确认；本机证据不替代正式验收或真实模型质量评测。此前 draft.5/旧 B target 的状态保留在历史记录中。

## 固定的提交与契约

- A Java 当前交付 target：`ec5c71c9be5a8766540fc48e174f215c0cf388ac`；其中 Q 406 修复代码 target：`24a07fd85c70cab3c522118697824727bf9651fe`。
- B Python 当前 target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`（代码/测试 target `2623a6282b2695a8ef96e3553a849729efd42403`）。B 已合入 A 的 draft.4 契约提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，消费者版本为 `0.2.0-draft.4`，Schema SHA-256 为 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 联调候选：`225124fbae8041efd67ee5e6ca5bf89fdbbe8884` 是真实联调运行提交，集成树 SHA-1 `7ea07ebe5d9763ef2e2b2d03b83815dc414dd07b`；其父提交分别为 B 代码 target `2623a62` 和 A Java target `ec5c71c`。当前 B target `b598f1d` 只在该代码树上增加交付/证据记录。

## 干净候选验证

在干净临时 worktree 执行，Python 3.12.14，依赖由 `uv sync --project services/ai --frozen` 安装。B 的版本化报告确认运行前后 worktree 均干净；临时 index 对已核对字节与 HEAD 完全相同的 `services/api/mvnw.cmd` 行尾属性误报设置 assume-unchanged，不改文件内容。

- Python：`uv run --project services/ai --frozen pytest services/ai/tests -q`，65 passed。
- Schema：`python3 contracts/validate.py`，54 个结构样例通过。
- 离线回归：`python3 -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`，16 passed。
- 双进程：`uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py --maven-settings /tmp/knowflow-maven-settings.xml --java-target ec5c71c9be5a8766540fc48e174f215c0cf388ac --require-clean --output /tmp/knowflow-jp01-clean-smoke.json`，8 tests、0 failure、0 error，运行前后 clean 均为 true。报告：[java-python-smoke-draft4.json](java-python-smoke-draft4.json)，来自 B 当前 target 的 clean-run evidence，SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`。

真实双进程场景包括：Java 健康客户端调用真实 Python health 并接受 draft.4/status/request ID；同一客户端拒绝 draft.2 fixture；实际 5 秒 deadline；凭证缺失/错误 401；404/405 与 `Allow`；进程不可达；独立慢响应夹具的 WebClient 超时。日志没有测试密钥；没有数据库或模型调用。

## Q 406 修复

Q review base `ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434` → 代码修复 target `24a07fd85c70cab3c522118697824727bf9651fe`。`HttpMediaTypeNotAcceptableException` 专用处理器保留 Spring 的 406 与支持类型 `Accept` 响应头，统一返回 `INVALID_REQUEST` JSON 错误体。回归测试使用 `Accept: application/xml`，断言 406、`Accept: application/json`、request ID 和错误体。`mvnw verify` 22 项通过；契约 54 项和离线回归 16 项通过。记录见 [A 线执行记录](agent-a.md) 与 [A 线 Q 审阅包](agent-a-review-package.md)。

JP-I1 的开发双进程门槛已通过；draft.4 仍待 Q 审阅和 M 消费确认，正式冻结/任务 DONE 条件没有代填。下一项 KF2-014 仍被 M 的 KF2-009 阻断；KF2-015 仍依赖 KF2-014。

## JP2 draft.5 Java target 与 B 消费状态（2026-10-30）

- A Java 代码 target：`489b746f9bfa8188041f12d9135cf98fe6846611`；Schema `0.2.0-draft.5` SHA-256：`3953784ab2bd2005cded12baa11caa99b6e47a79c77d5a1078b158f59f5639ef`。
- B 的真实 `origin/python` target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`，应用代码 target `2623a6282b2695a8ef96e3553a849729efd42403`。其 `services/ai/src/knowflow_ai/protocol.py` 仍将版本固定为 draft.4 和 SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`；`app.py` 只有 health 路由，README 明确索引/检索/生成未启用。B 尚未消费 draft.5，也没有索引与问答业务端点。
- draft.4 真实 health smoke 仍可复核：A `ec5c71c9be5a8766540fc48e174f215c0cf388ac`、B `b598f1d...`、运行 target `225124fbae8041efd67ee5e6ca5bf89fdbbe8884`；8/8 通过，报告 SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`。它验证的是旧 draft.4 Java 客户端和固定 B 版本，不能当作当前 draft.5 联调。
- 当前 Java `RealPythonHealthSmokeTest` 在设置 `KNOWFLOW_REAL_AI_BASE_URL` / `KNOWFLOW_REAL_AI_SECRET` 后会真实调用 draft.5；本轮未设置变量，测试作为 1 个 assumption skip 记录。不能把实际 B draft.4 直接伪装成 draft.5 服务。
- A 的真实 PostgreSQL/MinIO 集成测试已覆盖 Java 侧上传、队列/索引写入与原子发布、问答证据校验 fixture、来源/文件和删除/迟到 Worker。全链路 A/B、真实模型质量/费用、Worker 跨进程中断恢复待 B 合入 B06/B09/B10/B12 并固定消费本 Schema 后再运行。

因此 JP2 的 A01–A11 可按 Java target 复核，A12 标记为跨服务阻塞；Q 审阅及 B 对 draft.5 的消费 SHA/测试结果待填。

## 2026-10-30：`local` draft.6 完整本地联调

- 基线：从 `main` 派生的 `local`，base commit `dd3abd4aa003fe5b6b88ce649b8806d9b82b8631`；本轮交付保留为未提交工作树。Java、Python 与消费者都使用 `0.2.0-draft.6`，Schema SHA-256 `d64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1`。
- Java：`services/api` Maven/Testcontainers 全量 **49 项，0 failure、0 error、1 skip**。集成复现期间修复了 Python source GET 的 Accept 媒体类型和重复添加 `X-Request-ID` 造成的逗号合并问题；对应客户端和“恰好一个 request ID”回归已更新。
- Python：**116 passed**；Schema **70** 个结构样例；模型离线回归 **16 passed**；真实 HTTP process smoke **8 passed**；本轮重新运行 Java 调用真实 Python health 的双进程 smoke **9/9**，报告见 `services/ai/docs/evidence/java-python-smoke-local-draft6-verified.json`。
- 本机依赖：PostgreSQL/pgvector 0.8.1 与 MinIO Compose 健康；迁移 V1–V5 已应用。使用真实 Java/Python 服务及本机数据库/对象存储完成合成文件上传→Java source 网关→合成 embedding→受 fencing 验证的批次/完成→READY→AI 只读向量检索→合成回答→Java scope/quote/locator/citation 校验和来源持久化；测试知识库已通过 Java API 删除。
- 当前 Compose 数据库权限审计：Flyway V5、失败迁移 0、vector 0.8.1；AI 查询角色可 SELECT 检索所需关系但无所测 DML/schema-create，应用角色无 superuser/database/role/schema DDL 权限，脱敏报告见 `services/ai/docs/evidence/local-db-role-audit-draft6.json`。种子资料 12 道开发题及 3 道留出题的标注证据均可在 Chunk 中复核，证据见 `services/ai/docs/evidence/seed-chunk-coverage-local-draft6.json`；它不代表向量排序或模型答案质量通过。
- 问答复现发现 Windows Proactor 与 psycopg async API 不兼容。Python 改为在 `asyncio.to_thread` 中使用同步 psycopg，仍强制只读事务、5 秒连接超时和 5 秒语句超时；新增线程/只读查询回归。整个合成 E2E 成功，外部 Embedding/LLM 调用均为 **0**。
- 新增 scope guard 后再次执行合成端到端：合法的文档/内容版本/索引版本通过 Python guard 和 Java 引文校验，上传至 READY、只读检索、回答来源持久化及测试知识库清理均通过。三种越界身份各有单测，确认 LLM adapter 创建前拒绝。最新脱敏报告：`services/ai/docs/evidence/local-backend-e2e-draft6-verified.json`；不包含文档正文、回答、向量、用户 token 或凭据。
- 真实删除取消链路也已通过：Java 调度器派发任务后，在合成 embedding 阻塞期间通过文档删除写 cancellation outbox；Python HTTP cancel 中断并收尾 `_index` 子任务，关闭 adapter；取消与物理清理 outbox 排空。等待后数据库仍为 `CANCELLED`，没有 Chunk、向量或迟到 completion。脱敏报告：`services/ai/docs/evidence/cancellation-e2e-local-draft6-verified.json`。
- 该联调复现并修复 Python 子任务泄漏：取消 `_execute` 时显式取消并等待 `asyncio.wait` 旁的 processing task，避免关闭 adapter 后 `_index` 仍运行。新增活动取消测试确认 processing 先结束、adapter 后关闭，且不写 batch/completion。Python 全量回归 **120 passed**；Maven **49 项，0 failure、0 error、1 skip**。真实 provider 质量/费用评测未执行；Q 审阅与 M 消费确认仍待执行，任务不标 DONE。
- 删除后的迟到 completion 现在也有 Java 集成回归：使用与现有批次匹配的 SHA-256 manifest 提交 `SUCCEEDED` completion，API 返回 `DOCUMENT_UNAVAILABLE`，全量 Maven/Testcontainers **49 项**通过（0 failure、0 error、1 skip）。
- Python worker 新增 heartbeat fencing 回归：Java heartbeat 返回 `LEASE_REJECTED` 后，worker 取消并等待活动 `_index`，先于 adapter 关闭完成清理，且不写 batch/completion；目标用例连续 **10/10** 通过。worker 测试 **5 passed**，Python 全量 **123 passed**，Schema **70** 个结构样例通过。
- 文档检查修复了旧 draft.4 消费说明与当前 draft.6 路由不一致的问题；解析和分段文档现与 IndexWorker/Java gateway 的实际调用和写入边界一致。
- 有界队列容量耗尽时，Python 不创建新 heartbeat 或接受回执；HTTP 返回脱敏可重试 `503` 并保留 request ID。两条定向回归通过，Python 全量 **123 passed**，契约结构验证 **70** 项通过。
- 10/30 重新执行 Java Maven/Testcontainers **49 项通过（0 failure/error，1 skip）**、Python **123 项通过**、Schema **70 项**、Python process smoke **8/8**、Java↔Python health **9/9**。最新 health 证据绑定当前 app/consumer/Schema 哈希，且外部模型/数据库调用为 0。
- 补充 provider 凭证 fail-closed HTTP 回归：索引入口缺少 Embedding 凭证时返回脱敏可重试 `503`，worker `accept` 未调用；问答入口分别缺少 Embedding 或 LLM 凭证时返回同样的 `503`，`AnswerService` 未构造，未触发数据库或模型请求。定向 `test_service.py` **21 passed**；Python 全量 **126 passed**；Schema **70** 个结构样例通过。真实外部模型调用为 0；唯一 pytest 提示是 Starlette/httpx 上游弃用警告。
- Java 公开问答边界补测：本地 AI HTTP fixture 返回上游 `503` 并携带私有错误标记；`DocumentApiIntegrationTest` 确认公开 API 返回可重试 `502 AI_PROCESSING_FAILED`，不泄漏上游正文，数据库问题记录进入 `FAILED/AI_PROCESSING_FAILED`。该用例类 **20 passed**，更新后的全量 Maven/Testcontainers **50 项，0 failure、0 error、1 skip，BUILD SUCCESS**。
- 超时边界复验：AI HTTP fixture 阻塞响应，触发 Java 配置的 30 秒响应时限；公开 API 返回脱敏可重试 `504 PROCESSING_TIMEOUT`，数据库问题记录为 `FAILED/PROCESSING_TIMEOUT`。`DocumentApiIntegrationTest` **21/21** 通过；含上游 503 与 timeout 回归的全量 Maven/Testcontainers **51 项，0 failure、0 error、1 skip，BUILD SUCCESS**。ReadTimeout 日志来自故意阻塞的测试 fixture。
- 2026-10-30 22:56（香港时间）提前复验下一日检查点：真实双进程 health **9/9**，真实 Java/Python/PostgreSQL/MinIO 合成上传→READY→只读检索/问答→活动删除取消通过；确认取消被送达活动执行、embedding 取消后 adapter 关闭，相关任务和清理队列无迟到写入并排空。修复重放工具的 Windows Java 子进程泄漏和清理等待，进程/队列复查通过；证据为 `services/ai/docs/evidence/local-backend-e2e-draft6-replay.json` 与 `java-python-smoke-local-draft6-replay.json`。Java 全量 **51 项（1 skip）**、Python **132 passed**；所选模型凭证缺失，provider 评测 `SKIPPED_NO_CREDENTIALS`，本次外部调用 0。Q/M 状态不变。
