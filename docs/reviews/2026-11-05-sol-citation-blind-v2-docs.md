# Citation-fix + blind-v2 文档独立审阅（2026-11-05）

Verdict CHANGES_REQUESTED

审阅范围：两份报告、`assets-box-blind-20261105-v2-judged-summary.json` 及 `.gitignore` 的 `/.blindtest*/` 变更。仅新增本审阅结论，未修改被审材料或业务代码，未 commit/push。

## P0

- 无。审阅对象未公开私有题面、答案、quote、证据原文或 span 位置；失败项仅含 hash、可回答性、outcome 和错误类别。

## P1

1. **公开 BEFORE 的 citation 分子、分母错误。** [citation-fix 报告第 24 行](../evaluation/2026-11-05-citation-fix.md#L24) 写 `1.000 (37/37*)`，但仓外 `/workspace/knowflow-runtime/reports/citation-fix-20261105/judged-before/metrics-final.json` 中 `citation_supported_count`、`citation_reviewed_count`、`citation_count` 均为 **33**；双法官也均评审了 33 条引用。37 是该 split 的 `gold_evidence_span_count`，并非 BEFORE 实际引用数。请改为 **1.000 (33/33)**，同步修正脚注；保留 BEFORE 的 `incomplete`。AFTER 实际为 37/37，可补上以明确两轮分母差异。此错误不改变比例，但破坏门禁样本量的可核验性。

2. **v2 门禁表标题错误归属法官。** [blind-v2 报告第 18 行](../evaluation/2026-11-05-box-blind-20-v2.md#L18) 写“Kimi 全同意”，与同文第 11 行、汇总 JSON 的 `judges.secondary` 以及仓外 `judged/judgements-kimi.json` 的实际 `judge=codebuddy-deepseek-v4.1-flash` 冲突。文件名保留 kimi 不代表实际使用 Kimi。请将标题改为“LLM consensus：Sol High + CodeBuddy DeepSeek v4.1 Flash”；保留 Kimi 429 回退说明。双法官 support 11/11、citation 25/25 标签确实完全一致，无需仲裁。

## P2

- 无其他阻塞或次要修改项。

## 核验结论

- **指标：** v2 汇总 JSON 的整个 `quality_gate` 与仓外 `/workspace/knowflow-private-blind/2026-11-05/judged/metrics-final.json` 完全相同，公开的全部 `metrics` 字段逐项一致；4 个失败 hash 与 sidecar 对应。Recall@5=1.000、MRR@10=0.9667、support=11/11、citation=25/25、不可答拒答=5/5、可答作答=11/15（0.7333），overall **failed**。公开 BEFORE/AFTER/holdout 的其余表内数值和状态与 `judged-before/metrics-final.json`、`judged-after/metrics-sol.json`、`judged-holdout/metrics-final.json` 一致；AFTER 两份法官文件的判定标签相同。
- **盲测使用边界：** 两份报告均明确 v2 失败、冻结结果、不得重跑或针对题目调参，后续修复仅在公开 seed 上验证；未发现宣称 v2 整体通过或授权用 v2 调参的文案。该结论针对文档表述，不将其视为对历史全部操作的独立证明。
- **SHA：** 已重算 v2 questions/corpus 及公开三轮、v2 四份 predictions 的文件 SHA-256，均与报告/指标相符。v2 dataset、code、prompt SHA 和 model 与仓外最终指标及汇总 JSON 一致；公开各轮的 code/prompt SHA 与各自指标相符。
- **花费：** 以只读方式核对指定 SQLite 账本：paid reservations **220** 笔，合计 **540760 microyuan = CNY 0.54076**，账本 hard limit 为 CNY 10。报告明确这是共享账本的预留总额，并区分订阅法官费用、draft 价格/策略，不应解读为 v2 单包实付或供应商最终账单。
- **gitignore：** `git check-ignore -v --no-index` 确认 `.blindtest/`、`.blindtest-v2-backup/`、`.blindtest.bak/`、`.blindtest-20261105/` 下的文件均命中第 32 行；`git ls-files '.blindtest*'` 无已跟踪文件。规则覆盖仓库根目录的 `.blindtest*` **目录**及其内容；尾随 `/` 不覆盖 `.blindtest*.zip` 等普通文件，前导 `/` 也限定根目录。当前目录备份场景已覆盖。

SOL_REVIEW_DONE verdict=CHANGES_REQUESTED
