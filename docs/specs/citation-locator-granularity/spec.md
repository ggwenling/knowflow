# Spec：引用定位粒度修复（citation locator）

状态：已实现（2026-11-07），未提交 git，等待确认

## 1. 现象

`eval-out/seed-v2-dev-0.2.0/` 与 `eval-out/seed-v2-holdout-0.2.0/` 中所有引用定位区间均为 `[0, 文档长度)`。用户点开引用看到整篇文档，而不是支撑该 claim 的片段。

## 2. 根因（两层）

1. **AI 层（主因）**：`services/ai/src/knowflow_ai/answering.py` 的 `_evaluate_generated()` 构造 `sources` 时，直接把检索证据的 `locator`（Chunk 级）回填给引用，从未按 claim 计算片段起止。
   - 证据 locator 来自 `ReadOnlyRetriever.retrieve()`（`answering.py` 约 512-523 行），取自 `knowflow.chunks.source_start/source_end`。
   - `chunking.py` 的 `DEFAULT_MAX_CODEPOINTS=800`，而现有评测文档只有约 74-141 个码点，因此每篇文档只有一个 Chunk，Chunk locator 就是 `[0, 文档长度)`。这解释了“为什么全是整篇”，但 Chunk 级 locator 本身是检索的正常设计。
2. **Java 层（阻断细化）**：`services/api/src/main/java/com/knowflow/api/answer/QuestionService.java`
   - `prepareAnswer()` 用 `sameLocator(source.locator(), chunk.locator())` 要求 AI 返回的 locator 与 Chunk locator **完全相等**，否则 `AI_PROCESSING_FAILED`；即使 AI 算出更细区间也会被拒。
   - 持久化与返回使用 `chunk.locator()`（约 479 行），而不是 AI 给出的细粒度 locator。

## 3. 契约判定：无需改契约

`contracts/schemas/protocol.schema.json` 的 `Locator` 对 `text_range` 只约束 `start >= 0`、`end >= 1`、`unit = unicode_code_point`，未要求等于 Chunk 区间。因此**契约允许更细粒度，属于实现未做到**。本次冻结版本 `0.2.0` 不变。

## 4. 目标

- 引用 locator 指向支撑该 claim 的文档内具体片段（Unicode 码点 `[start,end)`）。
- 无法可靠定位时回退到 Chunk 区间（整篇只是兜底，不是默认）。
- 不改契约、不改评测打分口径、不重跑数据集、不提交 git。

## 5. 非目标

- 不改 Chunk 切分策略（`chunk_max_codepoints`、overlap）。
- 不改 PDF 的 `pdf_page` 定位（最小页级，保持等于 Chunk 页）。
- 不改检索排序、剪枝、拒答、repair 逻辑。
- 不改 `eval-out/` 历史产物。
- 不改 `contracts/` 任何文件。

## 6. 设计

### 6.1 AI 侧：claim → Chunk 内片段

新增纯函数（放在 `citation_verify.py`，复用现有分词/边界逻辑）：

- `claim_units(answer)`：返回 `[(claim_text, [source_id, ...]), ...]`，基于现有 `_claim_groups()`，只暴露稳定接口。
- `locate_claim_span(claim, text)`：
  1. 原文直接命中：`text.find(claim)`，命中即返回 `(index, index + len(claim))`。
  2. 否则按现有句界把 `text` 切成带偏移的单元，用现有 bigram 覆盖率（阈值 0.55）和否定/数字校验挑选最佳支撑单元，返回该单元 `(start, end)`。
  3. 都不满足返回 `None`。
- `source_claim_spans(answer, text_by_source)`：按 `source_id` 聚合其所有 claim 的片段，取 `min(start), max(end)`。

在 `answering._evaluate_generated()` 构造 `sources` 时：

- 对每个保留的 `source_id` 计算 Chunk 内片段；
- 若证据 locator 为 `text_range` 且片段存在：
  - `locator = {kind: text_range, start: 原start + 片段start, end: 原start + 片段end, unit: unicode_code_point}`
  - `quote = text_content[片段start:片段end]`
- 否则保持现状：`locator = 原 Chunk locator`，`quote = 完整 text_content`（兜底）。
- 同一 `source_id` 的多个 claim 片段合并为连续区间；任一条 claim 无法定位则对该 source 整体回退，避免误定位。

### 6.2 Java 侧：接受并持久化更细区间

`QuestionService.prepareAnswer()`：

- 将 `sameLocator` 改为 `locatorWithinChunk(actual, stored)`：
  - `pdf_page`：`kind/page` 与 Chunk 相同，`start/end/unit` 为 null（维持页级）。
  - `text_range`：`kind/unit` 相同、`page` 为 null、`stored.start <= actual.start < actual.end <= stored.end`。
  - 完全相等仍然通过（向后兼容）。
- 持久化与返回改用 `source.locator()`（经 `toPublicLocator`），不再强制 `chunk.locator()`。
- 现有 `quote` 校验（`chunk.text().contains(source.quote())`）不变，细粒度 quote 天然满足。
- 数据库约束 `question_sources_retention_shape_check` 已允许任意 `start >= 0`、`end > start`，无需迁移。

### 6.3 评测采集器兼容

`evaluation/collector/prediction.py` 目前要求 `source.locator == trace.locator`，细化后未来采集会误报 `SERVICE_SOURCE_TRACE_MISMATCH`。改为包含关系校验（`text_range` 子区间、`pdf_page` 同页），否则拒绝。仅改校验，不改 `retrieved_evidence` / `citations` 结构，不改打分口径。

## 7. 兼容性

- **契约**：不改；`Locator.text_range` 已覆盖。
- **已有数据**：历史 `question_sources` 里 Chunk 级 locator 仍合法，前端按 `[start,end)` 截取，照常显示。
- **前端**：`apps/web/src/components/source-viewer.tsx` 已用 `Array.from(text).slice(start, end)`，无需改动。
- **Java**：完全相等的旧行为仍被接受。
- **评测**：`eval-out/` 历史文件不重跑、不改写；未来采集只放宽 locator 校验，`citations[].evidence` 仍是检索证据 span（评测口径未变）。

## 8. 测试

Python（`services/ai/tests/test_answering.py`）：

1. 引用 locator 为严格子区间：断言 `start > chunk.start` 或 `end < chunk.end`，且 `document_text[start:end]` 包含该 claim 的文本。
2. 无法定位时回退：构造 claim 与证据无交集，断言 locator 等于 Chunk 区间。
3. 更新现有 `test_answer_service_returns_only_cited_scope_sources` 中对 `quote == text_content` 的断言为“quote 是支撑片段”。

Java（`services/api/src/test/.../DocumentApiIntegrationTest.java` 或最接近的现有测试）：

4. 窄于 Chunk 的 `text_range` 被接受并原样持久化/返回；越界区间（超出 Chunk）仍被拒绝。

采集器（`evaluation/` 现有测试）：

5. 子区间 locator 通过、越界 locator 仍报错。

回归：现有 Python / Java / 契约校验测试保持通过。

## 9. 评测口径影响

- 打分逻辑（recall@5、citation_accuracy 等）不变；不重跑数据集。
- `eval-out/` 中已有引用的 `[0, 文档长度)` 是 Chunk 级检索证据 span，本次不回填历史数据；修复只影响此后新生成的问答与 API 返回。

## 10. 改动文件

- `services/ai/src/knowflow_ai/citation_verify.py`（新增定位纯函数）
- `services/ai/src/knowflow_ai/answering.py`（构造 sources 时使用细粒度 locator/quote）
- `services/ai/tests/test_answering.py`（新增/调整测试）
- `services/api/src/main/java/com/knowflow/api/answer/QuestionService.java`（包含校验 + 持久化 AI locator）
- `services/api/src/test/java/com/knowflow/api/document/DocumentApiIntegrationTest.java` 或同层测试（若现有夹具可直接扩展）
- `evaluation/collector/prediction.py` 及其测试（兼容子区间）

## 11. 风险

- claim 为非逐字改写时，定位到“最佳支撑句”而非逐字区间；测试以逐字场景为准，非逐字仍能缩小范围。
- `quote` 从整 Chunk 变为片段，历史前端会同时展示 quote 与截取文本，二者一致。
