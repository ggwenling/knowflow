# seed-v3-hard 首次拒答诊断（公开集，2026-11-05）

结论：**本硬集未复现盲测 false_refusal**。30 道 answerable 题全部为 `answered`，10 道 unanswerable 题全部为 `refused`；没有可答误拒，也没有不可答误答。建议 **不改代码，直接进入盲测 v6**，把 v6 作为独立验证；本结果不足以证明盲测问题已修复。公开集后续应加难，但当前没有首次误拒样本支持先改 prompt、context assembly、verifier 或 repair 门禁。

## 范围与复核方法

本次诊断只使用以下输入：

- `/workspace/knowflow-runtime/reports/seed-v3-hard/seed-v3-hard-development.predictions.json`
- `/workspace/knowflow-runtime/reports/seed-v3-hard/seed-v3-hard-development.predictions.diagnostics.json`
- `/workspace/knowflow-runtime/reports/seed-v3-hard/seed-v3-hard-holdout.predictions.json`
- `/workspace/knowflow-runtime/reports/seed-v3-hard/seed-v3-hard-holdout.predictions.diagnostics.json`
- `/workspace/knowflow/evaluation/data/seed-v3-hard/questions.json` 的 `id / split / category / answerable / question`。

未查看题目的 `reference_answer / evidence / annotation` 等内容，未读取公开集原始 documents、应用代码、prompt、服务日志、review、formal-score 或账本，未读取 private-blind。未启动服务、重跑模型或修改代码；唯一产物为本报告。背景中的盲测表现及 support/citation 分数来自任务说明，本次未独立重算。

按题目 ID 连接 predictions 与 diagnostics，校验 split 覆盖、重复/缺失 ID，以及 prediction outcome、diagnostic outcome、citation decision 一致性。development 32 题、holdout 8 题均完整且唯一，没有跨 split 混入，没有 `error_code` 非空记录。

两个 split 的 run 元数据完全一致：

- `code_sha`: `63dc144e0bc3b6c4c68323d630440a0d15aa02b5`
- `model`: `deepseek-flash+BAAI/bge-m3`（按产物记录；任务中的 grok HEAD 不应解读为模型名）
- `config_sha256`: `7e97d46b338042fdbb03b5570d5132350ab4864b64e5825404c85afe3176c220`
- `prompt_sha256`: `f670f2fa0d12cf9178162b4071435b009efa5825f6c321e4d09b406467363218`

四份产物记录的 dataset ID 均为 `qingzhu-seed-v3-hard`，dataset hash 均为 `84d22ce04d3b28ae9b09cd152a76269eb5a4af872f0487212f2b71f8f20c1e86`。这里只核对产物之间的标识一致性，未据此声称验证了执行环境或最终 prompt 内容。

## 结果：没有目标错误

| split | answerable→answered | answerable→refused | unanswerable→refused | unanswerable→answered |
| --- | ---: | ---: | ---: | ---: |
| development | 24/24 | 0 | 8/8 | 0 |
| holdout | 6/6 | 0 | 2/2 | 0 |
| 合计 | 30/30 | 0 | 10/10 | 0 |

全部拒答题为 `hard-31` 至 `hard-40`，均标注为 unanswerable。其中 holdout 为 `hard-33 / hard-37`，其余 8 题为 development。最终答复均为“没有足够的资料证据回答这个问题。”，没有给出价格、租约时长、向量维度、OCR 引擎、PDF 页数、jobId 格式、隔离级别、owner 算法或并发数等猜测。

diagnostics 分为两组：

| 数量 | decision / reason | repair_gate_reason | repair_attempt / repair_outcome |
| ---: | --- | --- | --- |
| 30 | answered / grounded | not_checked | 0 / not_attempted |
| 10 | refused / model_declined | ineligible_reason | 0 / not_attempted |

因此没有“先误拒、再由补问救回”造成的表面满分。严格说，产物没有提供原始首次生成全文；这里能确认的是最终结果无误拒，且全部记录均未尝试该 repair。`model_declined` 是日志记录的拒答原因，不能进一步还原模型内部判断。

`ineligible_reason` 在本集只落在正确拒答上。它说明这类拒答未进入 repair，不能据此认定门禁有错，也不能证明它在遇到可答首次拒答时具备恢复能力。本集没有检验到后者。

## 为什么“硬集”仍未复现

### 1. 检索覆盖几乎消除了找证据的压力：最强的直接证据

40/40 题的 `retrieved_evidence` 都有 10 条；忽略顺序和每题 source ID 后，`document_id / content_version_id / start / end / text_sha256` 集合完全相同。全部题都拿到了以下十份相同版本的证据记录：

`access, adr, api, chunk, draft, files, locator, outbound, publish, timeout`。

每条范围均从 0 开始，结束位置为 74–141，十条 `end-start` 合计为 1151（按记录坐标计算）。例如 `hard-01` 同时检索到 `adr / draft / timeout`，`hard-03` 同时检索到 `api / chunk`，`hard-07` 同时检索到 `access / timeout`。排序变化没有导致某份证据从结果中消失。

这支持“本次检索覆盖过于充分，缺少漏召回、关键跳落在截断之外等压力”的解释。它不证明检索器在更大、更嘈杂语料上也很强；也不证明这里存在专门兜底或答案泄漏。未读取最终 context payload，不能确认这十条是否全部按相同形式送入模型，或排除 assembly 层面的其他差异。

### 2. 多数难度来自问法变化，答案仍容易局部抽取或并列拼接

| category | development | holdout | 可观察的题型特点 |
| --- | ---: | ---: | --- |
| multi_hop | 7 | 1 | 常为两个明确事实并列，或显式版本替代关系 |
| paraphrase | 7 | 1 | 改写“分段、重叠、地址、超时、发布、重试”等稳定概念 |
| numeric_date | 4 | 2 | 日期、整数范围、期限及短字符串码点区间 |
| partial_evidence | 3 | 1 | 包含明确边界、禁止编造及“材料是否提供”类问题 |
| background_phrased | 3 | 1 | 保留草案、数据库事务、Markdown、LLM 等识别线索 |
| unanswerable_background | 7 | 2 | 缺少具体参数或实现细节 |
| unanswerable_other | 1 | 0 | 索引任务并发上限 |

从题面与最终答复可见，`hard-03` 是必填字段加单批上限，`hard-05` 是两种状态码；这类 multi_hop 在两份短证据都在场时，主要考验事实拼接。`hard-17 / hard-18 / hard-19` 直接询问文档日期；`hard-09 / hard-10 / hard-20 / hard-21` 询问默认值或范围。不能把这些类别名直接等同于长链推理、弱相关证据识别或复杂数值推导。

`hard-25` 问的是“说明里有没有价格和训练政策”，回答“本材料不提供”即可正确作答；它与 `hard-31` 要求实际计费单价形成清楚的边界，但没有充分施压于“部分事实已知、其余未知时仍应完成可答部分”的情形。`hard-23 / hard-26` 也更像对明确边界规则的问答。

这些观察支持“问法加难了，证据识别及答案构造仍偏直接”的判断。由于未读原始 documents，不能量化题面与原文的词汇重合率。

### 3. 公开 holdout 与 development 仍有明显主题重合

例如 `hard-12`（holdout，扫描件 OCR）与 `hard-06`（development，扫描 PDF 与 embedding）共享关键前提；`hard-19`（holdout，草案状态）与 `hard-01 / hard-27`（development，现行重试参数）共享草案主题；`hard-22`（holdout，码点）与 `hard-04 / hard-23`（development，码点计数/偏移）共享概念。

这不是泄漏指控，也没有证据表明模型在 split 之间保留了状态。它只说明 8 题 holdout 的主题覆盖与 development 接近，不足以单独代表跨语料、跨任务的泛化。

### 4. 与盲测的分布差只能提出假设，不能在本次访问范围内证实

任务说明中的 v2–v5 仍有大量首次误拒，而本集在上述短证据、全覆盖检索条件下没有误拒，提示两者可能在证据密度、干扰内容、跨片段推断、隐含前提或可答边界上不同。也可能存在运行配置差异，但本次没有盲测产物可作同配置对照。

因此可以说“本集没有覆盖触发旧问题的条件”，不能说已经定位了盲测根因，也不能把本次成功归因于某项代码修复。

## 额外发现：answered 不保证完整作答

`hard-01` 的题目要求“现在线上客户端实际采用哪一组数值”。最终答复只保留“草案默认 20 秒、上限 60 秒”和“草案未批准、不生效”，没有给出现行默认值和上限。相同主题的 `hard-27` 最终答复则明确写出当前默认 10 秒、上限 30 秒；两题检索元数据均包含相同版本的 `adr / draft / timeout`。

`hard-01` 同时记录 `claims=3 / kept_claims=2 / dropped_claims=1 / pruned_markers=2`，最终仍为 `answered / grounded`。这与“某条声明被过滤后，剩余内容有依据但未覆盖核心问题”的现象一致。由于缺少过滤前全文与逐声明判定，不能确认被丢弃的就是现行数值，也不能判定是生成遗漏、引用绑定问题还是 verifier 误删。粗粒度的检索缺失不是首要解释；最终 assembly 是否完整仍不可见。

这是**完整性缺口，不是本次目标中的 false_refusal，也不是 unanswerable 误答**。不能据 `answered` 或 support 高分声称 30/30 都完整答对；support 只约束保留下来的陈述有无依据，无法自动覆盖“题目要求的关键事实是否还在”。此处无需改动既有 outcome 计数，但应在后续评审中单列问题要求覆盖率。

另一条有丢弃的题目是 `hard-25`（2 条保留 1 条），最终仍明确表达材料不提供所问事实，题意没有出现同等明显的缺口。`hard-02 / hard-15 / hard-28 / hard-22` 各有 `repaired_claims=1`，但全部 `repair_attempt=0 / repair_outcome=not_attempted`；不要把这一计数当作额外模型补问或 v5 拒答 repair 的成功案例。

## 决策与下一步

推荐 `proceed_v6`：按本次公开集的 outcome 点估计，development 与 holdout 都满足 answerable ≥0.93、unanswerable refusal ≥0.95。没有发现需要在 v6 前修复的可答误拒或危险不可答误答；先扩大 `model_declined` 的 repair 资格或放松 verifier，缺少本集上的定向收益证据，还可能改变当前正确拒答行为。`hard-01` 应保留为完整性复核线索，尚不足以从这些产物确定具体代码修法。

“满足门槛”只适用于本次样本结果。即使暂按独立同分布二项样本计算，合计 30/30 与 10/10 成功率的单侧 95% 精确下界分别约为 0.905 和 0.741，均不能从统计上保证目标阈值；题目间主题重合还会削弱这种理想化推断。8 题 holdout 尤其不能替代盲测验证。

建议保留本次 code/config/prompt 快照进入 v6，以便判断旧问题是否还存在；本任务仅给出建议，未执行盲测。若 v6 再出现首次误拒，应按“检索是否有足够证据 → 最终 context 是否带入 → 首次生成是否拒答 → verifier 是否删空 → repair 为何不合格”的顺序核对，而不是仅凭 `ineligible_reason` 选定根因。

公开集加难可作为后续独立工作，不作为此次进 v6 的前置阻塞，也不从 private-blind 抽题：

1. 扩大原创语料及近似干扰材料，使关键证据不再每题全数返回；仍保留可独立核验的可答依据，区分检索失败与有证据仍拒答。
2. 增加需组合多个独立片段才能得到的结论、证据分散的版本优先级、指代改写、日期/数值推导；避免仅把两个可抽取字段并列称为多跳。
3. 增加“已知事实可答、未知细节需保留”的混合题及相邻不可答对照；评审最终答复是否覆盖核心要求，防止删句后仅剩背景也获得 answered 满分。
4. 用新主题和独立事实族组织公开 holdout，明确其分布边界；拒答仍保留为允许结果，不能为了提高 answerable rate 强迫所有题作答。

SOL_DIAG_DONE reproduce=no recommend=proceed_v6
