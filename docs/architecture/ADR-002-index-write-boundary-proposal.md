# ADR-002：Java 受控批量索引写入网关

- 状态：`ACCEPTED_FOR_DEVELOPMENT / Q_REVIEW_PENDING`。实现按此候选设计推进；未通过 Q 复核前不表示跨服务生产协议已冻结。
- 对应：KF2-011、KF2-018、JP2-A02/A05/A07/A08。
- 作者：Codex-A；日期：2026-10-30（Asia/Hong_Kong）。
- 契约输入：`0.2.0-draft.5`，具体 Schema 哈希随 Java 交付记录固定。

## 决策

Python 使用 `knowflow_ai` 只读角色检索。它不能更新任务/文档状态，也不能直接插入或修改 Chunk/向量。索引写入统一通过 Java 内部 API，由 `knowflow_app` 在数据库事务内写入。

网关每次请求同时校验服务凭证和执行上下文：路径 task ID、文档与知识库 owner、内容版本、候选索引版本、当前 task status、lease ID、未过期数据库租约、执行令牌摘要、fencing 代次及文档未删除状态。事务先按固定锁序锁定 document、task、index version，再验证和写入；任何检查失败都回滚整批。`SELECT ... FOR UPDATE` 与删除/取消、租约替换、完成发布使用相同锁序，避免 check-then-write 竞态。

批次最多 32 个 Chunk、请求体最多 1 MiB。Embedding 固定 1024 维且有限；文本上限 800 Unicode 码点；Chunk sequence 在候选索引内连续。`batch_id` 与 `batch_sequence` 在一个执行中唯一；相同身份和摘要重放返回原回执，不重复写入；同一身份或序号使用不同摘要返回 409。批次摘要的语言无关字节编码、微精度量化和共享样例见 [`contracts/api-draft.md`](../../contracts/api-draft.md#draft5-批次摘要与写入语义) 与 `contracts/index_batch_hash.py`。

候选版本按一次 task 执行隔离。重试不能复用上一次执行的部分索引；重领创建新的 `index_version`，并原子递增 fencing、替换 lease 和令牌摘要。旧 Worker 的 heartbeat、source read、batch write、failure/success completion 全部拒绝。活动版本在新候选完整通过 Java 验收前保持可查询。

## 完成与发布

Worker 的 `Completion` 仅表达成功/失败，不提供可信计数。Java 从数据库核对 Chunk 实际数量、Embedding 一对一数量、1024 维和连续序号，并核实 Manifest 与已落库批次摘要。验收、task 成功、候选 READY、活动指针切换、旧版本 RETIRED 与发布回执在同一事务内完成。文档删除或内容版本改变与发布采用相同 document 行锁；删除先提交时发布拒绝，发布先提交时删除随后立即使文档不可见。

失败、超时和进程退出不清除当前活动版本。局部候选由可重试清理任务回收；清理失败只延迟物理释放，不恢复外部可见性。完成回放只有在原执行身份和相同规范化结果摘要匹配时可以返回 `ALREADY_ACCEPTED`，且绝不再次切换活动版本；已删除文档优先返回不可用。

## 身份和租约默认值

- 内部共享 Bearer 凭证认证服务，执行令牌绑定单次 task lease；两者用途独立。
- 租约 60 秒，heartbeat 每 15 秒；期限由 PostgreSQL `CURRENT_TIMESTAMP` 判断，Java 负责延长值。
- 单任务最多 3 次执行，失败退避 5 秒、30 秒；模型请求本身不自动重试。
- 候选索引每次执行新建；最大 Chunk 批次 32 行、序号递增且每个 HTTP 请求不超过 1 MiB。
- 租约、批次和请求限制作为可配置开发默认值，不能当作生产吞吐/容量指标。

## 备选方案

直接给 Python 写数据库表仍不能表达有效租约、删除和 fencing 的原子条件；仅给安全视图 `INSERT` 权限无法阻止旧 Worker 改写已发布版本。触发器虽能保护单行状态，却难以原子核对任务、文档、lease 和跨表批次重放。Java 网关让授权判断、范围锁、审计摘要与写入共用同一事务，并保持 AI 数据库角色只读。

## 必须验证的风险

PostgreSQL 真实测试需并发覆盖同批重放/摘要冲突、同序号不同批次、过期 lease、替换 fencing、错误文档/版本、发布与删除竞态、Worker 崩溃后隔离部分写入、旧活动版本保持、成功 completion 重放及失败 completion。共享 SHA 样例必须由 Python 消费端原样通过。Schema 结构样例和单元测试不能替代这些事务及双服务验收。
