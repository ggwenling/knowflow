# 0.2.0 三端消费确认（契约已冻结）

状态：**工程证据项 APPROVED；完整消费／负责人签收 IN_REVIEW，待负责人；契约已冻结为 `0.2.0`（2026-11-07）**。工程候选：`cd68d7f88d92ee2dd16740b0cf4c7ecc1676cbac`。当前共享 Schema SHA-256：`a206d3aa00f4a932b4ea0d871e73350d9000b51cffcdba90008ac0da5999b4b1`。独立依据：[Sol 工程审阅](../docs/reviews/2026-11-03-sol-cd68d7f.md)，Base `b7e83c8cf475195ac54b7b58a96ba275e44b8625`、Target 如上、Verdict APPROVED。本次仅转录已出具的独立结论，不由文档编辑者自签。勾选只适用于每条写明的工程证据范围，不替代正式三端／M 人工消费签收；历史段落的旧 SHA 和批准叙述不作为当前签收依据。

## 2026-11-03 当前工程证据（人工签收独立）

- Sol 对 `cd68d7f88d92ee2dd16740b0cf4c7ecc1676cbac` 给出 **APPROVED（工程范围）**，详见上述独立审阅的“旧发现处置”“工程与安全核对”“本会话验证”。旧 R1/R2 及 #14 日志 L1 已关闭，无新增未关闭 P0/P1/P2；不表示 #14 全部许可／生产日志工作完成。
- Sol 实际复验：Python 全量沙箱首轮 348 passed / 1 failed，沙箱外复验 **349 passed**；Web **69 passed**、typecheck/lint、Java 日志定向 **2 passed**、Schema **85 structural cases**、OpenAPI **4 passed**、离线 mock/provider smoke **16 passed**。目标 PR run `41630396504` 的 python-contract / java / web 全部 success，包含隔离全栈步骤。完整失败／重跑及已有构建产物边界保留在独立报告中，不编造 Linux 或全 Java 测试计数。
- `3adc864` 是承载独立审阅文件的后续文档提交；当前及后续文档同步不改变被批准的工程 Target，不将其自动表述为已经 Sol 审阅。历史 SSE 抓包记录见 `docs/reviews/2026-11-03-sse-consumption.md`，不把旧恢复／性能报告重绑到当前候选。

## 前一轮 SSE 补验（历史，尚未签收）

- 代码目标 `802fe48e7d4c689c224c72273a937ac1c8472d73`；Sol 精确 SHA 复核 APPROVED。补齐部分输出后的错误、上游取消及用户主动停止，修复取消被显示为失败；详见 `docs/reviews/2026-11-03-sse-consumption.md`。
- 目标代码本地 Python 338 项、Web 46 项、typecheck/相关 lint、Schema 85 项和 OpenAPI 4 项通过。本地中间工作树全栈 E2E 1/1；最终两项测试收紧定向 15 项通过，目标 SHA 本地重跑因镜像仓库网络失败未执行测试。最终目标 [PR CI #20](https://github.com/ggwenling/knowflow/actions/runs/41596593798) 三个 job 全绿：Java 84（1 skip）、Linux Python 335 passed（3 skipped）、Web/Docker E2E 1/1（14.3秒），正常 TXT/PDF、error/cancelled 共享 Schema 与顺序，以及历史/主动停止断言通过。
- 以上补验不替代下方三端完整消费清单及负责人签收；所有正式签收框保持未勾选。

## 2026-11-03 较早本地证据（历史，尚未签收）

- 验证代码基线：`local@bb25dc194fc1aeb3b0c21b7f57d364988308c8ea`；随后 `9c9b4a0` 增加备份证据，未改动代码。Schema 指纹如上。Web typecheck/lint/43 项单测通过，Docker production Web 镜像与全栈 Chromium E2E 1/1 通过；Java Maven/Testcontainers 83 项（1 skip），Python 324 项，Schema 85 项、OpenAPI 4 项通过。
- 浏览器 E2E 覆盖注册、上传至 READY、正常 TXT/PDF 0.2.0 SSE 问答帧及共享 schema、来源查看、owner 隔离、删除和移动视口；错误/取消 SSE 路径及完整消费语义仍未覆盖。这属于本地执行证据，不等于 M/项目负责人已签收。
- Java Testcontainers 新增 3 项实际 MVC wire 断言：Document 的空活动索引 ID 与 QUEUED Task 的空 failure code 确实不输出该键；processing 问答历史及过期来源的 nullable 字段显式输出 JSON `null`。OpenAPI 单测 4 项、Schema 85 structural cases 均通过。覆盖范围仅限这些已命名字段与端点。
- 候选 `79678830b14047aabc41e3cd5f607f564728fb6a` 已推送；push-triggered GitHub Actions run #15 的 `python-contract`、Java、Web/Docker E2E 三个 job 全部成功。PR #3 的重复 pull_request run #16 在本记录时 Web job 仍运行中。Sol High 对该候选的代码/契约复核为 APPROVED，但 Java/Python 与 M 消费者签收、最终 Q/M 结论仍未完成。
- 这些检查未替代 Q 对当前提交的独立代码/契约审阅，也未逐项证明下方所有授权、租约、超时和数据保留断言。因此所有 Q/M 复核框继续保持未勾选，直至审核者在最终目标 SHA 上记录结论、阻断项和日期。
- push-triggered 远端 CI run #15 已在候选 `7967883` 上通过三项 job；PR #3 的 pull_request run #16 在本记录时 Web job 仍运行中。版本化 OpenAPI 候选的测试通过不等于 Q/M 已冻结契约。

## Java / API

- [x] **APPROVED（工程证据登记）**：目标 `cd68d7f`、共享 schema 指纹及目标 PR CI 的 java success 已由 Sol 独立审阅记录；本地定向日志 2 项通过，完整 Java／容器步骤以目标 CI 的实际结果为准。证据：独立报告“本会话验证”。
- [ ] **待负责人**：完成版本不匹配、身份、owner、内部凭证与租约/fencing 的完整消费签收；工程 CI 通过不代签此项。
- [ ] **待负责人**：验证索引批次幂等、过期与重复 worker、删除/发布竞态、候选失败清理及活动索引保留的完整消费确认；历史恢复证据保留原绑定 SHA。
- [x] **APPROVED（限定工程核对）**：Java 请求 ID 关联、公开 JSON wire/null、Web SSE 终态／来源及删除立即失效的实现和已有回归已纳入 Sol 审阅。证据：独立报告“工程与安全核对”。
- [ ] **待负责人**：同步和 SSE 问答、幂等提交、deadline/取消、profile、来源及历史持久化，以及删除／保留期后不泄露原文的完整跨端消费签收。

## Python / AI

- [x] **APPROVED（工程证据登记）**：目标 `cd68d7f`、固定 schema 指纹、Sol 沙箱外 Python **349 passed** 和目标 python-contract CI success 均有独立记录。证据：独立报告“本会话验证”。
- [ ] **待负责人**：版本、结构及 runtime profile 不匹配等完整 Python 消费确认；不由测试汇总代替签收。
- [x] **APPROVED（限定日志工程核对）**：Sol 核对 Python usage 的有限整数白名单、通用异常不输出原文、worker 启动失败清理；不扩展为全部 SDK/debug／生产日志脱敏已验证。证据：独立报告“工程与安全核对”。
- [ ] **待负责人**：来源范围、只读检索、向量维度、分批写入、重试／取消后不迟到写入，以及外部模型错误脱敏的完整消费和环境验收。
- [x] **APPROVED（结构及离线工程证据）**：Sol 复验 Schema 85、OpenAPI 4、离线 mock/provider smoke 16 通过，并核对 SSE 消费实现；不等于真实模型质量或全部运行时授权已验证。
- [ ] **待负责人**：无答案、同步/SSE 答案和来源的完整草案消费，以及 Java 来源映射／失效语义跨服务签收。

## M / 前端与项目负责人

- [x] **APPROVED（自动化工程证据）**：Sol 运行 Web 69 项、typecheck/lint 通过，并核对目标 web CI 的 Check Web、Install browser、Run isolated full stack 全部 success。自动浏览器工程证据不替代 M 人工操作。
- [x] **APPROVED（agent 工程验收）**：gpt-6.1-sol 实际执行 M1 7/7；注册/隔离、MD/PDF 上传与 READY、更新/重建、刷新持久化、文档分页通过。 见 [2026-11-09 签字与证据](../docs/acceptance/2026-11-09-web-v2-agent-acceptance.md)。
- [x] **APPROVED（agent 工程验收）**：gpt-6.1-sol 实际执行 M2 9/9；流式、取消、历史分页、切库/刷新、文本/PDF、来源失效、移动与键盘通过。 见 [2026-11-09 签字与证据](../docs/acceptance/2026-11-09-web-v2-agent-acceptance.md)。
- [x] **APPROVED（agent 工程验收）**：gpt-6.1-sol 实际执行 M3 4/4；本地 synthetic 出站与实际 API 故障/重试通过；浏览器、环境、日期和 agent 签字已记录。 见 [2026-11-09 签字与证据](../docs/acceptance/2026-11-09-web-v2-agent-acceptance.md)。

## Q / 结论

- [x] **APPROVED（独立工程审阅）**：Sol 报告明确 Base `b7e83c8` / Target `cd68d7f`、schema、范围、发现和复验，Verdict APPROVED；原 R1/R2 及日志 L1 已关闭。正式依据：`docs/reviews/2026-11-03-sol-cd68d7f.md`。
- [ ] **待负责人**：组织三端完整消费确认及总体验收；契约已于 2026-11-07 冻结为 `0.2.0`，`local` 已合并进 `main`，三端完整消费签收仍待完成。

## 负责人待办（本次工程 APPROVED 未覆盖）

- [ ] **待负责人**：真实 RAG 采集、逐引用人工审核和正式质量门；公开开发／验证及离线 smoke 不代替真实评测。
  - 2026-11-04 证据注记：公开合成集真实采集与质量门见 `docs/evaluation/2026-11-04-rag-real-public-seed-v2.md`（花费约 0.074 CNY）；**本清单负责人签收框仍保持未勾选**；私有盲测与 PRICE/POLICY 签核独立。
- [ ] **待负责人**：预算硬 cap 或明确获批软预算政策、费用和真实调用授权；2026-11-04 公开集真实调用已发生（见上注），签核前不扩大调用范围。
- [ ] **待负责人**：私有盲测题、资料和答案保管及独立执行，不修改或读取私有题。
- [ ] **待负责人**：部署、升级失败回滚、目标环境备份恢复和真实用户试用。M 浏览器人工签收仍见上方未勾选条目。
