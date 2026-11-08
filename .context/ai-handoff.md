---
schema_version: 1
handoff_id: 20261108-070720
updated_at: 2026-11-08T07:07:20Z
from: codebuddy
to: either
status: blocked
source_machine: WENLING
target_machine: same
branch: local
commit: 8a80835181145ae3c70802dcef760f8498fc86b2
---

# AI project handoff

## Outcome

在 `local@8a80835` 上完成 web-v2 v1 的规范修复、回归、提交、推送与 CI，并把项目级人工/外部阻断项整理成可执行材料。接收方先解除 PR 阻塞（本机无 `gh`/token），再推动 M 人工验收与项目级签核。

## Current state

### 已完成（2026-11-08）

- UI 规范修复：导航/卡片/历史改真实 `Link`；新增 skip link 与 `<main id="main-content">`；补齐搜索、选择器、textarea 的可见焦点；知识库搜索 `?q=`、详情筛选 `?status=`、历史搜索 `?history=` 写入 URL；历史列表 `content-visibility`；骨架屏改 transform 扫光；表单补 `name`/`autoComplete`；相对时间改 `Intl`；新增 `theme-color`、viewport 与 OG 图。
- 回归：Playwright **16 passed / 1 skipped**（skip 为需要隔离迁移环境的回退用例）；新增 `e2e/a11y.spec.ts`。
- 提交与 CI：
  - `1591b91` `feat(web-v2): deliver unified workspace v1`
  - `f8a81de` `chore(web): wire v2 into compose, ci and docs`
  - `8d438eb` `docs(delivery): add acceptance and readiness evidence`
  - `8a80835` `fix(e2e): keep rollback check compatible with legacy and v2 ui`
  - CI run `42456844122`（https://github.com/ggwenling/knowflow/actions/runs/42456844122）：`evaluation-e2e`、`python-contract`、`java`、`web` 四个 job 全部 success。
- 验收与证据：
  - `apps/web-v2/scripts/acceptance.mjs` 真实链路 6 步全 PASS，产出 `eval-out/acceptance-20261108/manifest.json` 与 10 张截图（含 1440/768/390）。
  - `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md`：M1/M2/M3 人工步骤与签字栏（空）。
  - `docs/acceptance/2026-11-08-citation-human-review.md` + `scripts/prepare-citation-review.py` + `scripts/validate-citation-review.py`：dev 31/9/47、holdout 18/2/28 工作表已生成，真人未签。
  - `docs/acceptance/2026-11-08-price-policy-signoff.md` + `scripts/audit-budget-ledger.py`：账本只读汇总；9907aca dev/holdout 预留 3.30752 CNY，超软目标 1.30752，无硬 cap/账单证据。
  - `docs/acceptance/2026-11-08-consumer-signoff-matrix.md`：三端证据矩阵，未勾选任何负责人项。
  - `docs/operations/2026-11-08-{pr-compliance-record,key-rotation-runbook,rate-limit-and-resource-boundaries,release-checklist}.md`。
  - `docs/evaluation/blind-holdout-preflight.md` + `scripts/blind-preflight.py`：未执行、未读取私有题集。
  - `deploy/{production-gap-closure.md,backup-pitr-runbook.md,alerts/*}`。
  - `docs/product/pilot-v1/*`：招募、同意、任务、指标、访谈模板（无真实数据）。
  - `apps/web-v2/THIRD-PARTY-LICENSES.md`：web-v2 生产依赖 221 条，0 unknown；根清单尚未合并。

### 仓库与运行环境

- `origin/local == HEAD == 8a80835`；工作树仅本交接修改，未跟踪 `eval-out/` 与 `.codebuddy/`。
- Compose 全栈 `knowflow-local` 在 `127.0.0.1:3000` 运行且 healthy；`infra/.env` 本地忽略，不提交。
- 旧版交接历史见 `git show 6da4675:.context/ai-handoff.md`。

### 阻塞

- **PR 未创建**：本机没有 `gh` CLI，环境也没有 `GITHUB_TOKEN`/`GH_TOKEN`。代码已推送，创建 PR 需要：
  `https://github.com/ggwenling/knowflow/compare/main...local?expand=1`
- M 人工验收、真人引用审阅、PRICE/POLICY、私有盲测、生产承接、真实用户试用仍待负责人执行；不得代签。

## Acceptance criteria

- [x] UI 规范修复完成，typecheck/lint/build 通过。
- [x] Playwright 16 passed / 1 skipped。
- [x] web-v2 与 infra/CI 变更已提交并推送 `origin/local`。
- [x] 当前 SHA 的四个 CI job 全绿（run 42456844122）。
- [x] 验收脚本、M 人工步骤、引用审阅、预算审计、盲测 preflight、消费矩阵、运维/发行/试用材料已产出。
- [ ] **创建 `local → main` PR**（阻塞：无 gh/token；不合并 main、不强推）。
- [ ] M1/M2/M3 人工执行并签字，随后才可更新消费清单。
- [ ] 真人引用审阅、PRICE/POLICY、私有盲测、生产与试用由负责人推进。

## Start here

1. 打开 compare URL 创建 PR（或安装并登录 `gh` 后 `gh pr create --base main --head local`）；记录 PR URL 与审批人，不合并。
2. 核对 `git status` 与 CI run；若 PR 触发新的 CI，等待并记录结论。
3. 按 `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md` 执行 M1/M2/M3，截图写入约定路径，填签字表；完成后才更新 `contracts/consumer-draft10-checklist.md`。
4. 负责人审阅引用工作表、预算审计与消费矩阵；签字前保持未完成状态。
5. 选择下一个项目级阻断（真人审阅/盲测/预算/生产）推进，不要扩大未授权范围。

## Files and commands

- `apps/web-v2/DESIGN.md` — 全站设计规范（含 Link/skip/focus/URL/touch 规则）。
- `apps/web-v2/scripts/acceptance.mjs` — 真实链路验收与截图；凭据只从 env 读取。
- `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md` — M 人工步骤与签字。
- `docs/acceptance/2026-11-08-citation-human-review.md` — 引用审阅说明。
- `docs/acceptance/2026-11-08-price-policy-signoff.md` — 预算签核包。
- `docs/acceptance/2026-11-08-consumer-signoff-matrix.md` — 三端签核矩阵。
- `docs/operations/2026-11-08-*.md` — PR 合规、密钥轮换、限流、发行。
- `docs/product/pilot-v1/` — 用户试用材料。
- `deploy/production-gap-closure.md`、`deploy/backup-pitr-runbook.md`、`deploy/alerts/` — 生产承接。
- Build: `cd apps/web-v2 && npm run typecheck && npm run lint && npm run build`
- E2E: `cd apps/web-v2 && npx playwright test`（需 Compose；`KNOWFLOW_E2E_STREAM_CAPTURE` 必填）
- 隔离全栈: `node scripts/e2e-web.mjs --v2`
- 验收: `cd apps/web-v2 && node scripts/acceptance.mjs`
- 引用审阅: `python scripts/prepare-citation-review.py`、`python scripts/validate-citation-review.py`
- 预算: `python scripts/audit-budget-ledger.py`
- 盲测 preflight: `python scripts/blind-preflight.py --dataset ... --expected-sha256 ...`（由题集保管人执行）

## Decisions and guardrails

- 契约冻结 `0.2.0`；本次未改后端、契约或迁移。
- 单轮问答；不得伪装多轮上下文。
- 不编造统计、更新时间、逐库文档数或模型能力。
- 登录/注册英文品牌语气；工作区中文。
- 导航用链接、动作用按钮；删除必须确认。
- 不读取 `data/raw/`、私有盲测题/答案、密钥文件；不把凭据写入仓库或交接。
- `infra/.env` 本地忽略；`eval-out/` 验收产物不入库；`.codebuddy/` 不属于源码。
- 当前分支 `local`；不合并 `main`、不强推；PR 创建后由负责人审批。
- `from: codebuddy` 是协议枚举的扩展；`to: either`。
- 不代签、不把“材料已准备”写成“已签收”。

## Working tree

- 已提交：`apps/web-v2/`、5 个跟踪文件修改、`infra/compose.legacy-web.yml`、`docs/*`、`deploy/*`、`scripts/*`。
- 未提交：本交接（`.context/ai-handoff.md`）。
- 未跟踪且不入库：`eval-out/`（评测/截图/审计产物）、`.codebuddy/`（工具数据）。
- 运行中的 Compose 栈保留给人工验收；停止用 `docker compose --project-name knowflow-local -f infra/compose.yml --env-file infra/.env down`（不要加 `--volumes`）。

## Remaining work (2026-11-08)

### P0 — 收口

| 项 | 状态 | 下一步 |
|---|---|---|
| web-v2 入库 | 已完成 `1591b91` | — |
| infra/CI 接入 | 已完成 `f8a81de` | — |
| 当前 SHA CI | 已完成 run 42456844122 | — |
| PR `local → main` | 阻塞 | 无 gh/token；打开 compare URL 或登录 gh 创建 |
| M 人工验收 | 待负责人 | 按 manual-acceptance 执行并签字 |
| UI 规范 | 已完成 | a11y.spec + 手工走查 |
| web-v2 许可 | 已完成清单 | 根 `THIRD-PARTY-LICENSES.md`/SBOM 合并仍待做 |
| 回退 E2E | 已完成 CI | legacy/v2 双兼容 |

### P1/P2 — 项目级

| 项 | 状态 |
|---|---|
| 真人引用/支持度审阅 | 工作表已生成；未审阅 |
| 私有盲测 | v5 answerable 0.800、绑定旧 SHA；preflight 已备，未执行 |
| 三端完整消费签收 | 矩阵已备；未签 |
| PRICE/POLICY/预算 | 审计已备；无硬 cap/账单/签字 |
| PR 合规 | 模板已备；分支保护/例外未取证 |
| 密钥轮换 | Runbook 已备；未执行 |
| 生产承接/告警/PITR | 文档与规则草案已备；未部署 |
| 真实用户试用 | 材料已备；未招募 |
| 发行合规 | 清单/SBOM 草案已备；版权主体/签名/校验和未完成 |

## Open questions

- 谁创建 PR 并审批？是否安装/登录 `gh`，或直接使用 compare URL？
- M1/M2/M3 由谁执行、在哪个浏览器/设备、证据存哪里？
- 真人引用审阅者、PRICE/POLICY 签核人、私有盲测独立评分者何时确定？
- 生产承接与环境负责人？是否先完成告警/PITR 再上线？
- 旧版 `apps/web` 的退役时间与回退窗口？

## Handoff log

- `2026-11-08T07:07:20Z` — `codebuddy` set status to `blocked`：完成 UI 规范修复、16/17 e2e、四个提交推送、CI 全绿（42456844122）、验收/引用/预算/盲测/消费/运维/试用材料；PR 因无 `gh`/token 未创建；人工签核与项目级阻断保持未完成。
- 上一版完整日志（2026-10-30 至 2026-11-04）保留在 `git show 6da4675:.context/ai-handoff.md`。
