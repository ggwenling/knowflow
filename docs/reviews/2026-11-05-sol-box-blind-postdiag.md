# Box 盲测诊断、修复与报告更新：独立审阅

- Verdict: **CHANGES_REQUESTED**
- Findings: P0 = 0；P1 = 2；P2 = 2。
- 日期：2026-11-05（Asia/Shanghai）。
- 审阅基线：`grok`，HEAD `374b75651ffbbd86763858a4dfc25a7513716171`，审阅对象为 brief 指定的未提交工作树及两份仓外文件。
- 边界：未参与实现或重跑采集；未读取 `.blindtest/` 或 private-blind 的题面、答案、quote、预测正文；未调用模型或重跑数据集。本文所有复现文本均为新建合成样例。只新增本审阅文档，不修改代码，不 commit/push。

报告对原始结果、冻结预测重打分和污染重跑的区分清楚，主要数字与资产一致，拒答 prompt 也落实了 brief 的文字要求。但新 scorer 存在可直接复现的误接受，且 support 仍依赖 citation 的全通过/至少一条通过条件。因此，冻结预测的 proxy 分数上涨不能据此认定 scorer 已有效修复；以下 P1 阻断批准。

## Findings

### P1-1：bigram fallback 把关键数值错误、否定含义相反的 claim 判为 supported

位置：`evaluation/runner/heuristic_review.py:165–194`，尤其 `170–188`；测试缺口位于 `evaluation/smoke/test_heuristic_review.py:20–31`。

`_soft_grounded` 只要求 bigram coverage ≥ 0.55，并再检查任意一个 bigram 存在于证据；后一个条件无法排除相同主题中的事实矛盾。该分支没有核验数值、否定、主体等关键事实是否一致。

直接调用当前实现的结果：

| 合成 claim | 合成 evidence | bigram coverage | `grounded` / `citation_supported` |
|---|---|---:|---|
| 申请人年龄必须达到80周岁 | 申请人年龄必须达到18周岁。 | 0.7500 | True / True |
| 申请人无需提交有效身份证明原件 | 申请人必须提交有效身份证明原件。 | 0.7857 | True / True |

`citation_supported` 的调用方式为：`citation_supported(claim + '[s]', 0, claim + '[s]', evidence)`。这些是事实冲突，并非同义改写；仅凭词面接近接受它们，会直接抬高 citation proxy，也会传导到 support。现有负例只使用完全无关的两个主题，无法检验这种误接受。

建议：soft match 不应单独授予语义 supported；至少对关键数值、否定及事实归属增加可靠约束，不能确认时保留 unsupported 或交由独立语义审阅。补充同主题数值错误、否定翻转、主体互换的负例，同时保留真正同义改写的正例。修复后重新审视评分结论，不能只凭更高通过率宣称修复有效。

### P1-2：support 仍由 citation 门控，且全通过时绕过整答核验

位置：`evaluation/runner/heuristic_review.py:227–247`，尤其 `237–245`；相关测试为 `evaluation/smoke/test_heuristic_review.py:34–38`；报告对应 `docs/evaluation/2026-11-04-rag-box-blind-20.md:62,78`。

函数在 citation 全部通过时立即返回 supported，完全不核验回答的其余事实、reference 或联合证据；在 citation 全部失败时，即使联合证据完整覆盖整答，也因 `cite_supported >= 1` 返回 unsupported。这不符合诊断提出的整答与联合证据独立判定要求。

两个合成复现：

```python
support_judgement(
    '档案保管期为五年。[a]月球由玻璃制造。',
    [True], '档案保管期为五年', ['档案保管期为五年。'],
)
# 实测 'supported'；第二句没有证据。

support_judgement(
    '档案保管期为五年。', [False, False],
    '档案保管期为五年。', ['档案保管期为五年。'],
)
# 实测 'unsupported'；这里固定局部判定失败，以单独检验 support 是否独立。
```

现有名为 `test_support_can_use_the_union_of_cited_evidence_after_one_local_failure` 的测试，证据只有基础费用和无关说明，并没有支持总额的事实；测试仍要求 supported。它既未证明联合证据足够，也未覆盖所有局部引用失败而整答有支持的情况。

建议：依据整答的重要事实与联合证据判断 support，citation 的结果作为独立维度记录；不要以全通过直接代替整答核验，也不要以至少一条通过作为整答成立的前提。补充未引用的无依据断言、联合证据完整但局部归属判定失败等测试。报告中“support 独立判定”和“说明 scorer 修复有效”应在完成验证后再成立。

### P2-1：并列句末 marker 的归属算法没有正确形成同一引用簇，测试只检查非空

位置：`evaluation/runner/heuristic_review.py:57–95`；`evaluation/smoke/test_heuristic_review.py:10–17`。

合成回答：`仓库每日清晨开门，访客必须提前预约。[src-a][src-b]`。按当前 helper 声明的“按顺序分配分句”语义，应分别归到前、后两个分句；实际：

```text
attributed_clause(answer, 0) -> 访客必须提前预约
attributed_clause(answer, 1) -> [src-a]
```

`_marker_attach_start` 跳过句号和空白，却不跨过前一个 marker，导致两个紧邻 marker 的 attach 不同，无法形成预期 cluster。第二个 marker 的 lead 甚至包含第一个 marker。现有测试对这个 helper 仅断言非空，因此两个错误结果都能通过；其 citation 正例还预先传入各自分句作为 claim，没有检验真实 collector 的 claim 形态。

用仓库 `evaluation.collector.prediction._claim` 生成相同回答的 claim，两条均为 `[src-a][src-b]`。当前 scorer 对任一 marker 分别传入“仓库每日清晨开门。”或“访客必须提前预约。”都返回 True：marker-only 的整答回退与半数片段阈值掩盖了归属错误。这里没有要求所有并列引用都覆盖整句，而是指出当前实现没有做到其声明的分句归属，也无法据此排除错引。

建议：明确紧邻 marker 的簇及内容范围，验证 helper 的精确返回值；使用 collector 实际生成的 claim 增加正确归属、错误归属和无关引用测试。不能用单纯 `assert attributed_clause(...)` 证明归属正确。

### P2-2：重跑元数据仍沿用旧 prompt 指纹，缺少绑定实际修复版本的证据

位置：`docs/evaluation/assets-box-blind-20261105-postdiag-metrics.json:6–11`；仓外 `collection-status-summary.json:11–16`；报告 `docs/evaluation/2026-11-04-rag-box-blind-20.md:83,107`。

报告说明 AI 进程加载了已修改的拒答 prompt，但原始资产、重跑资产和重跑采集摘要中的 `prompt_sha256` 均为同一个 `3115dbae…`。重跑 `code_sha` 也仍指向未包含修复的 HEAD，报告虽诚实说明了工作树未提交，却没有补充实际 prompt 或采集工作树的内容指纹。仓库 collector README 第 15 行要求记录实际实现及 prompt 指纹。

这不能证明 prompt 没有加载，但现有元数据无法独立核实重跑究竟使用了哪个 prompt；因此也不足以支持报告将拒答变化直接归因为 prompt 对齐。

建议：保留原始采集与冻结预测产物，新增更正说明或旁证，记录实际 system prompt、采集工作树及 scorer 的内容指纹，明确旧 `prompt_sha256` 的含义及局限；将因果表述收敛为“更新后该次重跑观察到 5/5 拒答”，除非有额外证据支持。不要静默修改冻结预测来消除元数据差异。

## 其余 brief 要点核验

| 要点 | 核验结果及边界 |
|---|---|
| 诊断脱敏与一致性 | 指定诊断文档仅见 hash、判定、计数与抽象根因，未见题面、私有答案、quote 或预测正文。5 个假阴性、6 条失败 citation、结构化状态与正文语义分开的口径，与报告一致。本次未读取私有材料，未重新裁决原诊断的逐题语义结论。 |
| 原始 / 重打分 / 污染重跑 | 三段明确区分，保留原始失败与污染声明。冻结预测 SHA 与原始公开资产一致；原始 support 11/16、citation 19/25、refusal 4/5；重打分 15/16、24/25、4/5；重跑 11/14、13/20、5/5，误拒答 1/15，均与指定资产吻合。三组总门禁均为 failed；报告没有宣称重跑总体通过。数字一致不代表 scorer 语义正确，见 P1。 |
| scorer 通用性与接线 | 未见 question_id/hash 特判；仓外脚本通过 `load_module` 加载仓库 `evaluation/runner/heuristic_review.py`，没有另留一套判定实现。脚本独立限制不可答题不能标 supported。算法和测试充分性见 Findings。 |
| refusal prompt 与测试 | `answering.py:143–144` 明确“核心所问”“即使有相关背景”“has_answer=false 和空 source_ids”“不要用背景信息冒充”。新增测试逐项断言这些关键句子，符合本项要求；文字断言本身不证明模型行为或因果效果。 |
| 公开回归表述 | 明确标为 seed-v2 development，比较 answered/refused outcome 31/9 及拒答率，并声明未改写既有 review；未冒充新的独立盲测或 support/citation 全量回归。本 brief 未提供该公开回归的独立采集摘要，本次未独立验证 31/9 的底层采集，仅核验表述边界。 |
| 价格与花费 | draft peak、非 owner-signed 的声明一致；重跑摘要确为预留 49,160 microyuan，即 CNY 0.049160。新增预留 0.049160 + 0.098320 = 0.147480；加既有原始采集及更早约 0.074，约为 0.270640，与报告约 0.27 自洽。这是预留/估算口径，不是供应商实付账单核对；公开回归金额未获本 brief 内的独立 ledger 佐证。 |
| 文件卫生 | `git ls-files` 中包含 `.blindtest/` 或 `private-blind` 的路径数为 0。检查原始和重跑公开聚合的每条 `question_results`，字段均仅为 `id_hash/outcome/category`，hash 长度均为 64；没有读取对应私有文件。 |

## 验证记录

仅运行本地离线测试与内存中的合成探针，不执行仓外填表脚本，也不读取其参数所指的数据集。

```text
PYTHONDONTWRITEBYTECODE=1 services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider evaluation/smoke/test_heuristic_review.py
5 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider services/ai/tests/test_answering.py
31 passed, 2 warnings

git diff --check
通过
```

heuristic 测试启动另有 asyncio fixture 默认作用域的弃用提示。answering 的两条 warning 来自取消检索测试中的本地 socket 服务线程 `ConnectionResetError`，未导致测试失败。合成探针结果记录在 Findings；没有把测试通过当作评分逻辑无缺陷的证明。

审阅时关键文件 SHA-256（文件内容指纹，不等同于采集时 prompt 指纹）：

| 文件 | SHA-256 |
|---|---|
| `evaluation/runner/heuristic_review.py` | `dfd705f31987ed5adc4d9b893344d62443db476c353a531ad5d1342870905568` |
| `evaluation/smoke/test_heuristic_review.py` | `efac7b3b8e6478689066c080e19c6de66f41d27dda1312ae3adb270a2684f3b7` |
| `services/ai/src/knowflow_ai/answering.py` | `ce8ac8b86688b4c703ddd1852b9ce60700de09b1dc141abe1abb55af197193d6` |
| `services/ai/tests/test_answering.py` | `fc95d7c9ffc3264f52c1541c9002fd327b5e5b6b79d5560fcec171c89917713a` |
| 仓外 `fill-box-blind-review.py` | `87780505bb93eade585f6a1c06c0cf3388c534706dd24b59ef823cd3e1f50348` |

本次不修改评分器、prompt、测试、报告或资产；以上均为审阅发现及建议。
