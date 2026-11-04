# Citation 修复轮次（2026-11-05）

- Branch: `grok`
- Fix HEAD（本轮公开 holdout / 盲测 v2 采集）：`aea779a2c43fb7ade2d9ee63ccd0eac9022b5601`
- 实现提交：`90e053c`（per-claim prompt + verifier）→ `85de4a1`（narrow + strict stacked）→ `aea779a`（stacked-only hard refuse）
- 设计笔记：[`2026-11-05-citation-fix-design-notes.md`](./2026-11-05-citation-fix-design-notes.md)
- 独立审阅：[`../reviews/2026-11-05-sol-citation-fix.md`](../reviews/2026-11-05-sol-citation-fix.md)（对 `90e053c` CHANGES_REQUESTED；P1 已在后续提交处理）
- 调参集：仅公开 `evaluation/data/seed-v2-reviewed`；**未**用盲测 v1/v2 调参
- Heuristic：`evaluation/runner/heuristic_review.py` 仍为 **proxy, not gating**

## 修复摘要

1. **Prompt**：禁止多事实末尾堆叠 `[s1][s2]`；每条可核查断言就近单独引用。
2. **Post-gen verifier**（`citation_verify.py`）：对堆叠/并行 marker 要求每条来源独立覆盖完整归一化断言（严格子串）；URL/邮箱点号保护；无标记单元忽略；**单 marker 不再 soft-refuse**（`aea779a`）。
3. **Collector `_claim`**：与服务切分对齐，避免复合 claim 误归。
4. 强制策略：验证失败时整答标准拒答（本轮已知代价：可答误拒答上升，见盲测 v2）。

## 公开 seed-v2 LLM 门禁

阈值同既有 gate v2。法官：Sol High + CodeBuddy（after/holdout 第二法官为 `deepseek-v4.1-flash`，因 Kimi 429）；after/holdout **0 分歧**，无需仲裁。

| Split | code_sha | gate | Recall@5 | MRR@10 | Support | Citation | Unans refuse | Ans answer |
|---|---|---|---:|---:|---:|---:|---:|---:|
| development BEFORE | `35b6296` | **incomplete**（1× `AI_PROCESSING_FAILED`） | 1.000 | 0.9785 | 1.000 (30/30) | 1.000 (33/33) | 1.000 | 0.9677 |
| development AFTER | `85de4a1` | **passed** | 1.000 | 0.9785 | 1.000 (30/30) | 1.000 (37/37) | 1.000 | 0.9677 |
| holdout AFTER | `aea779a` | **passed** | 1.000 | 1.000 | 1.000 (19/19) | 1.000 (25/25) | 1.000 | 1.000 |

BEFORE citation 为实际作答引用 33/33（非 gold span 数）；AFTER development 为 37/37。gate incomplete 因 1× execution error，不将 BEFORE 记为正式通过。

Predictions SHA（仓外 runtime）：

| Set | sha256 |
|---|---|
| dev before | `c0a66db22822c01ed9ca5d6b1d145646c398744e98ee36464a1cd4035efd9325` |
| dev after | `493c892e8426f100f291df39597733f086ed10174ec5f0ac21a61718a8cef813` |
| holdout after | `cd01bfe5425f946f5d1c6659305925f15b31c9379234012b91e7cd158a6cd8ec` |

Prompt SHA：BEFORE `3115dbae…` → AFTER/holdout `6a7be9f9cef66bb16a54ae5be02271b869bd47189ba6e639b065be50b3c38d3d`。

## 花费（本轮 citation-fix 账本）

- Ledger：`/workspace/knowflow-runtime/data/budget/citation-fix-20261105-023600.sqlite3`
- 预留合计：**CNY 0.54076**（paid reservations 220；含公开 before/after/holdout 与盲测 v2 采集）
- 价格/策略：draft peak PRICE + POLICY（`draft-not-owner-signed`）
- Soft/hard：8 / 10 CNY；本账本未触达

法官会话走 Codex / CodeBuddy **订阅**，不计入上述 DeepSeek/SiliconFlow 预留。

## 与盲测的关系

- 盲测 v1（2026-11-04）已污染，**禁止**再调参。
- 新盲测 v2：[`2026-11-05-box-blind-20-v2.md`](./2026-11-05-box-blind-20-v2.md) — 权威一次性结果；**citation/support 全过，answerable answer 因误拒答失败**。
- 解读：本轮修复显著压住引用幻觉，但 post-gen **整答拒答**路径把部分可答且可引用的输出打成 refused，出现「引用错误 → 误拒答」的权衡。后续不得用 v2 题面调参；仅可在公开 seed 上改 verifier 策略（例如：剪除未 grounding 的断言/引用，仅当无可保留 grounded 内容时才整答拒答）。

## 仓外产物

`/workspace/knowflow-runtime/reports/citation-fix-20261105/`（predictions、judged-*、ledger.path）；私有盲测 `/workspace/knowflow-private-blind/2026-11-05/`（不入库）。

## 剪枝轮次（over-refusal 修复）

根因：post-gen verifier 失败时整答拒答，把可保留 grounded 断言一并丢掉（盲测 v2：answerable 0.733）。

实现（`d077e6a` → URL 边界 `6ff1074`/`75baab5`/`f00a17d`）：`prune_ungrounded_claims` 删除未 grounding 的断言/引用；仅当无可保留 grounded 内容时才标准拒答。Sol 对 P1c 复审 **APPROVE**（`docs/reviews/2026-11-05-sol-citation-prune-p1c-rereview.md`）。

### 公开 seed-v2（prune 后 LLM consensus）

| Split | code_sha | gate | Support | Citation | Unans refuse | Ans answer |
|---|---|---|---:|---:|---:|---:|
| development prune | `d077e6a` | **passed** | 1.000 (31/31) | 1.000 (40/40) | 1.000 | **1.000** |
| holdout prune | `502bc9f` | **passed** | 1.000 (19/19) | 1.000 (28/28) | 1.000 | **1.000** |

holdout 第二法官曾对 2 题标 incomplete→unsupported；Sol 仲裁维持 supported。

### 盲测

- v2（`aea779a`，整答拒答策略）：answerable **0.733 failed**；citation/support 1.0 — [`2026-11-05-box-blind-20-v2.md`](./2026-11-05-box-blind-20-v2.md)
- v3（`f00a17d`，剪枝策略）：answerable **0.800 failed**；support 0.917、citation 0.966 passed — [`2026-11-05-box-blind-20-v3.md`](./2026-11-05-box-blind-20-v3.md)

### 花费更新

citation-fix 共享账本两口径：盲测 v3 **采集结束快照** reserved **CNY 1.268328**（paid 516）；报告撰写时账本累计 **CNY 2.684136**（paid 1092，含采集后继续发生的 provider 预留/重试）。超过项目软目标 <2 的指导线；已停止新增 real collect 并停服务。
