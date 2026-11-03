# 真实公开集评测报告：qingzhu-seed-v2-reviewed

- 报告时间（Asia/Shanghai）：2026-11-04 01:10 CST
- 代码 SHA（采集时 `run.code_sha`）：`d5e1eb7f3a0094481a26cb6465ed57537099ee03`
- 报告提交时分支 HEAD：`d5e1eb7f3a0094481a26cb6465ed57537099ee03`（推送后以本文件所在提交为准）
- CI：`d5e1eb7` Web engineering E2E **success**（python-contract / web / evaluation-e2e / java）
- 数据集：`evaluation/data/seed-v2-reviewed`（公开合成集；**非盲测**）
- 模型：Embedding `BAAI/bge-m3`（SiliconFlow）；LLM `deepseek-flash`（DeepSeek）
- schema_sha256：`20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`
- config_sha256：`8ffa919a184adbc1af0562764079b76098060cd209fe24ad6330f0bd8d4c304e`
- prompt_sha256：`3115dbaedeb7b5a650e1a1b332dd243d6cb5ffe4fbc22217c61deb2acf647f6b`

## 价格 / 策略证据（草稿，非负责人签核）

| 文件 | 说明 | sha256 |
|---|---|---|
| `PRICE_FILE.offpeak.draft.json`（仓外 runtime） | DeepSeek **offpeak** 草稿价；`verified_by=draft-not-owner-signed`。采集时北京时间约 01:00，落在常见闲时窗 00:30–08:30，故选用 offpeak，**未等待**闲时切换。 | `e55c132c6435858bdee92fea4761396a931fbcf8af8fb52e1fee354c8601518d` |
| `POLICY_FILE.draft.json`（仓外 runtime） | token / payload 上界草稿；同上未签核。 | `0399b2ae841d3dad5a3ae3c61a9dd67d8efae6d4c4d71e7adea76b144dbedd4d` |

**负责人签核前不得把上述草稿当作正式 PRICE/POLICY。** 账本按草稿字符串计费预留；与供应商实际账单可能不一致。

## 花费（BudgetLedger 预留，microyuan→CNY）

共享账本摘要（整数微元，保守预留，失败不退款）：

```json
{"limit_microyuan": 10000000, "reserved_microyuan": 73740, "remaining_microyuan": 9926260, "paid_reservations": 60, "zero_price_reservations": 80}
```

| 项目 | 值 |
|---|---:|
| 累计预留 | **0.07374 CNY**（73740 microyuan） |
| paid / zero-price 预留次数 | 60 / 80 |
| soft stop / hard | 8 / 10 CNY |
| 距 soft stop | 充足（未触发） |
| 真实付费调用 | 是（SiliconFlow embedding + DeepSeek LLM） |
| 盲测 | **未触碰**（盲测仅在负责人 Windows `D:/konwflow/.blindtest/`） |

## 指标对照门槛

门槛来源：Recall@5 ≥0.85，MRR@10 ≥0.75，support ≥0.90，citation ≥0.95，unanswerable refusal ≥0.90，false refusal ≤0.10（以 answerable_answer_rate ≥0.90 等价报告），review coverage 100%。

### development（40 题）

| 指标 | 门槛 | 实测 | 结果 |
|---|---:|---:|---|
| Recall@5 | ≥0.85 | 1.0 | passed |
| MRR@10 | ≥0.75 | 0.9785 | passed |
| support | ≥0.90 | 1.0 | passed |
| citation | ≥0.95 | 1.0 | passed |
| unanswerable refusal | ≥0.90 | 1.0 | passed |
| false refusal | ≤0.10 | 0.0 | passed |
| review coverage（support/citation） | 100% | 1.0 / 1.0 | passed |

质量门：**passed**。明细见 `assets-real-20261104-development-metrics.json`。

### holdout（20 题）

| 指标 | 门槛 | 实测 | 结果 |
|---|---:|---:|---|
| Recall@5 | ≥0.85 | 1.0 | passed |
| MRR@10 | ≥0.75 | 1.0 | passed |
| support | ≥0.90 | 1.0 | passed |
| citation | ≥0.95 | 1.0 | passed |
| unanswerable refusal | ≥0.90 | 1.0 | passed |
| false refusal | ≤0.10 | 0.0 | passed |
| review coverage（support/citation） | 100% | 1.0 / 1.0 | passed |

质量门：**passed**。明细见 `assets-real-20261104-holdout-metrics.json`。

## 审核说明

- 公开合成集的支持/引用审核由 `know-bot-public-seed-reviewer` 对照题面 `reference_answer` / gold quote 与检索 span 正文完成；审核包与原始预测保留在 box 运行时目录，**未**把题面或模型答全文写入本仓库。
- 本报告只提交聚合指标与花费，不含盲测内容。

## 运行方式摘要

1. 用户态 PG :55432 + MinIO :59000 + Java :8080。
2. `real_service.py` 绑定 127.0.0.1:8000，读取仓外 PRICE/POLICY 草稿与 `DEEPSEEK_API_KEY` / `EMBEDING_KEY`。
3. `evaluation/collector` 采集 development，再采集 holdout；累计账本同一文件。
4. `runner_v2.evaluate(..., quality_config_path=..., review_path=...)` 出正式门禁。

## 结论

公开集 development + holdout **均达到质量门槛**；本会话真实预留花费 **≈0.074 CNY**，远低于 soft 8 / hard 10。无需本轮改进迭代。待负责人签核正式 PRICE/POLICY 后，可用同一流程复跑并替换草稿声明。盲测请负责人按 `docs/evaluation/windows-blind-eval-runbook.md` 在本地执行。

## 文档修订与审阅

- Windows 盲测 runbook 在 `b8a8a60` 按真实 CLI/`<repo>/.blindtest` 路径修订；Sol High 复审 `docs/reviews/2026-11-04-sol-b8a8a60.md`：**APPROVED（限 F1–F4）**。
- 公开集指标报告本体审阅见 `docs/reviews/2026-11-04-sol-cf923ba.md`（报告与 assets 通过；当时 runbook 为 CHANGES_REQUESTED，已关闭）。
