# blind-v4 报告只读审阅

- Reviewer：Sol High
- 日期：2026-11-05
- Verdict：**APPROVED**（文档审阅通过；v4 质量门禁仍为 **failed**）
- 审阅时仓库 HEAD：`b72cee0d311621000a4304284488ccbfde5caf0a`；报告采集 HEAD：`b03c7104f78a6ded9140b6705791d35b96d2cc07`。
- 对象：[v4 报告](../evaluation/2026-11-05-box-blind-20-v4.md)、[公开汇总 asset](../evaluation/assets-box-blind-20261105-v4-judged-summary.json)。只读对照仓外 `metrics-final.json`、[repair 第三次复审批准](2026-11-05-sol-under-citation-repair-rereview3.md)及采集 HEAD。

未发现阻断项或必须修改的 P1/P2 文案问题。

| 检查项 | 核验结果 |
| --- | --- |
| 私有信息边界 | 通过。逐段检查报告及完整 asset，未见私有题目、答案或引用正文；逐题信息仅为两条 `id_hash12`、answerable、outcome 与失败分类。asset 未携带 `question_results`。程序检查全部原始 question ID 均未出现在两份公开文件中；两条失败 hash 均与仓外 false_refusal 记录的 SHA-256 前 12 位一致。运行指纹、配置与费用为元数据。 |
| 门禁数字 | 通过。asset 的整个 `metrics`、`quality_gate` 与仓外文件分别完全相等，dataset/predictions 指纹、样本数及采集 code SHA 一致。报告八项门禁的数值和状态均与 asset 一致。Recall@5、MRR@10 均为 1.0；support 为 13/13、citation 为 30/30、unanswerable refusal 为 5/5，两项 review coverage 均为 1.0。 |
| Overall | 通过。answerable answer 为 **13/15 = 0.8667 < 0.90**，该项及 Overall 均明确标为 **failed**；answered 13、refused 7（5 正确拒答、2 误拒答）一致。对照表的 0.867 是三位小数展示，与主门禁表无矛盾。 |
| 默认关闭与批准范围 | 通过。报告第 4、15、65 行明确写出 repair 默认关闭已合入、v4 使用 shipped default（off）、未在本包试 opt-in 或调参，并明确否定由本结果推出默认开启可安全上线。asset 的配置也为 off。`b03c710` 的父提交为批准所审的 `b7dced8`，两者差异仅新增该批准报告；只读核对采集 HEAD，开关 unset 时返回 false，示例环境为 off。与 rereview3 的默认关闭批准及 opt-in 已知限制相符。 |
| 花费 | 通过。报告与 asset 均记本轮 reserved **0 → 49,160 microyuan**，即 **CNY 0.049160**；与 v3 收口累计 **CNY 2.684136** 相加恰为 **CNY 2.733296**。本轮与跨轮累计分开，订阅法官不计 ledger、draft 价格口径也已注明。v3 收口基数与既有 v3 报告及 rounds summary 一致。 |
| 服务已停 | 通过。报告明确记载采集后 stop-services、Java/AI 已停。审阅时只读运行 `ss -ltnp '( sport = :8080 or sport = :8000 )'`，两端口均无监听；进程检查也未见 Java、uvicorn、gunicorn 或 ai_service 服务进程。 |

本次为文档一致性审阅：费用核验限于公开记录与算术，采集配置核验限于报告、asset、批准记录及历史代码；未重放采集、重做法官仲裁或审计 SQLite 账本。服务检查证明审阅时状态，不追溯 stop-services 的历史执行过程。仓外文件仅用于数字、指纹及失败 hash 核对，未将私有逐题正文或原始 ID 写入审阅。

审阅开始工作树干净。唯一写入为本审阅文件；未修改实现、被审报告、asset 或仓外文件，未启动服务、调用 provider、重新跑 holdout、调参、提交或推送。

SOL_REVIEW_DONE verdict=APPROVED
