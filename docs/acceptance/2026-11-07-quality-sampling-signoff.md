# 质量抽审签收包（support / citation）

**范围**：`eval-out/seed-v2-dev-9907aca/` 与 `eval-out/seed-v2-holdout-9907aca/`
**新基线**：评测提交 `9907aca25968ed8ad3677c1119088cfbc8166293`；其后提交 `d2b3ff1` 为采集器 sidecar（记录 API source locators），不改变本次两卷产物的 `code_sha`。
**性质**：agent 预审的抽样复核，供真人快速审阅并签收；**不是全量重审**，不替代逐题人工审核。
**依据文件**：两卷目录下的 `predictions.json`、`review.json`、`metrics.json`、`run-metadata.json`、`predictions.diagnostics.json`、`citation-locators.json`。
**生成日期**：2026-11-07

---

## 1. 一页汇总

### 1.1 两卷整体指标

| 指标 | development | holdout |
|---|---|---|
| 题数 | 40 | 20 |
| 执行错误 | 0 | 0 |
| 质量门 `quality_gate.status` | passed | passed |
| `recall_at_5` | 1.0（37/37 gold span） | 1.0（25/25 gold span） |
| `mrr_at_10` | 0.9785（n=31） | 1.0（n=19） |
| `answerable_answer_rate` | 1.0（31/31） | **0.9474（18/19）** |
| `answerable_false_refusal_rate` | 0.0 | **0.0526（1/19）** |
| `unanswerable_refusal_rate` | 1.0（9/9） | 1.0（1/1） |
| `answered_count` | 31 | 18 |
| `human_supported_answer_rate` | 1.0（31/31） | 1.0（18/18） |
| `citation_accuracy` | 1.0（47/47） | 1.0（28/28） |
| `human_support_review_coverage` | 1.0（31/31 answered） | 1.0（18/18 answered） |
| `citation_review_coverage` | 1.0（47/47） | 1.0（28/28） |
| 延迟 p50 / p95 | 1688 / 2062 ms | 1672 / 2282 ms |
| 评测绑定 `code_sha` | `9907aca…` | `9907aca…` |

> **`mrr_at_10` 分母口径**：已修正为 `answerable && gold`。本轮不存在“answerable 但无 gold”的题（该类计数为 0），因此历史数值不变：development 0.9785、holdout 1.0；`mrr_at_10_question_count` 分别为 31 / 19。
>
> **holdout 的 0.9474 来自 `candidate-40` 的 1 次误拒**（answerable 题被 refused）；门禁阈值 0.90 仍通过，但这是本轮唯一的人工决策点，详见 H3。

### 1.2 引用定位审计（本轮新增）

| 项目 | development | holdout |
|---|---|---|
| `citation-locators.json` 记录数 | 33 | 21 |
| `span_len == quote_len` | 33/33 | 21/21 |
| 其中 quote 为整篇短文档（`[0,len)`） | 1 | 5 |
| 其余为子区间（句级/跨句） | 32 | 16 |
| 是否参与打分 | 否（`purpose` 明确为 audit attachment，not consumed by scoring） | 否 |
| 对 `metrics.json` 数值影响 | 无 | 无 |

- `citation-locators.json` 的 `source` 为 `knowflow.question_sources JOIN knowflow.questions`，是采集后从持久化表导出的审计附件，独立于 `predictions.json`。
- `review.json` 的 `evidence.start/end` 仍记录整篇来源区间；**本轮新增的真实定位在 `citation-locators.json`**，两者按 `source_id` 对齐。
- 上一版“区间全是整篇 `[0,len)`”的疑点已消除：dev 仅剩 1 条、holdout 仅剩 5 条整篇记录，且这些记录的 quote 本身就是整篇短文档，不是统一整篇定位。

### 1.3 审阅覆盖与真实审阅者

| 分卷 | 题数 | answered | refused | answered 有 agent 审阅 | refused 有逐题审阅 | 引用总数 | 引用有 agent 判定 |
|---|---|---|---|---|---|---|---|
| development | 40 | 31 | 9 | 31 | 0 | 47 | 47 |
| holdout | 20 | 18 | 2 | 18 | 0 | 28 | 28 |
| 合计 | 60 | 49 | 11 | 49 | 0 | 75 | 75 |

真实审阅者标识：

- development：`agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`（31 条 answered）；9 条 refused 的 `reviewed_by=null`。
- holdout：`agent:trae-konwflow-seedv2-holdout-9907aca-review-20261107T111000Z`（18 条 answered）；2 条 refused 的 `reviewed_by=null`。
- 真人审阅者：**0 条**；support 与 citation 的 100% 均为 agent 判定。

### 1.4 本次抽样覆盖

- 抽样 10 题（development 5 + holdout 5），占 60 题的 **16.7%**。
- 覆盖 13 条 citation 标记、10 条唯一 locator 记录；总引用 75 条、总 locator 记录 54 条。
- 覆盖类型：可答题（factual / rewrite / chinese_keyword）、不可答题（no_answer）、多证据题（multi_evidence）、跨文档题、以及 `candidate-40` 复合双问误拒。

| 编号 | 分卷 | 题号 | 类别 | 覆盖点 | outcome |
|---|---|---|---|---|---|
| D1 | development | candidate-01 | factual | 可答、句级单引用 | answered |
| D2 | development | candidate-16 | rewrite | 可答、改述问法 | answered |
| D3 | development | candidate-31 | multi_evidence | 多证据、跨 2 个文档、引用修复 | answered |
| D4 | development | candidate-38 | multi_evidence | 多证据题中的单文档收敛 | answered |
| D5 | development | candidate-52 | no_answer | 不可答 | refused |
| H1 | holdout | candidate-04 | factual | 可答、句级单引用 | answered |
| H2 | holdout | candidate-34 | multi_evidence | 多证据、跨 2 个文档 | answered |
| H3 | holdout | candidate-40 | multi_evidence | 复合双问、answerable 误拒 | refused |
| H4 | holdout | candidate-49 | chinese_keyword | 可答、草案与 ADR 区分 | answered |
| H5 | holdout | candidate-56 | no_answer | 不可答 | refused |

### 1.5 当前签字缺口

1. **真人签字缺失**：49 条 answered 的支持度判定、75 条引用判定全部由 agent 完成，`reviewed_by` 无真人。
2. **不可答题与误拒题未审**：11 条 refused（development 9 + holdout 2）在 `review.json` 中 `support_judgement=not_applicable`、`reviewed_by=null`。其中 `candidate-40` 是 answerable 误拒、`candidate-56` 是 no_answer 正确拒答，性质不同，需人工分别确认。
3. **抽样不等于全量**：本包只覆盖 10/60 题、13/75 条 citation、10/54 条 locator；其余 50 题、62 条 citation、44 条 locator 仍只有 agent 判定。
4. **agent 理由未落盘**：`review.json` 只保存判定码（`supported` / `not_applicable`），没有自然语言理由字段；本包中的“复核说明”是依据原文与 `predictions.diagnostics` 的转述，不是 agent 原始理由。
5. **`candidate-40` 误拒仍在**：holdout `answerable_answer_rate=0.9474`，虽过 0.90 门禁，但属于可答题被拒；需要负责人决定接受或要求再修。
6. **sidecar 未参与打分**：句级定位只在 `citation-locators.json`，`metrics.json` 不消费该附件；需要确认验收流程是否正式接收该审计证据。
7. **作废批次未纳入本包**：`seed-v2-dev-42d3b3d` / `seed-v2-holdout-42d3b3d` 为 provider 故障窗口的作废批次（`complete=false`；dev 13 题、holdout 20 题 `COLLECTION_INCOMPLETE`；无 `metrics.json`），本包不使用其结论。

---

## 2. development 抽样（5 题）

> 每条引用同时列出两个区间：`locator` 为 `citation-locators.json` 的真实定位；`review evidence` 为 `review.json` 的整篇来源区间。`locator` 单位为 `unicode_code_point`，左闭右开 `[start,end)`。

### D1. candidate-01｜factual｜可答

**问题原文**：创建索引任务请求需要提供哪些必填字段？

**模型答案**：

> 创建索引任务使用 POST /v1/index-jobs，必填字段为 documentId（UUID）和 profileId（字符串）[78005d14-484d-3212-afe8-2a0943745d58]。

**引用与原文**

- `cite-0` · 文档 `api` · locator `[73,111)` · review evidence `[0,141)` · source_id `78005d14-484d-3212-afe8-2a0943745d58` · 判定 `supported`

  > 定位原文：`必填字段为 documentId（UUID）和 profileId（字符串）`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `review.json` 未保存自然语言理由；`predictions.diagnostics` 为 `decision=answered, reason=grounded, claims=1, kept=1, dropped=0, repaired=0, repair_attempt=0`。
- 复核说明：答案中的 `POST /v1/index-jobs`、`documentId`、`profileId` 与原文逐项对应；`locator` 精确落在“必填字段”这一句。

**人需要确认的点**：确认“必填字段只有这两个”这一结论是否由原文充分支持（原文只列这两个字段，未显式写“仅”）。

---

### D2. candidate-16｜rewrite｜可答

**问题原文**：索引任务请求必须提供哪两个字段及其类型？

**模型答案**：

> 必填字段为 documentId（UUID）和 profileId（字符串）[782241ec-ba1b-3ef7-88fa-eb9501bab5b0]。

**引用与原文**

- `cite-0` · 文档 `api` · locator `[73,111)` · review evidence `[0,141)` · source_id `782241ec-ba1b-3ef7-88fa-eb9501bab5b0` · 判定 `supported`

  > 定位原文：`必填字段为 documentId（UUID）和 profileId（字符串）`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=1, kept=1, dropped=0, repair_attempt=0`。
- 复核说明：改述问法没有改变事实，答案与原文“documentId（UUID）和 profileId（字符串）”一致；locator 与 D1 相同。

**人需要确认的点**：确认改述题允许直接复用同一句原文，不要求额外解释。

---

### D3. candidate-31｜multi_evidence｜可答

**问题原文**：任务超时时会返回什么错误？此时 Python 能否自行发布索引？

**模型答案**：

> 超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT [5f83fcdb-91e1-35ea-a527-7be07449031c]。 取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引 [5f83fcdb-91e1-35ea-a527-7be07449031c]。 只有 Java 服务可以发布活动索引版本[a808f329-7076-3913-a4ff-c7ac5c95ef4c]； Python 只提交候选结果 [a808f329-7076-3913-a4ff-c7ac5c95ef4c]。

**引用与原文**

- `cite-0`、`cite-1` · 文档 `timeout` · locator `[47,116)` · review evidence `[0,118)` · source_id `5f83fcdb-91e1-35ea-a527-7be07449031c` · 判定 `supported`

  > 定位原文：`超时对外返回 HTTP 504，错误码 PROCESSING_TIMEOUT。`（换行）`取消只释放计算资源，不能恢复已删除文档，也不能自行发布索引`

- `cite-2`、`cite-3` · 文档 `publish` · locator `[19,54)` · review evidence `[0,114)` · source_id `a808f329-7076-3913-a4ff-c7ac5c95ef4c` · 判定 `supported`

  > 定位原文：`只有 Java 服务可以发布活动索引版本；Python 只提交候选结果`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=4, kept=4, uncited_claims=1, repaired_claims=1, repair_attempt=0`。
- 复核说明：两个子问题分别由 `timeout` 与 `publish` 两篇文档支撑；locator 分别定位到两句；诊断显示有 1 条 claim 在生成后被补上引用（`repaired_claims=1`），但没有发起额外模型重试（`repair_attempt=0`）。

**人需要确认的点**：确认 4 个 citation 标记复用 2 个 locator（同一句被两条 claim 引用）是否可接受，以及自动补引用是否算完成闭环。

---

### D4. candidate-38｜multi_evidence｜可答

**问题原文**：扫描 PDF 需要什么额外能力？演示有提供它吗？

**模型答案**：

> 扫描 PDF 需要 OCR，本演示版本未实现 OCR。[de0a33d9-9bc3-30b6-b4ae-8792141ddccb]

**引用与原文**

- `cite-0` · 文档 `files` · locator `[91,117)` · review evidence `[0,119)` · source_id `de0a33d9-9bc3-30b6-b4ae-8792141ddccb` · 判定 `supported`

  > 定位原文：`扫描 PDF 需要 OCR，本演示版本未实现 OCR`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-dev-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=1, kept=1, dropped=0, repair_attempt=0`。
- 复核说明：答案两个分句都与定位句直接对应，属于单文档收敛，不需要第二篇文档。

**人需要确认的点**：确认“多证据题”允许收敛到单一文档作答，只要两个分句都有直接原文支撑。

---

### D5. candidate-52｜no_answer｜不可答

**问题原文**：Embedding 供应商每千 token 的正式报价是多少？

**模型答案**：

> 没有足够的资料证据回答这个问题。

**引用与原文**

- 无引用；`review.json` 的 `citations` 为空，`citation-locators.json` 也没有该题记录。

**agent 判定与理由**

- 原记录：`support_judgement=not_applicable`；`reviewed_by=null`；`reviewed_at=null`。本题**没有被 agent 逐题审阅**。
- `predictions.diagnostics`：`decision=refused, reason=model_declined, repair_gate_reason=unsupported_question, repair_attempt=0`。
- 复核说明：答案仅为统一拒答句；现有产物中没有可供人工核对的支持/反对证据片段。

**人需要确认的点**：确认该题在语料中确实没有正式报价，拒答是正确行为，而不是检索遗漏。

---

## 3. holdout 抽样（5 题）

### H1. candidate-04｜factual｜可答

**问题原文**：chunkSize 的默认值和允许范围分别是多少？

**模型答案**：

> chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数。[80c86109-9f37-3f2d-a903-a4b1129435eb]

**引用与原文**

- `cite-0` · 文档 `chunk` · locator `[27,71)` · review evidence `[0,114)` · source_id `80c86109-9f37-3f2d-a903-a4b1129435eb` · 判定 `supported`

  > 定位原文：`chunkSize 默认 360 个 Unicode 码点，允许 180–720 的整数`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-holdout-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=1, kept=1, dropped=0, repair_attempt=0`。
- 复核说明：默认值、范围、单位均与定位句一致。

**人需要确认的点**：确认“180–720 的整数”是闭区间，答案没有改变原文的边界含义。

---

### H2. candidate-34｜multi_evidence｜可答（跨文档）

**问题原文**：演示支持哪些文件？上传文本与发送给 LLM 的检索片段有何关系？

**模型答案**：

> 支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF[fe0d1dbd-1d6e-31d0-b008-f6cb14e77bb8]。 Embedding 请求发送获准的文档分段文本[8f29a838-4365-3564-a93e-0aaecdc25c18]； LLM 请求发送当前问题和检索到的获准片段[8f29a838-4365-3564-a93e-0aaecdc25c18]。

**引用与原文**

- `cite-0` · 文档 `files` · locator `[19,53)` · review evidence `[0,119)` · source_id `fe0d1dbd-1d6e-31d0-b008-f6cb14e77bb8` · 判定 `supported`

  > 定位原文：`支持 UTF-8 TXT、Markdown 和含可提取文字的 PDF`

- `cite-1`、`cite-2` · 文档 `outbound` · locator `[19,65)` · review evidence `[0,131)` · source_id `8f29a838-4365-3564-a93e-0aaecdc25c18` · 判定 `supported`

  > 定位原文：`Embedding 请求发送获准的文档分段文本。`（换行）`LLM 请求发送当前问题和检索到的获准片段`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-holdout-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=3, kept=3, uncited_claims=0, repaired_claims=0, dropped=0, repair_attempt=0`。
- 复核说明：两个子问题分别落在 `files` 与 `outbound`；`outbound` 的 locator 同时覆盖 Embedding 与 LLM 两句；本轮答案已去掉上一版“上传文本经获准分段文本”的改写，直接使用原文表述。

**人需要确认的点**：确认 3 条 citation 复用 2 个 locator（`outbound` 两条 claim 共用一段）是否可接受。

---

### H3. candidate-40｜multi_evidence｜复合双问（answerable 误拒）

**问题原文**：失败重试上限是什么？任务超时是否会改变已删除文档状态？

**模型答案**：

> 没有足够的资料证据回答这个问题。

**引用与原文**

- 无引用。检索结果包含 `timeout` 文档（source_id `d09b4166-dcc3-3bd6-9ee5-9151d8b9ec3b`，review evidence `[0,118)`），但模型未生成任何 citation。

**agent 判定与理由**

- 原记录：`support_judgement=not_applicable`；`reviewed_by=null`；`reviewed_at=null`。本题**没有被 agent 逐题审阅**。
- `predictions.diagnostics`：`decision=refused, reason=model_declined, repairable=true, repair_gate_reason=no_verbatim_fact, repair_attempt=1, repair_outcome=failed_unrelated, claims=0`。
- 复核说明：
  - **检索命中**：`timeout` 文档已在检索结果中，全卷 `recall_at_5=1.0`（25/25 gold span）。
  - **首轮拒答**：模型首轮返回 `model_declined`。
  - **repair 已触发**：`repairable=true`、`repair_attempt=1`，复合题 repair 没有停在闸门外。
  - **repair 失败原因**：repair 产出的答案不是逐字事实，被 `no_verbatim_fact` 拒绝，`repair_outcome=failed_unrelated`。
  - **结论**：这是生成与判定问题，不是检索问题。

**人需要确认的点**：确认是否接受 holdout 的 1 次 answerable 误拒（`answerable_answer_rate=0.9474`），或要求针对 `no_verbatim_fact` 的 repair 判定继续修复；确认复合双问的“逐字事实”要求是否过严。

---

### H4. candidate-49｜chinese_keyword｜可答

**问题原文**：未批准的 retry draft 能否代表当前生效配置？

**模型答案**：

> 未批准的 retry draft 不能代表当前生效配置：重试草案 v1.2 的状态为草案，未批准，不生效 [d8cb0816-68e0-3a40-87ee-49bc754f3f28]； 已批准的 ADR-017 替代重试草案 v1.2 的重试等待参数 [9b515c17-5cb1-3731-bc75-47a955567f61]。

**引用与原文**

- `cite-0` · 文档 `draft` · locator `[0,74)` · review evidence `[0,74)` · source_id `d8cb0816-68e0-3a40-87ee-49bc754f3f28` · 判定 `supported`

  > 定位原文：`# 合成项目「青竹」重试草案 v1.2`（换行）`状态：草案，未批准，不生效。`（换行）`编辑日期：2026-09-20。`（换行）`提议默认等待 20 秒，上限 60 秒。`

- `cite-1` · 文档 `adr` · locator `[0,94)` · review evidence `[0,94)` · source_id `9b515c17-5cb1-3731-bc75-47a955567f61` · 判定 `supported`

  > 定位原文：`# 合成项目「青竹」ADR-017`（换行）`状态：已批准；2026-10-01 生效。`（换行）`本 ADR 替代重试草案 v1.2 的重试等待参数。`（换行）`当前客户端重试等待默认 10 秒，上限 30 秒。`

**agent 判定与理由**

- 原记录：`support_judgement=supported`；`reviewed_by=agent:trae-konwflow-seedv2-holdout-9907aca-review-20261107T111000Z`；`reviewed_at=2026-11-07T11:10:00Z`。
- `predictions.diagnostics`：`decision=answered, reason=grounded, claims=2, kept=2, uncited_claims=0, dropped=0, repair_attempt=0`。
- 复核说明：草案“不生效”与 ADR-017“替代其重试等待参数”分别由两篇文档支撑；两条 locator 都是 `[0,len)`，因为这两篇短文档的 quote 本身就是整篇。

**人需要确认的点**：确认当 quote 为整篇短文档时，`[0,len)` 的 locator 仍算合格；这是 holdout 5 条整篇记录中的 2 条。

---

### H5. candidate-56｜no_answer｜不可答

**问题原文**：真实问答服务承诺的 p95 延迟是多少？

**模型答案**：

> 没有足够的资料证据回答这个问题。

**引用与原文**

- 无引用；`review.json` 的 `citations` 为空，`citation-locators.json` 也没有该题记录。

**agent 判定与理由**

- 原记录：`support_judgement=not_applicable`；`reviewed_by=null`；`reviewed_at=null`。本题**没有被 agent 逐题审阅**。
- `predictions.diagnostics`：`decision=refused, reason=model_declined, repair_gate_reason=unsupported_question, repair_attempt=0`。
- 复核说明：答案仅为统一拒答句；现有产物中没有可供人工核对的证据片段。

**人需要确认的点**：确认语料中确实不存在“真实服务承诺 p95”这一事实，拒答正确。

---

## 4. 抽样复核结论（供签收参考）

- 7 道 answered 抽样题的 agent 判定均为 `supported`；2 道 refused 抽样题未被 agent 审阅，只有系统拒答诊断。
- 抽样未发现答案与定位原文直接冲突的表述；句级 locator 与 quote 长度逐条一致。
- 本轮唯一实质性质量缺口是 **`candidate-40` answerable 误拒**：检索命中、repair 已触发，但被 `no_verbatim_fact` 拒绝；归因是生成/判定，不是检索。
- 本包不能证明其余 50 题、62 条 citation、44 条 locator 同样正确；不能替代全量人工审阅。

---

## 5. 签字栏

> 签字含义：签字人已阅读本包 10 题抽样，并对第 1.5 节列出的缺口知情；签字不等于对 60 题全量审阅负责。

| 字段 | 填写 |
|---|---|
| 审阅人（姓名 / 工号） | |
| 审阅日期 | |
| 复核范围确认 | □ 已阅读 development 5 题 + holdout 5 题（共 10 题 / 13 条 citation / 10 条 locator） |
| 结论 | □ 同意签收（抽样未见阻断问题）　□ 有条件同意（见异议）　□ 不同意 |
| 对 `candidate-40` 误拒 | □ 接受（0.9474 过门禁）　□ 不接受，需继续修复再签 |
| 对整篇短文档 locator | □ 接受 `[0,len)` 作为该条证据的自然边界　□ 不接受，需再细化 |
| 对 sidecar 审计证据 | □ 接受 `citation-locators.json` 作为验收附件　□ 需纳入正式打分链路后再签 |
| 对 refused 未逐题审阅 | □ 接受　□ 需补人工确认 development 9 题 + holdout 2 题 |
| 异议 / 备注 | |
| 签字 | |

---

## 6. 证据路径

| 内容 | 路径 |
|---|---|
| development 预测 | `eval-out/seed-v2-dev-9907aca/predictions.json` |
| development 审阅 | `eval-out/seed-v2-dev-9907aca/review.json` |
| development 指标 | `eval-out/seed-v2-dev-9907aca/metrics.json` |
| development 运行元数据 | `eval-out/seed-v2-dev-9907aca/run-metadata.json` |
| development 定位审计 | `eval-out/seed-v2-dev-9907aca/citation-locators.json` |
| holdout 预测 | `eval-out/seed-v2-holdout-9907aca/predictions.json` |
| holdout 审阅 | `eval-out/seed-v2-holdout-9907aca/review.json` |
| holdout 指标 | `eval-out/seed-v2-holdout-9907aca/metrics.json` |
| holdout 运行元数据 | `eval-out/seed-v2-holdout-9907aca/run-metadata.json` |
| holdout 定位审计 | `eval-out/seed-v2-holdout-9907aca/citation-locators.json` |
| 诊断（引用修复/拒答原因） | 两卷同名 `predictions.diagnostics.json` |
| 作废批次（不使用） | `eval-out/seed-v2-dev-42d3b3d/`、`eval-out/seed-v2-holdout-42d3b3d/` |

> 本文件只做记录，不修改代码、不修改评测产物。
