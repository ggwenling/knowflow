# Answer repair 默认开启安全闸设计

- 日期：2026-11-05；设计基线：`grok` / `6b6b3a9`。
- 状态：**设计 ready；当前实现不能直接改成默认 on 后发布。** Luna 应先实现下述完整接受链，再提交 Sol 对 **default-on** 的独立审阅。
- 本次交付仅此设计文档；未修改 `services/`，未执行采集、provider 调用或评测。
- 信息边界：仅检查公开 Sol 评审、公开评测报告、相关实现/测试和 public seed-v2 的 manifest；未读取任何盲测私有题面、答案、引用正文或私有产物。

## 1. Verdict 与批准条件

**有条件可行：默认开启“有界、可证明直接作答的修复路径”；不默认开放任意自然语言补问答案。** 仅改开关、扩充疑问词列表、提高全题 overlap 阈值、只限定剪枝 reason，均不足以关闭 P1。任一安全闸不确定即保持 canonical REFUSAL，不发布背景摘录或只回答部分要求的答案。

采用两项必须同时落地的改变：

1. 触发从 `repairable = not pruning.ok` 改为明确的引用失败白名单及运行条件；问题必须能被封闭的、完整匹配的规则解析为一个明确请求。
2. 接受从 `_has_question_content_overlap` 改为 **核心请求与单条证据事实绑定**。问题、最终答案和引用原文须解析到相同主体、关系、限定条件，答案还必须填入问题真正请求的值；完整原文照录、citation verifier 通过仍是必要条件。

第一版只支持第 3 节明确列出的规则。规则外的问法保持拒答，不回退到旧 overlap，也不增加 LLM 可答性裁判。这样可以给出可复现的接受边界，代价是修复覆盖率有限。扩规则只能基于 public seed-v2 development，并重新过全部负例与审阅；不得为了提高覆盖率引入“未知时也尝试接受”的分支。

Sol 批准默认开启必须同时满足：

- 历次精确负例、rereview3 的“有多高”改写及第 5 节扩展矩阵，在 **unset 默认开启、显式 on、显式 off × 同步/SSE** 下全部符合期望；不得靠覆盖服务私有 `_repair_enabled` 字段模拟默认开启。
- 至少一个真实引用失败后可修复的正例在 unset 下成功；失败路径、预算、长度、取消、契约约束均保持。
- 公开集成对验证不出现新增不可答误发布或其他原正确拒答被背景答案覆盖；support/citation 不退化，answerable_answer_rate ≥0.90，审核覆盖 100%。默认开启的安全批准与后续盲测指标通过须分别记录。
- 无未关闭的 P0/P1。不能沿用 rereview3 在默认 off 下的 APPROVED 作为默认 on 的批准。

公开 v4 基线是 repair **默认 off** 下 answerable 13/15、unanswerable refusal 5/5，未试 opt-in。两个公开失败 hash 只能说明 false_refusal，无法说明首轮是否自报可答、是否被剪空或是否可被本方案修复。如果假设题数仍为 15，≥0.90 至少需要 14/15；这只是门槛算术，不能推出本设计会挽回其中任一题。不得查询 hash 对应正文或据其调参。

## 2. 触发：先证明属于允许尝试的失败

### 2.1 当前逻辑的实际边界

`AnswerService._evaluate_generated()` 在生成结果的 JSON/ID/作用域检查通过后调用 `prune_claims()`，目前设置 `repairable = not pruning["ok"]`。`_finalize_generation()` 再判断开关和剩余时间。首轮 `has_answer=false` 与空 evidence 不进入补问。

注意 `not ok` 也包括 `answer_too_long_after_prune`，不一定代表“没有保留断言”：超长结果可能仍有 kept claims。`no_cited_claims` 也不代表允许跳过来源声明检查；正常服务入口先要求 declared IDs 非空、正文 marker 集与其一致，因此一些纯无引用输出在到达该 reason 前就已失败。实现不得为了让此 reason 可达而放松入口检查。

### 2.2 新 eligibility 的必要且联合条件

以下全部为真才将策略层 `repairable` 设为 true：

| 条件 | 可测试规则 |
| --- | --- |
| 首轮是待修复答案 | 原始生成结果已通过现有结构、ID、批次/作用域及响应契约检查；原始 `has_answer is True`。 |
| 有证据 | 本请求检索 evidence 非空；使用原批次快照，不重检索、不扩大 scope。 |
| 首轮已经拒答 | 评估后 `decision=refused`、正文为 REFUSAL、`sources=[]`。 |
| 是引用失败 | `pruning.reason` 仅允许 `empty_after_prune`、`no_cited_claims`。 |
| 确有断言但没有可保留项 | `claims > 0`、`kept_claims == 0`、`kept_source_ids == []`，且有 dropped 或 uncited claim；不能仅看 `not ok`。 |
| 核心请求可解析 | 问题全文被第 3 节规则唯一匹配；一个主体、一个请求关系、一个结果槽；每个限定成分均有绑定或被明确判为无语义的格式字符。 |
| 运行条件 | 开关开启；未取消；总 deadline 尚余 ≥6s；每请求至多一次 repair。预约仍由原预算入口负责，软停不能绕过。 |

不在调用前要求 evidence 已含答案，以保留历次负例的“一次尝试后拒答”可比性；证据事实证明放在接受阶段。题目解析本身不消耗 provider 调用。

### 2.3 明确禁止补问

| reason / 情况 | 行为 |
| --- | --- |
| `model_declined`，无论 evidence 是否非空 | 保留标准拒答，attempt=0，outcome=`not_attempted`。不得把首轮模型拒答解释成引用问题。 |
| `empty_evidence` | 同上；不创建补问模型。 |
| `grounded` / 已有可发布首轮答案 | 保留首轮结果，attempt=0；本设计不修改首轮答案相关性规则。 |
| `answer_too_long_after_prune`，包括仍有 kept claims 的情况 | 保留标准拒答，attempt=0；不得借补问绕过长度失败。 |
| 空正文、纯 marker、`claims==0` 或未知剪枝 reason | 标准拒答且不补问；reason 默认拒绝，新增枚举必须显式审阅才能加入白名单。 |
| 结构/声明 ID/作用域校验失败，缺 declared IDs、伪造来源、marker 不一致 | 不补问；保持既有协议/模型错误边界，不修复成可发布答案。此类不是“证据不足”reason；本设计不把请求本身的协议错误伪装为 REFUSAL。 |
| 不支持或歧义问题、多问、比较/计算/排名、未知限定条件 | 首轮已被剪空则保持标准拒答，不补问；不删除未知部分后再解析。 |
| 显式关闭 | attempt=0，outcome=`not_attempted`。 |
| 满足 eligibility 但剩余 <6s | attempt=0，outcome=`skipped_deadline`。恰好 6s 允许尝试，仍受总 deadline 约束。 |
| 取消 | 传播原取消行为，不调用 repair 或终止在途 repair；不转换成成功拒答来吞掉取消。 |

## 3. 核心接受闸：封闭的请求/事实绑定

### 3.1 第一版可实现的请求模型

新增纯函数模块（建议 `repair_gate.py`），返回 `RepairTarget` 或有枚举原因的拒绝；不读取 gold/reference，不调用模型。`RepairTarget` 包含 `subject`、`relation`、`constraints`、`expected_value_type`、规则版本。它是由完整语法提取的请求，不是从全题 bigram 中挑出若干关键词。

第一版规则固定如下，便于 Luna 实现及 Sol 审阅。`Y` 是独立的四位 ASCII 数字年份，`E` 是非空、无歧义的实体字面名称；各槽必须有原问题的 span。为避免任意实体正则把“预测/比较/条件”等语义吞成名字，第一版 `E` 使用版本化的精确名称表，最低包含公开合成例的 `公司/甲公司/乙公司`；未知名字拒绝，不从 evidence 自动扩表，不做模糊匹配。实际扩表只能来自公开 development 或明确的产品实体配置，并随规则复审。如果存在两种分槽方式就拒绝。内部正规化仅 NFC、首尾空白及明确的格式空白；年份/值/单位按槽比较，不按子串比较。

| relation | 接受的问题全文形式（末尾 `？/?` 可省） | 请求与允许的源事实形式 |
| --- | --- | --- |
| `search_gate` | `[Y 年]索引何时可检索` | 主体=索引；年份可选；请求可检索所需状态。源事实：`[Y 年]索引 READY 后才可检索`；值=READY 后。这里支持状态门槛问题，不支持询问准确日期、时刻或耗时。 |
| `default_cache_state` | `[Y 年]缓存默认关闭吗` 或 `[Y 年]缓存默认状态是什么` | 主体=缓存；请求默认状态；源事实：`[Y 年]缓存默认关闭` 或 `…默认开启`；值是开启/关闭枚举。问“关闭吗”时，引用“默认开启”也直接给出了否定答案，不可删除状态词。 |
| `net_profit` | `[缓存默认关闭时，]E [Y 年]净利润是多少` 或 `…净利润有多高` | 主体=E，关系=净利润，年份可选；若带缓存条件则 conditions 中必须保留它。源事实：`[缓存默认关闭时，]E [Y 年]净利润为 N U`；N 为单个明确十进制数（可负），U 为元/万元/亿元。值必须是金额，年份不算金额。 |

方括号在上表表示语法可选项，不是正文字符。`Y 年` 周围的分隔空白可有可无；`E`、`Y`、`净利润` 之间只允许格式空白。`N` 只接受 `-?[0-9]+(?:\.[0-9]+)?` 形态，无千分位、范围或科学记数法；用十进制定点值而非浮点比较。源事实可带一个固定前缀 `原始资料说明`，这是公开 fake fixture 的叙述前缀；除此之外不做任意前缀/后缀剥离。源事实尾部仅允许一个句末 `。/.` 和格式空白，问题尾部仅允许一个 `？/?` 和格式空白。所有匹配均锚定完整输入，禁止搜索到一个子句就忽略其余语义。

这三类是最低实现范围；**不是**根据盲测选择的关系。前两类来自现有公开正例，第三类用于保护 Sol 已公开的净利润负例。没有枚举到的问法一律不修复，例如“净利润同比增长多少”“2027 和 2028 哪年更高”“请预测净利润”。扩展为通用自然语言理解不属于第一版。

### 3.2 接受条件 A1–A7：全部满足才覆盖首次 REFUSAL

**A1 原有校验通过且完整。** 补问生成继续走同一个 `_evaluate_generated()` / `prune_claims()` / AnswerResponse 契约。必须 `has_answer=true`、`decision=answered`、最终正文不超过 16,000 code points，所有 IDs 都在原 evidence 快照中。第一版修复只接受一条完整事实、一条实际引用、一个 source_id；要求原补问正文也只包含这一事实及引用，`kept_claims=1`、`dropped_claims=0`。不能把“正确一句+错误一句”剪成半份答案再通过核心闸；纯 marker、前言、附加结论也不能被当作无害内容略去。

**A2 来源逐字绑定。** 去掉服务识别的引用 marker 后，最终事实正文在所附单个来源的一条完整事实单元中逐字成立（沿用 NFC/空白正规化；不删数字、否定、限定词）。不得从多个来源或多个不完整句子拼出证明。marker 的位置仍由原 verifier 解释，不自行写一套不同的引用归属规则。候选须覆盖完整事实单元；不能从“公司净利润为 100 万元是错误示例”中只截取前半句。

**A3 同一关系、同一主体。** 问题、答案事实和支持它的源事实须分别成功完整解析，再比较 `subject` 和 `relation`。`公司` 不覆盖 `甲公司`，`甲公司` 不覆盖 `甲公司子公司`；不自动补主语，不进行代词消解。源里出现主体名、年份和“净利润”字样但没有金额事实，仍不满足此条及 A5。

**A4 所有限定条件按角色绑定。** 年份、问题给出的数值/单位约束、条件、默认/当前等关系限定均须在同一事实中绑定到所问关系。不存在“全题覆盖达到一定比例即可忽略剩余条件”。`2027` 不能被 `12027`、`2027` 字样的 source_id 或另外一句缓存背景覆盖；数字出现在正确槽之外也不算满足。问题未给年份时，不允许任选某一年的净利润当无条件答案；第一版要求答案与问题的约束槽精确相等，不做范围包含、单位换算或隐式条件推断。未知修饰成分直接拒绝解析。

**A5 请求值被填入。** 金额请求必须有净利润关系下的 N+U；状态请求必须有对应状态；状态门槛请求必须有对应 READY 后条件。`未披露`、`未知`、`暂无数据`、复述问题、只有年份、只有“净利润”名词，都不是请求值。第一版也不接受预测、假设、目标、示例、引用他人问题、否定某金额而未给真实金额等事实形态。完整语法不匹配即拒绝，不能靠再补几个否定停用词放行。

**A6 证据上下文和冲突不含疑点。** 支持单元必须是独立陈述事实。若其含义依赖跨句主语、表头、上文条件、代码/引号内示例、标题标为预测/草案等未解析上下文，则第一版拒绝该证明，不提取局部肯定短句。扫描原批次 evidence：同一主体/关系/约束若存在不同已解析值，或出现同一核心关系但带无法解释的否定/条件/限定，拒绝本次修复。不能只选候选引用的有利句、用别处的金额补齐，或自行决定版本/事实优先级。上下文无法判清时拒绝，不要求为任意文档格式做语义推断。

第一版将 A6 落为保守、确定的规则，避免把“判清上下文”留给 Luna 自行猜测：**被用作证明的整个 `text_content` 必须完整匹配一条源事实语法**（包括可选固定前缀/句末标点），不从长 chunk、标题、表格、代码块或引号中抽子句。对其他 evidence：完整解析为不同主体或不同关系的事实时，才可据此判为无关；同主体、同关系但约束不同的事实不能仅因年份或条件不同而忽略，同主体、同关系、同约束时比较值。若同主体、同关系、同约束的值冲突，或同主体、同关系但约束不同，阻止本次修复。无法完整解析且包含所问主体字面名的来源也阻止本次修复，不要求额外命中连续关系锚词；普通改写或空白差异不能证明无关。该保守扫描可拒绝相关但无害的长背景，这是已接受的覆盖率代价。不得用简单切句丢弃标题、条件或否定来绕开它。检索若无法提供足够完整的语境，保持拒答；本轮不新增检索以补语境。

**A7 最终响应同一出口。** A1–A6 只检查实际将发布的完整正文和对应 source，全部通过后才原子替换首次响应，`repair_outcome=answered`。同步和 SSE 共用这个分支；检查完成前不得发出首版或补问候选正文。标准拒答必须是 `没有足够的资料证据回答这个问题。`、`has_answer=false`、`sources=[]`，不附背景摘录或解释。

### 3.3 与旧 overlap 的关系

**替换接受依据，而不是在现有启发式后再加一个宽松 OR。** `_has_question_content_overlap` 不再参与补问发布授权，可以删除；若保留作本地诊断，它的结果不能影响最终判定。全题 ≥50%、已知疑问词前主体 token、数字集合包含均不是充分条件。数字覆盖职责由 A4 的带角色约束匹配接管；主体与核心关系覆盖由 A3 接管；直接作答由 A5 接管。

特别是“缓存默认关闭时，公司 2027 年净利润有多高？”：能解析出 `relation=net_profit`，但缓存摘录只能解析成 `default_cache_state`，既无净利润关系又无金额，必须失败。即使候选添加“净利润”三个字、照录提到“未披露净利润”的句子，或共享所有题目词，也不能填上金额槽。

提示词可要求“只输出能直接回答核心所问的一条完整原文事实，无法满足则 has_answer=false”，但它只是减少无效输出；可发布性的判断必须在服务端完成。不采用模型自报“可答”或另一个 LLM 的 yes/no 代替上述证明。

## 4. 调用顺序、诊断与失败语义

建议 `_finalize_generation()` 顺序：首轮现有评估 → 若已可发布则直接返回 → 构造并冻结首次标准拒答 → 判定 reason/计数 eligibility → 全题解析 → 开关/时间/取消检查 → 至多一次受预算约束补问 → 同一 verifier/契约 → A1–A6 → 原子选择最终响应。取消检查沿用既有控制机制，并在任何 provider 调用之前再次执行。

保留 `repair_attempt` 的当前含义：0=未进入补问调用，1=进入一次（预算预约拒绝也记这一次尝试），不是“成功发出 HTTP 的次数”。不得用它代替 ledger 计费次数。

| 结果 | repair_attempt | repair_outcome | 对外行为 |
| --- | ---: | --- | --- |
| 未满足 eligibility / 问题不支持 / 显式 off | 0 | `not_attempted` | 保留首轮结果；若首轮已剪空则标准拒答。 |
| 时间不足 | 0 | `skipped_deadline` | 标准拒答。 |
| 原 verifier 仍不通过或补挂后超长 | 1 | `still_ungrounded` | 标准拒答。 |
| 补问自报无答案 | 1 | `declined` | 标准拒答。 |
| verifier 通过，但 A1 完整性附加条件或 A2–A6 失败 | 1 | `failed_unrelated` | 标准拒答；内部细分失败原因。 |
| 补问契约失败 | 1 | `failed_contract_validation` | 标准拒答，不变成 SSE error 或同步请求错误。 |
| 补问超时 / provider / 预算软停等受控错误 | 1 | 保留现有 `failed_<ProcessingError.code>` | 标准拒答；不吞取消，不添加重试。 |
| 所有闸通过 | 1 | `answered` | 仅发布完整修复答案及其一条 source。 |

`prune_claims()` 的 `reason` 和 counts 继续表示引用检查结果；策略层 `repairable` 才表示是否可尝试，不把超长或未知问法标为可修复。拒绝候选时保留首次拒答的 decision/reason/counters，不拿候选 `decision=answered` 污染最终诊断。

建议新增有限枚举字段 `repair_gate_reason` 到内部 citation diagnostics/sidecar，取值例如 `not_checked`、`unsupported_question`、`ambiguous_question`、`ineligible_reason`、`no_claims`、`candidate_incomplete`、`no_verbatim_fact`、`subject_mismatch`、`relation_mismatch`、`constraint_mismatch`、`missing_value`、`unsupported_context`、`conflicting_evidence`、`passed`。多个失败按 A1→A6 顺序记录首个原因；不得记录 span、实体、题面、答案、引用正文、token 列表或 source_id。预测行和 AnswerResponse/SSE schema 不增加字段。

## 5. 必测矩阵

### 5.1 历次 Sol 精确负例及公开正例

公共 fixture：`s1=src-evidence-1`，`s2=src-evidence-2`；默认资料 1 为“原始资料说明索引 READY 后才可检索。”。首轮均使用现有 `_ungrounded_generated()`：

```text
索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。
```

首轮原始 `has_answer=true`，声明 s1/s2。每例必须先独立证明 `_evaluate_generated()` 得到 REFUSAL、`empty_after_prune`、kept=0；不能把“模型首轮直接拒答”冒充触发测试。补问候选 `has_answer=true` 并只声明实际所引来源。

下表每行执行 **同步与 SSE × unset 与 on**；在空串、空白、未知值默认开启时也执行同样矩阵。预期列是最终值。

| ID / 场景 | 问题 | 资料 2 / 补问完整正文（省略 marker 仅用于表格可读性） | has_answer | repair_attempt | repair_outcome |
| --- | --- | --- | --- | ---: | --- |
| N0 零重叠 | 公司 2027 年净利润是多少？ | 资料：原始资料说明缓存默认关闭。候选：原始资料说明缓存默认关闭。 | false | 1 | `failed_unrelated` |
| N1 共享公司 | 公司 2027 年净利润是多少？ | 资料：原始资料说明公司缓存默认关闭。候选：公司缓存默认关闭。 | false | 1 | `failed_unrelated` |
| N2 共享背景 | 缓存默认关闭时，公司 2027 年净利润是多少？ | 资料：原始资料说明缓存默认关闭。候选：缓存默认关闭。 | false | 1 | `failed_unrelated` |
| N3 年份+背景 | 缓存默认关闭时，公司 2027 年净利润是多少？ | 资料：原始资料说明公司 2027 年缓存默认关闭。候选：公司 2027 年缓存默认关闭。 | false | 1 | `failed_unrelated` |
| N4 rereview3 残留 | 缓存默认关闭时，公司 2027 年净利润有多高？ | 同 N3。 | false | 1 | `failed_unrelated` |
| P0 真正引用失败可修复 | 2027 年索引何时可检索？ | 将资料 1 改为“原始资料说明 2027 年索引 READY 后才可检索。”；资料 2 沿用缓存背景；候选完整照录资料 1，引用 s1。 | true | 1 | `answered` |
| P1 缓存状态修复 | 2027 年缓存默认关闭吗？ | 资料 2：原始资料说明 2027 年缓存默认关闭。候选完整照录并引用 s2。 | true | 1 | `answered` |

N0–N4 的候选都实际附上 `[src-evidence-2]`，P0/P1 也按现有格式在句末标点前附 marker；不使用无引用候选绕开真正的接受分支。每个负例的同步最终正文精确等于 REFUSAL，sources 为空；SSE 成功事件顺序为 `started → delta → sources → completed`，唯一正文为 REFUSAL、sources 事件的 has_answer=false，无候选文本、无 error。正例仅发校验后的答案和对应一条 source。

**off 对照**：上述所有行在 `off/false/0/no`（含大小写/首尾空白）下均应 false / 0 / `not_attempted`，正例也不修复。**默认开启测试**必须删除环境变量后重新构造服务、运行真实 finalize 链；不能只断言开关辅助函数。

### 5.2 不能靠新增词表修好的相邻负例

以下为公开 Sol 负例的设计变体/合成测试，不来自任何盲测包。除标注外，均使用引用失败首轮、支持解析的问题、同一 verifier 能通过的单 marker 候选；因此 default-on 下预期 **false / 1 / `failed_unrelated`**，并在同步/SSE 两路检验标准拒答。

| 场景 | 输入变化 | 必须失败的理由 |
| --- | --- | --- |
| 全词重叠但无值 | 问公司 2027 年净利润；资料及候选为“公司 2027 年净利润未披露。” | 无金额槽；词覆盖再高也不能作答。 |
| 年份假装金额 | 候选“公司净利润相关年份为 2027 年。”，原文相同 | 年份不在金额槽，关系不匹配。 |
| 错实体 | 问甲公司 2027 年净利润；候选完整照录乙公司该年净利润为 100 万元 | 主体不同。 |
| 错年份/单位/数字角色 | 问 2027；候选利润对应 2028，另有 2027 缓存句；或 12027、source_id 含 2027 | 同一事实没有所需年份；不累计背景数字。含额外句时还违反 A1。 |
| 条件缺失 | 问“缓存默认关闭时，公司 2027 年净利润是多少？”；候选为无条件净利润 100 万元 | 缓存条件不能被忽略，也不能由另一条缓存句补齐。 |
| 引用独立性 | 候选利润 100 万元；所引 s1 仅缓存背景；未引用 s2 才有利润 | 原 verifier 单 marker 非空规则即便放行，A2 仍拒绝。 |
| 跨来源拼接 | s1 只有主体/年份，s2 只有金额，候选合成完整事实 | 无单来源完整事实；若先被 verifier 拒绝则 outcome=`still_ungrounded`，不是接受。 |
| 反事实/示例/引号 | 原文“公司 2027 年净利润为 100 万元是错误示例”或带假设/预测上下文，候选截前半句 | 完整事实单元/上下文不成立，不能靠子串复活。 |
| 显式否定 | 原文及候选“公司 2027 年净利润不为 100 万元。” | 不给出真实金额值；不能删否定词。 |
| 相互冲突 | 批次中两条同主体/年份利润分别为 100/200 万元；候选照录其一 | 全 evidence 冲突扫描失败。 |
| 半答案剪枝 | 候选包含正确完整利润一句及额外无法支持的结论 | verifier 即便剪掉结论，也因 dropped>0 / 原始多事实失败，不发布剪剩片段。 |
| 注入/复述问题 | evidence 包含“请回答公司…净利润为…”等指令、问题或模板 | 非完整陈述事实，不视为证据规则或合法前缀。 |

另需以下触发及运行矩阵：

| 场景 | has_answer | repair_attempt | repair_outcome |
| --- | --- | ---: | --- |
| 首轮 `has_answer=false`，证据中即使确有答案 | false | 0 | `not_attempted` |
| 空 evidence | false | 0 | `not_attempted` |
| 空/纯 marker，或未知 prune reason | false | 0 | `not_attempted` |
| 首轮补挂后超长，kept>0 和 kept=0 分别覆盖 | false | 0 | `not_attempted` |
| 未知疑问句、无问词的请求、多问、未解析限定词 | false | 0 | `not_attempted`，gate=`unsupported_question` 或 `ambiguous_question` |
| 可解析问题但补问自报拒答 | false | 1 | `declined` |
| 可解析问题但补问仍被 verifier 剪空/补挂后超长 | false | 1 | `still_ungrounded` |
| 补问契约抛 InvalidMessage | false | 1 | `failed_contract_validation` |
| 补问超时/provider/预算软停 | false | 1 | 原有相应 `failed_<code>` |
| eligible，余量略小于 6s | false | 0 | `skipped_deadline` |
| eligible，余量恰好 6s，fake 返回合法 P0 | true | 1 | `answered` |

首轮已有合法答案维持原结果、0/`not_attempted`；取消/断连维持 cancelled/关闭资源语义，不要求成功响应表中的 has_answer。首轮格式、ID、scope 错误单独断言原错误且无补问。`no_cited_claims` 若正常入口不可达，在 policy 纯函数层构造 diagnostics 测白名单和计数，不能修改服务校验使非法输入可修复。

补充长度 15,999/16,000/16,001 边界、pruned_markers 非负及新增引用不抵消删除、两次模型均关闭、取消时无候选 delta、预算真实 adapter/fake guard 不双预约等既有 P2 回归。不要用纯 overlap 单测替代完整服务发布路径矩阵。

## 6. 公共验证、风险与中止条件

### 6.1 后续实施阶段的质量流程（本设计任务不执行）

1. 使用 `evaluation/data/seed-v2-reviewed`；development 可用于调整规则，holdout 只核验冻结方案。记录代码、规则版本、prompt、配置和公开集 split 指纹，on/off 共用相同模型、检索及预算政策。
2. 先完成离线 fake/MockTransport 的正负例与同步/SSE 测试，再在公开 development 做成对检查。冻结后核验公开 holdout；不因 holdout 失败反复调规则并仍宣称独立验证。
3. 报告 answerable answer、unanswerable refusal、support/citation、误拒答、error、覆盖率、eligible/attempted/answered 数量、总成本与延迟。特别报告每个 **off 拒答 → on 发布** 的转换，100% 审查其核心作答和逐句支持；不只看最终平均数。
4. 本方案新增的错误发布必须为 0；unanswerable refusal 不低于配对 off 基线，原正确拒答不得变成背景摘录。support/citation 不低于 off 基线且分别满足现有门槛 0.90/0.95，answerable_answer_rate ≥0.90；不能用可答率提升抵消任何不可答回归。基线为满分时就要求维持满分。公开小样本通过不证明任意自然语言安全。
5. Sol 独立审阅必须明确 verdict 是 default-on；通过后才交后续独立盲测执行者验证泛化。不得重跑 v1–v4 来找可接受参数；后续盲测结果只允许以 aggregates/类别/hash 返回给实现侧，不得读取私有正文调参。

### 6.2 主要风险与取舍

- **修复不了首轮直接拒答。** 该边界是产品约束；如果剩余误拒答来自 `has_answer=false`，本设计不会提升相应项。不得为目标数值擅自解除边界。
- **封闭语法降低召回。** 同义改写、表格、跨句、多事实问题会保持拒答；这可能导致默认开启依然达不到 0.90。应报告实际 eligible 覆盖和提升，不暗示一次补问必然解决两道 false_refusal。
- **规则与上下文识别仍可能漏义。** 完整语法、单事实单来源和上下文拒绝比 token overlap 明确，但不是通用语义证明。发现可复现背景/假设/冲突误放时，视为默认开启的 P1 候选，关闭相应发布路径；不能降格成 opt-in P2 后继续默认开启。
- **额外调用和时延。** 默认 on 意味着 eligible 请求最多两次生成；受同一预算预约、28s 总 deadline、剩余 ≥6s 和单次上限保护。不得增加第三次问询或独立 LLM judge；保留显式 off 作为回退。
- **首次答案的既有局限仍在。** 本次证明针对新增修复发布路径；不要将它宣传为所有首轮答案的核心可答性校验已完成。

### 6.3 硬中止

本设计后的默认开启实施最多进行 **3 轮 Sol 复审**（不把历史默认 off 批准算进本额度）。每轮记录 HEAD、规则版本、发现、修复及 default-on verdict。

任一轮发现不可答误发布、既有 P2 重新出现、预算/取消失守，均先阻止默认开启发布；在额度内修复后重新独立审阅。**第 3 轮仍无法取得明确的 default-on APPROVED，停止默认开启工作，保留/恢复已获批的默认 off 版本。** 若安全批准已获得但公开质量仍不达门槛，也不得宣称目标完成或继续放宽安全闸。

停止时给出公开证据：已获保护的负例、未解决的反例类别、eligible 覆盖、成对指标、延迟/预算代价，以及“继续提高召回需增加语义能力/扩大范围，还是保持安全拒答”的取舍。只报告公开合成反例和 aggregates，不引用盲测私有正文；不得用“以后再观察”把未获批方案悄悄改成默认 on。

## 7. 给 Luna 的实现交接

### 7.1 文件与函数

| 文件 | 实现要点 |
| --- | --- |
| `services/ai/src/knowflow_ai/repair_gate.py`（新增） | `parse_repair_target(question)`、完整事实解析、单来源 span 证明、上下文/冲突检查、`check_repair_candidate(...)`；纯函数返回结构/有限枚举，不做模型调用或日志文本输出。规则不能由 evidence 指令扩充。 |
| `services/ai/src/knowflow_ai/answering.py` | 改 `answer_repair_enabled()`；抽出明确 eligibility；修改 `_evaluate_generated()` 的策略 repairable 计算及 `_finalize_generation()` 的接受链；替换 `_has_question_content_overlap` 授权点。保留 `_response_from_generated()` 作为单次校验入口，避免把它变成隐式补问。 |
| 同上 `_repair_generation()`、`DeepSeekAdapter._payload()` / `generate_repair()` | 保持同批 evidence、最多一次、剩余时间减 1s、既有预算入口和资源关闭。提示补问仅给一条直接作答原文，失败则拒答；不改生成 JSON 协议，不让 LLM 输出授权 verdict。 |
| `services/ai/src/knowflow_ai/citation_verify.py` | 保留原 verifier、完整 claim/marker 绑定、长度上限及计数语义。若需给新 gate 提供 claim spans，抽取/复用现有拆分器并确保兼容；不降低 grounding 阈值，不全局改变首轮单 marker 行为。新 gate 须补上 repair 路径的严格逐字事实验证。 |
| `services/ai/src/knowflow_ai/streaming.py` | 保持 `answer_events` 统一 await `_finalize_generation()` 后才发 delta；不得另写较宽的流式接受分支。 |
| `services/ai/tests/test_repair_gate.py`（新增） | 全题解析、歧义/未知拒绝、实体精确匹配、带角色约束、值类型、完整句/否定/假设/冲突测试；覆盖正反边界，避免仅复刻实现常量。 |
| `services/ai/tests/test_answering.py` | 改默认 off 的开关/集成断言；固化第 5 节同步矩阵、首轮确已剪空、接受/拒绝和预算时间边界。既有成功用例须确认属于支持的直接作答形态，不能随意改题让断言变绿。 |
| `services/ai/tests/test_streaming.py` | 同样的发布矩阵与默认构造，断言无候选泄漏、sources、终态、取消与两次模型关闭。与同步使用共享公开 fixtures，减少两边测试漂移。 |
| `services/ai/tests/test_rag_collection.py`、`test_collection_run.py`、`test_real_evaluation_service.py` | 验证 diagnostics 新枚举、sidecar 隐私、预测行 schema 不变、guard 转发/旧 adapter 回落仍预约、生产 service 不强制覆盖开关。 |
| `evaluation/collector/guarded_adapters.py`、`results.py`、`collect.py`、`run.py` | 预算边界保持；若 diagnostics 的字段白名单/落盘逻辑需要调整，仅增加枚举 gate reason，绝不写入请求/答案/证据文本。 |

运行与改动匹配的聚焦测试及必要完整回归；本任务仅设计，不在此执行。不得为了验收默认 on 而删除 off 对照、历史负例或长度/取消回归。

### 7.2 开关真值表与文档

统一 `strip().lower()` 后：

| 输入 | 新行为 |
| --- | --- |
| 未设置、空串、纯空白 | on |
| `on/true/1/yes` | on |
| `off/false/0/no` | off |
| 其他未知字符串 | on，并记录无原始值的配置警告 `unrecognized_kept_enabled` |

即“默认 on，只有显式 off 别名关闭”；unknown 不充当隐式关闭。开关只允许进入安全闸，显式 on 也不能绕过任何条件。`.env.example` 设为 `KNOWFLOW_ANSWER_REPAIR=on`，注明 unset 同义、off 为回退、每题最多两次生成。

同步更新 `services/ai/.env.example`、`services/ai/docs/answer-streaming.md`、`docs/evaluation/windows-blind-eval-runbook.md` 和公开实现记录 `docs/evaluation/2026-11-05-under-citation-repair.md` 的当前策略说明，说明 eligible 范围、严格接受条件、预算和失败拒答。历史 Sol 审阅与 v4 报告保持原样；只追加版本化的后续状态，不改写历史默认 off 下的事实。发布说明必须写清尚未验证后续盲测提升。

**交付定义：** ready 表示安全设计边界、实现点和验收条件已足够明确，可交 Luna 实现并申请 default-on APPROVED；不表示实现已完成、Sol 已批准或 answerable 指标已达标。若封闭规则不足以达到指标，应按第 6 节报告取舍，不能用启发式兜底补齐。

## 8. 公开依据

- [Sol 初审](../reviews/2026-11-05-sol-under-citation-repair.md)：背景摘录 P1、长度/计数 P2。
- [Sol rereview](../reviews/2026-11-05-sol-under-citation-repair-rereview.md)：共享主体及背景仍漏过。
- [Sol rereview2](../reviews/2026-11-05-sol-under-citation-repair-rereview2.md)：年份+背景 7/12 overlap 反例。
- [Sol rereview3](../reviews/2026-11-05-sol-under-citation-repair-rereview3.md)：批准限默认 off；“有多高”在显式 on 下仍可漏过。
- [v4 公开聚合](../evaluation/2026-11-05-box-blind-20-v4.md)：默认 off 的 13/15 与 5/5，不提供本方案效果证据。
- [public seed-v2 报告](../evaluation/2026-11-04-rag-real-public-seed-v2.md)：允许的公开验证路径；历史满分不替代本轮成对验证。

SOL_DESIGN_DONE status=ready
