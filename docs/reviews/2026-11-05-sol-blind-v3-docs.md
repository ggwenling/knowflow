# Prune 公开门禁 + blind-v3 文档审阅（2026-11-05）

**Verdict: CHANGES_REQUESTED**

审阅版本：`85a4eb4`。范围为 `2026-11-05-citation-fix.md` 的剪枝轮次增补、`2026-11-05-box-blind-20-v3.md`、v3 judged summary JSON 及 Sol P1c 复审记录。仅新增本报告，不改实现、测试或被审文档，不 commit/push。

## P1

1. **共享账本的两个花费时点未标明，汇总字段容易被当成当前总额或 v3 单包费用。** [v3 JSON 第 139 行](../evaluation/assets-box-blind-20261105-v3-judged-summary.json#L139) 的 `spend_cny_ledger_citation_fix: 1.268328`，对应仓外 v3 `judged/predictions.collection-status.json` 中的采集结束快照：paid reservations **516** 笔，`reserved_microyuan=1268328`。[citation-fix 第 81 行](../evaluation/2026-11-05-citation-fix.md#L81) 的“约 CNY 2.68”则与本次只读 SQLite 核验一致：paid reservations **1092** 笔，`SUM(microyuan)=2684136`，即 **CNY 2.684136**。两个数字各有依据，但 [v3 花费说明](../evaluation/2026-11-05-box-blind-20-v3.md#L49) 只链接共享账本，未解释 JSON 保留的是较早快照，读者无法直接判断二者关系。

   建议将 JSON 字段改名或补充元数据，明确“v3 采集结束时的共享账本累计预留”，并在花费段写明：**v3 采集结束快照 CNY 1.268328（516 笔）；报告更新时累计 CNY 2.684136（1092 笔），两者均为共享账本累计预留，不能当作 v3 单包实付。** 为 citation-fix 原有 CNY 0.54076 / 220 笔及最新累计值标注阶段或统计时点；保留 draft 价格/策略、订阅法官与预留的区别。无需新增 real collect 来修正文案。

## 核验结果

- **私有内容：通过。** 四份对象未发现私有题面、金标答案、预测正文、quote、证据原文或 span 位置。v3 失败项仅公开 hash、answerable、outcome、错误类别。另以脚本将私有 questions/corpus/review 中抽取的 50 个长度至少 20 字符的正文值与四份对象做完整子串检查，命中为 0；该检查不替代人工检查，也不证明任意改写片段不存在。仓库未跟踪 `.blindtest*` 文件，根目录 `.blindtest/` 与 `.blindtest-v3/` 内容均命中 gitignore。
- **公开 prune 门禁：通过。** 与仓外 `/workspace/knowflow-runtime/reports/citation-fix-20261105/judged-dev-prune/metrics-final.json`、`judged-holdout-prune/metrics-final.json` 核对：development `d077e6a` 为 support **31/31**、citation **40/40**、可答 **31/31**、不可答拒答 **9/9**；holdout `502bc9f` 为 support **19/19**、citation **28/28**、可答 **19/19**、不可答拒答 **1/1**。两轮 gate 均为 **passed**，表内数值及采集 code SHA 一致。表格没有将这些结果冒称为 `f00a17d` 上重新采集的结果。
- **v3 门禁：通过核对，评测结论仍是 failed。** 公开 JSON 的整个 `quality_gate` 与仓外 `/workspace/knowflow-private-blind/2026-11-05-v3/judged/metrics-final.json` 完全相同，所有公开 `metrics` 字段逐项相同。Recall@5 **38/39=0.9744**，MRR@10 **1.000**，support **11/12=0.9167**，citation **28/29=0.9655**，不可答拒答 **5/5**，可答作答 **12/15=0.800**，两项 review coverage 均为 **1.000**。仅 answerable answer 未达 0.90，overall **failed**。4 条失败记录与 sidecar 和最终 consensus 重建结果完全一致；outcomes 为 answered **12** / refused **8**。
- **完整性与法官归属：通过。** 重算 v3 questions、corpus、最终 predictions 文件 SHA-256，均与公开值一致；dataset、code、prompt SHA 及 model 与最终 metrics 一致。两法官实际存在 **5** 道 support 分歧、**2** 条 citation 分歧；仲裁文件的 5 道 support 均裁为 supported，汇总 consensus 为 11 supported / 1 unsupported。secondary 实际标识为 `codebuddy-deepseek-v4.1-flash`，与公开说明一致。
- **盲测边界：通过。** v3 表明确写 overall failed，解释段写“禁止用本题调参”及冻结权威基线；citation-fix 增补同样写 v3 answerable failed。未发现宣称 v3 整体通过或可用于调参的文字。此结论针对公开表述及所核对产物，不证明历史全部操作，也不以跨题集的 v2/v3 差异单独证明因果改善。
- **P1c 复审：通过引用核对。** 既有记录为 **APPROVE**，目标提交与 v3 采集 HEAD 同为 `f00a17db144f7e579acce35d73283af91e8d7964`。其中测试通过数为既有复审记录，本次文档审阅未重跑实现测试。
- **预算边界：数字可核对，披露需修正。** 当前账本 hard limit 为 **CNY 10**；累计预留 CNY 2.684136 低于文中 soft/hard **8/10**，但超过所述项目软目标 **2**。相对原阶段 CNY 0.54076，累计增加 **CNY 2.143376**，也超过期望额外 <1。法官订阅已与 DeepSeek/SiliconFlow 预留区分；这些证据不能当作供应商最终结算账单。

未发现 P0；唯一阻塞项为上述花费披露 P1，修正不涉及实现或门禁重跑。

SOL_REVIEW_DONE verdict=CHANGES_REQUESTED
