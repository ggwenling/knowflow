# 任务执行记录和协作规则

任务状态遵循：PLANNED → READY → IN_PROGRESS → IN_REVIEW → CHANGES_REQUESTED / APPROVED → INTEGRATING → DONE。缺配置用 WAITING_INPUT，外部/技术阻断用 BLOCKED，并注明解除条件。没有独立 Q 审阅和集成验证，不标 DONE。原始 KF2 计划是只读基线；实际状态另记在 [execution-log.md](execution-log.md)。

## 文件所有权

- A：services/api、contracts、Flyway、公共架构 ADR；Java 负责业务状态和唯一正式契约。
- B：services/ai、evaluation 及 AI 研究/评测记录；受契约和授权数据范围约束。
- M：apps/web、infra、.github、tests/e2e 及产品/交付体验记录。
- Q：docs/reviews；审阅具体 SHA，不接管作者实现。

所有权交接必须写入任务执行记录。共享目录不是独立分支隔离；共用工作区时按文件单写，切分支、提交和更新远端前检查 git status；不要重置或覆盖他人未提交内容。独立 worktree 优先。

## 分支与提交

每项任务记录 base SHA、分支、变更路径、验证命令/结果、target SHA 和未完成项。沿用仓库已有命名时记录缘由；本批约定使用 python 分支。小提交只包含一个任务，PR 描述可复制自 [PR/审阅模板](../reviews/pull-request-review-template.md)。作者不得填写 Q 的审阅结论。

## 任务卡（复制后填写）

- 任务 ID / 标题：
- 负责人 / 实际执行者 / 所有权交接：
- 目标 / 本次排除：
- 硬依赖和对应通过版本：
- 基线 SHA / 分支 / worktree：
- 修改范围 / 禁止修改：
- 契约版本或缺失项：
- 完成条件：
- 验证命令 / 环境 / 结果 / 未执行原因：
- 变更文件 / target SHA：
- 阻断 / 风险 / 下一步：
- Q 审阅及修复复核：
- 实际集成验证 / 最终状态：
