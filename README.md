# KnowFlow

AI 知识库与文档助手实践项目，首轮面向需要反复查询中文项目规范和 API 文档的研发成员。产品场景、真实用户假设和试用协议见 [docs/product](docs/product/scenario.md)。

## 当前状态

Java API 已实现认证、知识库/文档状态、租约与 fencing、受控索引批次写入、原子发布、问答快照和来源权限边界。Python AI 服务已有解析/分段、Embedding 适配器、lease-fenced Worker、只读范围检索和证据校验问答。本地 `local` 继续作为 Java、Python 与 Web 的集成开发分支；共享契约为 `0.2.0-draft.10` 候选，尚未冻结或发布。Web 现有同源 HttpOnly 会话代理、中文文档核验工作台和隔离合成模型全栈环境；独立 Q 审阅、真实模型质量/费用及正式 M1 验收仍待完成。

当前本机会话未提供模型密钥，因此没有新的真实 Embedding/LLM 请求。已有模型服务商验证记录是合成夹具上的独立证据；不得上传未确认授权的项目资料。详情见 [模型、隐私和费用记录](evaluation/smoke/provider-profile.md)。

## 仓库布局

- `apps/web`：M 主线 Next.js 前端、同源会话代理与浏览器 E2E。
- `services/api`：Codex-A / Java Spring API、业务状态与唯一索引写入/发布方。
- `services/ai`：Codex-B / Python FastAPI 解析、索引执行、受限检索与生成方。
- `contracts`：共享契约由 A 发布，B 提交消费与字段提议。
- `infra`：M 负责的 Compose、CI 和本地开发支撑。
- `docs/planning`：计划基线；`docs/tasks`、`docs/reviews`：任务和审阅记录。
- `evaluation`：模型、解析、许可与评测证据。

## 本地推进计划

继续在 `local` 进行集成开发；Java 文件仍归 Codex-A，Python/evaluation 文件仍归 Codex-B，共享契约由 A 单写，Web/infra/E2E 由当前 Codex 承接 M 范围。全栈 Compose 仅用本地合成模型进行工程验收；真实模型调用需要另外配置获准资料与凭证，并记录质量、隐私和费用证据。

Python 环境需 Python 3.12，命令见 [Python 服务开发说明](services/ai/README.md)。Java 开发需要 Java 21 与 Docker daemon；PostgreSQL/pgvector、MinIO 本地 Compose 命令见 [Java 服务开发说明](services/api/README.md)。服务密钥仅通过本机环境注入，不提交仓库。
