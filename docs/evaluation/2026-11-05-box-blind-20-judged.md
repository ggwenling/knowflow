# Box 盲测 20 — LLM 门禁审阅（2026-11-05）

- Branch: `grok`
- Rubric: `2026-11-05-v1`（claim 须由对应 `source_text` 支撑；整题 support 看已引用证据；不可答且 answered → support=`unsupported`）
- Judges: (1) Sol High `sol-high-llm-judge`；(2) CodeBuddy `kimi-k3.1-pro`；(3) 分歧由独立第三 Sol `sol-high-llm-judge-r3` 仲裁
- Spend: **RMB 0**（仅 Codex / CodeBuddy 订阅；未走 DeepSeek / SiliconFlow）
- Private I/O: `/workspace/knowflow-private-blind/2026-11-04/judged/` only（不入库）
- Heuristic: `evaluation/runner/heuristic_review.py` 为 **proxy, not gating**；Sol R4 residual P1 记为 known limitation（未关闭）

关联：[`2026-11-04-rag-box-blind-20.md`](./2026-11-04-rag-box-blind-20.md) · [`2026-11-05-box-blind-20-diagnosis.md`](./2026-11-05-box-blind-20-diagnosis.md)

## 方法

1. 对 original 与 post-diag 两套 predictions 各生成 runner 兼容 `review-template`（仓外）。
2. 两位独立法官只写 judgements-only JSON（question_id + judgements，无题面/答案拷贝进 judgements 文件之外的仓库）。
3. 用仓外 `merge_judgements.py` 合成 runner 可评分的 review；`runner_v2.evaluate` + 私有 `gate.json` 重算门禁。
4. 不一致项开第三 Sol 会话独立重判；本报告门禁采用 **consensus**（Sol 初判 ⊕ 仲裁覆盖）。

## 门禁表（LLM consensus）

阈值：Support≥0.90 · Citation≥0.95 · Unanswerable refusal≥0.90 · Answerable answer≥0.90 · Review coverage=1.0 · Recall@5≥0.85 · MRR@10≥0.75

| Gate | Original (judged) | Post-diag (judged) |
|---|---|---|
| Recall@5 | 1.000 passed | 1.000 passed |
| MRR@10 | 1.000 passed | 1.000 passed |
| Support | **0.875 failed** (14/16) | **0.929 passed** (13/14) |
| Citation | **0.880 failed** (22/25) | **0.700 failed** (14/20) |
| Unanswerable refusal | **0.800 failed** (4/5) | 1.000 passed |
| Answerable answer | 1.000 passed | 0.933 passed |
| Support review coverage | 1.000 passed | 1.000 passed |
| Citation review coverage | 1.000 passed | 1.000 passed |
| **Overall** | **failed** | **failed** |

Assets: [`assets-box-blind-20261105-original-judged-summary.json`](./assets-box-blind-20261105-original-judged-summary.json) · [`assets-box-blind-20261105-postdiag-judged-summary.json`](./assets-box-blind-20261105-postdiag-judged-summary.json)

## 失败项（仅 hash + category）

### Original consensus

| id_hash12 | answerable | outcome | fail categories |
|---|---|---|---|
| `55515dc10c35` | true | answered | support, citation |
| `1931ea79adc1` | true | answered | citation |
| `22d252ae8204` | false | answered | support, unanswerable_refusal |

### Post-diag consensus

| id_hash12 | answerable | outcome | fail categories |
|---|---|---|---|
| `55515dc10c35` | true | answered | support, citation |
| `d2087ac961bd` | true | answered | citation |
| `1931ea79adc1` | true | answered | citation |
| `339c8aa2ffe9` | true | refused | false_refusal |

## 法官一致率

| Set | Support agree | Citation agree | Disagreements | Resolver |
|---|---|---|---|---|
| Original | 15/16 (0.9375) | 24/25 (0.9600) | 2 | Sol r3 → both `unsupported` |
| Post-diag | 13/14 (0.9286) | 14/20 (0.7000) | 7 | Sol r3 → all 7 `unsupported` |

Asset: [`assets-box-blind-20261105-judge-agreement.json`](./assets-box-blind-20261105-judge-agreement.json)

Post-diag 上 Kimi 对全部 citation 判 `supported`，与 Sol 分歧大；仲裁一律维持更严一侧。一致率本身应视为方法局限信号，而非产品通过证据。

> `false_refusal` 来自结构化 outcome（可答却 refused），不是 support/citation 语义审核失败；聚合 Answerable answer 已计入 14/15。

## Contamination

Post-diag predictions 在 original 失败诊断与 refusal prompt / 启发式改动之后采集，**不可当作独立盲测门禁**；仅作对照。Original predictions（SHA `830f80b2…`）仍是未污染基线。

## 与早期启发式诊断的关系

[`2026-11-05-box-blind-20-diagnosis.md`](./2026-11-05-box-blind-20-diagnosis.md) 中的 `scorer_false_negative` **未关闭**。分层对照（避免把不同预测/规则混为“会话方差”）：

| id_hash12 | 早期 diagnosis | 本轮 LLM consensus | 解释边界 |
|---|---|---|---|
| `55515dc10c35` | original 假阴性 | 同 original SHA 下仍 support/citation 失败 | 同一预测上的直接争议 |
| `d2087ac961bd` | original 假阴性 | original 本轮无失败；post-diag citation 失败 | post-diag 为另一套预测，不能单凭 hash 归因方差 |
| `1931ea79adc1` | 未覆盖 | original+post-diag citation 失败 | 扩大审核范围新发现，非推翻旧判 |
| `22d252ae8204` | 按正文语义偏假阴性 | original：不可答却 answered → support 强制 unsupported + refusal 失败 | 本轮规则与早期语义口径不同 |

两边同为 LLM、非人类金标。门禁口径以双法官+仲裁 consensus 为准。

## 局限

- LLM judge ≠ 人类审核；同组织编写题面与法官提示，存在同源偏差。
- 第二法官（Kimi）在 post-diag 上为 **全通过**（14/14 support、20/20 citation），与 Sol 分歧大；70% citation 一致率等于 Sol 正类比例，不能证明负例识别力。
- 第三 Sol 仲裁可见双方标签（非盲评），且与初判同为 Sol；post-diag 7/7 维持 Sol。独立会话≠错误相互独立；仲裁解决的是本次标签选择，不是金标准确性。
- 未做跨厂商付费 API 复审（spend 约束）。
- 启发式模块保留为 smoke/proxy，Sol R4 P1 仍为 known limitation。
