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
| 2 | KF2-004 共享契约 | 001、002、003 | BLOCKED | 仅允许草案准备；等待原设计、M 场景、B 运行基线及 A/B/M/Q 确认 |
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
