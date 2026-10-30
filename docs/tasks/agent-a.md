# Codex-A 执行记录

## JP2 Java 后端当前交付（2026-10-30）

当前 `java` 分支已提交 Java 后端候选，代码 target 为 `489b746f9bfa8188041f12d9135cf98fe6846611`，基于 `f63a295`；契约为 `0.2.0-draft.5`，Schema SHA-256 `3953784ab2bd2005cded12baa11caa99b6e47a79c77d5a1078b158f59f5639ef`。该提交可供 Q 独立复核，但仍是候选，不代表 Q 批准或 B 已消费。

| 子任务 | Java 交付状态 | 证据与边界 |
|---|---|---|
| A01 HTTP 状态映射 | 已实现，待 Q 复核 | 400、404、405、406、415 保留正确状态；405 保留 `Allow`，406/415 保留框架支持媒体类型头。对应回归测试通过。406 修复提交 `24a07fd`，415 修复提交 `b2e6fe2`。 |
| A02 draft.5 / ADR-002 | 候选已发布，B 消费与 Q 审阅待处理 | API Schema、成功/失败样例、索引批次/Manifest 摘要、lease/heartbeat/completion/cancel 与可信问答范围已固定；消费清单记录 Java SHA 和 Schema SHA。 |
| A03 隔离开发环境 | 已实现并启动验证 | `services/api/compose.dev.yml` 独立启动固定摘要的 pgvector PostgreSQL 与 MinIO；本机 Compose 健康检查通过，迁移角色真实应用 V1–V5。没有修改共享 `infra/`。 |
| A04 上传、文档与任务查询 | 已实现 | 真实 MinIO/PostgreSQL 覆盖 TXT/MD/PDF 上传、签名/大小检查、摘要、202/QUEUED、列表与状态查询；对象写入或事务失败走补偿清理队列，越权返回无资源信息。 |
| A05 队列、租约与 fencing | 已实现 | 原子数据库领取、60 秒租约、15 秒 heartbeat、fencing 替换、5/30 秒退避、最多 3 次尝试、过期执行隔离重领；并发领取、旧租约、失败重试和 heartbeat 边界有数据库测试。 |
| A06 受控源文件读取 | 已实现 | 内部读取按当前任务/文档/版本/有效 lease 核验，响应只提供字节与摘要元数据，不暴露对象键或主凭据；越权、失效和删除后读取有回归。 |
| A07 批量写入网关 | 已实现 | 同一事务内校验 service auth、owner/范围、token hash、lease/fencing、1 MiB/32 条、1024 维有限向量、Chunk 序号/文本摘要和批次 SHA；相同摘要重放幂等，复用身份但摘要不同冲突。 |
| A08 完整性验收与发布 | 已实现 | Java 对数据库中实际 Chunk、向量、序号、批次和 Manifest 核对后，在同一事务完成 task、候选状态与活动版本切换；失败不覆盖旧活动索引。 |
| A09 问答可信快照 | Java 入口已实现 | owner/READY 索引快照由 Java 构造，WebClient 调 Python，返回来源逐项按快照、Chunk 和引用片段核验；调用前后检查可见性。真实模型/完整 B 问答尚未联调。 |
| A10 来源与原文件代理 | 已实现 | 来源绑定问题/用户/文档/内容/索引/Chunk；原文件代理提供有界单段 Range，校验对象长度与 SHA；删除后来源与文件立即失效。 |
| A11 删除、取消与可重试清理 | 已实现 | 逻辑删除立即撤销可见性和 lease；取消、对象/索引物理清理经 outbox 重试。覆盖删除与迟到 batch/heartbeat/completion、清理重试。 |
| A12 后端集成与故障验收 | Java 侧完成；真实跨服务闭环待 B | Java + 真实 PostgreSQL/MinIO 的上传、索引发布、问答 fixture、来源/文件与删除故障测试通过。`origin/python@b598f1d` 仍只提供 draft.4 health 与解析，不含 B06 索引执行器或 B09 真实生成；没有真实模型凭证，因此不宣称 A/B 完整闭环、Worker 进程中断恢复或生产质量验收完成。 |

### JP2 验证

- `cd services/api && ./mvnw clean verify`：46 项，0 失败、0 错误、1 项可选真实 Python smoke 因未设置外部服务变量而跳过；其余 Java 测试使用真实 Testcontainers PostgreSQL/pgvector 和 MinIO。
- `python3 contracts/validate.py`：Schema 与 70 个结构样例通过；`python3 -m unittest contracts.test_index_batch_hash -v`：5 项跨语言批次摘要测试通过。
- 独立 Compose `config --quiet`、PostgreSQL/MinIO 健康检查及真实本机库 V1–V5 Flyway 迁移均通过；`git diff --check` 通过。
- draft.4 真实 Java/Python health 联调仍以原固定候选为准：A `ec5c71c`、B `b598f1d`、运行 target `225124f`，8/8 通过，报告 SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`。这不表示 draft.5 已被 B 消费；当前 B target 的实际版本与 Schema SHA 见[联调记录](java-python-integration.md)。

本段 JP2 记录和 Q 审阅包以更晚的文档提交追加，不改变上述代码 target。Q 结论留空，等待独立复核。

### 2026-10-30 后续审查修复

- Review base `533b1f1622accb696fdf26e90e8a8c322998ea0b` → Java 修复 target `806190b07e71d028dcb3327fcd663a1ff625d01b`；引用替换、S3 总读取时限、存储 I/O 事务边界及 MinIO 最终就绪等待修复可供 Q 复核，详细验证记录见 [后续 Q 审阅包](agent-a-review-package.md)。
- `cd services/api && ./mvnw clean verify`：49 项，0 失败、0 错误、1 项 opt-in 真实 Python smoke 跳过。契约结构校验 70 项，跨语言摘要测试 5 项通过。

## 初始准备（2026-10-29）

- 日期：2026-10-29（Asia/Hong_Kong）；实际执行者：当前 Codex，角色 A。
- 仓库：`https://github.com/ggwenling/knowflow.git`；工作目录：`/workspace/knowflow`。
- 已从 `origin/main` 的 `7d5095b` 创建并切换到 `python`。分支名按用户要求，不将任务身份改为 B。
- 已读取 V0.2 计划包和任务数据，确认 A 有 16 项核心任务、3 项可选任务。
- 初始基线无未提交修改，无 `AGENTS.md`、业务代码或 V1.1 设计包。
- 环境：Java 21.0.12.1、Python 3.12.14；Maven 未安装。Java 骨架准备时需先落实构建工具及服务依赖版本，不宣称当前能够编译 Spring 服务。
- 云环境可连接，Git 拉取已实际成功；未配置模型凭证或目标硬件基线。未发起真实模型调用。
- 仅修改 A 的架构、任务记录和公共契约；未接替 B/M/Q，也未改计划包的初始状态。

## 原始 KF2 计划顺序（JP-01 历史快照；当前状态以 JP2 表为准）

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

## 2026-10-30：本机 `local` draft.6 Java 集成复核

- 基线为从 `main` 派生的 `local`，base commit `dd3abd4aa003fe5b6b88ce649b8806d9b82b8631`；本轮 Java 变更与 B 消费端一起留在未提交工作树。共享 Schema `0.2.0-draft.6` SHA-256：`d64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1`。
- `services/api` 全量 Maven/Testcontainers 套件：**49 tests，0 failures，0 errors，1 skipped，BUILD SUCCESS**。迁移 V1–V5 在本机 PostgreSQL/pgvector 上成功；MinIO 健康。
- Java/Python 实际双进程 health smoke **9/9**。真实 Java 和 Python 服务通过本地 Java 网关完成合成 Markdown 上传、租约派发、源文件读取、批次/完成、PostgreSQL READY 发布；问答通过 AI 只读检索后，由 Java 对 scope、Chunk quote、locator 和 citation 重新校验并持久化。详细脱敏报告见联调记录 `local-backend-e2e-draft6.json`。
- 新增 B 侧 fail-closed scope guard 后，真实本机合成问答链路再次通过；Python 先核对检索返回的 document/content/index tuple 是否属于 Java 提供的可信快照，再构造 LLM 请求。越界 document、content version、index version 三类单测均验证 LLM 不会被创建；最新报告见 `services/ai/docs/evidence/local-backend-e2e-draft6-verified.json`。
- 本机问答联调发现 Windows Proactor 不支持 psycopg 异步连接；对应 Python 只读查询改为线程池中的同步 psycopg，保留只读事务和 5 秒超时。索引和问答均由合成 adapter 执行，真实外部模型调用 **0**。
- Java 公共 API 行为与既有安全/发布边界回归通过；合同仍是候选版本，Q 审阅及 M 消费确认待执行，KF2 状态不因此登记为 DONE。
- 本轮再次执行 `mvnw.cmd -B test`，全量结果仍为 49 tests、0 failures、0 errors、1 skip。当前本机数据库角色审计已检查 V5/pgvector、AI 查询与禁止写权限、app 无 DDL，报告见 `services/ai/docs/evidence/local-db-role-audit-draft6.json`。
- 删除边界新增结构有效的迟到 completion 检查：任务删除后，带正确 batch/manifest 摘要的 `SUCCEEDED` completion 被 Java 拒绝并返回 `DOCUMENT_UNAVAILABLE`。目标用例和全量 Maven/Testcontainers 49 项均通过。
- 10/30 再次执行 Java Maven/Testcontainers 全量套件：49 tests，0 failures、0 errors、1 skip，BUILD SUCCESS；Testcontainers 实际应用 V1–V5，并启动 pgvector PostgreSQL 与 MinIO。

## 2026-10-30：JP-I1 draft.4 双进程完成

- A Java target：`ec5c71c9be5a8766540fc48e174f215c0cf388ac`；B Python target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`（测试代码 target `2623a6282b2695a8ef96e3553a849729efd42403`）；共同消费 A draft.4 提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 联调运行提交 `225124fbae8041efd67ee5e6ca5bf89fdbbe8884`（A/B 父 target 分别为 `ec5c71c` / `2623a62`）。真实 Java/Python smoke 8/8 通过，且实际通过 `AiInternalHealthClient` 验证正确版本接受、draft.2 拒绝、5 秒 deadline。清洁运行报告与哈希见[联调记录](java-python-integration.md)。
- B 全量测试 65 项、契约 54 项、Python 离线回归 16 项通过；Q 406 修复 target `24a07fd85c70cab3c522118697824727bf9651fe` 的 Java `verify` 22 项通过。KF2-004 仍是待审候选；JP-I1 开发验证通过但不代替 Q/M 正式审批。
- KF2-014 仍 `BLOCKED`（缺 M KF2-009）；KF2-015 仍受 KF2-014 阻断。

## 2026-10-30：local 最新 Java / Python 边界复验

- Java 公开问答上游 AI `503` 回归通过：对外返回脱敏、可重试 `502 AI_PROCESSING_FAILED`，数据库问题状态为 `FAILED/AI_PROCESSING_FAILED`。`DocumentApiIntegrationTest` 20/20；Maven/Testcontainers 全量 **50 项，0 failure、0 error、1 skip，BUILD SUCCESS**。
- 同步复验 Python 全量 **126 passed**、Schema **70** 项、离线模型回归 **16** 项、Python HTTP smoke **8/8**、真实 Java→Python health smoke **9/9**。当前 provider 凭证缺失，外部模型请求 0。
- 增加 Python 问答响应超时回归：真实 WebClient 调用本地阻塞 HTTP fixture，Java 30 秒读超时映射为脱敏可重试 `504 PROCESSING_TIMEOUT`，问题状态持久化为 `FAILED/PROCESSING_TIMEOUT`。`DocumentApiIntegrationTest` **21/21**，全量 Maven/Testcontainers **51 项，0 failure、0 error、1 skip，BUILD SUCCESS**；上游 `503` 映射用例仍通过。

## 2026-10-30：Q 复核修复（406 Content Negotiation）

- Q review base：`ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434`；代码修复 target：`24a07fd85c70cab3c522118697824727bf9651fe`；审阅记录随 Java `ec5c71c` 推送。
- `Accept` 无可用表示时，专用处理器保留 Spring 的 406 status 与支持类型响应头，返回脱敏的 `INVALID_REQUEST` 错误体；新增 MockMvc 回归验证 status/header/request ID/body。
- `mvnw verify` 22 项、契约样例 54 项、Python 离线回归 16 项均通过。请 Q 复核具体修复 SHA，不预填批准结论。

## 2026-10-30：提前复验下一日 Java 检查点

- `./services/api/mvnw.cmd -B -f services/api/pom.xml test`：**51 项，0 failure、0 error、1 skip，BUILD SUCCESS**，包含 Testcontainers 迁移、租约/fencing、删除和迟到 completion 回归；跳过项为未配置真实 Python 服务的独立 smoke，另以真实双进程 health **9/9** 验证。
- 本地 Compose V1–V5、pgvector 0.8.1 和角色权限复核通过。真实 Java/Python/PostgreSQL/MinIO 合成索引、问答及活动取消重放见 `services/ai/docs/evidence/local-backend-e2e-draft6-replay.json`。测试服务已退出、三种清理队列为空；本次无外部模型调用。
- 这是 10/30 提前复验，未声称 10/31 当天复跑；工作树仍为未提交的 `local` 候选，Q/M 结论不变。
