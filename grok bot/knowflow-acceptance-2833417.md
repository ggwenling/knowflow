# KnowFlow Codex 计划推送验收报告

- 验收时间：2026-11-03（Asia/Hong_Kong）
- 验收范围：只读核对 GitHub `ggwenling/knowflow` 的 `local` 推送；未评论、未改 Issue、未合并、未调用付费/真实模型 API
- 对照计划：`docs/planning/v0.2/p0-p1-closeout-plan-2026-11-02.md`
- Issue 映射：`/workspace/knowflow-plan-mapping.md`（#5–#15）
- 验收 HEAD：`28334179b1a44044284ced38d2dff68ba5b2a40f`（短 SHA `2833417`）

## 1. 基线与历史

| 项 | 结果 |
|---|---|
| `main` HEAD | `b7e83c8cf475195ac54b7b58a96ba275e44b8625`（未变） |
| 推送前 `local` | `1d0fd5e` |
| 当前 `local` / PR #3 head | `28334179b1a44044284ced38d2dff68ba5b2a40f` |
| `1d0fd5e` 是否祖先 | **是**（`compare 1d0fd5e...local`：ahead 25 / behind 0）→ **未见强推改写**，#13 基线风险基本解除 |
| `main...local` | ahead **48** / behind **0**（原先约 23，本次新增 25） |
| PR #3 | 仍 open，未合并；head 已跟到 `2833417`；mergeable=clean |

### 自 `1d0fd5e` 起新增提交（25）

时间均已转为 Asia/Hong_Kong：

| SHA | 时间 (HKT) | 主题 |
|---|---|---|
| f1f47d88bd3d | 2026-11-02 19:52:27 | fix(ai): close resources on worker lifecycle failure |
| fbe7038c47ed | 2026-11-02 20:01:55 | test(operations): add isolated backup restore drill |
| 38252b34023d | 2026-11-02 20:13:30 | 11/2 |
| 7a393ec617d9 | 2026-11-03 12:55:53 | feat(evaluation): bind retrieval traces to answer predictions |
| 309103e426dd | 2026-11-03 12:56:01 | test(web): verify draft10 SSE and keyboard source flow |
| 3de11462f802 | 2026-11-03 12:56:17 | test(performance): cover configured admission capacity |
| 365a0adcc413 | 2026-11-03 12:56:30 | test(operations): verify backup restore history and cleanup |
| f7c037d43e4a | 2026-11-03 12:56:41 | test(recovery): bind isolated outages to source revision |
| 948ff9a0b82d | 2026-11-03 13:01:02 | fix(performance): remove and verify temporary Docker images |
| 6cc458daa476 | 2026-11-03 13:08:19 | chore(recovery): expose safe upload failure code |
| b42111d6a2af | 2026-11-03 13:29:43 | fix(contract): align draft10 stream and RAG collection |
| 4018564ba79f | 2026-11-03 13:32:55 | docs(operations): preserve restore attempt five evidence |
| 24f10e486c48 | 2026-11-03 13:36:08 | fix(evaluation): validate runtime question identity |
| bb25dc194fc1 | 2026-11-03 13:53:58 | test(recovery): verify MinIO write after restart |
| 9c9b4a08bbab | 2026-11-03 14:03:58 | docs(evidence): bind restore drills to local revision |
| 857cec59daba | 2026-11-03 14:10:48 | docs(acceptance): record November 3 evidence |
| 00147f6aa03e | 2026-11-03 14:12:51 | docs(acceptance): correct review snapshot |
| 882863717182 | 2026-11-03 14:24:41 | test(contract): verify Java JSON null semantics |
| 8fb0687328dc | 2026-11-03 14:26:19 | docs(contract): scope SSE verification coverage |
| 79678830b140 | 2026-11-03 14:27:31 | docs(acceptance): clarify SSE review gap |
| 65774c47506d | 2026-11-03 14:38:06 | docs(acceptance): record remote CI and Q review |
| 802fe48e7d4c | 2026-11-03 15:27:50 | fix(web): preserve SSE cancellation and verify failure consumption |
| 4db75a987028 | 2026-11-03 15:37:53 | docs(acceptance): record SSE consumption evidence and remaining gates |
| a30394a90423 | 2026-11-03 15:59:10 | fix(sse): enforce stream lifecycle and correlate request IDs |
| **28334179b1a4** | **2026-11-03 16:01:53** | **docs(acceptance): close SSE engineering scope with verified evidence** |

说明：计划文档把“当前代码候选”写成 `a30394a`（Sol 工程 APPROVED 绑定 SHA）；远端 HEAD 多了一个文档提交 `2833417`。代码树相对 `a30394a` 无再改动，但正式签收应明确绑定 **HEAD `2833417`** 或注明 docs-only delta。

## 2. 变更文件（相对 `1d0fd5e`，79 文件）

- **contracts (5)**：`openapi-draft10.json`、`consumer-draft10-checklist.md`、`test_openapi_draft10.py`、`validate_sse_capture.py`、`README.md`
- **services/api (6)**：问答 SSE/ID 关联、SourceResponse、准入测试、DocumentApiIntegrationTest null/wire
- **services/ai (17)**：app、recovery/SSE/RAG 测试与工具、多份 recovery evidence JSON
- **apps/web (8)**：workspace/api SSE 状态机、E2E、样式
- **evaluation (17)**：collector（budget/guarded/mapping/prediction/wiring）、performance runner/evidence、test_run
- **docs (5)**：closeout 计划、SSE 消费证据、real-collection-design、backup-restore-acceptance、annotation notes
- **CI (1)**：`.github/workflows/web-e2e.yml`
- **other (20)**：infra backup-restore 脚本与大量 evidence、`.context/ai-handoff.md`、`.tmp-annotation/*`、`scripts/e2e-web.mjs`

## 3. CI（目标 SHA `2833417`）

Checks API（非 legacy statuses；combined legacy status 为空/`pending`，以 Actions checks 为准）：

| 触发 | Run | python-contract | java | web |
|---|---|---|---|---|
| push | [41600421766](https://github.com/ggwenling/knowflow/actions/runs/41600421766) | success | success | success |
| pull_request (PR #3) | [41600428669](https://github.com/ggwenling/knowflow/actions/runs/41600428669) | success | success | success |

附加：Cursor Bugbot = neutral（无新问题）；Approval/Security Agent = success。  
**结论：目标 HEAD 三 job 全绿，可作为工程 CI 证据。**

## 4. 计划文档逐阶段核对

计划状态字面：`IN_PROGRESS`；候选写为 `local@a30394a`；schema SHA-256 `20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`（已核对 = `contracts/schemas/protocol.schema.json`）；明确 **未合并 main、未完成 M 签收、未完成真实模型质量验收**。

### 4.1 状态与来源校准 / 审核来源与文档修正（#12）

| 维度 | 计划声称 | 仓库实据 | 判定 |
|---|---|---|---|
| human-reviewer / agent 来源保留 | 有 | `evaluation/data/seed-v2-reviewed/manifest.json` 含 `annotation_provenance`：`human-reviewer`、`prior_agent_review`、异常时间戳 note、确认时间≠完成时间 note | **通过（内容）** |
| 指纹记录 | 原 `4ce66d29…` → 新 `023f14ba…` | runner 指纹算法 `sha256(manifest+\0+questions)`：`b7e83c8`=`4ce66d29…`，`1d0fd5e`/HEAD=`023f14ba…` | **通过** |
| 注意 | — | 该 provenance/指纹在 `1d0fd5e` 已存在，**本次 25 提交主要是延续记录，非新改数据集** | 信息项 |
| 交接摘要 | 计划已整理 | closeout 计划与 SSE 证据文档已更新；正式签收框仍未勾 | **部分** |

### 4.2 P0 独立 Q/M 代码及契约验收（#8；叠加 #5/#6/#7/#10）

| 维度 | 计划声称 | 仓库实据 | 判定 |
|---|---|---|---|
| Sol 对工程候选 APPROVED | `a30394a` / 早前 `7967883`/`802fe48` 等 | 证据写在 `docs/reviews/2026-11-03-sse-consumption.md` 与 closeout 计划；**未见独立 Sol 会话文件**（对比旧的 `docs/reviews/2026-11-02-q-b7e83c8.md` 这种独立审阅件） | **存疑（独立性证据不足）** |
| 正式 Q/M | 仍 CHANGES_REQUESTED / 未总体 APPROVED | 清单 `contracts/consumer-draft10-checklist.md` 状态 **IN_REVIEW**，Java/Python/M/Q 正式勾选框 **全部未勾** | **未完成** |
| draft.10 schema hash | 已登记 | protocol.schema.json 哈希匹配；OpenAPI 候选存在且引用该 hash | **通过（登记）**；**未冻结** |
| OpenAPI / 消费清单 | 已补齐候选 | `openapi-draft10.json` + checklist + 测试存在；OpenAPI unittest 本地 4/4 通过；CI python-contract 绿 | **部分（工程产物有，签收无）** |
| 远端 CI | 多轮记录；最新候选当时“记录时未结束” | **HEAD 现已全绿**（见 §3） | **通过（CI）** |
| M 浏览器签收 | 待负责人 | 仅有工程侧 Docker E2E/证据叙述，无负责人签收记录 | **未完成** |
| merged / contract frozen / DONE | 计划未勾合并；契约未冻结 | PR #3 未合并；README/checklist 明确 DRAFT/IN_REVIEW | **未宣称合并/冻结（正确）** |

作者自签风险：**高关注**。文档写“Luna 不可用 → 根代理实施，Sol 独立审阅”，但 Sol APPROVED 语句与实现证据同文件、同作者提交链（`ggwenling`），缺少可核对的独立 Sol 审阅产物。工程 APPROVED ≠ 正式 Q APPROVED；计划自身也仍把正式 Q/M 留为未完成——这点诚实，但对外表述易被误读成“P0 已过”。

### 4.3 P1 真实 RAG 采集评分（#9）

| 维度 | 声称 | 实据 | 判定 |
|---|---|---|---|
| top10 捕获 / top5 生成 / collector | 组件已接 | `evaluation/collector/*`、`test_rag_collection.py` **25 passed**（本地 cheap） | **部分（工具）** |
| 质量门 / 错误≠拒答 | 设计与 CLI 非零退出 | 计划勾选“尚未接通真实评测驱动”；无真实预测/人工审核包/门禁报告绑定 HEAD | **未完成（真实跑）** |
| ¥10 预算 | fail-closed；Sol 不批准启用 | budget ledger + guarded adapters；文档称无供应商硬 cap；**真实 provider 调用声明为 0** | **未完成**；**未见未授权付费调用红旗** |
| 门槛指标 | 未跑 | 无分子分母报告 | **未完成** |

### 4.4 P1 20 题私有盲测（#9）

计划与 SSE 证据均写：**负责人尚未准备**；仓库无盲测题/答案泄露迹象 → **未完成**（正确停住）。

### 4.5 P1 故障恢复与性能（#14）

| 维度 | 声称 | 实据 | 判定 |
|---|---|---|---|
| PG / MinIO / 第二批 embedding 失败 | 通过 | `...final-bb25dc1-attempt2.json` 存在，`result=DEVELOPMENT_PASS_SYNTHETIC_RECOVERY`，四场景 `passed:true`，`model_calls` 语境为 0，绑定 `bb25dc1` | **部分（合成/隔离通过）** |
| 负载 10/100 × 1/4/8 | 48/48 @cap8 | `baseline-cap8-final-20261103-9c9b4a0.json` 存在，绑定 `9c9b4a0`；明确合成适配器，非真实 provider | **部分** |
| Linux 资源边界 / 许可 / 日志脱敏生产核对 | 未完成勾选 | 未见完整交付 | **未完成** |
| 真实 provider 延迟成本 | 阻塞于预算门 | 一致 | **未完成** |

注意：恢复/性能证据绑定的是中间 SHA（`bb25dc1`/`9c9b4a0`），其后仍有 SSE 等代码变更；是否需在 HEAD 重跑取决于变更是否触及恢复路径（SSE 偏问答前端/关联，风险中低，但签收规范上仍建议重绑或做差分说明）。

### 4.6 P2 部署 / 备份恢复 / 两周试用（#15）

- 隔离 backup-restore 证据：`infra/evidence/backup-restore-20261103-final-bb25dc1.json` 存在 → **部分（隔离演练）**
- 干净生产部署、升级回滚、两周真实试用：计划未勾 → **未完成**

## 5. 实质抽查与廉价测试

已执行（无网络模型调用）：

| 检查 | 结果 |
|---|---|
| `contracts/schemas/protocol.schema.json` SHA-256 | = 登记值 `20121f69…` |
| `python -m unittest contracts.test_openapi_draft10` | **4 passed** |
| `uv run … python contracts/validate.py` | **PASS schema + 85 structural cases**（注明授权/租约/DB 未执行） |
| `pytest services/ai/tests/test_rag_collection.py` | **25 passed** |
| `pytest evaluation/performance/test_run.py` | **14 passed** |
| Sol 独立审阅件 | 有旧 `2026-11-02-q-b7e83c8.md`；**无**针对 `a30394a`/`2833417` 的独立 Sol 文件 |
| 消费清单 | OpenAPI/checklist 已更新；正式勾选全空 |

## 6. 密钥 / 私有数据扫描（`1d0fd5e..HEAD`）

- **未见**提交 `.env`、真实 API key、`sk-…`、云厂商密钥、私钥
- E2E 使用测试口令字面量（如 `KnowFlow-e2e-only-2026!`）与运行时 `secrets.token_hex`；证据 JSON 含 `secret_in_process_logs: false`
- 文档提及本机忽略的 `services/ai/.env` 有凭证但**不得输出/提交**——与 diff 一致
- 盲测：仅有“尚未准备 / 不入库”陈述；`.tmp-annotation/source.json` 为公开合成「青竹」资料片段，**不是** 20 题私有盲测题
- **结论：无私有盲测泄露；无已提交密钥红旗；无未授权真实花费证据（文档一致声称 provider=0）**

## 7. 阶段总评

| 阶段 | 对应 Issue | 总评 |
|---|---|---|
| 基线核对 | #13 | **通过**（基于 `1d0fd5e` 快进，无强推） |
| 状态与来源校准 | #12 | **通过/部分**（provenance 实据在，且早于本批；文档继续校准） |
| P0 Q/M + 契约 | #8 (+#5/#6/#7/#10) | **部分 + 存疑**（工程与 CI 强；正式签收未做；Sol 独立性证据弱） |
| P1 RAG 真实采集评分 | #9 | **未完成**（工具部分就绪） |
| P1 盲测 | #9 | **未完成** |
| P1 恢复与性能 | #14 | **部分**（合成证据有；HEAD 重绑/真实 provider/Linux 许可未完） |
| P2 部署/试用 | #15 | **未完成**（仅有隔离备份演练） |
| 合并 PR #3 | #4 | **未完成**（需负责人批准） |

## 8. 阻断项与红旗

**阻断（按计划出口仍缺）：**
1. 正式独立 Sol/Q 审阅产物绑定 **HEAD `2833417`**（或明确 docs-only 继承自 `a30394a` 的独立 Sol 文件）
2. Java/Python/M 消费清单逐项签收 + 负责人浏览器 M 签收
3. 真实 RAG 评测：预算硬门禁（或负责人书面批准软预算）→ 采集 → 人工评分 → 质量门报告
4. 20 题私有盲测（负责人保管）
5. （若要以 HEAD 冻结）恢复/性能证据重绑或书面差分豁免
6. PR #3 合并授权；P2 部署与两周试用

**红旗 / 存疑：**
- Sol “工程 APPROVED”主要出现在实现方撰写的验收文档中，**独立性存疑**；不得据此关闭 #8 正式 Q
- 计划候选 SHA（`a30394a`）落后远端 HEAD（`2833417`）——易造成签收错绑
- `human-annotation-review.json` 内仍残留 “This is agent review…” 方法描述与 `human_reviewed` 状态并存的文案噪音（manifest provenance 更清晰，但建议清理以免误读）
- **未发现**未授权付费调用；预算仍 fail-closed（正向）

## 9. 建议的下一步（可并行 / 需批准）

### 可立即并行（不改 `local` 主线代码或仅只读 / 旁路分支）

1. **独立 Sol High 会话**：对 `2833417`（或 `a30394a`+docs delta）出具独立审阅文件，结论与发现单独落盘；作者不得代签  
2. **#11 分支卫生**：只读盘点报告  
3. **#14 只读**：依赖许可证 + 日志脱敏审计报告  
4. **#15 部署草案**：`agent/deploy-prep` 仅写新 `deploy/` 文档/脚本，不碰业务代码  
5. **Know Bot / 第二意见只读预审**：对照消费清单做问题清单（非签收）

### 需负责人批准后才能推进

A. **合并 PR #3 → main**（#4）——即使工程 CI 全绿，仍缺正式 Q/M；若只合“工程收尾”须在合并说明中再次强调非质量签收  
B. **付费/真实模型调用**（#9）——批准 ¥10 硬/软预算策略后，Sol 复核门禁，再跑采集  
C. **M 浏览器签收**——负责人本人按 checklist 操作并签字  
D. **准备并保管 20 题盲测**——冻结候选后再开独立评测会话  

### 建议主路径（验收后）

1. 先派 **独立 Sol 复审 HEAD**（解除自签存疑）  
2. 并行：分支卫生、许可/脱敏审计、deploy 文档草案  
3. 负责人决定：是否在缺 M/真实质量的情况下仍合并工程 PR #3  
4. 预算授权 → RAG 采集评分 →（冻结后）盲测 → HEAD 上确认恢复/性能 → P2 试用  

---

报告文件：`/workspace/knowflow-acceptance-2833417.md`  
本轮未对 GitHub 做任何写操作。
