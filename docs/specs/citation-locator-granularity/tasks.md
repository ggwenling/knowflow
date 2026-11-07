# Tasks：引用定位粒度修复

依赖顺序执行；每步完成后跑对应测试。不提交 git、不重跑数据集、不改契约。

1. [x] AI 定位纯函数
   - 文件：`services/ai/src/knowflow_ai/citation_verify.py`
   - 新增 `claim_units(answer)`、`locate_claim_span(claim, text)`、`source_claim_spans(answer, text_by_source)`；复用 `_claim_groups`、`_protected_boundaries`、`_bigrams`、`_negation_conflict`、`_numeric_conflict`。
   - 验证：新增单元测试覆盖逐字命中、句级回退、无匹配返回 None。

2. [x] AI 构造细粒度 sources
   - 文件：`services/ai/src/knowflow_ai/answering.py` 的 `_evaluate_generated()`
   - `text_range` 且能定位时，locator 映射为文档绝对区间，quote 为对应片段；否则保留 Chunk locator 与完整 text_content。
   - 验证：`python -m pytest services/ai/tests/test_answering.py -q`。

3. [x] 补 Python 断言
   - 文件：`services/ai/tests/test_answering.py`
   - 断言区间严格小于 Chunk、且 `document_text[start:end]` 包含 claim 文本；补一个定位失败回退用例；调整既有 `quote == text_content` 断言。
   - 验证：同上。

4. [x] Java 接受并持久化细粒度 locator
   - 文件：`services/api/src/main/java/com/knowflow/api/answer/QuestionService.java`
   - `sameLocator` → `locatorWithinChunk`（pdf_page 同页；text_range 为 Chunk 子区间）；`prepareAnswer` 持久化/返回 `source.locator()`。
   - 验证：`mvn -q -f services/api/pom.xml -DskipTests compile` 后跑受影响测试。

5. [x] Java 测试
   - 文件：`services/api/src/test/java/com/knowflow/api/answer/QuestionServiceLocatorTest.java`
   - 窄区间通过、越界/单位不一致/页级形状不合法被拒绝。
   - 验证：`mvn -Dtest=QuestionServiceLocatorTest test`。

6. [x] 评测采集器兼容
   - 文件：`evaluation/collector/prediction.py`（及对应测试）
   - response source locator 改为“位于 trace locator 内”校验；pdf_page 仍要求同页。
   - 验证：采集器既有测试。

7. [x] 回归与报告
   - 跑 `contracts/` 校验、Python 受影响测试、Java 受影响测试。
   - 输出报告：根因层、改动文件、测试结果、评测口径影响；不提交 git。
