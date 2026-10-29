# KnowFlow

AI 私有知识库与智能文档助手。项目当前处于计划与设计准备阶段，目标是提供文档管理、权限受控检索、问答和可核验的来源引用。

执行编制为两个 Codex Coding Agent、一个 Muse 主线 Agent、一个 Code Review Agent：

- Codex-A：Java API、权限、索引任务与版本管理、公共契约。
- Codex-B：Python 解析、索引、检索、生成与 RAG 评测。
- Muse：前端主线、基础设施、真实联调和端到端验证。
- Code Review：持续审阅三条主线，并复核最终交付。

## V0.2 执行计划

修订日期：2026-10-29。任务拆分为 44 项核心任务、12 项可选增强，共 56 项；各任务包含负责人、依赖、修改范围、验收标准和验证要求。

- [计划包说明](./docs/planning/v0.2/README.md)
- [项目计划书](./docs/planning/v0.2/KnowFlow_V0.2_项目计划书.md)
- [详细任务拆解](./docs/planning/v0.2/KnowFlow_V0.2_任务拆解.md)
- [Agent 协作与派工手册](./docs/planning/v0.2/KnowFlow_V0.2_Agent协作手册.md)
- [任务表 CSV](./docs/planning/v0.2/KnowFlow_V0.2_任务表.csv)
- [任务数据 JSON](./docs/planning/v0.2/KnowFlow_V0.2_任务数据.json)
- [文档审阅记录](./docs/planning/v0.2/文档审阅记录.md)

本次提交交付计划文档，尚未实现项目功能。原计划提及的 V1.1 技术设计包仍需核对，模型配置、目标硬件、开发投入和真实试用也需在执行阶段验证。
