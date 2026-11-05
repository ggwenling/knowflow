# blind-v5 报告独立文档审阅

- Reviewer：Sol High；2026-11-05。
- 审阅 HEAD：`5d3ce88ba2a1bba4da25251a504c4c460fa5b43c`；采集 HEAD：`533ad7d1d8134bf9230244dd02066b77db75314b`。
- 对象：[v5 报告](../evaluation/2026-11-05-box-blind-20-v5.md)、[公开汇总资产](../evaluation/assets-box-blind-20261105-v5-judged-summary.json)。只读对照仓外 `metrics-final.json`、[default-on round2 批准](2026-11-05-sol-repair-default-on-rereview.md)及 Git 历史。
- **Verdict：APPROVED。** 未发现阻断性文档问题；此批准针对报告的准确性与信息边界，v5 质量门禁仍为 **failed**。

## 1. 信息边界

人工检查两个公开文件：仅见聚合指标、运行/配置/费用元数据、内容指纹及以 `id_hash12` 标识的失败分类；未发现私有题面、答案或引用正文。`cite-1=unsupported` 为引用序号和判定，未包含引用内容。

程序核对确认：仓外 `question_results` 未复制进公开资产，20 个原始 `question_id` 均未出现在两个公开文件中；失败对象仅含 `id_hash12 / answerable / outcome / categories`。四个失败 hash 均能对应仓外记录，其 answerable/outcome 一致，三项 false_refusal 集合完全一致。仓外 metrics 没有逐引用判定，故未据其声称独立重判第四项 citation 或法官一致性。

本次只读取指定仓外 metrics 作数字和 hash 核对，未读取私有题面、答案、引用正文或其他私有产物，未将原始题目 ID 写入工具输出或本报告。

## 2. 数字与门禁

程序逐字段比较：公开资产的完整 `metrics`、完整 `quality_gate` 及共有顶层元数据（版本、数据集标识/指纹、预测指纹、split、样本数）与仓外 metrics **完全一致**；采集 SHA 也一致。报告八项门禁的数值和状态全部匹配。

| 门禁 | Observed | Minimum | 状态 |
|---|---:|---:|---|
| Recall@5 | 1.000 | 0.85 | passed |
| MRR@10 | 1.000 | 0.75 | passed |
| Support | 1.000（12/12） | 0.90 | passed |
| Citation | 0.960（24/25） | 0.95 | passed |
| Unanswerable refusal | 1.000（5/5） | 0.90 | passed |
| Answerable answer | **0.800（12/15）** | **0.90** | **failed** |
| Support review coverage | 1.000 | 1.00 | passed |
| Citation review coverage | 1.000 | 1.00 | passed |
| **Overall** | | | **failed** |

20 题中 answered 12 / refused 8，后者为 5 正确拒答 + 3 误拒答，彼此自洽。v4 对照列的 13/15 → 0.867、2 项误拒答及其余聚合值与公开 v4 报告一致。报告没有将 default-on 安全批准或公开集 passed 写成 v5 达标。

## 3. default-on 与冻结边界

报告明确写明 repair 默认开启已合入，v5 在已发布默认 on 下采集、没有设置 off，并声明“一次性权威跑，未后调”“禁止用本题调参”“结果冻结为权威基线”；公开资产的 config/run 与此一致。

批准记录明确为 **APPROVED（default-on）**，针对实现 `87bcefd`。Git 核实 `533ad7d` 在其后仅新增该批准报告，没有实现差异；采集 HEAD 中 `answer_repair_enabled()` 对 unset/空值默认返回 true，仅显式关闭别名返回 false。当前审阅 HEAD 相对采集 HEAD 只新增本次两份评测文档，未改实现。因此批准与采集版本的对应关系清楚。

“未用 v5 调参”在现有文档声明与版本记录中没有发现矛盾；本次未重跑采集，也未独立审计完整执行历史或运行时环境，不能把文档审阅扩张为对所有未记录操作的证明。repair_attempt 为零不等于开关关闭，报告已说明 eligibility 未进入补问。

## 4. 花费与服务

报告与资产一致，使用十进制定点算术复核通过：

- 公开 seed：147,480 microyuan = **CNY 0.147480**。
- v5 增量：196,640 − 147,480 = 49,160 microyuan = **CNY 0.049160**。
- 本轮合计：0.147480 + 0.049160 = **CNY 0.196640**，未把本轮总额再次算作盲测增量。
- 项目累计：既有 **CNY 3.003676** + 本轮 **CNY 0.196640** = **CNY 3.200316**；既有累计、本轮与项目累计的口径清楚。

仓外 metrics 不含费用字段，本项验证为报告/资产一致性、换算与算术核对，未读取 SQLite 账本或独立重建历史支出。报告明确记载采集后已执行 stop-services、Java/AI 已停；本次 `ss -ltnp` 复核 **8080/8000 均无监听**，未启动服务或发起付费调用。

## 5. 非阻断文案建议与修改范围

“同一 ledger 先跑公开集（非盲测；调参/核对允许）”建议收窄为“同一 ledger 先跑公开集：development 可调参，holdout 仅核验冻结方案”，以贴合设计的 split 边界。该句当前存在表达歧义，未发现实际使用 holdout 或 v5 调参的证据，不构成阻断。

所有审阅对象保持只读；未修改实现、测试、原报告或汇总资产，未提交或推送。唯一写入为本审阅文件。未运行实现测试或重新评分；执行了 JSON 精确比较、门禁表核对、hash 核对、费用算术、Git 历史及监听状态检查。

SOL_REVIEW_DONE verdict=APPROVED
