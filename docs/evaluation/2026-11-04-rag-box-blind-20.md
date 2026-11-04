# RAG Box 盲测跑评（20 题）

## 运行信息（原始采集）

- 时间（Asia/Shanghai）：collection status 2026-11-05T00:07:04+08:00；正式门禁完成 2026-11-05T00:08:25+08:00。
- 仓库分支：`grok`；code SHA：`bf720e4393511e68f72304c276d7893ae729b23a`。
- 结果：正式门禁 **FAILED**（runner rc=1；聚合指标已写出）。
- 采集尝试 1 以 rc=1 / `ConnectError`（connection refused）结束，账本预留为 0 且未生成预测文件；重启 AI 后尝试 2 以 rc=0 完成 20 题。

## 数据集与来源

- 数据集：box-authored private pack；题包 questions SHA-256：`66c2d61e526026f60b0313f779cd3d9c866a57b3795fe60bf8275db419223c46`；corpus SHA-256：`f8ee1accc7dd3f20d1d982e379088557d6b3db87f630667a4ff03d5c375f15e4`。
- 转换后 runner dataset SHA-256：`7ff4e731ed21ae7ac0355516a067161d7846a64bfeb86cdb12a0ea50588aa96f`；样本量 n=20（15 可答、5 不可答）。这是同组织构建的私有包跑评，**不是负责人 Windows 盲测**。
- 出题：CodeBuddy kimi-k3.1-pro；校验：CodeBuddy deepseek-v4.1-flash（fixes=0）；runner：Codex luna-max。
- 模型：`deepseek-flash+BAAI/bge-m3`。
- schema SHA-256：`20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`；config SHA-256：`7e97d46b338042fdbb03b5570d5132350ab4864b64e5825404c85afe3176c220`；prompt SHA-256：`3115dbaedeb7b5a650e1a1b332dd243d6cb5ffe4fbc22217c61deb2acf647f6b`。
- quality config SHA-256：`e44c9beaf3b15ab4fe5b3ee9680dd891b96cf73a6bf2d4955b5750e7722e223b`。
- runtime `run-real-collect.py` SHA-256：`438211d779f9edb63ca394c0f8f3c8505297edb9e689a22516d5314f5e6dd6e8`；其 stale offpeak 价格标记已更正为 peak-draft，采集逻辑未改。

## 价格与账本（原始采集）

- 价格/策略：**draft peak**；deepseek-flash input 0.2、output 0.8 CNY / 1M tokens；`verified_by=draft-not-owner-signed`。负责人已授权本 box 跑使用草稿价，价格未签核。
- `PRICE_FILE.draft.json` SHA-256：`674baf7fabea92a28882b489fbae1667fa410e7f72f231eea2a1be30f2701b67`；`POLICY_FILE.draft.json` SHA-256：`0399b2ae841d3dad5a3ae3c61a9dd67d8efae6d4c4d71e7adea76b144dbedd4d`。
- 账本：预留 49,160 microyuan = **CNY 0.049160**；limit 10,000,000 microyuan = CNY 10.00。

## 原始门禁结果（启发式 review proxy）

| 门禁 | 阈值 | 实测 | 结果 |
|---|---:|---:|---|
| Recall@5 | ≥0.85 | 1.0000 (30/30 spans) | **PASSED** |
| MRR@10 | ≥0.75 | 1.0000 | **PASSED** |
| Supported answer rate (script review proxy) | ≥0.90 | 0.6875 (11/16) | **FAILED** |
| Citation accuracy (script review proxy) | ≥0.95 | 0.7600 (19/25) | **FAILED** |
| Unanswerable refusal rate | ≥0.90 | 0.8000 (4/5) | **FAILED** |
| False refusal rate | ≤0.10 | 0.0000 (0/15) | **PASS** |
| Review coverage | 100% | support 100% (16/16); citation 100% (25/25) | **PASS** |

总体门禁失败：支持率、citation accuracy 与不可答拒答率未达阈值。n=20 中只有 5 题不可答；拒答门禁对单题高度敏感。

审核覆盖为脚本填充的 16/16 答案与 25/25 citation。`fill-box-blind-review.py` 使用自动启发式 reviewer `know-bot-box-blind-reviewer`，这不是独立人工标注。

### 原始失败摘要（仅 hash 前缀）

- `sha256:22d252ae8204` | fail | citation + support + refusal
- `sha256:55515dc10c35` | fail | citation + support
- `sha256:7ee3f7e0772b` | fail | citation + support
- `sha256:d2087ac961bd` | fail | citation + support
- `sha256:e224b8d1b48d` | fail | citation + support

聚合 JSON：`docs/evaluation/assets-box-blind-20261104-metrics.json`（predictions SHA `830f80b2…`）。

## 诊断（2026-11-05，独立 Sol High）

详见 `docs/evaluation/2026-11-05-box-blind-20-diagnosis.md`。

- 独立 LLM 复审：5/5 失败题判定为 **scorer_false_negative**（6 条 unsupported citation 均为假阴性）。
- `product_defect: 0`（按正文语义）；同时指出 `outcome=answered` 与正文“信息不足”的**结构化状态不一致**，建议同时修 scorer 与 `answering_refusal` 状态对齐。
- 根因抽象：`sentence_around` 作用域过宽、精确子串不识别同义/推论、support 机械继承 citation 失败。

## 修复

1. **Scorer**：新增 `evaluation/runner/heuristic_review.py`；`fill-box-blind-review.py` 复用。分句/归属作用域、bigram soft match、support 独立判定；不可答题不得标 supported。单测 `evaluation/smoke/test_heuristic_review.py`。
2. **Refusal 状态对齐**：`services/ai/src/knowflow_ai/answering.py` system prompt 明确：核心所问无法被资料充分支持时，即使有背景也必须 `has_answer=false`。单测覆盖 prompt 约束。

## 原始预测 + 新 scorer 重打分（非重采）

冻结 predictions SHA `830f80b2…`，仅替换 review 脚本后正式门禁：

| 门禁 | 原始启发式 | 新 scorer 重打分 | 结果 |
|---|---:|---:|---|
| Recall@5 | 1.0000 | 1.0000 | PASS |
| MRR@10 | 1.0000 | 1.0000 | PASS |
| Support proxy | 0.6875 | **0.1250 (2/16)** | FAIL（未达 0.90） |
| Citation proxy | 0.7600 | **0.4400 (11/25)** | FAIL |
| Unanswerable refusal | 0.8000 | 0.8000 | FAIL（预测未变） |
| False refusal | 0.0000 | 0.0000 | PASS |

摘要：`docs/evaluation/assets-box-blind-20261105-original-rescored-summary.json`。冻结预测重打分数字见上表；不把 proxy 变化单独等同产品质量通过；拒答需产品侧重采。不把 proxy 上涨单独等同于产品质量已通过。

## 诊断后重跑（已污染，仅一次）

- 时间（Asia/Shanghai）：2026-11-05T00:56–01:00 左右；正式门禁随后完成。
- 分支 `grok`；采集时 `git rev-parse` code SHA 仍为 `374b756…`，但工作树已含上述未提交修复（AI 进程加载了更新后的 `answering.py`）。
- **盲测已因诊断复审而污染**；本重跑不可再当作未泄露盲测。
- predictions SHA：`71d8fc2e04436d4b47b073d8cc825ac4d36b594080208c5d7b0c13ef907cc107`。
- 账本预留 **CNY 0.049160**（新 ledger `box-blind-20-postdiag-*`）；draft peak 同前。
- 聚合：`docs/evaluation/assets-box-blind-20261105-postdiag-metrics.json`。

| 门禁 | 阈值 | 重跑实测 | 结果 |
|---|---:|---:|---|
| Recall@5 | ≥0.85 | 1.0000 | **PASSED** |
| MRR@10 | ≥0.75 | 1.0000 | **PASSED** |
| Supported answer rate (script review proxy) | ≥0.90 | 0.1429 (2/14) | **FAILED** |
| Citation accuracy (script review proxy) | ≥0.95 | 0.4500 (9/20) | **FAILED** |
| Unanswerable refusal rate | ≥0.90 | **1.0000 (5/5)** | **PASSED** |
| False refusal rate | ≤0.10 | 0.0667 (1/15) | **PASS** |
| Review coverage | 100% | support 14/14; citation 20/20 | **PASS** |

### 重跑失败摘要（仅 hash 前缀）

- `sha256:55515dc10c35` | fail | citation + support
- `sha256:d2087ac961bd` | fail | citation + support
- `sha256:7ee3f7e0772b` | fail | citation
- `sha256:1931ea79adc1` | fail | citation + support
- `sha256:339c8aa2ffe9` | fail | false_refusal（可答题被拒；未破 false-refusal 门禁）

拒答门禁在更新后的污染重跑中观察到通过（含原 `22d252ae8204`）；见实现指纹说明。support/citation 在**新采样**上仍失败：模型改写后的答案与引用组合与冻结预测不同，启发式仍有缺口；不宣称产品已达门禁。

## 公开 seed-v2 回归（development，廉价）

- 同 draft peak；预留 **CNY 0.098320**。
- 结果对比既有 development 预测：answered/refused = 31/9（与基线相同）；false refusal rate 0.0；unanswerable refusal rate 1.0。
- 未见可答误拒答抬升；未改写已入库的 seed-v2 review JSON。

## 花费汇总（本诊断/修复轮）

| 项目 | CNY |
|---|---:|
| 原始 box 盲测（既有） | 0.049160 |
| 诊断后 box 重跑 | 0.049160 |
| 公开 development 回归 | 0.098320 |
| 本轮新增合计 | ≈0.147480 |
| 项目累计（含更早公开 eval ≈0.074） | ≈0.27（低于 soft 8 / hard 10） |


## 实现指纹（诊断后工作树）

采集时 `git rev-parse` 仍为 `374b756…`，下列内容指纹用于核对实际加载的修复（不等同于 collector 记录的旧 `prompt_sha256=3115dbae…`，该字段未随 system prompt 字符串更新）：

| 产物 | SHA-256 |
|---|---|
| `evaluation/runner/heuristic_review.py` | `b5a5b905a99f0a10e3c2ad5df59dbc9b48d4c3562ed9350c9e5b19c518dee521` |
| `services/ai/src/knowflow_ai/answering.py` | `ce8ac8b86688b4c703ddd1852b9ce60700de09b1dc141abe1abb55af197193d6` |
| system prompt 关键句拼接指纹 | `c75390c145088929429a3aea6a26448b7122a954effdd4798a62e878ee7e7637` |
| 仓外 `fill-box-blind-review.py` | `87780505bb93eade585f6a1c06c0cf3388c534706dd24b59ef823cd3e1f50348` |

拒答：更新后的**该次**污染重跑观察到不可答 5/5 拒答；在缺少与 collector `prompt_sha256` 同步的前提下，不把该变化单独断言为唯一因果。

## 局限与文件卫生

- 同组织出题并使用同语料公开集；≠负责人 Windows blind。
- 价格为 draft peak、非 owner-signed；support/citation 仍为脚本启发式 proxy。
- 诊断后重跑已污染盲测；原始结果与重跑结果均保留。
- `git ls-files` 对 `.blindtest/` 与 private-blind 路径检查为 0 命中；公开聚合 JSON 的 `question_results` 仅保留 id_hash、outcome、category。
