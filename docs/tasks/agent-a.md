# Codex-A 执行记录

## 初始准备（2026-10-29）

- 日期：2026-10-29（Asia/Hong_Kong）；实际执行者：当前 Codex，角色 A。
- 仓库：`https://github.com/ggwenling/knowflow.git`；工作目录：`/workspace/knowflow`。
- 已从 `origin/main` 的 `7d5095b` 创建并切换到 `python`。分支名按用户要求，不将任务身份改为 B。
- 已读取 V0.2 计划包和任务数据，确认 A 有 16 项核心任务、3 项可选任务。
- 初始基线无未提交修改，无 `AGENTS.md`、业务代码或 V1.1 设计包。
- 环境：Java 21.0.12.1、Python 3.12.14；Maven 未安装。Java 骨架准备时需先落实构建工具及服务依赖版本，不宣称当前能够编译 Spring 服务。
- 云环境可连接，Git 拉取已实际成功；未配置模型凭证或目标硬件基线。未发起真实模型调用。
- 仅修改 A 的架构、任务记录和公共契约；未接替 B/M/Q，也未改计划包的初始状态。

## 计划顺序（当前执行记录见下文）

本文件记录实际执行状态；计划包中的 `PLANNED` 保留为规划快照。无 Q 审阅/实际集成证据的任务不标记 `DONE`。阻断任务不占用正在开发名额；一次仅推进一项允许的准备工作。

| 顺序 | 任务 | 依赖 | 实际状态 | 当前产物或解除条件 |
|---|---|---|---|---|
| 1 | KF2-001 V0.2 新基线决策 | 无 | IN_REVIEW | 用户授权采用新基线；原 V1.1 及旧任务映射仍未验证，见[兼容性记录](../architecture/compatibility.md) |
| 2 | KF2-004 共享契约 | 001、002、003 | IN_REVIEW | Java 与 B 已共同消费 draft.4（B target `b598f1d`，代码 target `2623a62`）；Q 审阅及 M 消费确认仍待处理，见[联调记录](java-python-integration.md) |
| 3 | KF2-006 Java 骨架 | 004、005 | IN_REVIEW | 骨架已可启动并通过认证/health/本地 WebClient 验收；005 与契约仍待审阅 |
| 4 | KF2-011 迁移与受限角色 | 004、005 | IN_REVIEW | Flyway/pgvector 与真实 PostgreSQL 权限测试通过；Q/M 消费确认待处理 |
| 5 | KF2-012 认证 | 006、011 | IN_REVIEW | 注册、登录、会话撤销/过期的真实 PostgreSQL 测试通过；Q 与安全/产品缺口待审阅 |
| 6 | KF2-013 知识库隔离 | 012 | IN_REVIEW | owner-scoped CRUD 与删除状态真实 PostgreSQL 测试通过；Q 审阅、物理清理与并发删除协调待处理 |
| 7 | KF2-014 上传与状态 | 009、013 | BLOCKED | `origin/python@b598f1d` 的 `infra/README.md` 仍无 Compose/Dockerfile/CI；等待 M 的 KF2-009 真实交付 |
| 8 | KF2-015 任务租约 | 007、014 | BLOCKED | B KF2-007 服务已交付，但仍依赖被阻断的 KF2-014 上传/状态基础设施 |
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

KF2-001、KF2-004、KF2-006 的逐项 SHA、验收范围及独立复核清单见 [A 线 Q 审阅包](agent-a-review-package.md)。

## KF2-001 初始准备记录（2026-10-29）

- 目标：核实已有材料，列明原设计缺口，建立可填的映射结构；不猜测旧设计。
- 依赖版本：V0.2 计划 `7d5095b`；V1.1 未提供。
- 变更：本执行记录、`docs/architecture/compatibility.md`、`docs/tasks/legacy-mapping.csv`。
- 核对命令：`git fetch origin`、`git branch -a`、`git ls-tree -r --name-only origin/main`、`rg --files --hidden -g '!.git'`；实际结果与上述材料清单一致。
- CSV 验证：以 Python `csv.DictReader` 检查 12 个唯一表头、0 条旧任务；零条是缺输入，不是兼容性通过。
- 原文件校验、SQL/API 对比、旧任务映射、Q 抽查：未执行，原因是原文件缺失。
- 基线 SHA：`7d5095b`；目标提交由 `git log -- docs/architecture/compatibility.md docs/tasks/legacy-mapping.csv` 定位，避免把提交自身 SHA 写入提交内容。
- Q 审阅：未执行；实际集成：未执行；最终状态：`WAITING_INPUT`。

## KF2-004 初始草案准备包（2026-10-29）

- 允许提前开展的范围：任务卡明确允许在 001 等待输入时整理提议契约；这不解除正式 Schema 的兼容性门槛。
- 基线 SHA：`12618ef8af1f648000aadbf13818f9f71d5cfabc`；分支/目录同上；契约标识 `0.2.0-draft.1`。
- 变更：`contracts/README.md`、`api-draft.md`、`schemas/protocol.schema.json`、`examples/protocol-cases.json`、`validate.py`、`requirements-validation.txt`；`docs/architecture/ADR-001-state-and-contract-draft.md`。
- 产物：状态单写、候选公开/内部 API、请求与错误、租约/完成与幂等、可信范围、引用定位、历史失效、SSE/取消提议、Flyway 分配规则、待决问题。尚不是完整 OpenAPI 或已冻结的 AI Schema。
- 实际验证：`python -m pip install -r contracts/requirements-validation.txt` 成功；`python contracts/validate.py` 通过 Schema 及 31 个结构样例；`git diff --check` 通过。Markdown 相对文件链接检查通过。
- 初次校验失败：环境的 `jsonschema` 未安装 RFC 3339 检查器，负例 `reject-time-without-zone` 未被拒绝。补齐固定版本的 `rfc3339-validator` 并增加缺检查器即失败的保护后通过；另验证缺检查器确实导致校验命令失败。
- 未执行：真实服务/模型/数据库、租约状态机和权限测试、B/M 消费确认、Q 独立审阅、实际集成。当前仅测试结构，样例中的模型维度和摘要均为合成占位，不是 KF2-003 的实测。
- 目标 SHA：由 `git log -- contracts docs/architecture/ADR-001-state-and-contract-draft.md` 定位；无审阅通过或正式发布记录。
- 当时阶段状态：`BLOCKED`，缺少 001 原设计核对、002 场景确认、003 运行基线与独立审阅。2026-10-30 用户批准采用 V0.2 新基线且 B/M 输入已合入后，契约候选更新为 `0.2.0-draft.2`；现为 `IN_REVIEW`，详见下方本轮记录。

## 初始交接计划（2026-10-29；已由下方本轮记录更新）

1. 项目负责人补充 V1.1 原设计包、旧任务与版本来源，A 继续 KF2-001；若决定放弃旧基线，需要明确记录该范围变更，不能静默假定。
2. 接收 M 的 KF2-002/005、B 的 KF2-003 交付与具体提交；A 按字段/状态差异完善 004 后交 Q 审阅。当前没有这些交付证据，也没有代替其他角色领取任务。
3. 005 满足后按任务卡准备 006 隔离骨架和构建工具；004 冻结后完成接口验收及 011 正式迁移，再顺序推进后续 A 任务。

当前无数据库、登录业务、索引任务或问答业务实现；后续 A 任务依赖契约、005、B/M 服务与审阅逐项推进。

## 2026-10-30：整合基线及计划执行

- 用户决定：以 V0.2 重新建立基线；继续使用 `python` 分支；本轮推进 KF2-001、004、006，并按实际审阅/集成证据更新状态。
- 远端：已执行 `git fetch origin python:refs/remotes/origin/python`，将 B/M 线 `origin/python@928b5d906969544693e8f5e4cc4b4dad72b5e5db` 合入本地 A 线；整合提交 `0a19a7a`，双方提交均保留，无强推。
- 冲突：`contracts/README.md` 新增/新增；已合并 A 契约草案与 B/M 所有权和配置规则。其余远端变更文件及证据均按 B/M 提交保留。
- KF2-001：批准新基线决策记录在 [compatibility.md](../architecture/compatibility.md)。旧 V1.1 及旧 `KF-*` 兼容不伪报通过；任务目前 `IN_REVIEW`，等待 Q 对具体提交审阅。
- KF2-004：输入含 B 线 1024 维 `BAAI/bge-m3`、`deepseek-flash` 别名和运行记录；别名可变、生产限制/数据条款适用性未决。Schema 升为 `0.2.0-draft.2`，增加模型请求/响应候选与合成样例；`python contracts/validate.py`：39 项结构样例通过。结构检查不验权限、模型响应的语义匹配、租约或数据库状态。
- B 线 KF2-002/003/005 按 `origin/python@928b5d9` 的审阅包标为 `IN_REVIEW`；未代填 Q 结论，不把已合并等同获批。
- KF2-006：已交付可独立编译、启动和验证的安全 Java 骨架。业务 API 与数据库接入仍待契约冻结及依赖审阅。
- KF2-006：Java 21、Spring Boot 3.5.16、Maven 3.9.16 和 Apache Maven Wrapper 3.3.4；发行包 SHA-512 与 Maven Central 校验值匹配。由于当前环境只安装 Java 21 JRE（无 `javac`），Maven 固定使用 Eclipse Compiler 3.36.0 编译 Java 21 字节码。Maven 需使用仅在 `/tmp` 配置的云代理 settings；代理配置和凭证未提交。
- KF2-006 验证：原始 8 项 Java 测试及审查修复后共 11 项 Java 测试通过；Maven `verify`、39 项契约结构样例通过。打包 JAR 冒烟确认有效 Bearer token 可启动并 health 为 `UP`，含换行密钥启动失败且不泄露密钥；404/405 集成测试核对统一错误体与 `Allow`。WebClient 只通过本地 loopback stub 测试请求 ID 和内部认证，未调用 B 服务或外部模型。
- KF2-006 审查修复 target：`eb88cc1fe40d91f2b4fe5b992e230779ad998daa`；最新复核范围见 [A 线 Q 审阅包](agent-a-review-package.md)。任务仍待 Q 对修复 SHA 审阅及依赖集成确认。
- 当前阶段整合基线：`0a19a7afc80fa778dd5b2e10e7a825360538a9f9`。逐项 target SHA、复核范围和验证命令见 [A 线 Q 审阅包](agent-a-review-package.md)。本轮未调用真实模型或读取/提交任何 API 密钥。

## 2026-10-30：JP-01 Java 路线（KF2-011 / JP-C1 / JP-I1 Java 侧）

- 仓库：`/workspace/knowflow-java`；分支：`java`；共同基线 `BASE_SHA=150cd847a5750143fb6eb2c74c762962381952fe`；Java 交付 target：`115931caaf99fe3fd9c473d2f0f1b6ebd9648ccd`。
- KF2-011：交付 Flyway `V1`，建立 users、knowledge bases、documents、content/index versions、index tasks、chunks、`vector(1024)` 及相关唯一、外键、状态和定位约束。迁移历史在独立 `knowflow_flyway` Schema；数据库管理员引导脚本建立无默认密码的迁移、应用、AI 登录角色。AI 只有检索所需表的 SELECT，不能改状态或写 Chunk/向量；应用角色无 DDL。
- 应用数据库配置成为可运行实现：Spring `database` profile 以 Hikari 和 `knowflow_app` 连接，默认 Java 启动仍不连接数据库；迁移使用单独 `db-migrate` profile / `--migrate-only` 命令。当前没有业务 Repository 或任务状态机。
- JP-C1：契约候选升至 `0.2.0-draft.3`，新增内部 health 最小报文；Schema SHA-256 `1b5133ddcdac4a6accb0faf4a88f2dda7204f5932151043168473d2d8574c5c5`。Java health 客户端带内部 Bearer 与 request ID，限时 5 秒、无自动重试，并核对响应版本、状态和 ID。该候选仍待 B 消费确认、M 相关消费确认和 Q 审阅；KF2-004 未冻结。
- KF2-011 验证：`cd services/api && ./mvnw -s /tmp/knowflow-maven-settings.xml verify` 成功，18 项 Java 测试通过。真实 `pgvector/pgvector:0.8.1-pg16`（镜像摘要记录于服务说明）/ PostgreSQL 16.12 覆盖 Flyway 空库与重复执行、CLI、1024 维向量、唯一/外键/检查约束、AI 无 DML、应用角色可连接但无 DDL。`python contracts/validate.py` 的 41 个结构样例通过；`python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q` 的 16 项通过；`git diff --check` 通过。
- JP-I1：Java→Python 请求只在本地 loopback stub 上完成；真实双进程联调 `WAITING_B_SERVICE`。截至 `origin/python@150cd847a5750143fb6eb2c74c762962381952fe`，`services/ai/` 只有 README 和 `.env.example`，无 FastAPI 实现。未修改 B 所有的 `services/ai/`，未把本地 stub 说成真实集成。
- ADR-002 提出 Java 有界批量写入网关并保留 AI 只读；B 的批大小/重试/清理需求与 Q 的 fencing 审阅未到位，方案仍为 `PROPOSED`，不开放 Python 直写，不启动 KF2-018。
- KF2-011 / KF2-004 状态：`IN_REVIEW`；真实 Python 联调未执行；Q 审阅未执行。数据库证据只覆盖新建空库，不声称兼容未知旧库或完成租约、fencing、删除/发布竞态。

## 2026-10-30：JP-01 G3 Java 后续（KF2-012/013）

- 分支：`java`；base 为 JP-01 Java 交付 `f2204a52f221e1b9691824cac845d0f75c6a2f29`；target：`895a1ba4655d9e875730d5bbeb65e570853c8d01`。
- KF2-012：`database` profile 下提供注册、登录、logout、`/me`。密码由 Spring Security PBKDF2 编码器处理；只存密码摘要。opaque bearer token 由 32 随机字节构造，有效期 8 小时，数据库只存 SHA-256；session 查询核对数据库到期时间与撤销状态。错误密码/未知账户使用相同 401；注册冲突不回显邮箱/密码，但 409 状态仍可能泄露地址冲突。未实现密码重置、refresh、多 session 撤销、邮箱验证及登录限速。
- KF2-013：创建、分页列表、详情、删除均从已验证 principal 派生 user id；每个查询显式限制 `owner_user_id`，JSON 多余字段拒绝，含 `owner_id` 的创建请求返回 400。删除事务标记知识库/文档不可见并取消排队/运行任务、清除租约。对象和向量的物理清理仍需 KF2-014/024 的存储/清理入口；后续创建文档任务也必须与删除做状态/锁协调。
- 契约候选升至 `0.2.0-draft.4`；Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。包含注册、登录、会话、当前用户、知识库、分页与通用冲突错误样例；B 未消费，M 未确认，Q 未审阅，KF2-004 仍未冻结。
- 验证：`cd services/api && ./mvnw -s /tmp/knowflow-maven-settings.xml verify` 通过，21 项 Java 测试；真实 PostgreSQL 16.12/pgvector 0.8.1 覆盖 V1/V2、应用 profile、注册/登录/哈希/过期/撤销、双用户 owner 隔离、owner 注入、资源 404 和删除文档/任务状态。`python contracts/validate.py` 通过 54 项；`python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q` 通过 16 项；`git diff --check` 通过。
- 任务状态 `IN_REVIEW`，不登记 `DONE`：Q 审阅和 M 消费确认待执行；登录限速、邮箱冲突产品决策、密码重置及对象/向量回收未实现。此记录写入时 JP-I1 仍等待 B 服务；最新双进程状态见[联调记录](java-python-integration.md)。

## 2026-10-30：JP-I1 draft.4 双进程完成

- A Java target：`ec5c71c9be5a8766540fc48e174f215c0cf388ac`；B Python target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`（测试代码 target `2623a6282b2695a8ef96e3553a849729efd42403`）；共同消费 A draft.4 提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 联调运行提交 `225124fbae8041efd67ee5e6ca5bf89fdbbe8884`（A/B 父 target 分别为 `ec5c71c` / `2623a62`）。真实 Java/Python smoke 8/8 通过，且实际通过 `AiInternalHealthClient` 验证正确版本接受、draft.2 拒绝、5 秒 deadline。清洁运行报告与哈希见[联调记录](java-python-integration.md)。
- B 全量测试 65 项、契约 54 项、Python 离线回归 16 项通过；Q 406 修复 target `24a07fd85c70cab3c522118697824727bf9651fe` 的 Java `verify` 22 项通过。KF2-004 仍是待审候选；JP-I1 开发验证通过但不代替 Q/M 正式审批。
- KF2-014 仍 `BLOCKED`（缺 M KF2-009）；KF2-015 仍受 KF2-014 阻断。

## 2026-10-30：Q 复核修复（406 Content Negotiation）

- Q review base：`ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434`；代码修复 target：`24a07fd85c70cab3c522118697824727bf9651fe`；审阅记录随 Java `ec5c71c` 推送。
- `Accept` 无可用表示时，专用处理器保留 Spring 的 406 status 与支持类型响应头，返回脱敏的 `INVALID_REQUEST` 错误体；新增 MockMvc 回归验证 status/header/request ID/body。
- `mvnw verify` 22 项、契约样例 54 项、Python 离线回归 16 项均通过。请 Q 复核具体修复 SHA，不预填批准结论。
