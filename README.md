# KnowFlow

AI 知识库与文档助手实践项目，首轮面向需要反复查询中文项目规范和 API 文档的研发成员。产品场景、真实用户假设和试用协议见 [docs/product](docs/product/scenario.md)。

## 当前状态

Java API 已实现认证、知识库/文档状态、租约与 fencing、受控索引批次写入、原子发布、问答快照和来源权限边界。Python AI 服务已有解析/分段、Embedding 适配器、lease-fenced Worker、只读范围检索和证据校验问答。两端及共享 Schema 当前在本地 `local` 集成分支推进，基于 `main`；契约为 `0.2.0-draft.6`，未冻结、未发布。真实双服务索引/问答闭环与 Q/M 正式验收仍待完成，不能把候选代码等同生产就绪。

当前本机会话未提供模型密钥，因此没有新的真实 Embedding/LLM 请求。已有模型服务商验证记录是合成夹具上的独立证据；不得上传未确认授权的项目资料。详情见 [模型、隐私和费用记录](evaluation/smoke/provider-profile.md)。

## 仓库布局

- `apps/web`：M 负责的 Next.js 前端。
- `services/api`：Codex-A / Java Spring API、业务状态与唯一索引写入/发布方。
- `services/ai`：Codex-B / Python FastAPI 解析、索引执行、受限检索与生成方。
- `contracts`：共享契约由 A 发布，B 提交消费与字段提议。
- `infra`：M 负责的 Compose、CI 和本地开发支撑。
- `docs/planning`：计划基线；`docs/tasks`、`docs/reviews`：任务和审阅记录。
- `evaluation`：模型、解析、许可与评测证据。

## 本地推进计划

当前使用 `local` 分支进行集成开发，`local` 由 `main` 建立；Java 文件仍归 Codex-A，Python/evaluation 文件仍归 Codex-B，共享契约由 A 单写。完整的今天与明天安排见 [JP-01 Java/Python 计划](docs/planning/v0.2/java-python-parallel-plan.md)：今天完成 draft.6 同步、两端回归和本地数据库环境准备；明天完成真实双进程联调、索引/问答边界与交付记录。所有候选验证与独立复核、正式冻结分开记录。

Python 环境需 Python 3.12，命令见 [Python 服务开发说明](services/ai/README.md)。Java 开发需要 Java 21 与 Docker daemon；PostgreSQL/pgvector、MinIO 本地 Compose 命令见 [Java 服务开发说明](services/api/README.md)。服务密钥仅通过本机环境注入，不提交仓库。
