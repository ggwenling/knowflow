# KnowFlow

AI 知识库与文档助手实践项目，首轮面向需要反复查询中文项目规范和 API 文档的研发成员。产品场景、真实用户假设和试用协议见 [docs/product](docs/product/scenario.md)。

## 当前状态

仓库包含 V0.2 计划、KF2-002 用户场景和 KF2-003 双模型验证记录。KF2-002、003、005 已在 python 分支交付并等待独立 Q 审阅；仓库当前尚未包含可运行的 Java 服务、Python AI 服务或 Web 应用。V1.1 设计包缺失，冻结的跨服务契约亦未建立。

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

从当前集成基线为任务创建独立分支/worktree；每个主线一次只写其所有权范围。见 [协作规则与任务卡](docs/tasks/README.md) 及 [PR 和审阅模板](docs/reviews/pull-request-review-template.md)。本地 Python 模型客户端回归和许可审计命令见 [KF2-003 冒烟说明](evaluation/smoke/README.md)。

每个服务的启动说明会列出依赖及配置，但在 KF2-004/006/007/008/009 完成前不能启动完整产品。服务需要的密钥须由本机/托管环境注入，不能提交到仓库。
