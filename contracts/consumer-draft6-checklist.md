# draft.6 消费清单（提交前核对）

状态：Java 与 Python 在本机 `local` 集成分支同步消费 draft.6；尚无提交 target 或真实业务双进程验收记录，Q 审阅待处理。不要将该清单视为正式冻结或独立消费确认。

本机 `local` 分支从 `main` 创建，尚未提交；共享 Schema SHA-256：`d64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1`。Java 常量、Python 精确哈希消费者、契约样例和消费测试均固定 `0.2.0-draft.6`。正式分线消费仍需各自提交 SHA 与独立复核；复制字段或只使用相同版本字符串不算消费。

## Python / B 索引消费者

- 把 `contract_version` 固定为 `0.2.0-draft.6`；未知字段拒绝。内部 Bearer 只证明服务身份，`LeaseContext` 才授权具体执行。
- `embedding_model_profile_id` 使用独立标识规则，允许 `BAAI/bge-m3` 中的 `/`；其他普通资源 ID 仍不因此放宽。
- `IndexDispatch` 中不接受任意 URL、本地路径或客户端对象键。按 task ID 和 lease 调用 Java `POST /internal/v1/tasks/{task_id}/source`，校验响应版本、task、document、content version、格式、SHA-256 和长度。
- 通过 Java `POST /internal/v1/tasks/{task_id}/index-batches` 写入向量；每批最多 32 条，整个 JSON body ≤1 MiB；每个向量恰好 1024 个有限值；文本 ≤800 Unicode 码点并匹配原文 UTF-8 SHA；Chunk sequence 全局连续。
- 按 `contracts/api-draft.md` 的精确字节规则计算 `batch_sha256`。消费测试必须使用 `protocol-cases.json` 的 `index-batch` golden vector 并得到同一 digest。相同批次可安全重放；`BATCH_CONFLICT`、`LEASE_REJECTED`、`DOCUMENT_UNAVAILABLE` 后停止写入并停止付费模型工作。
- 每 15 秒 heartbeat；Java 租期默认 60 秒。取消请求按 task、lease、fencing 精确取消，旧代次取消不得终止当前新执行。Python 不创建持久调度队列，也不持有 Java DB 写凭据。
- Completion 只上报成功或稳定失败类别，不以自报计数替代 Java 对实际写入的验收。只有 Java 发布后才视为索引可检索。
- 答案内部调用消费 `TrustedAnswerRequest`，不能接受浏览器提交的 owner/scope。输出最多 5 个来源；无答案时 `has_answer=false` 且 sources 为空。有事实回答时需引用真实检索证据。

## Java / A 自测矩阵

- 正常：固定批次摘要回执、JSON body 上限、源文件返回字节摘要、同 lease heartbeat、Java 实际验收与发布。
- 拒绝：错误版本/未知字段、错误媒体类型、错误维度/NaN/Infinity/文本摘要、伪造范围、重复/跳跃序号、超 32 条/超 1 MiB、摘要冲突。
- 授权：错误内部密钥、他人/删除文档、错误 content/index/task、错误令牌、过期 lease、旧 fencing。
- 并发与恢复：同一批并发重放只落一份；不同摘要冲突；删除和写入/发布竞态；部分写入后崩溃与新版本重领；旧版本保持可用；清理失败可重试但不可恢复可见性。

## M / 页面消费者

- 公开上传返回 202 后显示 QUEUED/PROCESSING；只有状态查询为 READY 时展示可问答。
- 使用统一错误体与 HTTP 状态；415、406 保留支持媒体类型头，405 保留 `Allow`。
- 浏览器只传知识库 ID 和文件/问题，不传 owner、文档状态、执行身份、索引范围、对象地址或来源授权字段。
- M 仍需确认外部注册、上传、任务、问答、来源和删除响应是否满足页面消费；不要求 M 消费内部 Java/Python 执行报文。

## 尚未由契约结构验证的事项

Schema 不验证来源归属、租约时效、批次摘要与真实数据库内容一致、原子发布、模型证据支持或删除竞态。以上必须由运行时代码和指定真实依赖测试证明。Q 未复核前，本版本保持 DRAFT。
