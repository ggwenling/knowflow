# RAG Box 盲测跑评（20 题）

## 运行信息

- 时间（Asia/Shanghai）：collection status 2026-11-05T00:07:04+08:00；正式门禁完成 2026-11-05T00:08:25+08:00。
- 仓库分支：`grok`；code SHA：`bf720e4393511e68f72304c276d7893ae729b23a`。
- CI：待推送后补。
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

## 价格与账本

- 价格/策略：**draft peak**；deepseek-flash input 0.2、output 0.8 CNY / 1M tokens；`verified_by=draft-not-owner-signed`。负责人已授权本 box 跑使用草稿价，价格未签核。
- `PRICE_FILE.draft.json` SHA-256：`674baf7fabea92a28882b489fbae1667fa410e7f72f231eea2a1be30f2701b67`；`POLICY_FILE.draft.json` SHA-256：`0399b2ae841d3dad5a3ae3c61a9dd67d8efae6d4c4d71e7adea76b144dbedd4d`。`.blindtest/config` 中副本与 runtime draft 文件一致。
- 账本：预留 49,160 microyuan = **CNY 0.049160**；limit 10,000,000 microyuan = CNY 10.00；剩余 9,950,840 microyuan = CNY 9.950840。priced reservations=20，zero-price reservations=30。低于本次 1 CNY 停止线及项目 soft 8 / hard 10 CNY。

## 门禁结果

| 门禁 | 阈值 | 实测 | 结果 |
|---|---:|---:|---|
| Recall@5 | ≥0.85 | 1.0000 (30/30 spans) | **PASSED** |
| MRR@10 | ≥0.75 | 1.0000 | **PASSED** |
| Supported answer rate (script review proxy) | ≥0.90 | 0.6875 (11/16) | **FAILED** |
| Citation accuracy (script review proxy) | ≥0.95 | 0.7600 (19/25) | **FAILED** |
| Unanswerable refusal rate | ≥0.90 | 0.8000 (4/5) | **FAILED** |
| False refusal rate | ≤0.10 | 0.0000 (0/15) | **PASS** |
| Review coverage | 100% | support 100% (16/16); citation 100% (25/25) | **PASS** |

总体门禁失败：支持率、citation accuracy 与不可答拒答率未达阈值。n=20 中只有 5 题不可答；拒答门禁对单题高度敏感，每题对应 20 个百分点，≥0.90 实际要求 5/5。

审核覆盖为脚本填充的 16/16 答案与 25/25 citation。`fill-box-blind-review.py` 使用自动启发式 reviewer `know-bot-box-blind-reviewer`，这不是独立人工标注；因此支持率与 citation accuracy 应按脚本 review proxy 解读，不能视为人工复核结论。

### 失败摘要

只列题目 SHA-256 前缀、pass/fail 与失败类别，不含题面、答案、quote 或 span。类别可重叠。

- `sha256:22d252ae8204` | fail | citation
- `sha256:55515dc10c35` | fail | citation
- `sha256:7ee3f7e0772b` | fail | citation
- `sha256:d2087ac961bd` | fail | citation
- `sha256:e224b8d1b48d` | fail | citation
- `sha256:22d252ae8204` | fail | refusal
- `sha256:22d252ae8204` | fail | support
- `sha256:55515dc10c35` | fail | support
- `sha256:7ee3f7e0772b` | fail | support
- `sha256:d2087ac961bd` | fail | support
- `sha256:e224b8d1b48d` | fail | support

失败题目类别计数：retrieval 0，refusal 1，support 5，citation 5，other 0；unsupported citations 6/25，出现在 5 题。检索未达标题数为 0。

## 局限与文件卫生

- 同组织出题并使用同语料公开集，存在组织内标注/语料熟悉度偏差；结果不等价于负责人 Windows blind。
- 价格为 draft peak、非 owner-signed；复核是脚本启发式，不是人工独立复核。
- `git ls-files` 对 `.blindtest/` 与 private-blind 路径检查为 0 命中；公开聚合 JSON 的 `question_results` 仅保留 id hash、outcome、category。
