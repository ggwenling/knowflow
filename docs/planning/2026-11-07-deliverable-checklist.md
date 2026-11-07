# KnowFlow 可交付清单（2026-11-07）

性质：只读盘点，不改代码、不改评测产物；本清单与两份签收包作为一次文档提交入库。依据仓库内规划/验收文档，以及 2026-11-07 基于 `9907aca` 的 development/holdout 产物（`eval-out/seed-v2-dev-9907aca/`、`eval-out/seed-v2-holdout-9907aca/`）；`0.2.0`（`2a7e68a`）与 `40f4b838` 两卷作为历史。事实不足处标“待核实”，不推测填写。

## 0. 盘点快照（2026-11-07）

- `local`、`origin/local`、`origin/main` 当前均指向 `d2b3ff1`（`9907aca` 之后新增采集器 locator 审计 sidecar）；`main` 已合并到交付分支，但其推送绕过了 PR 规则。
- 契约已冻结为 `0.2.0`（`2a7e68a`，Schema SHA-256 `a206d3aa…`）；许可文件已落地（`d5abfe2`，Apache-2.0，版权主体待确认）。
- 发布工程三项已在本机验证：不可变 tag `05fbd6e51e` 已推送本地 registry（api/web/ai 三 digest 已记录）、重复发布被拒；Flyway 备份/恢复隔离实测 v2→v8→v2→v8 通过；egress 非白名单 403、无代理 DNS 失败；端到端冒烟 PASS（`/health/ready` 三项 UP、可答 1 引用、不可答拒答、整轮 5.2s）。
- 评测基线更新为 `9907aca`：development 与 holdout 两卷八项全过（dev 31 answered / 9 refused、47 citations；holdout 18 answered / 2 refused、28 citations）。`d2b3ff1` 仅新增 locator 审计 sidecar，不在评测 `code_sha` 内、不参与打分；私有盲测仍绑定 `40f4b838`。
- 工作树有未提交改动：5 个跟踪文件被修改（`.github/workflows/web-e2e.yml`、`README.md`、`infra/README.md`、`infra/compose.yml`、`scripts/e2e-web.mjs`）；未跟踪 `apps/web-v2/`、`infra/compose.legacy-web.yml`、`eval-out/`（按约束不入库）。
- 状态图例：`已完成` / `部分完成` / `未开始` / `无证据` / `待核实`。

## 1. 代码收口

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 修复提交已进入评测绑定 | 部分完成 | `eval-out/seed-v2-dev-9907aca/run-metadata.json`、`eval-out/seed-v2-holdout-9907aca/run-metadata.json`（`code_sha=9907aca`） | `9907aca` 已覆盖此前修复；仅 `d2b3ff1`（locator sidecar）不在 `code_sha` 内；各提交仍无独立审阅记录 | B（评测）/ Q（审阅） |
| [ ] | 所有修复提交已推送到远端开发分支 | 已完成 | `git rev-list --left-right --count origin/local...HEAD`（0/0） | 远端 CI 结论仍待核实（见 CI 行） | A/M |
| [ ] | 开发分支合并到 `main` | 已完成（机制合规待补） | `origin/main`、`origin/local`、`HEAD` 均为 `d2b3ff1` | 合并已发生，但本轮说明 `main` 推送绕过 PR 规则；需补合规记录或事后审批 | 项目负责人 + A |
| [ ] | `main` 推送遵守 PR/分支保护规则 | 未完成 | 本轮说明：推送绕过 PR 规则；仓库内无 PR 审批/分支保护变更记录（待核实） | PR 审批证据、分支保护例外授权、审计说明 | 项目负责人 + A |
| [ ] | 共享契约冻结 | 已完成 | `contracts/README.md`（FROZEN 0.2.0，Schema SHA-256 `a206d3aa…`）；提交 `2a7e68a` | 冻结本身已完成；剩余为三端完整消费/负责人签收 | A + 项目负责人 |
| [ ] | Java/Python 两侧完整消费签收 | 未完成 | `contracts/consumer-draft10-checklist.md` 状态：工程证据 APPROVED，完整消费/负责人签收 IN_REVIEW；`docs/reviews/2026-11-03-sol-cd68d7f.md` | 针对冻结版 `0.2.0` 的完整消费签收（版本/授权/租约/幂等/删除竞态/来源语义） | A、B，项目负责人签字 |
| [ ] | M 侧消费签收 | 未完成 | 同上清单 “M / 前端与项目负责人” 三项未勾选 | 人工浏览器验收记录（见 2.5） | M + 项目负责人 |
| [ ] | 当前目标 SHA 的 CI 三/四 job 全绿 | 待核实 | `.github/workflows/web-e2e.yml`；历史 run `41630396504`（`cd68d7f`） | `9907aca` / `d2b3ff1` 的 CI run 链接与结论未在仓库内留存 | M/A |
| [ ] | 工作树干净且产物不入库 | 未完成 | `git status --porcelain`：5 个跟踪文件有修改（CI、README、infra/compose、infra/README、e2e 脚本，后者为 web-v2 试验且未参与发布构建）；未跟踪 `apps/web-v2/`、`infra/compose.legacy-web.yml`、`eval-out/` | 未提交改动需收口或说明；`eval-out/` 按约束不入库 | M + 项目负责人 |

## 2. 质量证据

### 2.1 development 分卷（`9907aca`）

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | development 40 题运行完成 | 已完成 | `eval-out/seed-v2-dev-9907aca/metrics.json`、`predictions.json`、`run-metadata.json` | — | — |
| [ ] | development 通过正式门禁 | 已完成（机器判定，八项全过） | `eval-out/seed-v2-dev-9907aca/metrics.json`（`quality_gate.status=passed`）；门槛配置同目录 `gate.json`（gate v2） | 该通过依赖 `review.json`：同目录 `metrics-noreview.json` 为未审阅口径 | — |
| [ ] | 支持度/引用审阅由真人签收 | 未完成 | 同目录 `review.json`：31 条 answered 的 `reviewed_by` 均为 `agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`；9 条 refused 未审 | 真人审核者身份、逐条复核、签收日期；当前为 agent 审核 | 项目负责人指定的人工审核者 |
| [ ] | 该次运行有正式报告并独立审阅 | 无证据 | 仓库 `docs/evaluation/` 未见 2026-11-07 9907aca 报告；`docs/acceptance/2026-11-07-quality-sampling-signoff.md` 已按 9907aca 更新（同批文档提交） | 报告文档、聚合资产、独立审阅记录 | B + Q |
| [ ] | 引用粒度修复后的评测覆盖 | 部分完成（仅审计） | 两卷目录下的 `citation-locators.json`：dev 33 条、holdout 21 条，句级区间；`run-metadata.json` 仍 `code_sha=9907aca` | 附件不参与打分、指标不受影响；仍需真人抽检 locator 与正文一致性并签收 | B（评测）/ Q（审阅） |
| [ ] | MRR@10 分母口径修正可追溯 | 已完成（说明） | `9907aca` 修正 MRR 分母口径；本轮该类题为 0，历史数值不变；dev `MRR@10=0.9785`、holdout `MRR@10=1.0` | 如后续题集含该类题，需在报告中单独披露分母口径 | B + Q |

指标摘要（来自上述 metrics）：dev Recall@5 1.0、MRR@10 0.9785、answerable answer 1.0、unanswerable refusal 1.0、support 1.0、citation 1.0、citation review coverage 1.0、47 citations、0 执行错误；延迟 p50 1688 ms、p95 2062 ms。

### 2.2 holdout 分卷

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 当前基线代码上的 holdout 20 题运行 | 已完成 | `eval-out/seed-v2-holdout-9907aca/run-metadata.json`（`code_sha=9907aca`）、`metrics.json`、`review.json`；`quality_gate.status=passed`（八项全过） | 18 answered / 2 refused、28 citations、0 执行错误、answerable 答出率 0.9474、holdout MRR@10=1.0；审阅仍为 agent | B（补充报告）/ 项目负责人指定的人工审核者 |
| [ ] | 历史公开 holdout 结果可追溯 | 部分完成 | `docs/evaluation/assets-real-20261104-holdout-metrics.json`（20 题，gate passed）；报告 `docs/evaluation/2026-11-04-rag-real-public-seed-v2.md`（绑定 `d5e1eb7`） | 资产本身未写 `code_sha`；不覆盖当前 HEAD；不是私有盲测 | B |

### 2.3 私有盲测

代码—证据对应：盲测结论仍绑定 `40f4b838`，未随 `9907aca` 两卷重跑而更新；两卷为公开集评测，不等于盲测通过。`9907aca` 已覆盖 `4f59d3c`（引用粒度）与 `42d3b3d`；`d2b3ff1` 仅新增 locator 审计附件，不参与打分。

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 私有盲测已执行 | 部分完成 | `docs/evaluation/2026-11-05-box-blind-20-v5.md`；`docs/evaluation/assets-box-blind-20261105-v5-judged-summary.json` | 最新 v5 质量门 **failed**：answerable answer 0.800（12/15），3 道误拒答 | 项目负责人 + 独立评测者 |
| [ ] | 私有盲测通过质量门 | 未完成 | 同上；`docs/reviews/2026-11-05-sol-blind-v5-docs.md`（仅批准文档，明确门禁 failed） | 新独立题集（协议要求失败后不得在同集反复调参）、通过的门禁、评分与预算证据 | 项目负责人 + 独立评分者 |
| [ ] | 盲测包由仓库外受控保管 | 部分完成 | `docs/evaluation/blind-holdout-protocol.md`；`docs/evaluation/windows-blind-eval-runbook.md` | 本任务未查看 `.blindtest/` 内容；承诺文件、SHA-256、保管记录的真实性待核实 | 项目负责人 |

### 2.4 真人支持度/引用审阅

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 公开集答案支持与逐引用真人审阅 | 未完成 | 2026-11-04 报告称审核者为 `know-bot-public-seed-reviewer`；9907aca 两卷 `review.json` 均为 agent；`docs/acceptance/2026-11-07-quality-sampling-signoff.md` 已按 9907aca 更新，签字栏为空（同批文档提交） | 真人审核者、逐条记录、签收日期；agent 审核不能替代 | 项目负责人指定的人工审核者 |
| [ ] | 数据集本身的真人标注可追溯 | 部分完成 | `docs/evaluation/human-review-v2.md`；60 题 `human-reviewer` 确认记录（见计划文档） | 该确认是题目标注，不等于对生成答案/引用的签收 | 项目负责人 |

### 2.5 M 侧浏览器人工验收

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | M 人工浏览器验收（注册、隔离、上传、READY、重建、分页） | 无证据 | 自动化证据：`docs/reviews/2026-11-03-sse-consumption.md`；`deploy/PRODUCTION-CHECKLIST.md` G5 未勾选 | 人工执行记录：执行者、浏览器/环境、日期、截图/录像、逐项结果 | M + 项目负责人 |
| [ ] | M 人工浏览器验收（流式问答、取消、历史、来源失效、移动/键盘） | 无证据 | 同上；`contracts/consumer-draft10-checklist.md` 未勾选项 | 同上 | M + 项目负责人 |

## 3. 预算与价格

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | PRICE 文件负责人签核 | 未完成 | 当前账本 `price_quote.verified_by="agent:TRAE (auto-verified from official pricing page, human confirmation pending)"`；`docs/acceptance/2026-11-07-price-budget-signoff.md` 已按新证据更新、签字栏为空（同批文档提交）；`.blindtest/config/PRICE_FILE.json` 存在（本任务未读取内容） | 负责人签字、签核日期、文件 SHA-256、适用范围；账本仍记录 human confirmation pending | 项目负责人 + 财务/采购 |
| [ ] | POLICY 文件负责人签核 | 未完成 | 同上，`POLICY_FILE.json`；价格包未签；`deploy/PRODUCTION-CHECKLIST.md` G0-4 未通过 | 软/硬预算政策文本、负责人批准、Sol 复核 | 项目负责人 + 财务 + Q |
| [ ] | 评测配置哈希可追溯 | 待核实 | `eval-out/seed-v2-dev-9907aca/run-metadata.json`、`eval-out/seed-v2-holdout-9907aca/run-metadata.json`（`config_sha256=20af54a4…`）；价格包列出各次 run 的配置哈希 | 该哈希对应的 PRICE/POLICY 文件签名、`verified_by`、与 11-04 差异原因 | B + 项目负责人 |
| [ ] | 真实花费已核算 | 部分完成 | `eval-out/seed-v2-dev-9907aca/budget-ledger.sqlite3`：累计 limit 10,000,000 microyuan；paid 323 笔、reserved 3,307,520 microyuan（**3.30752 CNY**）；zero-price 431 笔；超软目标 1.30752。原因：为覆盖引用粒度修复补跑一轮；另有 provider 故障窗口导致的一批作废采集中途终止（`eval-out/seed-v2-dev-42d3b3d/`、`eval-out/seed-v2-holdout-42d3b3d/` 无 metrics，未计入结论） | 供应商账单/发票、实际计费与预留差异、汇率/税费口径；超软目标 1.30752 的追认 | 财务/采购 + 项目负责人 |
| [ ] | 与供应商账单核对 | 无证据 | 账本 `eval-out/seed-v2-dev-9907aca/budget-ledger.sqlite3`；价格包明确“供应商控制台账单仍待财务核对”；历史 11-04 花费用 `docs/evaluation/2026-11-04-rag-real-public-seed-v2.md` | 供应商后台账单导出、对账记录、差异说明 | 财务/采购 |
| [ ] | 预算上限机制有效 | 部分完成 | `services/ai/src/knowflow_ai/budget.py`；账本 hard limit 10 CNY；项目软性上限 2.00 CNY 已超出；`docs/acceptance/2026-11-07-price-budget-signoff.md` | 供应商侧硬支出上限或超额拒绝证据；11-05 曾出现预留增长至 2.684 CNY 的闲置进程事件（`docs/evaluation/2026-11-05-blind-rounds-summary.md`） | 项目负责人 + 财务 + Sol |

## 4. 安全与运维

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 密钥轮换/撤销完成 | 未完成 / 待核实 | `docs/reviews/2026-11-03-license-log-redaction-audit.md` B4；`.context/ai-handoff.md` Open questions；当前受跟踪文件密钥模式扫描 0 命中 | 供应商后台撤销/轮换记录、执行日期、新密钥注入与旧密钥失效验证 | 项目负责人 + 供应商管理员 |
| [ ] | 生产等价环境部署 | 已完成（限定范围） | `docs/operations/2026-11-07-deployment-gap-remediation.md` §12.3、§13.5（生产形态栈、HTTPS 入口、隔离、不可变 tag 拉取启动，G1–G8 通过）；端到端冒烟 PASS 5.2s | 本机单机栈已闭环；生产待承接：registry 认证/TLS/tag 不可变策略、云侧安全组、代理 HA 与日志留存、异地备份 PITR/RPO/RTO、发布流水线审批 | M/运维 + 项目负责人 |
| [ ] | 升级失败回滚演练 | 已完成（镜像层 + Flyway 备份/恢复） | `docs/operations/2026-11-07-production-deploy-rollback-drill.md`：回滚到 `d5abfe2`，40.6 s；§13.2/§13.5：隔离库 v2→v8→v2→v8、备份 SHA-256 与租约计数一致 | 异地备份、PITR、RPO/RTO 与定期恢复抽检；正式环境发布流水线审批 | M/运维 |
| [ ] | 日志脱敏（代码层） | 已完成（限定范围） | `docs/reviews/2026-11-03-license-log-redaction-audit.md` B2；`docs/reviews/issue-14-log-redaction-audit-25c8dc3.md` | 生产日志抽样、第三方/框架/反代日志、容器日志轮转与保留策略（审计 R1/R2/R5） | 运维 + M |
| [ ] | 限流 | 部分完成 | Java/Python 问答并发上限（默认 4，可配置，见计划文档）；`contracts/README.md` 关于注册 409 邮箱冲突的说明 | 边缘/网关限流、注册枚举防护、生产参数压测与配置证据 | A/M + 运维 |
| [ ] | 告警 | 无证据 | 仓库未见监控/告警配置；`deploy/PRODUCTION-CHECKLIST.md` G6 未勾选 | 错误率、延迟、磁盘、队列积压、预算异常的告警渠道与阈值 | 运维 |
| [ ] | 备份恢复 | 已完成（限定范围） | `infra/evidence/backup-restore-20261103-final-bb25dc1.json`；`docs/operations/2026-11-07-deployment-gap-remediation.md` §12.2、§13.2（生产等价栈 DB 备份/恢复、隔离库 v2→v8→v2→v8）；`docs/operations/backup-restore-acceptance.md` | 异地副本、保留期、PITR、RPO/RTO、定期恢复抽检与真实硬件故障恢复 | M/运维 + 项目负责人 |
| [ ] | 清理与资源边界 | 部分完成 | `docs/acceptance/recovery.md`；`services/ai/docs/evidence/recovery-e2e-draft10-2026-11-03-final-bb25dc1-attempt2.json` | Linux 解析资源边界、生产容量、长期运行泄漏验证 | B + 运维 |

## 5. 产品验证

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 真实研发用户试用（3–5 人） | 未开始 | `docs/product/pilot-protocol.md`（IN_REVIEW，明确未招募） | 招募、知情同意、对照记录、访谈记录、异常记录 | 项目负责人 |
| [ ] | 耗时指标（真人） | 无证据 | 仅有 9907aca 工程延迟 p50 1688 ms / p95 2062 ms（`eval-out/seed-v2-dev-9907aca/metrics.json`），非用户研究 | 逐任务定位/核验耗时、超时样本、方法对照 | 项目负责人 |
| [ ] | 满意度/复用指标 | 无证据 | `docs/product/pilot-protocol.md` 中的记录模板为空；两周复用“未验证” | 满意度记录、两周主动复用天数与任务数、退出原因 | 项目负责人 |
| [ ] | 试用后修复与复测闭环 | 无证据 | — | 问题清单、修复提交、复测结果 | 产品 + A/B/M |

## 6. 许可与发行

| 勾选 | 条目 | 当前状态 | 已有证据路径 | 缺什么 | 需要谁出面 |
|---|---|---|---|---|---|
| [ ] | 项目自身许可证 | 已完成（版权主体待确认） | `LICENSE`（Apache-2.0，提交 `d5abfe2`）；根 `NOTICE` 声明 Apache-2.0、版权主体“KnowFlow contributors（待确认）” | 确认法人/组织版权主体并同步 `LICENSE`/`NOTICE`；第三方语料声明边界 | 项目负责人 + 法务 |
| [ ] | 根 NOTICE 定稿 | 部分完成 | `NOTICE`（已声明 Apache-2.0 与来源，仍标注版权主体待确认、上游 NOTICE/基础镜像待核实） | 版权主体、上游 NOTICE 汇总、独立审阅、发行签收 | 法务 + 项目负责人 |
| [ ] | 随镜像分发的第三方声明 | 部分完成 | `deploy/THIRD-PARTY-NOTICES.md`（仍为 DRAFT，第 3 节全文未补齐）；`THIRD-PARTY-LICENSES.md`（827 行依赖许可清单，基线 `f2b5c67`） | 许可证全文集合、各组件 NOTICE、镜像内实际分发清单 | M/发行 + 法务 |
| [ ] | 依赖清单与证据 | 部分完成 | `THIRD-PARTY-LICENSES.md`（703 条依赖）；`docs/reviews/2026-11-03-dependency-inventory.json`；`docs/reviews/issue-14-license-audit-25c8dc3.md` | Maven/npm 全量 SBOM、容器镜像层与 Linux native 证据、许可证 CI 门禁 | B/M + 法务 |
| [ ] | 发行证据 | 已完成（本机验证） | `docs/operations/2026-11-07-deployment-gap-remediation.md` §13.1、§13.4、§13.5：tag `05fbd6e51e`、api/web/ai 三 digest、重复发布 exit 1、拉取后 digest 一致、冒烟 PASS 5.2s；清单 `D:\konwflow-prod-drill\releases\release-05fbd6e51e.json` | 生产待承接：registry 认证/TLS、仓库级不可变策略、发布流水线审批；发布说明、签名/校验和与可复现构建记录 | M/发行 + 项目负责人 |
| [ ] | 发行合规签收 | 未完成 | 根 `NOTICE` 明确“待独立审阅及负责人发行签收” | 法务/负责人书面签收 | 项目负责人 + 法务 |

## 7. 总体判断

当前不具备“可交付”条件，主要阻断项按优先级：

1. **质量门部分闭环**：`9907aca` 上 development 与 holdout 两卷八项全过（47 / 28 citations，holdout answerable 0.9474、MRR@10 1.0），引用 locator sidecar 已作为审计证据（dev 33 / holdout 21，不参与打分）；但最新私有盲测 v5 的 answerable answer 0.800 失败且仍绑定 `40f4b838`；所有审阅仍为 agent 而非真人。
2. **代码/契约部分收口**：提交均已推送、`main` 已合并、契约已冻结为 0.2.0；但 `main` 推送绕过 PR 规则，三端完整消费签收仍未完成，且除 `d2b3ff1`（仅审计附件）外各提交仍无独立审阅记录。
3. **签核缺失**：PRICE/POLICY、答案支持/引用审阅、M 浏览器人工验收均无负责人签字（两份 2026-11-07 签核包签字栏为空）。
4. **预算证据不足**：本地账本累计预留 3.30752 CNY，超软目标 1.30752；原因为引用粒度补跑一轮，以及 provider 故障窗口导致的作废采集中途终止（未计入结论）；仍没有供应商账单对账，也没有供应商侧硬上限。
5. **运维部分验证**：本机生产等价栈的部署、镜像回滚、Flyway 备份/恢复（v2→v8→v2→v8）、egress 拦截与端到端冒烟均已完成；剩余必须由生产环境承接：registry 认证/TLS/tag 不可变策略、云侧安全组、代理 HA 与日志留存、异地备份 PITR/RPO/RTO、发布流水线审批；告警仍无证据。
6. **产品未验证**：无真实用户试用、无真人耗时/满意度/复用数据。
7. **发行工程本机已闭环，生产承接未完成**：Apache-2.0 LICENSE 已落地（版权主体待确认）、NOTICE 已更新；不可变 tag `05fbd6e51e` 与三 digest、重复发布拒绝、Flyway 备份/恢复、egress 拦截、冒烟均已验证；剩余为生产 registry 认证/TLS/不可变策略、发布流水线审批，以及第三方许可证全文、SBOM、发布说明/签名/校验和。

## 8. 待核实清单

- [ ] `9907aca`、`d2b3ff1` 的 CI 结果与是否有独立审阅文件。
- [ ] `main` 绕过 PR 规则是否有书面例外授权、事后审批或审计记录。
- [ ] `.blindtest/config/SIGNOFF.md` 是否为有效的 PRICE/POLICY 负责人签核（本任务未读取该私有目录内容）。
- [ ] `run-metadata.json` 的 `config_sha256=20af54a4…` 对应的实际 PRICE/POLICY 文件名与哈希，以及签核包所列哈希是否一致。
- [ ] 供应商后台是否已完成 2026-11-03 审计所提密钥的撤销/轮换。
- [ ] 生产环境承接项：registry 认证/TLS/tag 不可变策略、云侧安全组、代理 HA 与日志留存、异地备份 PITR/RPO/RTO、发布流水线审批。
- [ ] `42d3b3d` 修复后生产等价栈的最终复跑记录（当前冒烟 PASS 5.2s 与 egress 实测结果需确认对应的确切 SHA）。
- [ ] 法人/组织版权主体确认结果，以及 `LICENSE`/`NOTICE` 的同步更新。
- [ ] `4f59d3c` 引用粒度修复在评测集上的实际行为（当前结论未覆盖）。
- [ ] 2026-11-04 holdout 资产的实际 `code_sha`（资产文件未记录，报告称 `d5e1eb7`）。
