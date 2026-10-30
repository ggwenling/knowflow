# KnowFlow Python / B 线接手交接文档

交接日期：2026-10-30（Asia/Hong_Kong）。接续会话：`codex -b 10/29`、`codex -b 10/30`。初版交接先核对项目、分支、任务和证据；收到用户的下一轮并行开发计划后，已按其第一批完成并验证 B02/KF2-017 分段和 B03/KF2-018 Embedding 适配器。本文尾部记录续作状态。

## 1. 接手结论与工作区

B 线已交付 Python 服务骨架、种子资料、解析组件、确定性分段及真实 Embedding Provider，并完成 Q 提出的 Unicode 空白处理和 draft.4 消费升级。索引执行、Java 网关写入、受控检索和问答完整链路尚未完成。接手后沿现有实现增量推进，不重建工程。

| 项目 | 本次核对值 |
|---|---|
| 仓库 | `https://github.com/ggwenling/knowflow` |
| 本地目录 / 分支 | `/workspace/knowflow` / `python` |
| 接手基线 / 远端 Python HEAD | `b598f1d62cc2367a4bfd49fccd3c31b521abff23` |
| Python 最近代码修复 target | `2623a6282b2695a8ef96e3553a849729efd42403` |
| 真实双进程验证候选 | `225124fbae8041efd67ee5e6ca5bf89fdbbe8884` |
| 该候选配对的 Java target | `ec5c71c9be5a8766540fc48e174f215c0cf388ac` |
| 本次读取的远端 Java HEAD | `894fc76`，在上述 Java target 后补充集成记录 |
| AGENTS.md | 本次未发现仓库或上级目录的适用文件 |

本环境最初只有 `work@7d5095b` 的计划文档快照；本次获取远端分支后，已切换到现有 `python` 基线。编写本文前工作区干净。没有合入远端 Java 的后续记录提交，没有合并或推送 `main`。以上是交接快照，后续开工需重新获取远端并核对差异。

本仓库远端抓取配置原先只包含 main；本次通过显式 refspec 读取各分支。后续若普通 fetch 没更新 Python，可使用：

```sh
git fetch origin '+refs/heads/*:refs/remotes/origin/*'
git status --short --branch
git rev-parse HEAD origin/python
```

## 2. 职责与文件边界

- B：`services/ai/`、`evaluation/`，以及本任务对应的 `docs/evaluation/`、`docs/research/ragflow/`。负责解析、分段、Embedding、检索、生成、引用定位和 RAG 评测。
- A：`services/api/`、`contracts/`、Flyway、共享架构 ADR，兼任集成协调。Java 是业务状态、任务租约和活动索引发布的唯一写入方。
- M：`apps/web/`、`infra/`、CI、端到端和产品试用。002/005 曾由旧 B 会话按用户指派代交付，不代表 B 长期接管 M 的目录。
- Q：独立复核，结论绑定 SHA。B 修复自己的问题，不代填批准或修改 Q 报告。

公共字段、接口或数据库需求先写入 [B 契约消费记录](../services/ai/docs/contract-consumption.md)，由 A 发布正式候选。不能自行修改共享 Schema、迁移或绕过受控写入。后续任务按用户粘贴的 JP2 计划和交接条件推进。

## 3. 已有交付与状态

这里的“已交付”表示代码或文档存在且有开发证据，不表示正式 DONE。原始任务 JSON/CSV 的 PLANNED 是计划快照，实际进展应结合后续记录和具体 SHA 判断。

| 任务 | 已有内容 | 接手时状态 / 证据入口 |
|---|---|---|
| KF2-003 | 双供应商模型冒烟、配置选择器、隐私/资源/许可记录 | IN_REVIEW；[供应商配置](smoke/provider-profile.md)、[运行基线](../docs/architecture/runtime-profile.md) |
| KF2-007 | Python 3.12 / FastAPI、内部认证、健康、请求 ID、统一错误、依赖锁、契约消费者和适配边界 | IN_REVIEW；首次提交 `9f43750`，后续 draft.4 修复见 `2623a62`；[服务说明](../services/ai/README.md) |
| KF2-010 | 10 份原创合成文档、15 道中文题；12 开发 / 3 留出，含 3 道无答案题、版本/哈希/引用标注 | IN_REVIEW；首次提交 `fc98d57`；[资料集说明](../docs/evaluation/dataset.md) |
| KF2-016 | UTF-8 TXT/MD、pypdf 6.21.4 文本 PDF 解析、来源身份、文件哈希、字符区间/物理页码、固定错误 | IN_REVIEW；首次提交 `8cd9139`，空白修复 `2623a62`；[解析说明](../services/ai/docs/parsing.md) |
| JP-I1 | 真实 Spring Boot + Uvicorn；实际 Java 健康客户端接受 draft.4、拒绝旧版并验证超时 | 开发验证通过，正式复核/冻结未关闭；[修复复核包](python-q-review-fixes.md) |
| KF2-002 / 005（历史代交付） | 场景和试用脚本、目录/配置/协作基础及相关修复 | 记录仍为 IN_REVIEW；[执行记录](../docs/tasks/execution-log.md)、[审阅包](../docs/reviews/KF2-002-003-005-review.md) |

模型真实冒烟曾通过，但 KF2-003 的线上证据绑定当时的 runner；随后加严“返回模型 ID 必须匹配请求”的修复只有离线回归证据，不能称最新 runner 已重新完成线上验证。JP-01 和本轮 Q 修复联调均未调用付费模型。

## 4. 当前实现可直接复用的接口

| 文件 / 对象 | 能力与限制 |
|---|---|
| `services/ai/src/knowflow_ai/app.py` | 仅启用 `GET /health/live` 和受内部 Bearer 保护的 `GET /internal/v1/health`；没有索引/回答业务入口 |
| `config.py` / `Settings` | 从进程环境读取配置，不自动加载 `.env`；共享密钥不合规则启动失败 |
| `protocol.py` | 严格校验 A 发布的 Schema 和原始文件哈希，不能静默接受新版本 |
| `parsing.py` / `parse_document` | 输入是 bytes 和可信来源身份，不接任意 URL/磁盘路径，不读数据库，不发布索引 |
| `ParsedDocument` / `TextBlock` | 文档、内容版本、文件、文件哈希、parser profile、块序号、正文及定位元数据；后续分段应复用 |
| `adapters.py` | ModelAdapter / Retriever / IndexExecutor 是 Protocol 边界；含模型 ID、向量条数/序号/维度/有限值检查和超时/取消包装；LLM、检索及索引执行 Provider 仍未实现 |
| `chunking.py` | 新增标题/段落优先的确定性分段，文本码点定位与 PDF 物理页隔离；复现和边界见[分段说明](../services/ai/docs/chunking.md) |
| `embedding.py` | 新增 SiliconFlow `BAAI/bge-m3` 1024 维真实 Provider 适配器；当前供下一阶段索引执行器调用，尚无业务路由 |
| `evaluation/smoke/model_smoke.py` | 独立模型冒烟工具；不能把脚本整体复制成生产业务层，也不能以其通过宣称索引或问答通过 |

TXT/MD 原文保留 BOM、CRLF、Markdown 和 emoji，区间为 Unicode 码点的 `[start,end)`，不是 UTF-8 字节或前端 UTF-16 偏移。纯 Unicode 空白加 BOM 返回 `EMPTY_DOCUMENT`，有效正文不被 strip 或归一化。

PDF 保留从 1 开始的物理页码和空页信息，未获得坐标时不编造。`PDF_NO_TEXT` 只表示无可提取文本。当前 8 MiB / 200 页 / 200,000 码点是开发限制，未证明生产容量；OCR、多栏顺序、解压展开、CPU/内存隔离及并发加固尚未完成。

## 5. 当前契约、配置与启动

- 契约版本：`0.2.0-draft.4`，由 A 的 `895a1ba4655d9e875730d5bbeb65e570853c8d01` 发布，仍为候选。
- Schema：`contracts/schemas/protocol.schema.json`。
- Schema SHA-256：`ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 部署或非 editable 安装时，通过 `KNOWFLOW_CONTRACT_PATH` 挂载同一只读文件；缺失/哈希错误应失败，不能降级或关闭校验。
- 共享密钥：`KNOWFLOW_INTERNAL_SHARED_SECRET`，Java/Python 一致；32–256 个符合约定的 Bearer 字符，只通过环境注入。
- Embedding：硅基流动 `https://api.siliconflow.cn/v1`，`BAAI/bge-m3`，1024 维；选择器 `KNOWFLOW_EMBEDDING_KEY_ENV=EMBEDING_KEY`。`BAAI/bge-reranker-v2-m3` 是重排器，不能用作 Embedding。
- LLM：`https://api.deepseek.com`，`deepseek-flash`；选择器 `KNOWFLOW_LLM_KEY_ENV=DEEPSEEK_API_KEY`。旧记录的 `DEEPSEEP_API_KEY` 不代表当前绑定。

本次环境状态报告两项模型变量 ready、网络 unrestricted/enforced；未读取或输出密钥值。B03 已使用一条合成文本完成硅基流动真实 Embedding 冒烟，证据见第 10 节。当前服务健康检查仍不连接模型或数据库。

从仓库根安装、启动的既有命令如下；Python 要求 3.12，uv 基线为 0.12.23。先在运行环境注入内部共享密钥，不把实际密钥填入本文或提交文件。

```sh
uv sync --project services/ai --frozen
uv run --project services/ai --frozen uvicorn knowflow_ai.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

## 6. Q 最新结论与证据边界

已查阅 `codex Q 10/30` 最新完成回合：Q 复审报告 Python 空白处理、draft.4 消费以及 Java 406 的上轮问题已修复；仍有一个 Java 问题：注册接口接收 `Content-Type: text/plain` 应返回 415，实际返回 500。该问题由 A 修复，Q 因此未合并或推送 main。不能把它列为 B 的待修代码，也不能因此宣称项目已获批准。

该结论来自 Q 会话；其提及的 `docs/reviews/2026-10-30-Q-review-r4.md` 不在本次 Python 基线中，本次未将报告复制进来。后续以 Q 可访问报告及其精确 target 复核，不能把会话摘要当作本分支已保存的审阅报告。

| 既有验证层 | 记录结果 | 证据范围 |
|---|---|---|
| Python 全量 | 65 passed | 服务、数据、解析及新增消费/空白回归 |
| 公共契约 | 54 个样例通过 | 报文结构，不能替代权限或租约事务验证 |
| 模型客户端离线回归 | 16 项通过 | 不证明供应商当前在线可用 |
| Java/Python 双进程 | 8 项通过 | 真实健康客户端、认证、request ID、404/405、旧版拒绝及超时；不含业务索引/问答 |
| 模型/数据库调用 | 此次 Q 修复联调均为 0 | 不作为 pgvector、fencing、真实业务模型或 M1 闭环证据 |

这些是版本化证据和既有会话的结果，本次没有重跑。当前修复与候选关系、复现命令见 [Q 修复复核包](python-q-review-fixes.md)，新联调证据为 [java-python-draft4-qfix.json](../services/ai/docs/evidence/java-python-draft4-qfix.json)，空白证据为 [unicode-whitespace-qfix.json](../services/ai/docs/evidence/unicode-whitespace-qfix.json)。

## 7. 下一步 Python 任务

**KF2-017 已完成开发实现**，状态为开发验证通过、待 Q 审阅和集成。按 JP2 第一批顺序，下一步是等 A02 发布 draft.5 后完成 B01；源文件、批次、完成和取消契约到达后，再按第二批实现索引执行器、客户端和流水线。未发布前不猜接口字段。

B02 实现的交接不变量：

1. 复用 `ParsedDocument/TextBlock`，确定并版本化简单切分配置、块序号及可复现输出；如涉及公共 Chunk 字段，向 A 提案。
2. 保留 document/content/file、PDF 物理页码或 TXT/MD 原文码点区间；跨页和重叠不能丢失来源关系，不能使用渲染后正文偏移。
3. 验证同输入同配置一致、中文/emoji/CRLF、长段落、空白、重叠、跨页和原文切片匹配。使用现有种子集与 PDF 夹具。
4. 按 SHA 提交最小差异和证据，交 Q；不同时扩展索引、检索或生成入口。

| 后续核心任务 | 硬依赖 | 接手时缺口 |
|---|---|---|
| KF2-017 分段 / 来源 | 016 | B02 已开发验证（`338c632`）；待 Q 审阅及 A 消费集成 |
| KF2-018 Embedding / 版本索引 | 003、011、017 | B03 已有真实模型适配器（`0e079e9`）；缺 A 的有界写入网关及有效租约/fencing 校验，索引流水线尚未完成 |
| KF2-021 受控向量检索 | 018、019 | 缺索引/Java 发布闭环、可信范围与活动版本快照的实际查询 |
| KF2-022 单轮生成 / 拒答 / 引用 | 003、021 | 缺真实检索上下文和引用映射，不得返回固定答案代替 |
| KF2-030 流式生成 / 取消 | 004、022 | 完整 SSE/取消契约及生成链路未完成 |
| KF2-035 解析资源加固 | 016、026 | 缺 M1 与生产资源边界验证 |
| KF2-037 60 题质量评测 | 010、021、022、026 | 当前仅 15 道公开合成题，非盲测；缺独立题集与真实链路 |
| KF2-038 延迟 / 资源 / 成本 | 003、031、037 | 缺完整流式链路、质量基线和目标硬件/账单证据 |

KF2-045 中文关键词、046 混合检索/RRF、047 Rerank、048 DOCX、051 Query Rewrite、054 增强采纳报告均为后续可选项，未启动；继续沿 [原任务拆解](../docs/planning/v0.2/KnowFlow_V0.2_任务拆解.md)的依赖门槛处理。

## 8. 跨线交接与阻断

- **A → B（018 前）**：受控批量写入契约、批次上限/摘要/幂等规则、执行身份、lease/fencing 校验、过期/错误版本拒绝样例和受限角色。现 [ADR-002](../docs/architecture/ADR-002-index-write-boundary-proposal.md)仍为 PROPOSED；`knowflow_ai` 只有相关表 SELECT，不应直接写 Chunk/向量或业务状态。
- **B → A**：017 输出形状、来源/模型字段需求、批次与失败语义；由 A 更新 contracts/迁移。Java 负责验收清单及发布活动索引。
- **A/M 基础设施**：Java 014 仍依赖 M 的 009，后续 015 的真实调度/租约也未交付。不要因健康联调通过而跳过上传、任务或对象存储门槛。
- **Q**：保持 IN_REVIEW，继续处理按新 SHA 提出的 B 侧反馈；Java 415 残留问题归 A。真实用户试用、生产部署、完整索引问答和 main 集成均未在当前交付中完成。

## 9. 后续复现入口与阅读注意

以下为复现命令；文档编写期间已运行 Python 测试、契约、离线模型和种子资料检查。需要重做双进程检查时使用隔离干净工作区，并将输出写入新文件，保留历史证据。

```sh
uv run --project services/ai --frozen pytest services/ai/tests -q
uv run --project services/ai --frozen python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q
python evaluation/data/tools/validate_seed.py
# 真实双进程还需要 Java 21 和可用的 Maven 网络配置
uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py --require-clean --java-target ec5c71c9be5a8766540fc48e174f215c0cf388ac --output /tmp/knowflow-jp-handoff-smoke.json
```

证据更新脚本可能写入仓库内报告，先阅读参数并使用隔离目录；不因文档交接重复发起付费模型调用。公开的留出题答案不构成盲测，模型别名不构成不可变版本锁，费用估算不构成实际账单。

历史记录的优先关系：

- [JP-01 共同计划](../docs/planning/v0.2/java-python-parallel-plan.md)已记录采用 V0.2 新基线，不再等待 V1.1 才能开发；旧 V1.1 兼容性仍未验证。
- [B 执行记录](agent-b-progress.md)开头的 java 分支、无服务、网络阻断、pypdf 尚为候选均是早期事实，读取时应继续看后续追加及修复段落。
- [首次 JP-01 交付包](python-jp01-delivery.md)的 draft.2/33 项/5 项联调是历史结果；当前使用 [Q 修复包](python-q-review-fixes.md)的 draft.4/65 项/8 项结果。
- 本 Python 基线的 `docs/tasks/java-python-integration.md` 仍写 BLOCKED_CONTRACT_VERSION；读取 `origin/java@894fc76` 的同路径已记录 DEV_PASS_Q_REVIEW_PENDING。B 不改 A 的中央记录，也不能把旧阻断继续当当前结论。
- Windows `services/api/mvnw.cmd` 存在已知 CRLF 属性问题。本次切分支出现换行差异后，已将原始字节与 HEAD blob 核对并恢复一致，只在本机 `.git/info/attributes` 对该路径设置 `-text`；未改源码、索引或提交。后续遇到类似情况先核对真实字节，不隐藏真实修改。

## 10. 并行计划第一批续作

用户粘贴的计划要求每线完成 12 项；当前只完成 Python 第一批中不依赖新契约的 B02 和 B03。提交和证据如下：

| 子任务 | 提交 | 结果 |
|---|---|---|
| B02 / KF2-017 | `338c6329742273f01eae8f9ac2956367c9d82f60` | 默认 800/100 的分段及定位；11 项定向测试通过；原种子答案证据仍可从 Chunk 切片核对 |
| B03 / KF2-018 | `0e079e92280e8370e5914d06dd88ebc7da1ed979` | SiliconFlow 适配器和错误/限速/超时/向量回归；真实合成请求返回 1024 维，使用 26 prompt tokens |
| Python 汇总验证 | `0e079e9` | 全套 100 项 Python 测试通过；契约 54、模型离线 16、种子题 15 全部通过 |

真实模型证据：[embedding-live-20261030-b03.json](../services/ai/docs/evidence/embedding-live-20261030-b03.json)。只记录状态、响应模型、维度、token 用量、耗时和代码哈希；实际成本未知。

### 等待的交接依赖

- 远端 Java 当前仍为 `894fc763b3c19a51225365f749e07cc033a4db34`；尚无计划要求的 draft.5 契约提交。B01 待 A02 发布的精确 SHA/Schema 哈希后更新消费者。
- 源文件读取、索引批次、完成和取消接口尚未由 A 发布；B04/B05/B06 按计划等待契约定义后接入，B 不写第二份共享 Schema 或猜测接口形状。
- 受控写入、完整性验收和活动版本发布在 A。Python 当前没有数据库写权限，不能把本地 fake/mock 通过称作真实索引集成。
- Q 最新复审残留的注册 `Content-Type: text/plain` 应返回 415 却返回 500 属 A 的缺陷；B02/B03 自身仍待 Q 按新 SHA 审阅。

下一步：在 A 发布 draft.5 后完成 B01；随后按计划的第二批实现 B04/B05/B06 和 B07，使用双方实际 Java 接口进行联调。第三批 B08–B12 需要索引发布、删除/取消链路和真实评测依赖逐项到位。任务状态继续按代码 SHA、Q 审阅和开发/真实集成证据分别记录。
