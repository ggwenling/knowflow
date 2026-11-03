# KnowFlow Codex 并行派工指令（T02 / T03 / T04 / T07）

- 仓库：https://github.com/ggwenling/knowflow
- 基线分支：`local`（PR #3 → `main`，head 约 `1d0fd5e`；派工前先 `git fetch` 并确认最新 SHA）
- 跟踪看板：#5 #6 #7 #10；工程收尾 PR：https://github.com/ggwenling/knowflow/pull/3
- 生成时间：2026-11-03（Asia/Shanghai）
- **状态：仅指令草稿，Know Bot 未启动任何 Coding Agent**

## 并行规则（必须遵守）

| Agent | 任务 | 允许改动 | 禁止改动 |
|---|---|---|---|
| Codex-A1 | T02 | 仅 `contracts/**`（必要时 docs 中 agent-a / ADR） | `services/**`、`apps/**`、`evaluation/**` |
| Codex-A2 | T03 | 仅 `services/api/**` | `contracts` 源 schema、`services/ai`、`apps/web` |
| Codex-B | T04 | `services/ai/**`、`evaluation/**` | `services/api`、少碰 `apps/web` |
| Codex-M | T07 | `apps/web/**`、必要时 `scripts/e2e-web.mjs` | Java/Python 业务内核、`contracts` 源 |

- 每人独立分支 / 工作区；命名建议见各指令。
- **不得**合并 `main`、删除分支、部署生产、调用付费 / 真实模型 API。
- **不得**仅凭自述完成；完成须有提交 SHA + 测试证据；正式 DONE 仍要等 T05（#8）Q 审阅。
- 契约仍是 `0.2.0-draft.10` **未冻结**；任何人不得擅自改成已冻结。
- 若与 PR #3 已有改动重叠：优先在分支上 rebase/`local`，用小步提交，PR 描述写清相对 #3 的增量。

建议启动顺序：四个指令可同时发给四个 Agent；若 A 只有一人，先跑 **T02**，再跑 **T03**。

---

## 指令 1 — Codex-A1 / T02（Issue #5）

```text
你是 KnowFlow 的 Codex-A（契约所有者）。只做 Issue #5 / T02：draft.10 契约冻结准备包。不要做 Java/Python/Web 实现。

仓库：https://github.com/ggwenling/knowflow
基线：从最新 local 拉分支 agent/a-draft10-freeze-prep（若冲突改用 agent/a-t02-<shortsha>）
跟踪：https://github.com/ggwenling/knowflow/issues/5
相关 PR（只读参考，勿合并）：https://github.com/ggwenling/knowflow/pull/3

目标：
补齐 draft.10 冻结所需材料：OpenAPI/Schema 对齐、consumer checklist、版本状态字段说明。未经 Java/Python/Web + Q 三方确认，不得把状态改成「已冻结」。

允许修改：
- contracts/**
- 必要时 docs/tasks/agent-a.md 或相关 ADR（仅文档）

禁止：
- 修改 services/**、apps/**、evaluation/**
- 合并 main、删除分支、部署、调用付费 API
- 作者代填 Q 结论

验收标准：
1. python contracts/validate.py 与 OpenAPI/结构相关测试通过
2. checklist 明确列出 Java / Python / Web 消费确认项与目标 SHA 填写栏
3. contracts/README（或等价文档）仍明确标注 DRAFT / 未冻结
4. 开 PR → base 用 local（或说明为何对 main），正文链接 #5，并声明「非冻结签字」

测试要求：
- contracts/validate.py
- unittest contracts.test_*（若仓库已有）
- 与 CI job python-contract 对齐的本地命令

交付物：
- PR 链接、HEAD SHA
- 测试命令与通过摘要
- 尚未完成项列表（若有）

完成后在 Issue #5 评论进度；不要声称 DONE（需 Q）。
```

---

## 指令 2 — Codex-A2 / T03（Issue #6）

```text
你是 KnowFlow 的 Codex-A（Java API）。只做 Issue #6 / T03：Java 侧 draft.10 消费与恢复回归确认。不要改 contracts 源 schema。

仓库：https://github.com/ggwenling/knowflow
基线：从最新 local 拉分支 agent/a-draft10-consume
跟踪：https://github.com/ggwenling/knowflow/issues/6
相关：PR https://github.com/ggwenling/knowflow/pull/3 ；契约任务 #5（只消费其产出，勿并行改 contracts）

目标：
确认 services/api 在目标 SHA 上完整消费 draft.10（历史、幂等、tombstone、模型身份等），保留 Testcontainers 回归。

允许修改：
- services/api/**（含 API 专属测试）

禁止：
- 修改 contracts 源 schema（只消费）
- 修改 services/ai、apps/web、evaluation
- 合并 main、删除分支、部署、付费 API

验收标准：
1. ./mvnw -B test（或与 CI java job 等价）全绿
2. 文档记录本分支消费的契约候选 / OpenAPI 文件与 SHA（指向 local 或 #5 PR）
3. 无越权 / 租约回归失败
4. 开 PR → base local，链接 #6

测试要求：
- Maven 测试与 CI java job 对齐

交付物：
- PR 链接、HEAD SHA、mvn 测试摘要、消费的契约引用

在 Issue #6 评论；勿标正式 DONE。
```

---

## 指令 3 — Codex-B / T04（Issue #7）

```text
你是 KnowFlow 的 Codex-B（Python AI + evaluation）。只做 Issue #7 / T04：Python draft.10 消费 + 评测工厂安全边界。不要改 Java API。

仓库：https://github.com/ggwenling/knowflow
基线：从最新 local 拉分支 agent/b-eval-guardrails
跟踪：https://github.com/ggwenling/knowflow/issues/7
相关：PR https://github.com/ggwenling/knowflow/pull/3 ；真实评测 #9 另案，本任务禁止真实付费调用

目标：
1) 确认 AI 服务消费 draft.10
2) 评测工厂注入保持 fail-closed，直至 token/budget 策略独立核验
3) 恢复演练证据可复现或已归档索引

允许修改：
- services/ai/**
- evaluation/**

禁止：
- 修改 services/api
- 大范围改 apps/web（除非为修测试夹具且最小 diff，优先不开）
- 合并 main、删除分支、部署
- 调用真实 Embedding/LLM 或任何付费 API（无项目经理书面授权）
- 提交密钥或私有盲测题

验收标准：
1. uv run pytest services/ai/tests（及仓库约定的契约校验）绿
2. create_evaluation_app（或等价入口）在未核验策略时拒绝启动真实服务
3. 恢复演练证据路径可指向；缺失则记 BLOCKED 原因而非假绿
4. 开 PR → base local，链接 #7

测试要求：
- pytest、合成 recovery e2e、对齐 CI python-contract

交付物：
- PR 链接、HEAD SHA、测试摘要、fail-closed 验证步骤

在 Issue #7 评论；勿标正式 DONE。
```

---

## 指令 4 — Codex-M / T07（Issue #10）

```text
你是 KnowFlow 的 Codex-M（Web / 工作台）。只做 Issue #10 / T07：Web draft.10 字段 / SSE / 分页消费确认。不要改 Java/Python 业务内核。

仓库：https://github.com/ggwenling/knowflow
基线：从最新 local 拉分支 agent/m-web-draft10
跟踪：https://github.com/ggwenling/knowflow/issues/10
相关：PR https://github.com/ggwenling/knowflow/pull/3 ；checklist 参考 contracts/consumer-draft10-checklist.md（只读勾选，不改冻结状态）

目标：
确认工作台与同源代理正确消费 draft.10：问答历史、幂等、分页、来源 tombstone；合成 E2E 覆盖关键路径。

允许修改：
- apps/web/**
- 必要时 scripts/e2e-web.mjs

禁止：
- 修改 services/api、services/ai 业务实现
- 修改 contracts 源并宣称冻结
- 合并 main、删除分支、部署、付费 API

验收标准：
1. npm typecheck / lint / test / build 绿
2. Playwright 全栈或 node scripts/e2e-web.mjs 绿（与 CI web job 对齐）
3. checklist 中 M 消费项已勾选并注明验证 SHA
4. 开 PR → base local，链接 #10

测试要求：
- 仓库 npm 脚本 + e2e-web + CI web job

交付物：
- PR 链接、HEAD SHA、前后端合成 E2E 摘要、checklist 勾选结果

在 Issue #10 评论；勿标正式 DONE。
```

---

## 派工后项目经理检查清单

- [ ] 四分支文件树无交叉（contracts / api / ai+evaluation / web）
- [ ] 各 PR base 为 `local`（或明确 rebase 策略），且未申请合 `main`
- [ ] 无真实模型调用、无密钥入库
- [ ] Issue #5/#6/#7/#10 均有进度评论与 SHA
- [ ] PR #3 CI 另盯；合并仍需单独批准 + T05（#8）

## 明确不在本轮派工

- T05 Q 审阅（#8）— 独立角色，作者不得代填
- T06 真实评测（#9）— blocked，待密钥与预算授权
- T08 分支卫生、T10 文档收口 — 流程项，可稍后
- 合并 PR #3 — 需额外批准
