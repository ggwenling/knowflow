# Box 盲测 postdiag：R4 最终独立复审

- Verdict: **CHANGES_REQUESTED**
- Findings：P0 = 0；P1 = 2；P2 = 1。
- 日期：2026-11-05（Asia/Shanghai）。
- 分支：`grok`；HEAD：`374b75651ffbbd86763858a4dfc25a7513716171`；对象为未提交工作树。
- Brief：`/workspace/knowflow-briefs/2026-11-05-sol-box-blind-postdiag-r4.md`；对照 `docs/reviews/2026-11-05-sol-box-blind-postdiag-r3.md`，范围沿用 R1 指定文件及两份仓外脚本/摘要。
- 独立性与边界：本会话未参与实现或采集；未读取 `.blindtest/` 或 private-blind 题面、答案、quote、预测正文；未调用模型、重跑数据集或执行仓外填表脚本。探针全部使用合成文本，在内存编译一次读取的 scorer 源码后执行，并核对执行前后原字节一致。只新增本文，不改代码、测试、报告或资产，不 commit/push。

R3 列出的原样负例与正例均已通过本轮复验；报告数字、冻结重打分摘要的 scorer SHA 也已同步。但保护仍依赖有限连接词切分和整答 marker 数量：把句号/“但”换成“且”，仍会发生跨事实借数、否定作用域错配和 reference 掩盖冲突；给答案追加另一条独立引用，则原本已被拒绝的 80/18 复合 claim 再次被 citation 放行。因此原样探针修复成立，P1 的通用条件仍未关闭。

本轮所有 scorer 结论绑定 SHA-256 **`b5a5b905a99f0a10e3c2ad5df59dbc9b48d4c3562ed9350c9e5b19c518dee521`**，不是 R3 的 `a18841ee…`。复验期间该源码字节未变化。

## R3 逐条状态

| R3 项目 | R4 状态 | 依据 |
|---|---|---|
| P1-1：数值归属、小数、否定作用域、中阿数字等价及完整 citation 冲突检查 | **Still open（原样例已修复）** | R3 原样例全部符合预期；“且”连接仍使多个事实进入同一数字/否定集合，见本轮 P1-1；复合 citation 检查受整答 marker 总数控制，见 P1-2。正确小数的端到端误拒见 P2-1。 |
| P1-2：support 的地点、短断言、reference 借数绕过 | **Still open（原样例已修复）** | 月球地点、“可出售”、“免费”、R3 原 reference 对照均拒绝，all-local-fail 与联合证据正例通过；现在确实逐 part 调用 grounded，不再有旧的长度/低 overlap 豁免。但 reference 的同分匹配片段仍能借出其他实体的数字，改变同一答案的 support，见本轮 P1-1。 |
| P2-2：报告结论与 scorer 指纹漂移 | **Closed（本轮可核验范围）** | 冻结摘要、报告指纹均为当前 `b5a5b905…`；两组数字与资产及算术一致，未继续声称 support 提升、citation 达标。污染重跑资产本身未附独立 scorer SHA，不能据此证明历史评分进程版本。 |
| R3 保持关闭的并列 marker 错配、prompt 表述与因果边界 | **保持 Closed（原指定范围）** | 两种标点位置、两个 marker 的真实 collector claim 均正确来源通过、交换来源拒绝；prompt 约束及测试保留。仍披露旧 collector prompt 字段、污染和拒答因果局限。 |

## 原样合成探针复验

下表除复合 claim 的额外说明外，统一调用：

```python
grounded(claim, evidence)
citation_supported(claim + '[s]', 0, claim + '[s]', evidence)
```

| claim | evidence | grounded / citation | 预期 |
|---|---|---|---|
| 申请人年龄必须达到18周岁 | 申请人年龄必须达到180周岁。 | False / False | 拒绝 |
| 申请人必须提交有效身份证明原件 | 申请人无需提交有效身份证明原件。 | False / False | 拒绝 |
| 电子档案可以直接删除 | 电子档案不可以直接删除。 | False / False | 拒绝 |
| 档案保管期限为五年 | 档案保管期限为十年。 | False / False | 拒绝 |
| 档案保管期限为80年，电子文件应当备份 | 档案保管期限为18年，电子文件应当备份。 | False / False | 拒绝 |
| 纸质档案保管期为80年 | 纸质档案保管期为18年。电子档案保管期为80年。 | False / False | 拒绝跨实体借数 |
| 档案保管期限为18年 | 档案保管期限为18.5年。 | False / False | 拒绝小数截取 |
| 电子档案不得直接删除 | 电子档案可以直接删除但不得备份。 | False / False | 拒绝错位否定 |
| 申请人必须提交有效身份证明原件 | 申请人必须提交有效身份证明原件。无需提交复印件。 | True / True | 保留直接支持 |
| 档案保管期限为十八年 | 档案保管期限为18年。 | True / True | 中阿等价 |
| 档案保管期限为18年 | 档案保管期限为十八年。 | True / True | 反向等价 |
| 申请人需提交有效身份证明原件 | 申请人应当提供有效的身份证明原件。 | True / True | 保留同义正例 |

补验“无需提交”对“必须提交”、以及“不可以直接删除”对“可以直接删除”的反向极性，两者 grounded/citation 均为 False。marker-only `[a]` 的 grounded/citation 也均为 False。

80/18 复合句另测 `……备份[a]` 与 `……备份。[a]` 两种形态，每种分别传完整 answer、marker-only `[a]` 为 claim，四次 citation 均为 False。说明 R3 的单 marker 原例已修复。

support 原样参数如下（`reference = '档案保管期为五年。'`）：

| answer / 参数 | R4 结果 |
|---|---|
| `档案保管期为五年。[a]电子档案保管期为80年。`；`[True]`；证据为普通档案五年、电子档案十八年 | unsupported |
| 同一 answer；`[False]`；证据仅电子档案十八年 | unsupported |
| 五年之后追加 `月球是玻璃。`；`[True]`；reference/证据仅五年 | unsupported |
| 五年之后追加 `月球由玻璃制造。`；其余同上 | unsupported |
| 五年之后追加 `档案保管地点位于月球。`；其余同上 | unsupported |
| 五年之后追加 `可出售。`；其余同上 | unsupported |
| 五年之后追加 `免费。`；其余同上 | unsupported |
| 原 80 年 answer、原证据；reference 改为五年加 `纸质档案保管期为80年。` | unsupported |
| `档案保管期为五年。`；`[False, False]`；reference/证据均五年 | supported |
| `仓库每日清晨开门，访客必须提前预约。`；`[False, False]`；reference 空；两条证据各覆盖一个分句 | supported |

并列引用通过真实 `evaluation.collector.prediction._claim` 构造 claim，未读取预测文件：

| answer 形态 | marker 0 归属 / marker 1 归属 | 正确来源 | 交换来源 |
|---|---|---|---|
| `仓库每日清晨开门，访客必须提前预约。[src-a][src-b]` | 仓库每日清晨开门 / 访客必须提前预约 | 均 True | 均 False |
| `仓库每日清晨开门，访客必须提前预约[src-a][src-b]。` | 同上 | 均 True | 均 False |

首批合成探针记录共 32 组，全部符合预期；一组 grounded/citation 配对或正确/交换来源配对计一组。后续边界对照发现的问题如下，未混入这 32 组的通过统计。

## Findings

### P1-1：数字与否定仍未绑定事实；“且”连接可恢复借数及 reference 掩盖冲突

位置：`evaluation/runner/heuristic_review.py:22–23,211–253,374–386`。

`_best_matching_evidence_clauses` 选择文本 overlap 最高的片段；`_numbers_compatible` 随后汇总所有最高分片段内的数字，`_negation_compatible` 仍只比较片段是否含否定词。当前切分处理“但/而”等连接词，却不处理“且”。一个片段中保留多个事实时，R3 的归属与作用域问题仍存在。

以下统一采用上文 grounded/citation 调用；support 另调用 `support_judgement(claim, [False], '', [evidence])`：

| claim | evidence | grounded / citation / support | 应有结果 |
|---|---|---|---|
| 纸质档案保管期为80年 | 纸质档案保管期为18年且电子档案保管期为80年。 | **True / True / supported** | 纸质为18年，应拒绝 |
| 电子档案不得直接删除 | 电子档案可以直接删除且不得备份。 | **True / True / supported** | 否定的是备份，应拒绝删除禁令 |
| 申请人必须提交有效身份证明原件 | 申请人必须提交有效身份证明原件且无需提交复印件。 | **False / False / unsupported** | 原件有直接支持，应接受 |

第一例把证据中的“且”换为“而”，grounded/citation 即恢复 False；第三例把“且”换为句号，即为已经通过的 R3 正例。事实没有随连接方式改变，但评分翻转。

reference 仍可掩盖证据中的明确冲突。下例仅改变 reference，answer、引用判断、cited evidence 均不变：

```python
answer = '档案保管期为五年。[a]电子档案保管期为80年。'
evidence = ['档案保管期为五年。电子档案保管期为18年。']

support_judgement(answer, [True], '档案保管期为五年。', evidence)
# 'unsupported'

support_judgement(
    answer, [True],
    '档案保管期为五年。电子档案保管期为18年且纸质档案保管期为80年。',
    evidence,
)
# 'supported'，错误
```

第二个 reference 本身也写的是电子档案18年；80年属于纸质档案。其复合片段与 cited evidence 的电子档案片段同为最高 overlap，数字并集把80借给电子档案，两个 answer part 因而都得到 grounded=True。完整 answer 对 cited evidence 仍为 grounded=False，但 reference 命中 1/2 达到回退门槛，最终 supported。

这同时复现 R3 P1-1 的事实归属缺陷与 P1-2 的 reference 掩盖冲突风险。修复需约束值和极性对应的主体/属性/动作，避免同分片段的数字并集消除已知冲突；仅继续扩充几个连接词不足以证明归属正确。应覆盖上述负例及无关否定正例。

### P1-2：完整复合 claim 的冲突检查取决于整答 marker 总数，追加独立引用即可绕过

位置：`evaluation/runner/heuristic_review.py:95–104,319–350`，尤其 `324–334`。

本次修复只在 `marker_count <= 1` 时检查完整 claim。它统计整个 answer，而非当前引用所属的局部引用簇。答案中另一句存在引用时，当前句虽然仍只有一条 citation，也会跳过完整 claim 冲突检查；`attributed_clause` 再裁掉前面的数值断言，只核验末尾备份分句。

使用真实 collector 构造 claim 的最小对照：

```python
evidence = '档案保管期限为18年，电子文件应当备份。'
a = '档案保管期限为80年，电子文件应当备份[a]。'
b = a + '访客必须提前预约[b]。'

def check(answer):
    marker = list(MARKER.finditer(answer))[0]
    claim = _claim(answer, marker.start(), marker.end())
    return claim, citation_supported(answer, 0, claim, evidence)

check(a)
# ('档案保管期限为80年，电子文件应当备份[a]。', False)
check(b)
# ('档案保管期限为80年，电子文件应当备份[a]。', True)，错误
```

两次 collector claim 与 evidence 完全相同，`_conflicts(claim, evidence)` 均为 True、`grounded(claim, evidence)` 均为 False；归属裁剪结果也都只是“电子文件应当备份”。新增的独立句和 `[b]` 不应改变 `[a]` 对同一冲突 claim 的判定，但当前实现将其重新放行。这是 R3 数值复合 claim 裁剪问题的未关闭路径，不是已经修复的两个并列 marker 分别归属两条事实场景。

应按当前引用簇与 claim 实际覆盖范围决定完整核验，保留真正并列引用的正确分工；同时补测“同一局部单引用，整答另有引用”的情况。

### P2-1：正确小数仍被句子/part 切分截断，citation 与 support 误拒绝

位置：`evaluation/runner/heuristic_review.py:10–12,30–36,122–124,325–334,375–381`；collector 同类边界在 `evaluation/collector/prediction.py:40–45`。

R3 的 `18` 对 `18.5` 负例已正确拒绝，但正例 `18.5` 对 `18.5` 仍未贯通：

```python
answer = '档案保管期限为18.5年[a]。'
evidence = '档案保管期限为18.5年。'
marker = list(MARKER.finditer(answer))[0]
claim = _claim(answer, marker.start(), marker.end())
# claim == '5年[a]。'

grounded('档案保管期限为18.5年', evidence)  # True
citation_supported(answer, 0, claim, evidence)  # False
citation_supported(answer, 0, answer, evidence)  # False
support_judgement(answer, [False], '', [evidence])  # 'unsupported'
```

`_CLAUSE_SPLIT` 已保护数字间的小数点，但 sentence 与 contentful part 的切分仍把 `.` 当边界：`sentence_around`/归属只剩“5年”，parts 为 `['档案保管期限为18', '5年']`。后续数值检查因此将完整小数的证据误判为不兼容。句号后 marker 形态 `档案保管期限为18.5年。[a]` 结果相同。该项是正确答案的误拒，未作为冻结 proxy 下降本身的 P1；应统一各层小数边界并补一个端到端正例。

## 报告、资产与实现指纹

| 结果组 | support proxy | citation proxy | 不可答拒答 | 可答误拒 | 总门禁 |
|---|---|---|---|---|---|
| 原始采集 | 11/16 = 0.6875 | 19/25 = 0.7600 | 4/5 = 0.8000 | 0/15 = 0.0000 | failed |
| 冻结预测重打分 | 2/16 = 0.1250 | 11/25 = 0.4400 | 4/5 = 0.8000 | 0/15 = 0.0000 | failed |
| 已污染重跑 | 2/14 = 0.1429 | 9/20 = 0.4500 | 5/5 = 1.0000 | 1/15 = 0.0667 | failed |

报告第73–78、93–107行与公开资产一致；计数除法、四位舍入、quality gate 的 observed 字段与相应 metrics 一致。原始与冻结摘要的 predictions SHA 均为 `830f80b23ac7b713107e263a6e82280d118c71d189ee122d1da98009b7f3ed0a`；重跑为 `71d8fc2e04436d4b47b073d8cc825ac4d36b594080208c5d7b0c13ef907cc107`。

冻结 proxy 相对原始值明显下降，两项也均低于阈值。报告已删除 R3 所指出的“citation 达阈值；support 提升”结论，继续明确 proxy、污染和产品未达门禁；**该下降本身不列 P1，也不据此宣称产品退化或修复有效**。本轮验证的是聚合一致性、算术和记录的指纹；未读取私有预测或独立重算数据集语义分数。

报告指纹表和冻结摘要的 `heuristic_review_sha256` 均与当前 scorer 相同，answering、仓外脚本也相符。污染重跑资产没有独立 scorer SHA；报告当前指纹表不能证明历史采集/重评分进程实际加载版本。collector 仍记录旧 `prompt_sha256=3115dbae…`，报告已披露，未把该次拒答变化归为唯一因果。完整 system prompt 按 AST 提取 `_payload` 的 system content 常量、UTF-8、无额外换行后，SHA 仍为 `c5d82cf369303db507c4aa4c665bf9de07f33a35e220d0c19549624703ed7acb`；报告的“关键句拼接”指纹不当作完整 prompt 指纹。

本轮按原字节核验的指纹：

| 对象 | SHA-256 |
|---|---|
| `evaluation/runner/heuristic_review.py` | `b5a5b905a99f0a10e3c2ad5df59dbc9b48d4c3562ed9350c9e5b19c518dee521` |
| `evaluation/smoke/test_heuristic_review.py` | `bb6eb1eb9cb24153cc1dc72aeba10e94c4288396d77a6169589bacf948cf7cbf` |
| `services/ai/src/knowflow_ai/answering.py` | `ce8ac8b86688b4c703ddd1852b9ce60700de09b1dc141abe1abb55af197193d6` |
| `services/ai/tests/test_answering.py` | `fc95d7c9ffc3264f52c1541c9002fd327b5e5b6b79d5560fcec171c89917713a` |
| `docs/evaluation/2026-11-04-rag-box-blind-20.md` | `11d3bc0f58233089f59151987a3f9cd19e44daae2261139e0e78fed169ba7700` |
| `assets-box-blind-20261104-metrics.json` | `3691e9af2e9d0e57bab6c11c4eb5cf91807f2ec9dac6a226cbbf5ac689b80a7c` |
| `assets-box-blind-20261105-original-rescored-summary.json` | `3c57a903dd0c2866a317d743c30e3a717bbf1bf03d5b78faef788f47897412c7` |
| `assets-box-blind-20261105-postdiag-metrics.json` | `d939789eaa88df1d5e869e6cede487441b1101ec5e6e470a0c3cd150bc9ed689` |
| `docs/evaluation/2026-11-05-box-blind-20-diagnosis.md` | `89bfb8b5a0ba2a329cd553ec7ce728b39be47050452c0ac0218d953f9c8f758c` |
| 仓外 `fill-box-blind-review.py` | `87780505bb93eade585f6a1c06c0cf3388c534706dd24b59ef823cd3e1f50348` |
| 仓外 `box-blind-20-postdiag/collection-status-summary.json` | `da2a082e13fa99e9d5a143fe2f4f210bc6e7f0b3c7095e140fd9f2d2aff09dd4` |

其余原范围核验：诊断保持 hash/分类/抽象根因，5 个假阴性及 6 条 citation 的结论仍限定指定范围，未重新裁决私有逐题结论。仓外脚本动态加载仓库 heuristic，保留不可答题不得 supported 的约束，无题号/hash 特判；本会话只读脚本，未执行。prompt 保留核心所问、背景不得冒充、`has_answer=false` 和空 `source_ids` 约束。公开回归仍为 development 的 31/9 outcome 对比，未宣称新的全量独立 support/citation 复审。费用继续声明 draft peak、非 owner-signed；49,160 microyuan = CNY 0.049160，新增 0.049160 + 0.098320 = 0.147480，含既有约0.074的累计约0.27算术自洽；预留不等同实际账单，未核验底层回归账本。`git ls-files` 的 `.blindtest`/private-blind 路径命中为0，两份公开全量聚合的 `question_results` 均只含 `id_hash/outcome/category`，hash 均为64位十六进制。

## 验证记录

```text
PYTHONDONTWRITEBYTECODE=1 services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider evaluation/smoke/test_heuristic_review.py
10 passed in 0.03s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src services/ai/.venv/bin/python -m pytest -q -p no:cacheprovider services/ai/tests/test_answering.py
31 passed, 2 warnings in 3.34s

git diff --check
通过
```

heuristic 测试启动有 pytest-asyncio fixture 默认作用域弃用提示；answering 的两条 warning 来自取消检索测试中本地 socket 服务线程的 `ConnectionResetError`，未导致失败。未新增测试文件、缓存或探针产物。现有测试通过，但未覆盖本轮“且”连接的事实绑定、追加独立引用触发裁剪绕过、以及正确小数端到端正例，不能据此关闭上述 Findings。

最终结论：原样回归及报告同步已完成，仍有可复现的事实冲突误接受和引用裁剪绕过，故本轮不批准。仅提交本审阅文档。
