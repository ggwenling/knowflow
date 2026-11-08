---
schema_version: 1
handoff_id: 20261108-152942
updated_at: 2026-11-08T15:29:42Z
from: codebuddy
to: either
status: blocked
source_machine: WENLING
target_machine: same
branch: local
commit: e744f99d3b6826f10e14e7c9ce1899495ececf0f
---

# AI project handoff

## Outcome

推送已提交并验证的 web-v2 优化/修复，触发并核对新 SHA 的 CI，创建 `local → main` PR；把工作树中另一套未提交的“质量门禁”改动留给独立复核。人工签核与生产/预算/盲测门禁仍由负责人执行。

## Current state

### P0 已完成（2026-11-08）

- **范围**：当前未提交的六阶段性能/正确性优化 + 之前 3 个账号/异步修复，合并为可交付的 web-v2 基线。
- **验证**：
  - `npm run typecheck`、`npm run lint`、`npm test`（28 单元）、`npm run build`、`npm run perf:budget`（9 路由全部在 +5% 内）通过。
  - 隔离全栈 **45 passed**（含真实注册/上传/READY/流式问答/引用/归属隔离/PDF/回退），SSE 捕获校验 PASS（text/pdf/error/cancelled/timeout/refusal 六类），旧版回退 **1 passed**。
  - M 验收脚本 6/6 PASS，产出 `eval-out/acceptance-20261108/manifest.json` 与 10 张 390/768/1440 截图。
  - 根 `THIRD-PARTY-LICENSES.md` 追加 web-v2 221 条生产依赖（未与旧版去重，已注明）；`apps/web-v2/THIRD-PARTY-LICENSES.md` 为完整明细。
- **提交**：
  - `89fdb0e` `fix(web-v2): harden workspace lifecycle and interactions`
  - `42f4904` `build(web-v2): ship standalone runtime`
  - `0607905` `test(web-v2): add performance budgets and diagnostics`
  - `2d9d4d0` `docs(web-v2): record optimization evidence and license merge`
  - `e744f99` `docs(handoff): record optimization review and docker blocker`
- **构建环境备注**：主机 `next build` 首次被 IDE 的批量删除保护拦住（`.next/trace-build` 500 文件），将旧 `.next` 移到 `D:\tmp\knowflow-next-old-20261108` 后干净构建通过；CI 新检出无此问题。

### 未提交、未纳入本次 P0 的工作

工作树还有另一套“质量门禁”改动，未在交接/报告中验证，归属未确认：

- 未跟踪：`apps/web-v2/.quality-stage/`、`scripts/blind_checks.py`、`scripts/citation_review.py`、`scripts/quality-gates.py`、`scripts/quality_budget.py`、`scripts/quality_catalog.py`、`scripts/quality_common.py`、`scripts/tests/`、`docs/acceptance/automated-quality-gates.md`。
- 已修改：`.gitignore`（`/eval-out/`）、`evaluation/adapters/private_pack_to_runner.py`、`evaluation/collector/run.py`、`scripts/blind-preflight.py`、`scripts/prepare-citation-review.py`、`scripts/validate-citation-review.py`。
- 处理：**不要 reset/clean/stash 或提交**；先独立审阅其来源、测试与对已签核脚本的替换关系，再决定是否纳入。

### 仓库与运行环境

- `origin/local` 仍在 `8a80835`；本地 HEAD `e744f99`，领先 5 个提交。
- 本机 Compose `knowflow-local` 已用当前代码重建，3000 端口 healthy；隔离 E2E 项目已由脚本清理。
- `gh` 仍不可用，环境无 `GITHUB_TOKEN`/`GH_TOKEN`；PR 未创建。
- 演示账号可用，但凭据不写入交接；`infra/.env` 本地忽略。

### 阻塞

- **PR 未创建**：打开 `https://github.com/ggwenling/knowflow/compare/main...local?expand=1`，或安装/登录 `gh` 后 `gh pr create --base main --head local`。
- **新 SHA CI 未运行**：5 个本地提交尚未推送；旧 run `42456844122` 只覆盖 `8a80835`，不能当成本轮证据。
- 人工/项目门禁：M1/M2/M3、真人引用审阅、PRICE/POLICY、私有盲测、生产承接、真实用户试用、发行合规仍未签。

## Acceptance criteria

- [x] 静态检查、28 单元、生产构建、9 路由包体预算通过。
- [x] 隔离全栈 45 项、SSE 六类捕获、旧版回退 1 项通过。
- [x] 验收脚本 6 步与 390/768/1440 截图通过。
- [x] web-v2 221 条许可进入根清单增补。
- [x] 代码/构建/性能/文档拆分提交（5 个）。
- [ ] 推送 `origin/local` 并在新 SHA 上跑 CI。
- [ ] 创建 PR、记录审批与分支保护证据；不合并 main、不强推。
- [ ] 质量门禁工作由独立负责人复核后再决定提交。
- [ ] M1/M2/M3 与项目级签核由负责人执行，AI 不代签。

## Start here

1. `cd d:/konwflow`，核对 `git log -6`、`git status --short` 与本文件一致；确认 5 个提交是最新基线。
2. `git push origin local`；记录 push 输出与 GitHub Actions run。
3. 等待 `web`、`java`、`python-contract`、`evaluation-e2e` 四个 job；失败则按日志修复并重新验证。
4. 打开 compare URL 创建 PR，记录 PR、审批人、分支保护/例外证据；不要合并。
5. 单独审阅未提交的质量门禁改动；在确认归属、测试与替换关系前不要提交或丢弃。
6. 人工门禁按 `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md` 等材料执行。

## Files and commands

- `apps/web-v2/performance/README.md` — 包体/浏览器/堆/镜像采样口径与命令。
- `apps/web-v2/performance/budgets.json` — 9 路由原基线 +5% 门禁。
- `apps/web-v2/src/hooks/use-documents.ts`、`workspace-provider.tsx`、`use-knowledge-bases.ts` — 请求作用域、分页删除、账户隔离。
- `apps/web-v2/src/lib/{request-scope,bounded-body,text-range,upload-rules,performance}.ts` — 取消、正文上限、Unicode、上传规则、脱敏指标。
- `apps/web-v2/e2e/workspace-regressions.spec.ts`、`base-pagination-mutations.spec.ts`、`optimization.spec.ts`、`performance-regressions.spec.ts` — 本轮回归。
- `docs/reviews/2026-11-08-web-v2-release-closure-review.md` — 独立复核、堆归因、P1/P2 修复、剩余门禁。
- `docs/reviews/2026-11-08-web-v2-independent-code-review.md` — REQUEST CHANGES 原文（P1/P2 已修，未改写审阅结论）。
- `THIRD-PARTY-LICENSES.md` — §4 末尾 web-v2 221 条增补。
- Build: `cd apps/web-v2 && npm run typecheck && npm run lint && npm test && npm run build && npm run perf:budget`
- 全栈: `cd apps/web-v2 && npm run e2e`（需 Docker + `uv` 的 Python 3.12；本机设置 `UV_PYTHON=D:\uv-python\cpython-3.12.13-windows-x86_64-none\python.exe`）
- 验收: `cd apps/web-v2 && node scripts/acceptance.mjs`
- Git: `git push origin local`；compare URL 见上。

## Decisions and guardrails

- 契约冻结 `0.2.0`；没有改后端/契约/迁移。
- 单轮问答；不伪装多轮；不改动 WebGL/低动态/链接/PDF/Unicode/账户隔离行为。
- 不读取 `data/raw/`、私有盲测题/答案、密钥；不输出凭据。
- `infra/.env`、`.codebuddy/`、`eval-out/`、`performance-results/` 不纳入提交。
- 质量门禁改动未验证，不提交、不清除；与已提交的 `scripts/*` 存在替换关系，需独立审阅。
- 不合并 main、不强推、不代签。
- 主机构建的 `.next` 批量删除保护是 IDE 环境限制；CI 新检出不受影响。

## Working tree

- 已提交：应用代码、mock/单元回归、standalone 构建、性能工具/CI、优化证据、根许可增补、Codex 审阅交接快照。
- 未提交：上述质量门禁改动；`.codebuddy/`、`eval-out/` 为工具/证据产物。
- 本交接文件将在提交后再次修改；`e744f99` 是当前代码/文档基线。

## Remaining work

### P0 收口

| 项 | 状态 | 下一步 |
|---|---|---|
| 5 个提交推送 | 未开始 | `git push origin local` |
| 新 SHA CI | 未开始 | push 后等待四个 job |
| PR `local → main` | 阻塞 | compare URL / 登录 gh |
| 质量门禁工作 | 未审阅 | 独立复核归属、测试、替换关系 |

### P1/P2 人工与外部门禁

| 项 | 状态 |
|---|---|
| M1/M2/M3 浏览器验收 | 待负责人 |
| 真人引用/支持度审阅 | 工作表已生成，未签 |
| 私有盲测 | v5 answerable 0.800、旧 SHA；preflight 已备，未执行 |
| 三端消费签收 | 矩阵已备，未签 |
| PRICE/POLICY/预算 | 审计已备；无硬 cap/账单/签字 |
| 密钥轮换/PR 合规 | Runbook/模板已备；未执行 |
| 生产承接/告警/PITR/限流 | 文档/规则草案已备；未部署 |
| 真实用户试用 | 材料已备；未招募 |
| 发行许可/SBOM/签名 | web-v2 许可已增补；全栈 SBOM/签名/版权主体未完成 |

## Open questions

- 谁推送并创建 PR、谁审批？是否安装/登录 `gh`？
- 未提交的质量门禁工作由谁负责？是否替换已提交的引用/预算/盲测脚本？
- M1/M2/M3、真人审阅、PRICE/POLICY、私有盲测、生产承接、试用分别由谁执行？
- 旧版 `apps/web` 的退役时间与回退窗口？

## Handoff log

- `2026-11-08T15:29:42Z` — `codebuddy` set status to `blocked`：完成 P0 验证（45 E2E + SSE + 回退 + 28 单元 + 构建/预算 + 验收截图 + 许可增补）与 5 个提交；本地 HEAD `e744f99`，`origin/local` 仍为 `8a80835`；PR 因无 gh/token 未创建；质量门禁改动未纳入。
- 上一版 Codex 交接快照已提交为 `e744f99`；更早历史见 `git show 8a80835:.context/ai-handoff.md`。
