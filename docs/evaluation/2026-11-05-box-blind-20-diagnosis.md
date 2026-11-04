# Box 盲测 20 失败诊断（独立 Sol 复审）

- Reviewer: Sol High
- Date: 2026-11-05 Asia/Shanghai
- Branch: `grok`
- Predictions SHA: `830f80b23ac7b713107e263a6e82280d118c71d189ee122d1da98009b7f3ed0a`
- Code SHA at collection: `bf720e4393511e68f72304c276d7893ae729b23a`
- Scope: 独立阅读指定五题的私有材料，逐引用、逐题作语义判定；不重跑评测，不调用模型服务，不修改业务代码，不 commit/push。

## 判定口径与核验

已对照私有 question、reference、gold evidence、预测回答、每条 citation 的 claim 与实际指向的文本，以及原 review、notes、sidecar、评分器实现和公开报告。预测文件 SHA 与采集 code SHA 均与 brief 一致。引用文本与 runner 文档切片及其哈希一致，引用关联一致；四道可答题的检索范围覆盖对应 gold。未发现指错文档、切片错位或证据版本不一致。

以下 citation 使用题内零起始序号，仅作定位，不披露来源标识或正文。对同一句末的并列引用，按各自支撑的事实分句判断归属，再核验联合证据是否覆盖整句；不会把自动抽取的复合 claim 中其他来源负责的分句，直接当作该引用捏造的事实。

`contentful_parts` 分割后，`grounded` 要求至少半数片段逐字出现在单条 evidence 中；同义表达、措辞连接和有证据的推导均可能不满足这一要求。`sentence_around` 不在分号处分句，可能把同一句内前面的其他事实并入当前 citation 的上下文。本组中该作用域扩大与单条 evidence 的匹配要求叠加，形成误判。

评分器的 support 分支在 citation 未全部通过时直接判 unsupported；即使 reference 子串命中达到阈值，也不能挽回。因而这里的 support 失败不能作为独立于 citation 误判的第二份产品缺陷证据。

## Per-failure verdicts

### sha256:55515dc10c35

- answerable: true
- heuristic: support=unsupported; citations=[unsupported, supported]
- independent_verdict: scorer_false_negative
- categories: citation=scorer_false_negative; support=scorer_false_negative

| citation 序号 | heuristic | independent verdict | root_cause |
|---|---|---|---|
| 0 | unsupported | scorer_false_negative | 复合比较句末并列引用；该来源支撑其中归属本来源的事实，另一来源支撑其余分句。自动上下文聚合后，要求当前单条证据命中整个复合句的半数片段，超出了该引用的事实归属范围。 |
| 1 | supported | supported | 对应事实有直接证据，与相邻引用共同覆盖复合句。 |

- root_cause: 关键结论与 reference 一致，补充事实也有对应来源。所引 chunk 覆盖相应 gold；失败来自 `sentence_around` 扩大的句子作用域及 `contentful_parts` 的单证据精确匹配要求，没有发现错误归属或无证据的关键结论。
- notes: 原 notes 的 reference 命中为 5/9，已经达到该启发式的阈值；support 仍失败，直接原因是 citation 未全通过。

### sha256:e224b8d1b48d

- answerable: true
- heuristic: support=unsupported; citations=[supported, unsupported]
- independent_verdict: scorer_false_negative
- categories: citation=scorer_false_negative; support=scorer_false_negative

| citation 序号 | heuristic | independent verdict | root_cause |
|---|---|---|---|
| 0 | supported | supported | 对应结论由所引证据直接支持。 |
| 1 | unsupported | scorer_false_negative | 同义结论与证据中的直接表述合并，分割后的片段含额外连接措辞；事实含义未改变，但完整子串命中不足半数。 |

- root_cause: 两条引用均指向覆盖相应 gold 的证据，回答的关键结论完整且正确。第二条 citation 是 `contentful_parts` 加精确子串阈值造成的假阴性，support 随之被连带判失败。
- notes: 原 notes 的 reference 命中为 5/8；这一命中结果同样未能越过 citation 全通过的必要条件。

### sha256:d2087ac961bd

- answerable: true
- heuristic: support=unsupported; citations=[unsupported, unsupported]
- independent_verdict: scorer_false_negative
- categories: citation=scorer_false_negative; support=scorer_false_negative

| citation 序号 | heuristic | independent verdict | root_cause |
|---|---|---|---|
| 0 | unsupported | scorer_false_negative | 对证据数值的同义复述改变了分割片段，精确子串规则未识别语义等价；关键数值及其归属均有证据。 |
| 1 | unsupported | scorer_false_negative | 对应来源支撑本分句；`sentence_around` 又跨分号纳入前面的另一来源内容，扩大单条证据需要覆盖的范围，claim 回退匹配也未识别同义复述。 |

- root_cause: 两来源分别覆盖所需事实，跨来源的简单计算正确，结论可由已引用证据推出。推导结果不必原样出现在某一条证据内。回答保留了假设性语境，没有把比较对象误作现行依据；未逐字重述 reference 的附加限定，不构成主要结论错误。
- notes: 原 notes 的 reference 命中为 0/6，反映逐字匹配不能识别改写和计算，不代表语义无支撑。两条 citation 的误判又直接触发 support 失败。

### sha256:7ee3f7e0772b

- answerable: true
- heuristic: support=unsupported; citations=[unsupported, supported]
- independent_verdict: scorer_false_negative
- categories: citation=scorer_false_negative; support=scorer_false_negative

| citation 序号 | heuristic | independent verdict | root_cause |
|---|---|---|---|
| 0 | unsupported | scorer_false_negative | 所引规则足以支持对题设的直接比较判断；新增的是可验证的逻辑推论，而非外部事实。精确子串规则把推论措辞作为未命中片段。 |
| 1 | supported | supported | 对应要点由所引证据覆盖。 |

- root_cause: 回答与 reference 的判断及关键要点一致，两条证据均覆盖对应 gold。`contentful_parts` 的片段阈值不识别由明确规则直接推出的结论，造成第一条 citation 假阴性，并连带污染 support。
- notes: 原 notes 的 reference 命中为 6/7；support 的失败来源仍是 citation 全通过条件。

### sha256:22d252ae8204

- answerable: false
- outcome: answered
- heuristic: support=unsupported; citations=[supported, unsupported]; refusal=fail
- independent_verdict: scorer_false_negative
- categories: citation=scorer_false_negative; support=scorer_false_negative; refusal=scorer_false_negative（依 brief 的语义标准）

| citation 序号 | heuristic | independent verdict | root_cause |
|---|---|---|---|
| 0 | supported | supported | 有限背景事实由所引证据直接支持，未据此断言未知事实。 |
| 1 | unsupported | scorer_false_negative | 背景关系的同义概括有对应证据；精确子串匹配失败，且句子上下文还含信息不足的说明。不能要求单条证据逐字包含这种说明。 |

- refusal_verdict: scorer_false_negative。正文明确保留了所问信息的未知状态，未给出无证据的实质性结论；有限背景说明不等于回答了不可答部分。因此不满足 brief 中“给出了实质性答案而非拒答”的产品缺陷条件。
- support_verdict: scorer_false_negative。背景事实及关系有证据，信息不足的判断与 reference 一致；核对语料也未发现遗漏的可答证据。没有将证据缺失反推为一个确定事实。
- root_cause: citation 失败来自同义概括和过宽上下文的字面匹配；support 失败继承 citation 误判。refusal 失败则存在结构化 `outcome=answered` 与正文拒答语义不一致的问题，不能仅凭该标签推断正文实质性乱答。
- notes: 本题按 brief 的正文语义标准归为假阴性，并不否认原结构化 outcome 会触发原门禁失败。状态一致性应单独核验；本次没有改写预测、review 或原报告，也没有据此宣称原门禁已经通过。原 notes 的 reference 命中为 1/4，不改变上述语义判断。

## Summary

- scorer_false_negative: 5
- product_defect: 0
- mixed: 0
- 原判 unsupported 的 citation：共 6 条，独立复审均为 scorer_false_negative。
- 整题 support：共 5 项失败，独立复审均为 scorer_false_negative。
- refusal：1 项失败，按 brief 的语义标准为 scorer_false_negative；结构化标签与正文语义的差异已单列。
- recommended_fix_targets: [scorer, answering_refusal]

scorer 应先修正 citation 的事实归属和上下文范围，允许并列引用分别支撑相应分句，并识别同义改写及有证据的简单推导。support 应依据整答与联合证据独立判定，避免机械继承任意一条 citation 的字面匹配失败。refusal 应分别核验正文是否保留未知信息及结构化状态是否一致；`answering_refusal` 在这里指状态对齐核验，不代表本轮确认了实质性乱答。

以上结论仅覆盖指定五题和对应六条失败 citation，不外推整套产品质量，也不替代原门禁结果。
