# Box 盲测 postdiag：R2 独立复审

- Verdict: **CHANGES_REQUESTED**
- Findings：P0 = 0；P1 = 2；P2 = 1（均为 R1 问题的残留）。
- 日期：2026-11-05（Asia/Shanghai）。
- 基线：`grok`，HEAD `374b75651ffbbd86763858a4dfc25a7513716171`；审阅对象为当前未提交工作树。
- Brief：`/workspace/knowflow-briefs/2026-11-05-sol-box-blind-postdiag-r2.md`；对照 `docs/reviews/2026-11-05-sol-box-blind-postdiag.md`，范围沿用 R1 brief，并核对更新后的 heuristic、tests、report、assets 及指定两份仓外文件。
- 边界：未参与实现或重跑采集；未读取 `.blindtest/` 或 private-blind 题面、答案、quote、预测正文；未执行仓外填表脚本、调用模型或重跑数据集。下文复现均为新建合成文本。只新增本文，不改代码、测试、报告或资产，不 commit/push。

R1 的两个原始 soft 反例、lunar 额外断言、all-local-fail 反例均已按预期通过新增测试；报告数字和因果措辞也已更正。但数值/否定保护仍可绕过，整答核验仍接受冲突断言，多 marker 的复合 claim 回退仍会接受错配来源。现有 6 个 heuristic 测试通过不足以关闭这三个问题。

## R1 逐条状态

| R1 项目 | R2 状态 | 已修复与残留 |
|---|---|---|
| P1-1：soft 数值/否定误接受 | **Still open** | 原 `80/18`、`无需/必须` 两例已拒识；但数字检查使用子串，否定检查只从 claim 单向检查 token，且 strict 分支绕过保护。见下文 P1-1。 |
| P1-2：support citation 门控及整答核验 | **Still open** | “全部 citation 通过即放行”和“至少一条 citation 通过”两个布尔门控已移除；`[False, False]` 的充分联合证据可通过，原 lunar 长句可拒绝。这两部分 **Closed**。但 material 检查只拒绝低于 0.25 overlap 的长片段，仍放行冲突或短断言，未完成整答核验。见 P1-2。 |
| P2-1：并列 marker 归属与测试 | **Still open** | 紧邻 marker 成簇、`attributed_clause` 精确顺序断言、marker-only claim 的正确/错配来源测试均已修复；该形态 **Closed**。句号前 marker 的真实 collector 复合 claim 仍触发整句回退并掩盖错配。见 P2-1。 |
| P2-2：prompt 指纹与拒答因果表述 | **Closed（报告更正范围）** | 报告新增当前实现内容指纹，明确 collector 的旧 `prompt_sha256` 未更新、采集 HEAD 不含未提交修改，并将拒答变化收敛为该次污染重跑的观察结果。可核验的源码/脚本指纹相符。旧元数据仍不能证明进程实际加载版本，但报告已披露该局限，本次不把事后指纹当作采集时证明。 |

## Findings

### P1-1（Still open）：数值与否定约束不完整，且不覆盖 strict 路径

位置：`evaluation/runner/heuristic_review.py:13–15,163–186,205–237`；测试：`evaluation/smoke/test_heuristic_review.py:30–35`。

`_numbers_compatible` 以 `number in haystack` 检查数字，因此 `18` 会命中 `180`；只匹配阿拉伯数字，也不识别中文数字冲突。`_negation_compatible` 在 claim 没有匹配到否定 token 时直接返回 True，无法拒绝“证据否定、claim 肯定”的反向冲突。`grounded` 又先执行允许半数片段命中的 `_strict_grounded`，只要该分支通过，soft 中新增的冲突检查完全不会执行。

实测下表全部返回 `grounded=True`、`citation_supported=True`。citation 调用统一为 `citation_supported(claim + '[s]', 0, claim + '[s]', evidence)`。

| 合成 claim | 合成 evidence | bigram coverage | 误接受原因 |
|---|---|---:|---|
| 申请人年龄必须达到18周岁 | 申请人年龄必须达到180周岁。 | 0.9167 | `18` 被当作 `180` 的子串接受。 |
| 申请人必须提交有效身份证明原件 | 申请人无需提交有效身份证明原件。 | 0.7857 | claim 无否定 token，反向否定冲突漏检。 |
| 电子档案可以直接删除 | 电子档案不可以直接删除。 | 0.8889 | 肯定 claim 被否定证据错误支持。 |
| 档案保管期限为五年 | 档案保管期限为十年。 | 0.7500 | 中文数字冲突未检查。 |
| 档案保管期限为80年，电子文件应当备份 | 档案保管期限为18年，电子文件应当备份。 | 0.8235 | `_numbers_compatible=False`、`_soft_grounded=False`，但 strict 的半数命中使最终判定仍为 True。 |

这些都是同主题事实冲突，直接影响 citation proxy。R1 原样反例已修复，不能据此推断“数字与否定冲突拒识”已普遍成立。

关闭条件：数字按完整值及其事实归属核验，否定按双向含义与作用范围核验；所有能授予 supported 的路径都必须受冲突检查约束。不能可靠确认时保留 unsupported。补充上述反向否定、数字子串、中文数字、strict 绕过负例，同时保留已有同义正例。

### P1-2（Still open）：material guard 仍放行冲突断言，reference/半数匹配继续掩盖整答错误

位置：`evaluation/runner/heuristic_review.py:274–299`，尤其 `286–298`；测试：`evaluation/smoke/test_heuristic_review.py:38–49`。

新增 guard 仅检查归一化长度至少 6 的片段；即便某个 material 片段的 strict 和 soft grounding 均失败，只要 bigram coverage 不低于 0.25，就继续执行整答半数匹配或 reference 半数匹配。因此，一个有证据的分句仍可为另一个错误分句取得整答 supported。citation 布尔门控已移除，但这不等于整答事实已核验。

合成复现：

```python
answer = '档案保管期为五年。[a]电子档案保管期为80年。'
reference = '档案保管期为五年。'

support_judgement(
    answer, [True], reference,
    ['档案保管期为五年。电子档案保管期为18年。'],
)
# 实测 'supported'；第二句 80 年与证据 18 年冲突。

support_judgement(
    answer, [False], reference,
    ['电子档案保管期为18年。'],
)
# 实测仍为 'supported'；本例 grounded(answer, cited_evidence)=False，
# 但 material guard 放行后，由 reference 分支授予 supported。

support_judgement(
    '档案保管期为五年。[a]月球是玻璃。', [True],
    reference, ['档案保管期为五年。'],
)
# 实测 'supported'；该额外断言只有 5 字，被 material 长度阈值跳过。
```

前两例中，单独 `grounded('电子档案保管期为80年', cited_evidence)` 都是 False，其 coverage 为 0.7。这说明即使已有局部数字检查正确拒识，support 自己的放行规则仍会接受同一错误；不只是 P1-1 的传导。第三例与已覆盖的“月球由玻璃制造”语义相近，只是长度变化就再次漏检。

关闭条件：以整答中的实质性断言是否受联合证据/reference 支持为准，不能用“同主题、有一些重合”替代事实核验，也不能仅按字数排除重要断言；已识别的冲突不得被其他分句或 reference 命中抵消。保留 all-local-fail 独立正例，补充高 overlap 冲突和短额外断言负例。

### P2-1（Still open）：多 marker 仍可通过 full_claim 整句回退接受错配来源

位置：`evaluation/runner/heuristic_review.py:240–262`，尤其 `248–252`；测试：`evaluation/smoke/test_heuristic_review.py:10–20`。只读对照 `evaluation/collector/prediction.py:40–46` 的 `_claim`，未读取预测文件。

新测试只覆盖 `……。[src-a][src-b]`，此时 collector 的 claim 为 marker-only，归属修复确实有效。但合法且常见的 `……[src-a][src-b]。` 会让 collector 抽取包含两个分句的 claim。尽管 `attr` 已正确取得，代码仍把 `full_claim` 追加为候选；候选间是 OR，复合 claim 的半数匹配便重新接受了只支持另一个分句的来源。

使用实际 collector helper 的合成复现：

```python
from evaluation.collector.prediction import _claim
from evaluation.runner.heuristic_review import (
    MARKER, attributed_clause, citation_supported,
)

answer = '仓库每日清晨开门，访客必须提前预约[src-a][src-b]。'
marker = list(MARKER.finditer(answer))[0]
claim = _claim(answer, marker.start(), marker.end())
# claim == answer（两个分句都在其中）
assert attributed_clause(answer, 0) == '仓库每日清晨开门'
citation_supported(answer, 0, claim, '访客必须提前预约。')
# 实测 True；该证据仅支持第二分句，不支持 marker 0 的归属分句。
```

marker 1 交换为“仓库每日清晨开门。”也实测返回 True。将句号移回 markers 之前，两种错配均正确返回 False；因此现有测试的通过依赖这一标点位置。

关闭条件：已确定并列引用归属时，不再允许 collector 的复合 full_claim 绕过该归属；用实际 `_claim` 构造句号前/后两种形态，并分别断言正确来源通过、交换来源失败。helper 的顺序断言应继续保留。

## 报告、资产与其余范围核验

| 项目 | 核验结果及边界 |
|---|---|
| 冻结预测重打分数字 | **Closed**。报告 `73–78` 行与更新摘要一致：support **12/16 = 0.75**、citation **24/25 = 0.96**、refusal **4/5 = 0.8**，总体 failed。摘要的 scorer SHA 与当前实现一致；predictions SHA 与原始公开资产一致。本次未读私有预测，未重新计算逐题语义分数。 |
| 原始 / 污染重跑区分 | 原始仍为 support 11/16、citation 19/25、refusal 4/5；当前污染重跑资产及报告为 **10/14 = 0.7143、12/20 = 0.6、5/5 = 1.0**，误拒答 1/15。三组总体均 failed；报告清楚声明污染与 proxy 局限。R1 文档记录的重跑 11/14、13/20 已随当前 scorer/资产更新，不应沿用为本轮数字。 |
| 实现指纹与因果措辞 | **Closed（报告更正）**。报告列出的 heuristic、answering、仓外脚本文件 SHA 均与当前文件相同，承认旧 prompt 字段未同步。表内“关键句拼接指纹”未给出精确拼接规则，本次不把它认作完整 system prompt 或运行时证据；见下方当前完整 prompt 指纹。报告 `107,137` 行已将 5/5 拒答写为该次重跑观察，不宣称唯一因果。 |
| 诊断与脱敏 | 指定诊断文档保持 hash、类别、判定与抽象根因，未见私有题面、答案、quote、预测正文；5 个假阴性与 6 条 citation 的限定范围与报告一致。本次不重新裁决其私有逐题语义结论。 |
| 通用性与接线 | scorer 未见 question_id/hash 特判；仓外填表脚本仍动态加载仓库 heuristic，独立禁止不可答题标 supported。未执行该脚本。 |
| 拒答 prompt | `answering.py` 的核心所问、背景不得冒充、`has_answer=false` 与空 `source_ids` 约束保留；新增测试断言关键句。静态测试不证明模型效果或采集时加载版本。 |
| 公开回归 | 报告仍标明 seed-v2 development，31/9 为 outcome 对比，未冒充独立盲测或新的全量 support/citation 人审；没有改写已入库 review 的声明。本范围无独立回归采集摘要，未验证其底层预测。 |
| 花费 | 仓外 collection 摘要仍为 draft peak、非 owner-signed，预留 49,160 microyuan = CNY 0.049160；新增 0.049160 + 0.098320 = 0.147480，累计约 0.27 的算术自洽。未将预留额视为实际账单；公开回归金额未获本范围独立 ledger 佐证。 |
| 文件卫生 | `git ls-files` 中 `.blindtest/` 或 `private-blind` 路径命中数为 0；原始与重跑公开聚合的 `question_results` 字段均仅为 `id_hash/outcome/category`，hash 均为 64 位十六进制。 |

## 验证记录

仅运行离线测试与内存合成探针；未新增测试文件。

```text
PYTHONDONTWRITEBYTECODE=1 services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider evaluation/smoke/test_heuristic_review.py
6 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider services/ai/tests/test_answering.py
31 passed, 2 warnings

git diff --check
通过
```

heuristic 测试启动有 asyncio fixture 默认作用域弃用提示；answering 的两条 warning 来自取消检索测试中的本地 socket 服务线程 `ConnectionResetError`，未导致失败。

除上述负例，还独立复核：原 R1 数值/否定反例现在均为 False；原 lunar 长句为 unsupported；原 `[False, False]` support 例为 supported；两个分句分别分布于两条证据、无 reference、局部判定均为 False 的真实联合证据合成例也为 supported。

审阅时内容指纹如下（均为当前文件/字符串，不等同于采集时进程证明）：

| 对象 | SHA-256 |
|---|---|
| `evaluation/runner/heuristic_review.py` | `1fe3ce6fcc8334f7000024f998cac2409ff28ee6f9ace65346ade0e168307564` |
| `evaluation/smoke/test_heuristic_review.py` | `cfcd39b94764598fc4cab7a3f7c611fefec50d8c9d1f4c124a46502e6edd0f91` |
| `services/ai/src/knowflow_ai/answering.py` | `ce8ac8b86688b4c703ddd1852b9ce60700de09b1dc141abe1abb55af197193d6` |
| `services/ai/tests/test_answering.py` | `fc95d7c9ffc3264f52c1541c9002fd327b5e5b6b79d5560fcec171c89917713a` |
| 当前完整 system prompt（AST 提取 `_payload` 中 system content 常量，UTF-8，无附加换行） | `c5d82cf369303db507c4aa4c665bf9de07f33a35e220d0c19549624703ed7acb` |
| 仓外 `fill-box-blind-review.py` | `87780505bb93eade585f6a1c06c0cf3388c534706dd24b59ef823cd3e1f50348` |
| `assets-box-blind-20261105-original-rescored-summary.json` | `aeb5766aa34c1f2c509d7ab8ed8fc23b249d0a17629c983cd972a09349125528` |
| `assets-box-blind-20261105-postdiag-metrics.json` | `94fab43ec52689bb42d9e5526fe058cb377223d8907faf1f03a8d600ae0293a1` |

批准前仍需关闭 P1-1、P1-2，以及 P2-1 的多 marker 整句回退残留，并用修正后的 scorer 同步摘要/报告；本轮只记录审阅结论，不执行修复或重打分。
