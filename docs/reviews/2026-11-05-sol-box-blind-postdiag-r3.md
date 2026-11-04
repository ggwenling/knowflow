# Box 盲测 postdiag：R3 独立复审

- Verdict: **CHANGES_REQUESTED**
- Findings：P0 = 0；P1 = 2；P2 = 1。
- 日期：2026-11-05（Asia/Shanghai）。
- 基线：`grok`，HEAD `374b75651ffbbd86763858a4dfc25a7513716171`；审阅对象为未提交工作树。
- Brief：`/workspace/knowflow-briefs/2026-11-05-sol-box-blind-postdiag-r3.md`；对照 `docs/reviews/2026-11-05-sol-box-blind-postdiag-r2.md`，范围沿用 R1/R2 指定文件及两份仓外脚本/采集摘要。
- 边界：未参与实现或采集；未读取 `.blindtest/` 或 private-blind 的题面、答案、quote、预测正文；未调用模型、重跑数据集或执行仓外填表脚本。所有探针均为合成文本，只在内存执行。本会话仅新增本文，不改代码、测试、报告或资产，不 commit/push。

R2 的四个单分句数值/反向否定负例、三个 support 负例以及多 marker 错配例已按预期拒绝。但数值仍可借用其他事实的值，否定只比较全段是否出现否定词；support 也仍保留长度豁免、低 overlap 门槛及整答/reference 回退。因此 P1-1、P1-2 仍未关闭，P2-1 的指定多 marker 回退问题已关闭。报告另有结论文字与指纹不同步问题。

**版本边界**：首次读取时，`support_judgement` 为逐 part 调用 `grounded` 的实现；审阅期间该文件发生非本会话写入，约 01:19 改回 material guard 加整答/reference 回退。以下结论统一绑定随后读取的 **SHA-256 `a18841ee9118abd60dbe81103c1404595eef4ec7d46f13f7e271541cd2b8c856`**（01:21 核验）。合成探针以一次读取的源码字节在内存编译，执行前后确认文件未变化；heuristic 测试也核对了运行前后同一 SHA。不能把首次读取的实现与后续资产或结果混作同一版本。

## R2 逐条状态

| R2 项目 | R3 状态 | 依据 |
|---|---|---|
| P1-1：数字、否定及 strict 绕过 | **Still open（部分关闭）** | `18/180`、两种反向否定、`五/十` 均已拒识；`grounded` 的 strict 接受路径已受冲突检查约束。但数字的事实归属、小数边界、否定作用范围仍有误接受和误拒绝。原 strict 合成例的完整 citation 调用仍为 True，详见下文。 |
| P1-2：整答 support 核验 | **Still open（指定原例已修复）** | R2 的 `80/18`、reference 回退、五字额外断言均为 unsupported，all-local-fail 与联合证据正例仍通过；但当前实现并非“每个 contentful part 各自 grounded”，仍能放行一个 grounded=False 的实质分句，reference 也能借出无关数字掩盖冲突。 |
| P2-1：多 marker 的 full_claim 回退 | **Closed（指定范围）** | 存在 attributed 时不再 OR full_claim；实际 collector `_claim` 构造的句号前、句号后形态，两条 marker 均正确来源 True、交换来源 False。 |
| R2 已关闭的 prompt 指纹/因果表述 | **保持 Closed（既有局限）** | answering 与仓外脚本指纹未变，报告继续披露旧 prompt 字段及污染，拒答变化仍限定为该次观察；不把当前内容指纹当作采集时进程证明。当前 scorer 的报告/资产版本漂移另列 P2-2。 |

## R2 失败例逐项合成复验

下表 citation 调用与 R2 一致：`citation_supported(claim + '[s]', 0, claim + '[s]', evidence)`。

| claim | evidence | grounded | citation_supported |
|---|---|---|---|
| 申请人年龄必须达到18周岁 | 申请人年龄必须达到180周岁。 | False | False |
| 申请人必须提交有效身份证明原件 | 申请人无需提交有效身份证明原件。 | False | False |
| 电子档案可以直接删除 | 电子档案不可以直接删除。 | False | False |
| 档案保管期限为五年 | 档案保管期限为十年。 | False | False |
| 档案保管期限为80年，电子文件应当备份 | 档案保管期限为18年，电子文件应当备份。 | False | **True** |

最后一例 `_strict_grounded=True`、`_conflicts=True`，最终 `grounded=False`，证明 strict 前置保护已生效。但 `attributed_clause` 在两个分句、一个 marker 时只保留末尾“电子文件应当备份”，citation 便以该分句授予 True（`heuristic_review.py:95–102,285–300`）。这是归属裁剪丢弃前述冲突，与原 strict 内部绕过不同；不能声称这条完整 citation 负例已经拒绝。应明确单 marker 复合 claim 的核验范围，并覆盖其与冲突检查的交互。

support 原例保持 R2 的全部参数：

| R2 合成调用 | R3 结果 |
|---|---|
| `档案保管期为五年。[a]电子档案保管期为80年。`；`[True]`；reference 五年；证据含普通档案五年、电子档案十八年 | unsupported |
| 同一 answer；`[False]`；reference 五年；证据仅电子档案十八年 | unsupported |
| `档案保管期为五年。[a]月球是玻璃。`；`[True]`；reference/证据均仅五年 | unsupported |
| 原 R1 的“月球由玻璃制造”长断言；其余参数同上 | unsupported |
| `档案保管期为五年。`；`[False, False]`；reference/证据均五年 | supported |
| `仓库每日清晨开门，访客必须提前预约。`；`[False, False]`；无 reference；两条证据分别覆盖两个分句 | supported |

并列引用使用真实 `evaluation.collector.prediction._claim`，未读取任何预测文件：

| answer 形态 | collector claim | 两条 attributed_clause（按 marker 顺序） | 正确 / 交换来源 |
|---|---|---|---|
| `仓库每日清晨开门，访客必须提前预约。[src-a][src-b]` | 两条均为 `[src-a][src-b]` | 仓库每日清晨开门 / 访客必须提前预约 | 两条均 True / False |
| `仓库每日清晨开门，访客必须提前预约[src-a][src-b]。` | 两条均含整个复合句 | 仓库每日清晨开门 / 访客必须提前预约 | 两条均 True / False |

测试已增加句号前 collector 复合 claim 的 marker 0 正确/错配断言；本次独立补验了 marker 1 和句号后形态的全部四个来源组合。

## Findings

### P1-1（Still open）：数字未绑定事实归属，否定仍按全段存在性判断

位置：`evaluation/runner/heuristic_review.py:160–197,204–217,268–275`。

`_numbers_compatible` 在整段证据的数字集合中找值，没有核验该数字属于哪个主体、属性；`_whole_number_present` 的边界仅排除相邻数字，小数点仍能形成误命中。`_negation_compatible` 在两端都含任意否定词时直接通过，未核验否定作用于哪个动作；反过来，证据中无关分句的否定也会推翻已有直接支持。

以下独立合成探针统一使用上表 citation 调用方式：

| claim | evidence | coverage | grounded / citation | 问题 |
|---|---|---:|---|---|
| 纸质档案保管期为80年 | 纸质档案保管期为18年。电子档案保管期为80年。 | 1.0000 | **True / True** | 把电子档案的 80 年借给纸质档案。 |
| 档案保管期限为18年 | 档案保管期限为18.5年。 | 0.8889 | **True / True** | `18` 仍被小数 `18.5` 的边界命中。 |
| 电子档案不得直接删除 | 电子档案可以直接删除但不得备份。 | 0.7778 | **True / True** | 两端都有“不得”，却分别否定删除与备份。 |
| 申请人必须提交有效身份证明原件 | 申请人必须提交有效身份证明原件。无需提交复印件。 | 1.0000 | **False / False** | 无关的复印件否定覆盖了原件的直接逐字支持；strict=True 也被拒绝。 |

另测中文/阿拉伯数字等价正例：`grounded('档案保管期限为十八年', '档案保管期限为18年。') == False`。原因是提取时同时加入规范值 `18` 和原始串 `十八`，随后要求两者都命中；这不是“数字含义相同”的核验。既有身份证明同义正例仍为 True，coverage=0.6154。

这些结果说明保护已覆盖 `grounded` 的分支，却未可靠识别其检查对象；既能接受冲突，也会系统性拒绝含无关否定的正确事实。关闭仍需将数值和极性绑定到相应主体/属性/动作，按完整数值处理小数，避免用整段集合或否定词是否存在替代作用范围核验，并保留正例。

### P1-2（Still open）：当前 support 仍放行未 grounded 的分句，reference 可掩盖冲突

位置：`evaluation/runner/heuristic_review.py:120–122,312–344`，尤其 `328–343`。

当前 material guard 跳过归一化长度不足 4 的 part；对更长片段，只要没有被 `_conflicts` 判出冲突且 coverage ≥0.25，即使 `grounded=False` 仍继续。之后整答半数匹配或 reference 半数匹配即可授予 supported。这与 R3 brief 所述“每个 contentful part 各自 grounded”不符。

```python
from evaluation.runner.heuristic_review import grounded, support_judgement

reference = '档案保管期为五年。'
evidence = [reference]

grounded('档案保管地点位于月球', evidence)
# False；coverage=0.3333，实际并无地点证据。
support_judgement(
    '档案保管期为五年。[a]档案保管地点位于月球。',
    [True], reference, evidence,
)
# 'supported'；第二分句通过 guard，整答 strict 半数命中放行。

support_judgement(
    '档案保管期为五年。[a]可出售。', [True], reference, evidence,
)
# 'supported'；“可出售”在 contentful_parts 中，grounded=False，
# 却因长度为 3 被 guard 跳过。

support_judgement(
    '档案保管期为五年。[a]免费。', [True], reference, evidence,
)
# 'supported'；“免费”更早被 contentful_parts 的三字门槛丢弃。
```

reference 掩盖冲突的独立对照如下；只改变 reference，证据与 answer 均冻结：

```python
answer = '档案保管期为五年。[a]电子档案保管期为80年。'
evidence = ['档案保管期为五年。电子档案保管期为18年。']

support_judgement(answer, [True], '档案保管期为五年。', evidence)
# 'unsupported'
support_judgement(
    answer, [True], '档案保管期为五年。纸质档案保管期为80年。', evidence,
)
# 'supported'；无关纸质档案的 80 被并入 check_sources，
# 抹去电子档案的数字冲突，随后 reference 命中半数放行。
```

最后一例与 P1-1 的数值归属缺陷有关；前面的地点断言和短断言则独立证明 support 本身仍有绕过，不能只修数字检查后关闭本项。应逐项核验实质断言，避免按字数豁免或用低 overlap 代替 grounding，且已发现的事实冲突不能被无关 reference 消除。现有三个负例通过不足以证明这些条件成立。

### P2-2（本轮报告问题）：表格已更新，但结论文字与 scorer 指纹未同步

位置：`docs/evaluation/2026-11-04-rag-box-blind-20.md:73–78,128–135`；`assets-box-blind-20261105-original-rescored-summary.json` 的 `heuristic_review_sha256`。

1. 表格与摘要均为 support **2/16=0.1250**、citation **15/25=0.6000**。第 78 行却仍写“citation proxy 达阈值；support 提升”，与 citation 阈值 0.95、原始 support 11/16=0.6875 直接矛盾。两项都是下降且未达标。
2. 报告指纹表及重打分摘要均记录 scorer SHA `6d0d6b8b2fd1f5423a5a1c6a1de2a43e039ceb70b5193b087056f08234e9e9d2`，当前复验版本为 `a18841ee…`。因此不能把这些资产作为当前 scorer 的分数证明；本次只能确认报告表格与既有聚合的算术一致。报告应明确指标对应的 scorer 版本，并在获得该版本的正式重打分结果后同步数字、结论和指纹，或明确保留为旧版本结果。本审阅不执行重打分。

该项不同于 R2 已关闭的 prompt 因果措辞问题；answering 与仓外脚本指纹仍相符，旧 collector prompt 元数据的局限也仍有披露。

## 报告数字、指纹与其余范围

| 项目 | 核验结果及边界 |
|---|---|
| 原始采集 | support 11/16=0.6875、citation 19/25=0.7600、不可答拒答 4/5=0.8000、误拒答 0/15；总体 failed。与原始公开资产相符。 |
| 冻结预测重打分 | support **2/16=0.1250**、citation **15/25=0.6000**、不可答拒答 4/5、误拒答 0/15；总体 failed。表格与摘要一致，结论文字及 scorer 版本问题见 P2-2。预测 SHA 与原始资产相同；未读取私有预测、未独立重算语义分数。 |
| 污染重跑聚合 | support **3/14=0.2143**、citation **10/20=0.5000**、不可答拒答 5/5、误拒答 1/15=0.0667；总体 failed。报告与聚合一致，继续明确污染、proxy 与总体未通过。聚合未包含当前 scorer SHA，不额外推断当前版本已重打分。 |
| prompt 与实现接线 | 核心所问、背景不得冒充、`has_answer=false`、空 `source_ids` 约束保留；prompt 测试通过。仓外脚本仍动态加载仓库 heuristic，独立禁止不可答题标 supported，未见题号/hash 特判。未执行该脚本。 |
| prompt 运行时边界 | 重跑资产和采集摘要的旧 `prompt_sha256=3115dbae…` 未变；报告已披露，拒答限定为该次重跑观察。内容指纹不证明采集进程当时实际加载版本；“关键句拼接”无精确规则，不认作完整 prompt 哈希。 |
| 诊断脱敏 | 诊断仅见 hash、判定、计数与抽象根因，5 个假阴性、6 条 citation 的限定范围与报告一致；未重新裁决私有逐题结论。 |
| 公开回归 | 仍明确 development，31/9 为 outcome 对比，未宣称新的全量 support/citation 独立审阅；本范围无可独立复核的底层回归采集产物。 |
| 花费 | 仓外摘要仍为 draft peak、非 owner-signed；49,160 microyuan=CNY 0.049160。新增 0.049160+0.098320=0.147480，含既有约 0.074 的累计约 0.27，算术自洽。预留非实际账单，未独立核验公开回归账本。 |
| 文件卫生 | `git ls-files` 中 `.blindtest` / private-blind 路径命中数为 0；原始和重跑聚合 `question_results` 仅有 `id_hash/outcome/category`，hash 均为 64 位十六进制。 |

本轮内容指纹（文件按原字节；prompt 按 AST 提取 `_payload` 中 system content 常量、UTF-8、无附加换行）：

| 对象 | SHA-256 |
|---|---|
| `evaluation/runner/heuristic_review.py` | `a18841ee9118abd60dbe81103c1404595eef4ec7d46f13f7e271541cd2b8c856` |
| `evaluation/smoke/test_heuristic_review.py` | `38c30d617122088ed2bf4b759beba817d63de78011a66d0432356e767b1713b7` |
| `services/ai/src/knowflow_ai/answering.py` | `ce8ac8b86688b4c703ddd1852b9ce60700de09b1dc141abe1abb55af197193d6` |
| `services/ai/tests/test_answering.py` | `fc95d7c9ffc3264f52c1541c9002fd327b5e5b6b79d5560fcec171c89917713a` |
| 完整 system prompt | `c5d82cf369303db507c4aa4c665bf9de07f33a35e220d0c19549624703ed7acb` |
| 仓外 `fill-box-blind-review.py` | `87780505bb93eade585f6a1c06c0cf3388c534706dd24b59ef823cd3e1f50348` |
| 仓外 `box-blind-20-postdiag/collection-status-summary.json` | `da2a082e13fa99e9d5a143fe2f4f210bc6e7f0b3c7095e140fd9f2d2aff09dd4` |
| `docs/evaluation/2026-11-04-rag-box-blind-20.md` | `c30e1f7beaebc0a351cc7edabc6549b6c7a5b733ba69a8176e866293b5e18189` |
| `assets-box-blind-20261105-original-rescored-summary.json` | `af23d969cd8e69ec04cc719abb19ad28cec95f9092ac576d964f37d2595e5cfa` |
| `assets-box-blind-20261105-postdiag-metrics.json` | `958f1304deaf46095894ed2b8243e26f38bc1ed4c7ddeb3f1211382745ad77c5` |

## 验证记录

仅运行离线测试及内存合成探针，没有新增测试文件：

```text
PYTHONDONTWRITEBYTECODE=1 services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider evaluation/smoke/test_heuristic_review.py
6 passed
（最终版本再次通过 pytest.main 相同参数验证，scorer 前后 SHA 均为 a18841ee…）

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider services/ai/tests/test_answering.py
31 passed, 2 warnings

git diff --check
通过
```

heuristic 启动时有 asyncio fixture 默认作用域弃用提示；answering 两条 warning 来自取消检索测试的本地 socket 服务线程 `ConnectionResetError`，均未导致测试失败。现有测试全部通过，但未覆盖上述额外数值归属、小数、否定作用范围及 support 绕过反例，不能据此批准。

批准前仍需关闭 P1-1、P1-2，并同步报告结论、指标版本和 scorer 指纹；本轮仅记录复审结果。
