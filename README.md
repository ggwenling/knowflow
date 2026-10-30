# KnowFlow

AI 知识库与文档助手实践项目，首轮面向需要反复查询中文项目规范和 API 文档的研发成员。产品场景、真实用户假设和试用协议见 [docs/product](docs/product/scenario.md)。

## 当前状态

仓库包含 V0.2 计划、KF2-002 用户场景和 KF2-003 双模型验证记录。KF2-002、003、005 已交付并等待独立 Q 复核；A 已提交 V0.2 新基线决策、共享契约候选和可运行的 Java 服务骨架及修复，仍待审阅。Python AI 服务及 Web 应用尚未实现。旧 V1.1 兼容性未验证；当前按已批准的 V0.2 新基线继续研发，跨服务契约尚未正式冻结。

硅基流动 BAAI/bge-m3（1024 维）和 DeepSeek deepseek-flash 的合成输入真实冒烟通过。实际项目文档不得在确认供应商条款和授权前上传外部模型。详情见 [模型、隐私和费用记录](evaluation/smoke/provider-profile.md)。

## 仓库布局

- apps/web：M 负责的 Next.js 前端。
- services/api：A 负责的 Java / Spring API 与业务状态。
- services/ai：B 负责的 Python / FastAPI 解析和 RAG 服务。
- contracts：共享接口由 A 唯一发布，其他主线先提交变更提议。
- infra：M 负责的 Compose、CI 和本地开发支撑。
- docs/planning：计划基线；docs/product：用户场景与试用协议。
- docs/tasks、docs/reviews：任务记录、PR 信息与独立审阅。
- evaluation：B 负责的模型、解析、许可与评测证据。

## 协作和验证

下一轮 Java / Python 使用同一份 [JP-01 并行开发计划](docs/planning/v0.2/java-python-parallel-plan.md)：Java 主做 KF2-011，Python 主做 KF2-007，并对齐契约、完成双服务 HTTP 联调。按用户指示先推进开发，保留待复核状态；两条主线分别使用 java / python 分支及独立工作区。

从当前集成基线为任务创建独立分支/worktree；每个主线一次只写其所有权范围。见 [协作规则与任务卡](docs/tasks/README.md) 及 [PR 和审阅模板](docs/reviews/pull-request-review-template.md)。本地 Python 模型客户端回归和许可审计命令见 [KF2-003 冒烟说明](evaluation/smoke/README.md)。

Java 骨架的独立启动方式见 services/api/README.md；完整产品仍需 Python、Web、基础设施及业务链路交付。服务需要的密钥须由本机/托管环境注入，不能提交到仓库。
