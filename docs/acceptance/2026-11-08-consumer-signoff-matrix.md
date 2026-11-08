# 三端消费签核矩阵（2026-11-08）

状态：**工程证据可引用；完整消费与负责人签收仍待完成**。本矩阵不勾选 `contracts/consumer-draft10-checklist.md`，只把证据与缺口放在一处，便于负责人逐项签收。

## 1. 已具备的工程证据

| 范围 | 证据 | 说明 |
|---|---|---|
| 契约冻结 0.2.0 | `contracts/README.md`；Schema SHA-256 `a206d3aa…` | 冻结本身完成，不等于三端签收 |
| Java 工程审阅 | `docs/reviews/2026-11-03-sol-cd68d7f.md`（Target `cd68d7f`，APPROVED） | 限定工程范围，不替代完整消费签收 |
| Python/契约自动化 | `.github/workflows/web-e2e.yml` 的 `python-contract` job；本地 `contracts/validate.py`、`contracts.test_openapi_draft10` | 需在当前 SHA 重新核对 CI |
| Web v2 自动化 | `apps/web-v2/e2e/*.spec.ts`；本次 16 passed / 1 skipped | 覆盖首页、登录、会话、真实链路、对话流、响应式、a11y |
| Web v2 人工验收材料 | `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md`；`eval-out/acceptance-20261108/manifest.json` | 自动证据已产出，人工签字为空 |
| 引用审阅材料 | `docs/acceptance/2026-11-08-citation-human-review.md`；`eval-out/citation-review-20261108/*.csv` | 工作表已生成；真人未签 |
| 预算审计 | `docs/acceptance/2026-11-08-price-policy-signoff.md`；`eval-out/budget-audit-20261108/*` | 只读汇总；无供应商账单/硬 cap |

## 2. 待签收项

### Java

| 项 | 状态 | 需要的负责人动作 |
|---|---|---|
| 版本不匹配、身份、owner、内部凭证、租约/fencing 的完整消费 | 待负责人 | 按 checklist 逐项签收，不只引用测试通过 |
| 索引批次幂等、过期/重复 worker、删除/发布竞态、候选失败清理、活动索引保留 | 待负责人 | 附证据路径与结论 |
| 同步+SSE 问答、幂等提交、deadline/取消、profile、来源/历史持久化、删除/保留期不泄露原文 | 待负责人 | 跨端逐项签收 |
| 请求 ID 关联、公开 JSON wire/null、SSE 终态/来源、删除立即失效 | 工程证据 APPROVED | 仍需签收人确认范围 |

### Python

| 项 | 状态 | 需要的负责人动作 |
|---|---|---|
| 版本、结构、runtime profile 不匹配的完整消费 | 待负责人 | 签收，不以测试汇总代替 |
| 来源范围、只读检索、向量维度、分批写入、重试/取消后不迟到写入、外部模型错误脱敏 | 待负责人 | 附运行/日志证据 |
| 无答案、同步/SSE 答案与来源的完整草案消费 | 待负责人 | 与 Java 映射/失效语义一起签 |
| usage 字段白名单、异常不输出原文、worker 启动失败清理 | 工程证据 APPROVED | 不扩展为生产全量日志已验证 |

### M / Web

| 项 | 状态 | 需要的负责人动作 |
|---|---|---|
| 注册登录、隔离访问、上传、READY、更新/重建、任务恢复、文档分页 | 待人工 | 使用 manual-acceptance 文档，留截图 |
| 流式问答、取消、历史分页、切库/刷新竞态、文本/PDF 原文、来源失效、移动导航、键盘 | 待人工 | 同上 |
| 数据出站与错误提示核对 | 待人工 | 记录浏览器、环境、日期、执行者 |

### 总体

| 项 | 状态 |
|---|---|
| 三端完整消费确认与总体验收 | 待负责人组织 |
| 真实 RAG 采集、逐引用人工审核、正式质量门 | 部分完成（公开集合成集已跑；真人审阅/盲测未完成） |
| 预算硬 cap 或获批软预算政策 | 未完成 |
| 私有盲测题/资料保管与独立执行 | 未完成 |
| 部署、升级回滚、目标环境备份恢复、真实用户试用 | 未完成 |

## 3. 勾选规则

- 只有负责人实际执行并留下证据，才允许在 `contracts/consumer-draft10-checklist.md` 勾选。
- 工程 APPROVED、CI 通过、自动化脚本、本矩阵本身都不等于签收。
- 任何签字都必须包含执行者、环境、日期、证据路径与结论。
- 本文件不修改 checklist 的勾选状态。
