# P0 工程收尾与 P1 RAG 验收

状态：IN_PROGRESS。工程候选为 `cd68d7f88d92ee2dd16740b0cf4c7ecc1676cbac`（历史基线位于 `local`；当前开发分支为 `grok`）；Sol 独立工程审阅为 **APPROVED**，依据 [2026-11-03-sol-cd68d7f.md](../../reviews/2026-11-03-sol-cd68d7f.md)。执行、证据范围及待负责人事项见下方最新检查点。较早代码全量验证基线为 `local@bb25dc194fc1aeb3b0c21b7f57d364988308c8ea`；性能证据另绑定 `local@9c9b4a08bbabc4efebd906e7cbd93dc83bb7a6c7`。较早候选 `7967883` 当时已推送并与 `origin/local` 同步；`origin/main@b7e83c8cf475195ac54b7b58a96ba275e44b8625` 未改变。draft.10 schema SHA-256 `20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`。先前约定 Luna 实现、Sol 独立审阅；本次 Luna 服务不可用后由根代理实施，Sol 独立审阅。M/项目负责人签收及真实模型质量验收仍待完成。

## 2026-11-04 真实公开集评测（grok 分支）

- 分支 `grok`；采集时代码 SHA `d5e1eb7f3a0094481a26cb6465ed57537099ee03`。报告：[2026-11-04-rag-real-public-seed-v2.md](../../evaluation/2026-11-04-rag-real-public-seed-v2.md)；聚合 assets：`docs/evaluation/assets-real-20261104-*.json`。当前文档同步时 HEAD 以协调者提交后为准；此前 `de830a8` 的 Web engineering E2E run `41682519659` 为 success。
- 数据集：`qingzhu-seed-v2-reviewed` / `evaluation/data/seed-v2-reviewed`，公开合成集，**非盲测**。development 40 题与 holdout 20 题质量门**全部 passed**：Recall@5 = 1.0；MRR@10 development 0.9785 / holdout 1.0；support、citation、refusal 门均通过，误拒 0。数字以报告表格为准，不另行推算。
- 花费：BudgetLedger 预留 **0.07374 CNY**（73740 microyuan）；paid 60 / zero-price 80；soft 8 / hard 10 未触发。PRICE/POLICY 仍为草稿，`verified_by=draft-not-owner-signed`，**待负责人签核**。
- 明确：公开集满分**不**等于真实水平或正式总体验收；盲测由负责人在 Windows 本机执行，本轮未触碰盲测数据。真实评测启动器修复 `ee359a0` 经 Sol High 复审 APPROVED（[2026-11-04-sol-ee359a0.md](../../reviews/2026-11-04-sol-ee359a0.md)）；盲测 runbook F1–F4 由 Sol 复审 Target `b8a8a60` APPROVED（审阅文件提交于 `de830a8`，[2026-11-04-sol-b8a8a60.md](../../reviews/2026-11-04-sol-b8a8a60.md)），本节不展开 runbook 内容。

## 2026-11-03 独立工程审阅与候选校准

- **APPROVED（工程范围）**：Target 为 `cd68d7f88d92ee2dd16740b0cf4c7ecc1676cbac`，Base 为 `main@b7e83c8cf475195ac54b7b58a96ba275e44b8625`；审核者为独立会话 Sol High。正式依据是 [独立审阅文件](../../reviews/2026-11-03-sol-cd68d7f.md)，不再使用旧候选或口头批准作为当前签审依据。
- 审阅关闭 `25c8dc3` 报告的 R1/R2 及 #14 日志 L1；确认目标 PR CI run `41630396504` 的 python-contract / java / web 全部 success。独立复验 Python 349、Web 69、Java 日志定向 2、Schema 85、OpenAPI 4、离线 smoke 16；保留报告中沙箱首轮失败及复测边界，不把历史恢复／性能证据重新绑定到该 Target。
- `3adc864` 仅提交上述审阅文件；本轮仅同步文档。独立批准绑定的工程候选仍是 `cd68d7f`，不将后续文档提交自动表述为已经 Sol 审阅。
- **待负责人**：完整 Java/Python/M 消费签收、M 浏览器人工签收、真实 RAG 及质量门、预算政策与授权、私有盲测、部署／回滚及试用。消费清单只将有上述证据的限定工程项标为 APPROVED，不代签整体验收；契约保持 draft.10、未冻结，本轮禁止合并 main、部署或付费调用。

## 2026-11-03 SSE 工程收尾（历史证据）

- 历史 SSE 实现基线 `local@a30394a9042383fafaab9e6ca6c71d64f7b5a156` 已推送；当前工程批准以本计划顶部绑定 `cd68d7f` 的独立审阅为准。完成 HTTP/SSE/内部请求 ID 关联、Web 状态机/终态关闭、has_answer 消费及失败清引用；真实 deadline、拒答及幂等冲突补验通过。
- Java84（1skip）、Windows Python341、Web64/typecheck/相关lint、Schema85/OpenAPI4；最终 Docker 浏览器1/1（场景43秒），六类共享Schema捕获及主动停止/历史验证通过，隔离资源清零。首轮抓包失败及最终重跑证据见 `docs/reviews/2026-11-03-sse-consumption.md`。有限SSE工程项完成，正式人工签收独立；候选远端CI在记录时尚未结束。

## 前一轮 SSE 消费补验（历史）

- 当前代码候选 `local@802fe48e7d4c689c224c72273a937ac1c8472d73` 已经 Sol 精确 SHA 审阅 APPROVED 并推送；`main` 未合并。此前文档候选 `65774c4` 也获 Sol 批准，PR CI run #18 三个 job 全绿。代码候选 [PR CI #20](https://github.com/ggwenling/knowflow/actions/runs/41596593798) 三个 job 全绿：Java 84（1 skip）、Linux Python 335 passed（3 skipped）、Web/Docker E2E 1/1（14.3秒）；最终四类 SSE 捕获共享 Schema/顺序及主动停止历史检查通过。
- 修复上游 cancelled 被前端误报为 FAILED；补充真实全栈 synthetic error/cancelled 与主动停止的 UI、历史持久化及不自动重发检查。Python 338 项、Web 46 项、typecheck/相关 lint、Schema 85 项和 OpenAPI 4 项通过。完整验证边界及本地 Docker 网络失败记录见 `docs/reviews/2026-11-03-sse-consumption.md`；Java/Python/M 的正式完整消费签收仍未完成。
- 用户给出 `services/ai/.env.example` 作为预算信息位置；仅检查变量名及是否有值，没有硬 cap 或超额拒绝证明，继续零真实 provider 调用。用户确认新增私有盲测和生产目标环境目前均无更新。

## 2026-11-03 较早检查点（历史证据）

- 本机验证通过（目标代码 `bb25dc1`）：Web typecheck、lint、43 项单测、Docker production Web 镜像构建、Docker 全栈 Chromium E2E 1/1；Java Maven/Testcontainers 83 项（1 项跳过）；AI 324 项；Schema 85 项、OpenAPI 4 项、批次摘要 5 项、离线模型 smoke 16 项。E2E 构建 Web/API/AI/migrate 镜像并检查正常 TXT/PDF 问答的 draft.10 SSE 帧、注册、上传/READY、owner 隔离、删除及 PDF；浏览器通过来源查看键盘操作和移动视口检查。错误/取消 SSE 路径及完整消费语义仍待验收。临时 Compose 容器、网络和卷清理后均为 0。Docker 代理已恢复；远端 CI 尚待推送后确认。
- 合成负载报告 `evaluation/performance/evidence/baseline-cap8-final-20261103-9c9b4a0.json` 绑定 `9c9b4a0`：10/100 文档 × 并发 1/4/8 × 每组 8 个请求，48/48 成功；合成环境 Java API 与 AI 准入上限均为 8。100 文档下首个 SSE delta p95 为 360/485/532 ms，完整回答 p95 为 625/844/1094 ms（并发 1/4/8）。报告有容器资源采样并确认清理。仅证明该 Windows Docker 合成适配器负载，不代表真实 provider 延迟、成本或生产容量。
- 故障恢复报告 `services/ai/docs/evidence/recovery-e2e-draft10-2026-11-03-final-bb25dc1-attempt2.json` 绑定 `bb25dc1`：PostgreSQL 读/索引写中断、MinIO 中断后 ready 与真实 PUT/GET/DELETE canary、第二批 Embedding 失败四项通过；临时数据库和服务端口清理，provider 调用 0。隔离备份恢复报告 `infra/evidence/backup-restore-20261103-final-bb25dc1.json` 同样绑定 `bb25dc1`，数据库/MinIO 恢复、字节一致、历史来源、owner 隔离、恢复后查询及两套 Compose 清理通过，迁移版本 8→8。均未测试生产升级回滚或真实用户环境。
- 当前 collector 已把 request-id 单次检索 trace 与 AnswerService 响应/错误组装为 runner-v2 行，逐次重映射引用标记，并支持经审核来源元数据的 SiliconFlow `BAAI/bge-m3` 零价 embedding 账本记录；`services/ai/tests/test_rag_collection.py` 当前定向测试 25 项通过。（截至 2026-11-03）尚未接通真实评测驱动；真实 provider 调用保持 0；该状态已于 2026-11-04 被 `grok` 上公开合成集真实采集取代，见上节。Sol 的预算审阅不批准启用真实评测：现有输入 token 计数不能证明 ¥10 硬上限；须有供应商级支出上限或由负责人明确批准可接受的软预算策略。
- Java `DocumentApiIntegrationTest` 增加 3 项 MVC wire 回归：可选空 `active_index_version_id` / `failure_code` 不输出，processing 历史和过期来源的 required nullable 字段显式为 JSON `null`。3 个 Testcontainers 方法、OpenAPI 4 项、Schema 85 structural cases 通过。此验证仅覆盖列出的字段与端点，不代表全部公开 JSON 响应或 SSE 消费验收。
- 远端 push workflow [#15](https://github.com/ggwenling/knowflow/actions/runs/41590144065) 在候选 `7967883` 上 4m48s 完成，`python-contract`、Java、Web/Docker E2E 三个 job 均成功。现有 PR [#3](https://github.com/ggwenling/knowflow/pull/3) 的 pull_request workflow [#16](https://github.com/ggwenling/knowflow/actions/runs/41590148290) 在本次记录时仍运行中（python-contract 与 Java 已成功，Web job 未结束）。`main` 尚未更新。
- Sol High 对候选 `79678830b14047aabc41e3cd5f607f564728fb6a` 的代码/契约复核为 APPROVED，无代码阻断；正式 Q/M 仍 CHANGES_REQUESTED，Java/Python 与 M 的消费清单未签、错误/取消 SSE 路径及完整消费语义待完成。
- 项目负责人此前确认尚未准备 20 题私有盲测；不生成、不查看或评分私有题。60 题开发/公开验证集人工审核者为 `human-reviewer`，不能代替新增私有盲测。
- Sol 对 `local@38252b3` 的先前审阅为 CHANGES_REQUESTED，原因是当时完整证据及 M 签收未齐，未指出新增契约代码缺陷。Sol 对 `00147f6` 的正式 Q/M 结论仍为 CHANGES_REQUESTED：代码无剩余 blocker；Java/Python 和 M 的消费签收、远端 CI、错误/取消 SSE 路径及完整消费语义尚缺。该次审阅指出的 OpenAPI null 兼容问题已由本节所列定向运行时测试覆盖；本轮代码/契约变更仍须由 Sol 在新最终 SHA 复核。M 签收仍待项目负责人。

## P0

- [x] 本地实际构建 Docker Web/API/AI/migrate 镜像并通过 Playwright Chromium 全栈 E2E 1/1；Web、Java、Python、Schema、OpenAPI 检查结果见上方当前检查点。
- [x] **APPROVED（目标 CI 工程证据）**：候选 `cd68d7f` 已推送；Sol 审阅核对该 Target 的 PR run `41630396504`，python-contract / java / web 三个 job 全绿。后续文档提交的 CI 单独核验，不改绑历史运行。
- [x] **APPROVED（独立工程审阅）**：Sol 对候选 `cd68d7f` 的工程范围给出 APPROVED；依据 `docs/reviews/2026-11-03-sol-cd68d7f.md`，旧 R1/R2 和日志 L1 均关闭。
- [x] 完成本轮 SSE 有限工程收尾：正常/拒答/错误/取消/真实 deadline/主动停止与历史、ID关联和Web生命周期回归；精确代码及证据见最新检查点。
- [ ] **待负责人**：在工程候选 `cd68d7f` 上完成 Java/Python 完整消费及 M 浏览器人工签收，再组织正式总体验收；当前 Sol 工程 APPROVED 不代签这些事项。PR #3 合并到 main 前仍须项目负责人签收。

## P1

- [x] 用户确认逐题审核现有 60 题，审核者 `human-reviewer`；保留公开 40/20 开发/验证划分，不声称双人人工一致性。
- [ ] **待负责人**：用户私下保管新增 20 道盲测题（15 道可回答、5 道不可回答），使用新合成资料和事实组；冻结候选后独立运行。
- [x] 公开集真实采集与质量门（合成）：`qingzhu-seed-v2-reviewed` 的 development+holdout 已在 `grok` 上完成真实采集并通过质量门，见 [2026-11-04 报告](../../evaluation/2026-11-04-rag-real-public-seed-v2.md)；仅代表公开合成集，不等于私有盲测或正式总体验收。
- [ ] **待负责人**：接通 Java 授权写入/索引/问答与真实 provider 的完整预测采集，保存前 10 名检索记录，完成人工答案支持和逐引用审核、错误/拒答区分及正式质量门；私有盲测 / 正式总体验收 / 价格政策签核仍待负责人。私有答案和盲测题不提交仓库。
- [x] 公开合成集质量门核验（合成）：development 40 / holdout 20 的门槛全部 passed，数字见上述 2026-11-04 报告；不代替盲测或负责人签收。
- [ ] **待负责人**：私有盲测与正式总体验收的真实质量门核验，门槛为 Recall@5 ≥ 0.85、MRR@10 ≥ 0.75、答案支持率 ≥ 0.90、引用准确率 ≥ 0.95、不可回答题拒答率 ≥ 0.90、可回答题误拒答率 ≤ 0.10、人工审核覆盖率 100%。记录分子、分母和分类结果。
- [x] 本轮公开合成集已发生真实调用，BudgetLedger 预留约 **0.074 CNY**（0.07374，73740 microyuan）；soft 8 / hard 10 未触发，按草稿 PRICE/POLICY 保守预留。
- [ ] **待负责人**：真实模型调用总预算人民币 10 元，覆盖索引、问答、重试和在途请求；需有可核验的供应商侧硬支出上限及超额拒绝证据，或经负责人批准的软预算政策，并由 Sol 复核。仅本地 token 估算不构成硬上限。**软预算政策与 PRICE/POLICY 正式签核仍待负责人；不得声称 hard cap 已签收。**
- [x] 在 `bb25dc1` 隔离恢复 E2E 中验证 PostgreSQL 读/写中断、MinIO ready+写入 canary 和第二批 Embedding 失败；恢复报告见当前检查点。
- [x] 在 `9c9b4a0` 完成 10/100 文档、并发 1/4/8 的合成负载测量。
- [ ] **待负责人**：测量真实 provider 的延迟与成本；先解决预算门禁。
- [ ] **待负责人**：验证 Linux 解析资源边界与依赖许可；完成数据出站说明、日志脱敏及生产故障排查核对。
- [ ] **待负责人**：在隔离环境完成干净部署、升级失败回滚和数据库/对象备份恢复；当前恢复报告不是生产部署或数据库降级证明。生产目标环境确定后单独验收。

## P2

- [ ] **待负责人**：由项目负责人组织至少两周真实用户试用，记录样本量、问题、修复和复测；当前尚无试用证据。可与工程 PR 分开验收。

## 当前验证与阻塞

- 历史故障定位：并发 8 曾在默认准入上限 4 时各 4/8 成功；Java QuestionService 会在 AI 请求前拒绝超额请求。诊断见 `evaluation/performance/evidence/diagnostic-concurrency8-repro-20261103.json`。随后合成 runner 同时将 API 与 AI 的测试上限设为 8，当前 9c9b4a0 报告 48/48 成功；生产默认值未改。
- evaluation/performance/run.py 现按目标并发上限为 synthetic Compose 的 Java API 和 AI 同时设置 KNOWFLOW_QUESTION_MAX_CONCURRENT，并在报告写明两个服务及上限；生产默认值未改。只提高 AI 上限的中间报告 baseline-cap8-20261103.json 仍为 4/8，保留为失败证据。
- 2026-11-03 最新 cap=8 报告为 `evaluation/performance/evidence/baseline-cap8-final-20261103-9c9b4a0.json`，绑定 `9c9b4a0` runner 和 Compose 输入，48/48 成功；旧 `baseline-cap8-current-20261103.json` 为较早的 `38252b3` 快照，不是当前报告。

- 历史记录（2026-11-02）：Web typecheck、lint、36 项单测及离线模型回归 16 项通过；schema 85 项结构校验通过，不能替代运行时授权检查。当前计数见本节开头 2026-11-03 检查点。
- 2026-11-02 Docker 构建及全栈浏览器 E2E 通过，测试使用合成 AI；隔离容器、网络和卷已清理。Java 全量 83 项（1 skip）通过。远端 CI 结果尚待核实。
- 评测命令在显式质量门失败或不完整时返回非零；对应三种状态回归通过。该改动不代表真实数据集或质量验收已完成。
- 60 题人工审核数据集 `qingzhu-seed-v2-reviewed` 原指纹 `4ce66d29dca63b366c01e6aab9573dbd61295207e12cd5a766fb25a907ee94c3`；补充来源后的指纹为 `023f14ba9e56df87cb2ea635638e01d3a543a4aeb2588856dc2c3aed7f8356b0`。40 道开发、20 道公开验证，50 道可回答、10 道不可回答；原 agent 的未来时间戳未核实，人工记录时间为用户确认时间。后续质量门须绑定新指纹。
- 60 题的人工审核已由用户确认；独立 Q/M 签收、私有盲测、生成答案人工审核及真实 provider 质量和费用尚待完成。
- Sol High 对 `b7e83c8` 的 Q 审阅为 CHANGES_REQUESTED；代理请求体超限与超时修复 `c075c0f`、来源修复 `4860ecf` 已获限定范围复审通过。分页修复 `24ab858` 待独立复审，完整 Q/M 签收和 OpenAPI 未完成。
- 2026-11-02 本轮 Python 全量 275 项、Web 全量 43 项、lint/typecheck/build 及分页竞态修复后隔离 Docker E2E 1/1 通过；以上为本地工作树验证，远端 CI 结果尚待核实。
- Sol 对第二批 Embedding 失败演练提出候选索引物理清理证据缺口；`79a400d` 补充活动知识库内的 FAILED、cleaned_at、零 Chunk/embedding 及旧索引可查询断言，五场景隔离演练通过，Sol 限定复审通过。数据库/MinIO 中断及负载测试仍未完成。
- Sol 对分页刷新竞态 `f551a68` 与离线评分 v2 引用标记覆盖缺陷修复 `c19d03f` 限定复审通过；真实预测采集及正式评分仍未完成。
- 项目负责人确认尚未准备 20 题私有盲测；准备和隔离要求见 `docs/evaluation/blind-holdout-protocol.md`。Sol High 的真实采集与评分设计见 `docs/evaluation/real-collection-design.md`，真实采集和正式质量验收仍未完成。
- draft.10 OpenAPI 候选 `d1ed60c` 经 Sol 限定范围抽查通过，公开 SSE 实际 wire/null、完整错误码与 M 签收仍待验证，候选未冻结。预算账本连接关闭修复 `a2bc020` 经 Sol 限定复核通过；账本尚未接到真实 provider。
- `379b838` 使用专属隔离环境演练 PostgreSQL/MinIO 读取中断与恢复，原文逐字节一致、原活动索引保留；尚未覆盖索引写入期间中断。`7c4bef8` 增加单次 top-10 捕获并向生成器提供前 5 的组件，但未接入真实 Java 采集或 provider 预算，均待 Sol 复核。
- Sol 对 `379b838` 限定复核通过；`7c4bef8` 发现 trace 二次写入及 locator 附带正文缺口，`3b8784d` 修复后限定复核通过。预算守卫尚未接入服务，真实采集和全局硬预算仍未完成。
- 远端 [CI run 41430594011](https://github.com/ggwenling/knowflow/actions/runs/41430594011) 的 Web 全栈、Java、Python/契约三项均成功，目标为 `e9f115f`；更新提交必须分别确认 CI。
- PostgreSQL 在已确认首批写入后中断的隔离演练 `b776bab`：成功报告 fencing 1→3、旧批次/完成回调拒绝、旧候选已物理清理、新索引可查询；Sol 限定复审通过。此前失败报告保留。该场景重放已接收批次，不能代表新批次事务中途断连或 MinIO 写入故障。
- 隔离合成负载 `baseline-2-20261102.json` 对 10/100 文档、并发 1/4/8 每组 8 请求进行了测量；并发 1 和 4 均为 8/8 成功，并发 8 各有 4 次成功和 4 次可重试 `AI_PROCESSING_FAILED`。该错误码不能单独证明是准入拒绝，整体状态为 `completed_with_errors`，性能验收未通过；真实 provider 调用 0。
