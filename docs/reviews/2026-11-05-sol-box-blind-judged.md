# Box 盲测 20：LLM 门禁报告与方法独立审阅

- Verdict: **APPROVED**
- Findings：P0 = 0；P1 = 0；P2 = 3（改进建议，不阻断本报告）。
- 日期：2026-11-05（Asia/Shanghai）。
- 分支：`grok`；审阅时 HEAD：`cb9cfd80d0b5dc24ad7f08f9437d539ad9feca11`；审阅对象包含当前未提交文件。
- Brief：`/workspace/knowflow-briefs/2026-11-05-sol-blind-judged-review.md`。
- 独立性：本会话未参与初判、Kimi 二判或仲裁实现；未新增语义法官判断。只新增本文，不改业务代码、被审报告、资产或仓外数据，不 commit/push，不调用付费 API。

批准范围是报告数字、证据链与方法记录。**Original 与 post-diag 的产品门禁均为 failed；本审阅不授权将产品标为通过，也不关闭 R4 的已知 P1。** Post-diag 保持已污染对照身份。

## 核验范围与证据

已读取 brief 指定的报告、三份 judged/agreement 资产、早期跑评报告、R4 审阅、heuristic 模块 docstring 及 `runner_v2.py` 的 review 契约；另对照早期 diagnosis、两套法官 brief 和仲裁 brief。

仓外核验在 `/workspace/knowflow-private-blind/2026-11-04/judged/` 内进行。用 `PYTHONDONTWRITEBYTECODE=1 python3` 调用当前 `runner_v2.evaluate`，分别读取冻结 predictions、`runner/` 数据集、`gate.json`、`review-final.json`，在内存重新评分，没有重采预测或调用模型。两次返回的**完整结果对象**均与对应 `metrics-final.json` 相等，不只比较门禁小数。输出仅含计数、标签、hash 和核验状态，未打印题面、答案、claim、source_text 或 quote。

随后独立重建逐字段标签映射，验证 answered 题集合、citation ID 顺序及唯一性、分歧集合、仲裁集合、最终 review 和公开逐 hash 摘要。未执行仓外 merge 写入脚本。

## 门禁核对

下表以 runner 四位小数为准；被审 Markdown 的三位显示是正常舍入。两份公开 summary 的 `metrics`、`quality_gate` 及 predictions SHA 与仓外最终结果完全一致，表格的数值和 passed/failed 标签也一致。

| Gate | 阈值 | Original | Post-diag |
|---|---:|---|---|
| Recall@5 | ≥0.85 | 30/30 = 1.0000 passed | 30/30 = 1.0000 passed |
| MRR@10 | ≥0.75 | 1.0000 passed | 1.0000 passed |
| Support | ≥0.90 | 14/16 = 0.8750 **failed** | 13/14 = 0.9286 passed |
| Citation | ≥0.95 | 22/25 = 0.8800 **failed** | 14/20 = 0.7000 **failed** |
| Unanswerable refusal | ≥0.90 | 4/5 = 0.8000 **failed** | 5/5 = 1.0000 passed |
| Answerable answer | ≥0.90 | 15/15 = 1.0000 passed | 14/15 = 0.9333 passed |
| Support review coverage | =1.00 | 16/16 = 1.0000 passed | 14/14 = 1.0000 passed |
| Citation review coverage | =1.00 | 25/25 = 1.0000 passed | 20/20 = 1.0000 passed |
| Overall | 全项满足 | **failed** | **failed** |

每组 20 题，15 可答、5 不可答，execution error 均为 0。Coverage 的分母是 answered 答案及其 citation，并非对所有拒答正文做了语义审核。`human_*` 是 runner 兼容字段名，本轮标注来自 LLM，不是人工金标。

预测指纹核对通过：

- Original：`830f80b23ac7b713107e263a6e82280d118c71d189ee122d1da98009b7f3ed0a`。
- Post-diag：`71d8fc2e04436d4b47b073d8cc825ac4d36b594080208c5d7b0c13ef907cc107`。

## 一致率及仲裁应用

| Set | Support 一致 | Citation 一致 | 分歧字段数 | 仲裁覆盖 |
|---|---|---|---:|---|
| Original | 15/16 = 0.9375 | 24/25 = 0.9600 | 2 | 2/2，均 unsupported |
| Post-diag | 13/14 = 0.9286 | 14/20 = 0.7000 | 7 | 7/7，均 unsupported |

以上与公开 agreement 资产、Markdown 及仓外分歧记录一致。分歧数按字段计：original 为 1 个 support 加 1 条 citation；post-diag 为 1 个 support 加 6 条 citation，后者涉及 3 个 hash，不能表述为 7 道分歧题。

对每个分歧键 `(question_id, field, citation_id)`，仲裁恰好覆盖一次，没有缺项、重复或额外覆盖。以 Sol 初判为基底、仅覆盖这些键后，得到的标签与 `judgements-final.json` 及 `review-final.json` 完全一致；非分歧字段保持原判。Review-template 也与当前 runner 从冻结输入重新生成的对象相等，最终 review 通过 runner 对预测/数据集指纹、原文及证据字段不可篡改、标签、审核人和时间戳的校验。

Original 两次仲裁分别同意 Sol 与 Kimi 各一次：`55515dc10c35` 的 support 维持 Sol unsupported；`1931ea79adc1` 的第 0 条 citation 从 Sol supported 改为 Kimi 一侧的 unsupported。Post-diag 的 7 个仲裁均同意 Sol，最终标签与 Sol 初判相同。最终结果可由逐项仲裁记录重建；因 9 项均 unsupported，数值也恰好等同于取更严标签，不能仅据这些数值证明仲裁的独立语义质量。

## 失败 hash 核对

公开报告与两份 summary 当前列出的失败 hash、answerable、outcome 和分类逐项一致，也与最终标签一致：

| Set | id_hash12 | answerable / outcome | fail categories |
|---|---|---|---|
| Original | `55515dc10c35` | true / answered | support, citation |
| Original | `1931ea79adc1` | true / answered | citation |
| Original | `22d252ae8204` | false / answered | support, unanswerable_refusal |
| Post-diag | `55515dc10c35` | true / answered | support, citation |
| Post-diag | `d2087ac961bd` | true / answered | citation |
| Post-diag | `1931ea79adc1` | true / answered | citation |

这项一致性核验不代表逐题失败摘要完整：两处共同漏标 post-diag 的可答误拒答，见 P2-1。

## Findings

### P2-1：可答误拒答未进入逐题失败摘要

位置：[门禁报告 post-diag 失败表](../evaluation/2026-11-05-box-blind-20-judged.md) 第 47 行、[post-diag summary](../evaluation/assets-box-blind-20261105-postdiag-judged-summary.json) 第 218 行。

`339c8aa2ffe9` 为 `answerable=true, outcome=refused`，summary 却给出 `fail_categories=["none"]`，报告也未列入该 hash。聚合数已正确计入 1/15 可答误拒答、answerable answer 14/15，故不改变任何门禁结论；但读者可能将逐题 none 理解为该题行为正确。

建议：增加该 hash 的 `false_refusal`（或明确等价的可答未回答分类），同步补入报告；或明确失败表仅列特定审核维度，并另列可答误拒答。验收时应保留 support=`n/a`、citation_pass=`null` 及既有聚合值，不把拒答伪造为 support/citation 审核失败。

### P2-2：早期 diagnosis 对照应分清相同预测争议、重采变化及规则差异

位置：[门禁报告与早期诊断的关系](../evaluation/2026-11-05-box-blind-20-judged.md) 第 70 行、[早期 diagnosis](../evaluation/2026-11-05-box-blind-20-diagnosis.md)。

报告正确保留了早期 `scorer_false_negative`，但把几个 hash 并列后以会话方差概括，无法精确说明分歧来自何处：

| id_hash12 | 早期 diagnosis 范围 | 本轮结果与解释边界 |
|---|---|---|
| `55515dc10c35` | original 假阴性 | 同一 original SHA 下仍有 support/citation 失败，构成直接待解释争议。 |
| `d2087ac961bd` | original 假阴性 | original 本轮无失败；post-diag citation 失败来自另一套预测，不能单凭 hash 相同归因会话方差。 |
| `1931ea79adc1` | 未覆盖 | 属于本轮扩大审核范围发现的失败，不能视为推翻早期该题判断。 |
| `22d252ae8204` | 按正文语义判假阴性 | 本轮明确规定不可答且 answered 必须 support=unsupported，并按结构化 outcome 计算 refusal；两者有已知规则差异。 |

建议补充上述分层对照。早期 diagnosis 对并列引用按各自事实分句归属审核，本轮 rubric 强调对应 claim/source_text；应明确完整复合 claim、局部断言和联合证据各自适用的判断范围。采用不含私有正文的合成示例固化口径即可；本审阅没有重新裁决私有语义，因此不认定已有失败必然是假阴性，也不认定“更严”自动更准确。

### P2-3：仲裁独立性应补充标签可见及同模型边界

位置：[门禁报告方法](../evaluation/2026-11-05-box-blind-20-judged.md) 第 14 行；仓外两份 `sol-blind-judge-resolve-*` brief。

仲裁来自独立会话，但输入分歧清单包含双方标签；original brief 也明确允许查看双方标签。它不是对既有标签盲评。第三会话与第一法官同为 Sol，post-diag 又恰好 7/7 维持 Sol，独立会话不能建立错误相互独立的保证。当前记录未显示复制标签或仲裁覆盖错误，但存在锚定及同模型相关偏差风险。

建议在方法局限中直述这些边界，并保留本次仲裁来源不变。后续若以法官分数支持发布，应预先约定仲裁规则、先隐藏双方标签独立作答，再对照分歧；这不要求本轮调用付费模型或重判数据。

## 方法风险及保留边界

**Kimi post-diag 是全通过，不只是近乎全通过。** 已核对其 support 为 14/14 supported、citation 为 20/20 supported；Sol 对其中 1 个 support、6 条 citation 判 unsupported。与全正类法官的 70% citation 一致率等于另一法官的正类比例，不能证明负例识别能力；100% coverage 也只证明填满标签。Original 的 Kimi 则为 support 15/16、citation 22/25 supported，不能把 post-diag 现象外推为其全部输出恒定。报告已承认该风险，当前 failed 结论没有据此放行产品。

**仲裁解决的是本次标签选择，尚未解决金标真实性。** 9 个分歧均归 unsupported 与“从严”相容，但没有人工金标证明其准确性。早期 diagnosis 的反向语义结论也来自 LLM；双方都不应被当成人工定论。报告保留矛盾、不回写关闭旧标签是合理边界，P2-2 建议进一步说明可比较范围。

**污染和样本量限制仍成立。** Original 保留冻结的未受本次诊断改动影响的预测基线；事后更换审核方法不使整套流程成为预注册评测，也不消除同组织出题及提示编写偏差。Post-diag 在诊断和产品 prompt 改动后采集，只能作污染对照。每组仅 5 道不可答题，单题使拒答率变化 0.20；support/citation 又有同题内相关性，不应将小样本点估计外推为稳定生产质量。

**Heuristic 降级与 R4 保留状态已确认。** [旧跑评报告](../evaluation/2026-11-04-rag-box-blind-20.md) 开头及后续 LLM 关联说明、[heuristic docstring](../../evaluation/runner/heuristic_review.py) 均标注 proxy, not gating；[R4 follow-up](./2026-11-05-sol-box-blind-postdiag-r4.md) 明确 residual P1 not closed，R4 原 Verdict 仍为 CHANGES_REQUESTED。此次最终 review 的标签链来自法官及仲裁，没有使用 heuristic 分数替换门禁。没有把改用 LLM 审核宣称为修复事实归属、引用裁剪绕过或小数边界缺陷；本审阅也未重新运行这些探针或关闭它们。

## 隐私、可复核性与验证结果

对被审报告及三份新资产检查了公开字段和文本：未见题面、答案、quote、原始题号或证据正文；逐题仅有 hash 与结构化标签。将两套私有 review-template 的 question/answer/claim/source_text 与这些公开文件作连续 24 字符窗口比对，命中为 0；独立题号 token 命中也为 0。该检查用于辅助发现逐字泄漏，不构成对所有短片段或语义改写泄漏的形式化证明。本文只保留 hash、数字、分类、抽象方法说明及文件位置。

本轮没有网络或模型调用，新增 API 花费为 0。报告中历史 judge spend RMB 0 与 brief 的订阅约束及 agreement 资产一致；未审计订阅账单或历史调用日志，不能把“未见调用记录”当作历史零花费的独立账务证明。

审阅快照 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `2026-11-05-box-blind-20-judged.md` | `2bdec9be49c75011a461b1b0589ed98362ad2237d06850cd3be298e40054fd51` |
| `assets-box-blind-20261105-original-judged-summary.json` | `97c032150165baf06f8eece863edc50d8fdffe23e38cef28990885f23d280ffb` |
| `assets-box-blind-20261105-postdiag-judged-summary.json` | `33935cb40f15233fd62b10e46a403e4145b749b02680a0bcf2edc22d55be44d1` |
| `assets-box-blind-20261105-judge-agreement.json` | `642eb38275c7914f55742074099d838447c86757c259c40947c0676cb40208c7` |
| `evaluation/runner/runner_v2.py` | `ce8507bf02c277c4bc11b694e8834b0a99a066de3b92262f8eb7f576d2945c63` |
| 当前 `evaluation/runner/heuristic_review.py` | `a11689bbd38e260043699d9d4b3d605517cda457daf5714af365a556aaa69754` |

当前 heuristic 指纹含降级 docstring，与 R4 探针绑定的 `b5a5b905…` 不同；本次只确认降级声明及未关闭状态，不用当前文件指纹替代历史探针记录。

验证结果：两组完整 metrics 重算相等；两组模板重建相等；全部法官标签覆盖完整；9/9 仲裁精确覆盖；公开门禁表、一致率和现有失败表核对通过；隐私窗口检查通过。仅新增本文，未修改输入文件。
