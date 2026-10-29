# KnowFlow 仓库工作约定

本文件随 KF2-005 建立，记录三条主线与审阅角色的协作规则。计划包原文在 `docs/planning/v0.2`，不得覆盖或改写；`README.md` 为计划索引，保持原样。

- 集成基线（KF2-005 建立时）：`7d5095b8bc987c1c7e6f4106887d3355fa88d4c2`（2026-10-29 计划提交）。
- 记录时间统一带时区；当前使用 Asia/Shanghai（UTC+8）。
- 现有结构优先：本仓库在 KF2-005 之前仅有 `README.md` 与 `docs/planning/`；新增结构不得改动这两处。

## 文件所有权

| 角色 | 默认写入范围 | 不自行修改 |
|---|---|---|
| A / Codex-A | `services/api/`、`contracts/`、Flyway、`docs/architecture/ADR-*` | `services/ai/`、`apps/web/`、`infra/`、`.github/`、`tests/e2e/` |
| B / Codex-B | `services/ai/`、`evaluation/`、对应研究记录 | `services/api/`、Flyway、`contracts/`、`apps/web/`、`infra/` |
| M / Muse | `apps/web/`、`infra/`、`.github/`、`tests/e2e/`、`docs/product/`、`docs/tasks/`、交付记录 | 后端授权、任务状态机、数据库迁移、AI 算法 |
| Q / Code Review | `docs/reviews/` | 主线实现、无关重构、作者尚在编写的文件 |

共享文件规则：

- 公共契约由 A 提交；B/M 只提交字段需求、示例或变更提议，不得各自提交不兼容版本。
- Flyway 仅 A 分配版本并提交；B 提供所需向量/全文结构和数据库角色需求，由 A 落地迁移，Q 检查。
- Compose、CI、根锁文件由 M 维护；A/B 只提交服务要求，由 M 集成。每个服务自己的依赖锁文件仍归该服务所有者。
- 所有权可通过显式交接调整，记录任务、文件、交接时段与当前提交；不能同时拥有写入权。

## 分支与工作区

- 分支命名：`agent/<角色小写>/KF2-XXX-<简述>`，例如 `agent/m/KF2-002-scenario`；从同一已知集成基线创建。
- 每个 Agent 记录自己的基线 SHA、当前分支和 worktree 路径（见各自任务卡）。
- 共用同一目录时：同一时段仅在各自文件范围修改，序列化切分支/合并；不覆盖其他 Agent 未提交的修改，不用强制重置清理共享工作区。

## 任务流转与审阅

- 流程：核对依赖与契约 → READY → IN_PROGRESS → 小步提交可审阅差异 → IN_REVIEW（Q 按基线/目标 SHA 审阅）→ 处理阻断项并提交修复 SHA → Q 复核 → APPROVED 后由 A 协调合并 → 集成检查通过 → DONE。
- 未获 Q 结论与集成验证前，不把任务记为 DONE。
- 每个主线 Agent 最多一个正在开发、一个待审任务。
- 审阅记录在 `docs/reviews/`，结论绑定具体 SHA；修复、冲突处理或集成后新增差异必须复核。
- 任务卡模板见 `docs/tasks/README.md`；审阅记录模板见 `docs/reviews/README.md`。

## 本地启动约定

- 服务启动以 Compose 为准（KF2-009 打通后落地）；各服务 README 在其骨架任务中补齐本服务启动命令。
- 现阶段尚无可启动服务；文档类变更无需构建即可审阅。
- 密钥、模型缓存、原始私有文档不得提交仓库（见 `.gitignore`）。
- 不进行外部发布，除非任务明确要求。
