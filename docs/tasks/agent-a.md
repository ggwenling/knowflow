# Codex-A 执行记录

## 执行基线与前置准备

- 日期：2026-10-29（Asia/Hong_Kong）；实际执行者：当前 Codex，角色 A。
- 仓库：`https://github.com/ggwenling/knowflow.git`；工作目录：`/workspace/knowflow`。
- 已从 `origin/main` 的 `7d5095b` 创建并切换到 `python`。分支名按用户要求，不将任务身份改为 B。
- 已读取 V0.2 计划包和任务数据，确认 A 有 16 项核心任务、3 项可选任务。
- 基线无未提交修改，无 `AGENTS.md`、业务代码或 V1.1 设计包。
- 环境：Java 21.0.12.1、Python 3.12.14；Maven 未安装。Java 骨架准备时需先落实构建工具及服务依赖版本，不宣称当前能够编译 Spring 服务。
- 云环境可连接，Git 拉取已实际成功；未配置模型凭证或目标硬件基线。未发起真实模型调用。
- 仅修改 A 的架构、任务记录和公共契约；未接替 B/M/Q，也未改计划包的初始状态。

## 按顺序领取

本文件记录实际执行状态；计划包中的 `PLANNED` 保留为规划快照。无 Q 审阅/实际集成证据的任务不标记 `DONE`。阻断任务不占用正在开发名额；一次仅推进一项允许的准备工作。

| 顺序 | 任务 | 依赖 | 实际状态 | 当前产物或解除条件 |
|---|---|---|---|---|
| 1 | KF2-001 原设计核对 | 无 | WAITING_INPUT | [兼容性记录](../architecture/compatibility.md)与映射表结构已建立；缺 V1.1 原文件与旧任务 |
| 2 | KF2-004 共享契约 | 001、002、003 | BLOCKED | [契约草案](../../contracts/README.md)、ADR、16 个 Schema 定义及 31 个结构样例已准备；尚未冻结 |
| 3 | KF2-006 Java 骨架 | 004、005 | BLOCKED | M 的 005 未有交付证据；完成后可做隔离骨架，004 冻结后验收接口 |
| 4 | KF2-011 迁移与受限角色 | 004、005 | BLOCKED | 等待冻结契约、模型维度与仓库约定，不先创建正式迁移 |
| 5 | KF2-012 认证 | 006、011 | PLANNED | 依赖通过后领取 |
| 6 | KF2-013 知识库隔离 | 012 | PLANNED | 依赖通过后领取 |
| 7 | KF2-014 上传与状态 | 009、013 | PLANNED | 需 M 的基础设施真实交付 |
| 8 | KF2-015 任务租约 | 007、014 | PLANNED | 需 B 的内部服务与上传接口 |
| 9 | KF2-019 索引发布 | 015、018 | PLANNED | 需 B 的真实索引写入证据 |
| 10 | KF2-023 问答入口 | 013、022 | PLANNED | 需 B 的真实生成与证据 |
| 11 | KF2-024 引用与删除 | 019、023 | PLANNED | 依赖通过后领取 |
| 12 | KF2-028 更新与切换 | 026 | PLANNED | 需真实 M1 闭环验收 |
| 13 | KF2-029 历史来源 | 024、028 | PLANNED | 依赖通过后领取 |
| 14 | KF2-031 SSE 网关 | 023、030 | PLANNED | 需 B 的真实流式生成 |
| 15 | KF2-033 问答历史 | 023、029、031 | PLANNED | 依赖通过后领取 |
| 16 | KF2-036 故障恢复 | 028、029 | PLANNED | 对实际服务和数据库执行故障验证 |
| 17 | KF2-049 团队成员 | 004、044 | DEFERRED | 计划默认关闭的增强项 |
| 18 | KF2-052 多轮契约 | 033、051 | DEFERRED | 计划默认关闭的增强项 |
| 19 | KF2-055 DOCX 接通 | 048 | DEFERRED | 计划默认关闭的增强项 |

## KF2-001 本次工作包

- 目标：核实已有材料，列明原设计缺口，建立可填的映射结构；不猜测旧设计。
- 依赖版本：V0.2 计划 `7d5095b`；V1.1 未提供。
- 变更：本执行记录、`docs/architecture/compatibility.md`、`docs/tasks/legacy-mapping.csv`。
- 核对命令：`git fetch origin`、`git branch -a`、`git ls-tree -r --name-only origin/main`、`rg --files --hidden -g '!.git'`；实际结果与上述材料清单一致。
- CSV 验证：以 Python `csv.DictReader` 检查 12 个唯一表头、0 条旧任务；零条是缺输入，不是兼容性通过。
- 原文件校验、SQL/API 对比、旧任务映射、Q 抽查：未执行，原因是原文件缺失。
- 基线 SHA：`7d5095b`；目标提交由 `git log -- docs/architecture/compatibility.md docs/tasks/legacy-mapping.csv` 定位，避免把提交自身 SHA 写入提交内容。
- Q 审阅：未执行；实际集成：未执行；最终状态：`WAITING_INPUT`。

## KF2-004 草案准备包

- 允许提前开展的范围：任务卡明确允许在 001 等待输入时整理提议契约；这不解除正式 Schema 的兼容性门槛。
- 基线 SHA：`12618ef8af1f648000aadbf13818f9f71d5cfabc`；分支/目录同上；契约标识 `0.2.0-draft.1`。
- 变更：`contracts/README.md`、`api-draft.md`、`schemas/protocol.schema.json`、`examples/protocol-cases.json`、`validate.py`、`requirements-validation.txt`；`docs/architecture/ADR-001-state-and-contract-draft.md`。
- 产物：状态单写、候选公开/内部 API、请求与错误、租约/完成与幂等、可信范围、引用定位、历史失效、SSE/取消提议、Flyway 分配规则、待决问题。尚不是完整 OpenAPI 或已冻结的 AI Schema。
- 实际验证：`python -m pip install -r contracts/requirements-validation.txt` 成功；`python contracts/validate.py` 通过 Schema 及 31 个结构样例；`git diff --check` 通过。Markdown 相对文件链接检查通过。
- 初次校验失败：环境的 `jsonschema` 未安装 RFC 3339 检查器，负例 `reject-time-without-zone` 未被拒绝。补齐固定版本的 `rfc3339-validator` 并增加缺检查器即失败的保护后通过；另验证缺检查器确实导致校验命令失败。
- 未执行：真实服务/模型/数据库、租约状态机和权限测试、B/M 消费确认、Q 独立审阅、实际集成。当前仅测试结构，样例中的模型维度和摘要均为合成占位，不是 KF2-003 的实测。
- 目标 SHA：由 `git log -- contracts docs/architecture/ADR-001-state-and-contract-draft.md` 定位；无审阅通过或正式发布记录。
- 最终状态：`BLOCKED`，草案准备已完成；缺 001 原设计核对、002 场景确认、003 运行基线与独立审阅。

## 下一步交接

1. 项目负责人补充 V1.1 原设计包、旧任务与版本来源，A 继续 KF2-001；若决定放弃旧基线，需要明确记录该范围变更，不能静默假定。
2. 接收 M 的 KF2-002/005、B 的 KF2-003 交付与具体提交；A 按字段/状态差异完善 004 后交 Q 审阅。当前没有这些交付证据，也没有代替其他角色领取任务。
3. 005 满足后按任务卡准备 006 隔离骨架和构建工具；004 冻结后完成接口验收及 011 正式迁移，再顺序推进后续 A 任务。

当前没有可按硬依赖进入正式实现/验收的下一项 A 任务；不把草案、缺输入记录或开发用样例标为 DONE。
