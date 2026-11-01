# JP-01 Java → Python 开发联调记录

状态：JP-I1 draft.4/draft.6 和 2026-10-31 draft.8 本机 E2E 均为历史证据。当前 `local` 候选升级为 draft.9；Python 全量与 Schema 验证通过，Java 内容更新/重建已编译且 SSE 内部组件单测通过。Java Testcontainers 场景因 Docker Engine 缺失未执行；公开 Java SSE API/问答持久化未完成。候选 Schema 仍待 Q 审阅/M 消费确认，真实模型质量仍未验证。

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

## 2026-10-31：draft.8 两分支消费与集成验收

- A Java target：`a70ce15f5d50e3a9923b37540b06504e14097dba`（A3 fix `32cc15050262a86f41db4676b60f922b466aa840`，draft.8 契约 `a68239b82e5885ad8aec559fb574dce6b70f95d8`）；B draft.8 consumer target：`1d0c26ab4f7c273a9913e47b9011a76b325dee0f`，E2E runner follow-up：`e57e6335e9448dc4ef89186f9b48df8ae7dd89c5`。health smoke 的集成 code HEAD：`54c5713cb7f04fa9ab323be227e9a7dcacae16e3`，tree `985056592b5899f6f1765af82356cf687195cfb9`。
- 契约 `0.2.0-draft.8` Schema SHA-256：`f4db55243d97b1bbd4938a8479bed7ce3a8f1955874ec3885f86906219032c5a`。Java 和 Python consumer 均已升版，Python 严格校验精确哈希并拒绝 draft.7；Java health client 通过真实 draft.8、拒绝 draft.7 fixture。
- Java：`./services/api/mvnw.cmd -B -f services/api/pom.xml test`，61 tests，0 failures/errors，1 opt-in smoke skipped；覆盖 PostgreSQL 16.12、pgvector 0.8.1、MinIO Testcontainers。Python：`uv run --project services/ai --frozen pytest services/ai/tests -q`，181 passed（1 条 Starlette/httpx 上游弃用警告）；`python contracts/validate.py`，70 structural cases；离线回归 16 passed。
- Python parser smoke 15/15、真实 HTTP process smoke 8/8；真实 Java Spring/WebClient ↔ Python Uvicorn health smoke 9/9。报告 `services/ai/docs/evidence/java-python-smoke-draft8-verified.json`、`parser-smoke.json`、`process-smoke.json` 仅记录脱敏断言与文件哈希；health smoke 不触发数据库或外部模型。
- `uv run --project services/ai --frozen python services/ai/tools/local_backend_e2e.py --env-file <本机开发配置> --output services/ai/docs/evidence/local-backend-e2e-draft8-replay.json` 于 10/31 在本地集成分支运行通过。真实 Java/Python/pgvector PostgreSQL/MinIO 完成合成资料上传、索引 READY、AI 只读检索、问答引用验证与持久化、活动 embedding 取消、adapter 收尾及物理清理；取消后任务 `CANCELLED`，无迟到 Chunk/embedding，取消/存储/index outbox 均为 0；知识库已删除、会话退出。测试账户保留在开发库。外部模型调用为 0，不能据此声称真实排名/回答质量通过。
- Compose 读取工作区外的既有本机开发配置，未复制或记录配置值；运行后停止本次启动的 KnowFlow 容器并保留 PostgreSQL/MinIO 数据卷，8000/8080 均无残留 listener。Embedding/LLM 凭证缺失，未调用 provider。结构 Schema 校验本身不执行权限、租约时效或数据库状态迁移语义检查。
- 业务 E2E 运行于集成 HEAD `860798a6a01aede62f73a79db3dbac86e8009821`、tree `367a1df8f64ed00e241dcc322ff6163104c0eac9`；报告 SHA-256 `9ebebb896e4451b2b3f57a3f07edede8388e7dc9311ceca8753ef8d6b2a4459e`，并绑定 draft.8 Schema 与 replay/worker/cancel/Java deletion outbox 源码哈希。
- 独立 Q 审阅/M 消费确认待完成；KF2-038 仍依赖 KF2-031 SSE 与 KF2-037 质量基线。draft.8 的内容更新/重建是候选协议说明，本次没有实现或验收对应业务端点。

## 2026-10-31：最新审查两项 P2 修复

- Python 作者分支 `python` 提交 `c2ceede` 修复数据库取消/截止时间无界等待，以及小分段配置阻塞事件循环；本地集成分支 `codex/integration-20261031` 合入提交为 `b4f538065451275452daa9b9cede64c245418c46`。Java 源码未改动。
- 数据库回归使用真实 psycopg 连接本地 PostgreSQL 协议黑洞，覆盖 1.2 秒 deadline、数据库不响应/无 cancel channel、单次与重复任务取消、连接阶段取消；所有数据库工作线程均在清理后退出，连接由查询线程关闭。
- 分段回归保留 boundary 语义与 golden Chunk/profile ID；16,000 字符、`chunk_max_codepoints=1` 的 worker 在 64 Chunk 间隔让出事件循环，真实测试心跳可续租、取消可及时停止后续工作。边界定位改为优先级索引上的二分查询；固定 golden 和 100 组随机逐 Chunk 对照均一致。
- 合并后复验：Python 全量 **187 passed**；Schema **70** cases；离线回归 **16 passed**；parser smoke **15/15**；Python HTTP process smoke **8/8**。Java Spring/WebClient ↔ Python Uvicorn health **9/9**，报告 `services/ai/docs/evidence/java-python-smoke-draft8-p2.json`，SHA-256 `e73e70d4fdfdded01de281a9d8b35313ac6593e1f94ce7d1a4219fbc174495ae`；报告绑定集成 HEAD `b4f538065451275452daa9b9cede64c245418c46`，clean before/after，数据库和模型调用 0。
- 本机 Java/Python/PostgreSQL/pgvector/MinIO 合成 E2E 通过，覆盖上传、索引 READY、只读检索/引用问答、活动取消、无迟到 Chunk/Embedding 写入、物理清理及 outbox 排空。报告 `services/ai/docs/evidence/local-backend-e2e-draft8-p2.json`，SHA-256 `891b58d4da5d33ebd61af421f4ba30135be08c01f561984c85f7f1a4a07ad025`；外部模型调用 0。合成账户仍留在本机开发库，KnowFlow Compose 容器已停止且数据卷保留，8000/8080 无残留 listener。
- 本次不重跑 Java 全量 Maven/Testcontainers（Java 文件未改）；此前 draft.8 Java 全量 61 tests、0 failures/errors、1 个 opt-in skip 的结果仍对应原 Java target。独立 Q 审阅、M 消费确认、真实 provider 质量/费用评测状态不变；未推送或合并 `main`。

## 2026-10-31：P2 已写入批次仍保留完整向量

- Python 作者分支 `python` 提交 `c6bfb1a282181e5ac43aca4ea73d9d601d78866c`；合入本地集成分支 `codex/integration-20261031` 的 merge 提交为 `03a8051f7319d4420e66709f8846321d6b1c7644`。Java 源码未改。
- `IndexWorker` 在 Java gateway 确认写入后，`batches` 仅保留 `batch_sequence`、`batch_id`、`batch_sha256`、`chunk_count`；末批写入完成后清空 `pending`。manifest digest 仍按相同字段和值生成，契约和 Java 接口未变。
- 新增 512 个单字符 Chunk 的 `tracemalloc` 回归，每条 Chunk 携带独立 1024 维向量。修复前回归复现 **17,525,103 bytes** 峰值并失败；修复后峰值断言低于 **16 MiB**，同时验证 8 个批次摘要仅含 manifest 所需四项。
- 合并后 Python 全量 **188 passed**，Schema 校验 **70 structural cases**，离线 provider 回归 **16 passed**；worker 定向 **12 passed**。真实 Java/Python/PostgreSQL/pgvector/MinIO 合成业务 E2E 通过，确认 Java 接受轻量摘要生成的 manifest；证据 `services/ai/docs/evidence/local-backend-e2e-draft8-memory-p2.json`，SHA-256 `ba8183cd8093eb248e666ee4da5825240f0da6f7919e518ee5a35fd2f807ca42`。取消后 Chunk/Embedding 均为 0，清理 outbox 排空。
- E2E 仅使用本地确定性合成 adapter，外部模型调用 **0**；测试知识库已删除、会话已注销，合成账户保留在本地开发数据库。KnowFlow Compose 已停止且数据卷保留。未改 Java 源码，因此没有重跑 Java Maven；此前 61 tests 的结论仍只对应原 Java target。Q/M 与真实 provider 质量/费用测量状态不变；未推送或合并 `main`。

## 2026-10-31：local draft.9 并行开发

- 开发基线：`local` 从 `codex/integration-20261031@493112dfa0b7f939041ef456ff39e7ff734445d3` 快进。共享 Schema draft.9 SHA-256 `fea46866e42e871993ebe37c845643f286105fd60627de4661574852307b2935`；AnswerStreamEvent 序号从 1 开始，事件为 started/delta/sources/completed 或唯一 error/cancelled。
- Java 交付内容更新/同内容重建、pending 原子发布、两次成功发布保留/旧载荷清理和 retired snapshot 访问。test-compile 通过，SSE 协议与引用映射 7/7 通过。Testcontainers 场景无法启动：本机 Docker Desktop Linux engine pipe 不存在。
- Python 交付真实 provider SSE 消费、answer JSON 增量解析、取消/超时/断连收尾、retired snapshot 只读访问及评测空白标注模板。Python 全量 219 passed；Schema 79 structural cases；离线回归 16 passed。真实 provider 调用 0。
- KF2-031 的实现与事务持久化已接通；其 Testcontainers 端到端场景尚未运行，见下一节的 Docker 环境阻断记录。
- KF2-037 仅完成工具/标注准备；仍无 60 道独立人工核验题、真实模型质量结果或费用数据。Q/M 审阅未执行，本轮不推送或合并 main。

## 2026-10-31：Java 公开 SSE 网关完成

- `POST /api/v1/knowledge-bases/{knowledge_base_id}/questions/stream` 已接通 Java `SseEmitter`、Python draft.9 SSE client 和现有问答持久化事务。Java 发送前逐事件检查快照可见性；sources 事件完成引用/Chunk/locator 校验和问题/来源原子保存后才发送，completed 不重复答案正文。
- 浏览器断连或超时会取消上游订阅并将 PROCESSING 问题标记为 `CANCELLED`；上游异常、非法事件、删除/版本清理和超时会发送唯一脱敏 error。跨 delta 引用标记由 bounded mapper 映射为公开 source UUID，内部 source ID 不出现在 SSE。
- 新增 `DocumentApiIntegrationTest.publicAnswerStreamForwardsValidatedEventsAndPersistsTheAnswer`，覆盖事件顺序、内部引用 ID 脱敏和 `SUCCEEDED` 持久化。该 Testcontainers 测试已编译，但当前 Docker Engine 缺失，执行在容器启动阶段阻断。
- 无容器 Java 编译与 SSE/citation 单测仍通过：test-compile SUCCESS，7/7 passed。公开 SSE 代码提交为 `e949c19`；整体 `local` 后续需在 Docker 可用时补跑集成测试。

## 2026-11-01：draft.10 双端复验

- Java 与 Python 在 `local` 分支同步消费 draft.10，Schema SHA-256 `d34b174e080226a6ac85387cccb1c084ccd19098b4db482caca1ecd63deec38c`。Java V7/问答历史/幂等/deadline 恢复与 Python profile/tombstone 消费均已通过各自全量套件。
- 首次尝试使用现存本机 `knowflow` 库时，上传因旧表缺少当前迁移列返回 500；确认该库没有当前 Flyway history 后未对其执行迁移。随后在临时隔离库从空库应用 V1–V7 并重放成功，完成后删除临时库。原库未迁移 schema；失败流程已删除合成知识库并注销会话，合成用户记录可能保留。本机 Compose 容器已停止、数据卷保留。
- 真实 Java/Python/PostgreSQL/pgvector/MinIO 合成 E2E 全通过：上传、索引 READY、只读检索、带来源合成回答、活动取消、无迟到 Chunk/Embedding、知识库清理及 outbox 排空。外部模型调用 0；报告 `services/ai/docs/evidence/local-backend-e2e-draft10-replay.json`。
- 测试期间新建的合成账户在原本地 `knowflow` 库中可能保留（知识库已由失败流程清理、会话已注销）；实现与审查修复已提交至 `local`，未推送。Q/M/真实 provider 质量与费用仍待完成。

## 2026-11-01 Review follow-up

- Category evaluation now checks `answerable_count` and `unanswerable_count` before division and reports `null` for the unavailable rate. Regression coverage uses `factual` with answerable-only rows and `no_answer` with unanswerable-only rows.
- Streamed `started` model profile is carried into `pendingAnswer`; the end-to-end test confirms profile IDs persist after the terminal `completed` event rather than being overwritten with null.
- Targeted checks: Python evaluation **10 passed**, Java `DocumentApiIntegrationTest` **38 passed**. Full checks: Python **235 passed** (1 existing deprecation warning), Java **76 tests, 0 failures/errors, 1 opt-in skip**.

## 2026-11-01：后续 P2 修复

- Java 的 SSE `StreamState.isTimeout()` 现在识别 `ApiFailure` 的 `PROCESSING_TIMEOUT` 代码。迟到 completion 回归断言只发送一条准确的终态错误，并确认失败记录没有答案或来源写入。
- 新增 V8 替代来源保留形状约束并要求表达式 `IS TRUE`。PostgreSQL 集成测试验证 V7→V8：畸形历史行使升级失败且事务回滚；删除该行后升级成功。PDF、text range 与全空 tombstone 接受；quote 存在但 kind/page/range endpoint 缺失时拒绝。
- Java 定向集成 **39 tests**、全量 **76 tests（0 failures/errors，1 opt-in skip）**通过。未在原本机 `knowflow` 库执行迁移。
- 相关代码、测试、V8 migration 与候选分配更新当前未提交在 `local`；未推送或合并 `main`。

## 2026-11-01：同步问答超时状态与候选题内容

- 最终答案保存遇到 deadline guard 时，`ask()` 的 `ApiFailure` catch 现在保留 `PROCESSING_TIMEOUT`。PostgreSQL 集成回归将仍在处理的问题 deadline 置为过去时间后放行同步 AI 响应，验证公开 504 与历史失败码一致，且没有答案/来源写入。
- `candidate-01` 题干改为“创建索引任务请求需要提供哪些必填字段？”，不再把 `documentId`、`profileId` 及其类型作为题干内容；重生成候选文件。
- Java 全量 **77 tests，0 failures/errors，1 opt-in skip**；Python 全量 **235 passed**，评测定向 **10 passed**。改动尚未提交或推送。

## 2026-11-01：候选数据换行与摘要校准

- `.gitattributes` 对 `seed-v2-candidate/documents/**` 设置 `-text`，避免 Windows checkout 转换受哈希校验的文档字节；candidate `manifest.json` 固定为 `eol=lf`。
- manifest 生成时使用固定 LF；`annotation_template()` 对 manifest 字节的 CRLF 统一成 LF 后计算 SHA-256。标注模板摘要已重生成。
- 测试同时覆盖临时 CRLF manifest 摘要稳定性，并逐一对比十份候选文档字节和清单哈希。评测定向 **10 passed**，Python 全量 **235 passed**（1 条既有弃用警告）。

## 2026-11-01：JP-02 执行结果

- Java 在 `QuestionController` 接入 SSE 生命周期观测：request ID、首个成功发送的非空 delta 耗时、总耗时、终态与安全错误码；不记录正文/异常消息。原子终态防止重复 lifecycle 日志。
- Python 增加候选机器标注草稿、需人工审核的安全导入器及 runner pending 拒绝门禁。60 条草稿保留 `reviewed=0`，不会进入质量评分。
- `services/ai/tools/recovery_e2e.py` 使用独立临时数据库、真实本地 Java/Python/PostgreSQL/pgvector/MinIO 与合成模型 adapters 验证四个场景：worker 重启后 fencing 与旧写拒绝、三次 worker 丢失终态且保留旧活动索引、Java 重启后问答 deadline 恢复、worker 离线时删除后不复活。报告 `services/ai/docs/evidence/recovery-e2e-draft10.json`，4/4 通过；临时库已删除，端口已释放，日志无 secret，外部模型调用 0。
- 当轮复验：Java **80 项，0 failure/error，1 opt-in skip**；Python **243 passed**（1 条既有弃用警告）；Schema **85 structural cases**；离线模型回归 **16 passed**。Schema 工具明确不执行授权、租约或数据库状态转换验证，这部分由真实恢复 E2E 与集成测试覆盖。
- `local` HEAD 为 `f5bf00f40cbd962c0423a7144ad6dd3a2eb02828`；本轮实现仍未提交、未推送、未合并。Q/M 审阅及真实 provider 质量/费用仍待完成。

## 2026-11-01：review follow-up

- Compose 恢复清理现在以服务为单位跟踪本次启动集合；对“PostgreSQL 已运行、MinIO 停止”情形只启动并停止 MinIO。Python 定向回归 **28 passed**。
- Java 将 Python 发出的 `PROCESSING_TIMEOUT` error event 记为 `timeout` 终态；生命周期定向测试 **4 passed**。本轮未重跑完整 Java/Python 套件或四场景 E2E。
- 当前 HEAD `013fcf5a2de72b09599037fb997765443f5d61ee`，两项修复留在 `local` 未提交工作树。

## 2026-11-01：修复后全量复验与恢复演练重跑

- Java 全量 Maven/Testcontainers **81 项，0 failure/error，1 opt-in skip**，含 timeout 分类回归；运行日志实测 `answer_stream_lifecycle ... terminal_status=timeout error_code=PROCESSING_TIMEOUT`。
- Python 全量 **252 passed**（1 条既有 Starlette/httpx 弃用警告），含新增 `test_http_client.py` 6 项与 `test_recovery_e2e.py` 3 项；Schema **85 structural cases**；离线模型回归 **16 passed**。
- 用修复后的 Compose 归属 harness 重跑 4 场景真实恢复 E2E，全通过：单 worker 重启后 fencing 1→2 且旧 batch/completion 均 `LEASE_REJECTED`；三次 worker 丢失终态 `WORKER_LOST` 且旧活动索引仍可查询；Java 重启后问题恢复为 `FAILED/PROCESSING_TIMEOUT` 且无答案/来源；worker 离线时删除后文档、来源文件、检索与内部来源读取全部拒绝，清理队列排空。报告 `services/ai/docs/evidence/recovery-e2e-draft10-compose-scope.json`。
- 收尾核对：隔离库 `knowflow_recovery_772a89955a5e` 已删除；运行前 PostgreSQL/MinIO 均未运行，运行后两者均停止（只停本轮启动集合）；端口 8000/8080 释放；进程日志无 secret；外部模型调用 0。修复前的 `recovery-e2e-draft10.json` 保留为历史证据。
- 新增 `knowflow_ai/http_client.py` 解决宿主机畸形代理环境令适配器构造抛异常、绕过 fail-closed 的问题；provider 适配器保留环境代理，内部 Java 网关不使用代理。两端源码未改共享契约，契约版本仍为 `0.2.0-draft.10`、SHA-256 `d34b174e080226a6ac85387cccb1c084ccd19098b4db482caca1ecd63deec38c`。
- 仍未完成：60 道候选题人工复核与 blind holdout、真实 provider 质量/费用测量、独立 Q 审阅与 M 消费确认。全部改动仍在 `local` 未提交工作树。
