# KF2-004 后端开发候选 API 目录

状态：`DRAFT 0.2.0-draft.5`。此版本是后端开发候选，需 B 精确消费提交和 Schema 哈希，并由 Q 审阅；不表示 KF2-004 冻结或生产 API。用户已批准 V0.2 重建基线，不再等待缺失的 V1.1 设计包。

## 公开入口：浏览器 → Java

| 候选入口 | 成功行为 | 身份与关键边界 |
|---|---|---|
| `POST /api/v1/auth/register`、`POST /api/v1/auth/login` | 注册或获取凭证 | 使用 `RegisterRequest` / `LoginRequest`；统一错误不返回密码或账户凭据 |
| `POST /api/v1/auth/logout` | 撤销当前凭证 | Bearer access token 的会话行标记撤销；重复/过期凭证按未认证处理 |
| `GET /api/v1/me` | 当前用户 | 身份只来自服务器验证后的凭证 |
| `POST /api/v1/knowledge-bases`、`GET /api/v1/knowledge-bases` | 创建/分页列表 | `CreateKnowledgeBase` 不接受 owner；列表只返回当前所有者资源 |
| `GET/DELETE /api/v1/knowledge-bases/{kb_id}` | 详情/逻辑删除 | 不存在、他人或已删统一 404；删除知识库同步撤销其文档可见性 |
| `POST /api/v1/knowledge-bases/{kb_id}/documents` | 202，文档与任务标识 | TXT/MD/文本 PDF；文件 8 MiB、PDF 200 页、文本 200,000 码点开发上限；对象路径由 Java 生成 |
| `GET /api/v1/documents/{document_id}` | 文档状态、当前活动索引与处理中任务 | 上传成功不等于 READY；更新失败时旧活动版本继续可用 |
| `DELETE /api/v1/documents/{document_id}` | 提交逻辑失效，安排清理 | 返回成功前提交逻辑删除；清理失败不恢复可见性 |
| `POST /api/v1/documents/{document_id}/rebuilds` | 202，新任务与候选索引版本 | KF2-004 冻结代次与幂等键前不可公开；重建不能直接切换活动版本 |
| `GET /api/v1/tasks/{task_id}` | 状态、脱敏失败原因、尝试次数 | 经文档/知识库关联检查所有者；不返回执行令牌 |
| `POST /api/v1/knowledge-bases/{kb_id}/questions` | 单轮答案、证据、版本信息 | 仅 `question` 和服务器支持的选项；未知/owner/范围字段拒绝；返回前再次检查可见性 |
| `POST /api/v1/knowledge-bases/{kb_id}/questions/stream` | SSE | 与非流式同一权限规则，每事件发送前复核，断开传播取消 |
| `GET /api/v1/sources/{source_id}` | 当前可访问的原文定位 | 验证 source→记录→所有者及文档/内容/索引/Chunk 对应关系，不能靠 ID 存在即放行 |
| `GET /api/v1/documents/{document_id}/contents/{content_version_id}/file` | 鉴权代理读取 | 版本必须属于该文档，禁止长期公开对象地址，限制 Range 读取 |
| `GET /api/v1/questions`、`GET/DELETE /api/v1/questions/{question_id}` | 所有者历史 | 失败/取消不标成功；每次提问独立检索，不把历史当多轮上下文 |

上传使用 `multipart/form-data` 的单一 `file` 部分，成功返回 `202` 和 `DocumentUploadAccepted`。开发限额为文件 8 MiB、PDF 200 页、TXT/MD 200,000 Unicode 码点。Java 忽略客户端路径和媒体声明，按文件名扩展名与文件签名匹配 `txt`、`md`、`pdf`；对象键由 Java 随机生成。失败时不留下可见文档、任务或孤儿对象；补偿删除失败写入可重试清理队列。

文档列表为 `GET /api/v1/knowledge-bases/{kb_id}/documents?limit=50&offset=0`；文档状态为 `GET /api/v1/documents/{document_id}`；任务状态为 `GET /api/v1/tasks/{task_id}`。列表只包含当前用户、活动知识库下未删除文档。上传提交后任务为 `QUEUED`；只有已发布索引才显示 `READY`，候选版本成功或 Worker 自报完成都不表示 `READY`。状态响应不返回执行令牌、对象键、原文、向量或内部凭证。

所有输出前检查以当前可见性为准。历史答案文本可能包含删除前已经显示的内容；不可借其来源访问已失效原文件。源版本保留期限待确认，不能无限保留或直接承诺固定天数。

### KF2-012/013 局部凭证与知识库候选

注册和登录使用 email + password JSON；密码长度候选为 12–128 字符。Java 使用 PBKDF2 编码器，仅持久化密码哈希。成功注册/登录返回一次性显示的 32 随机字节 opaque Bearer token、用户 ID/email 和 `expires_at`；服务端只保存 token 的 SHA-256 哈希。access token 有效期为 8 小时，无 refresh token；logout 撤销当前 token。重复邮箱的注册响应使用通用消息，但 409 状态仍可能暴露邮箱冲突；需要 M/Q 在产品集成前评估验证邮箱或限速设计。客户端凭证存放、浏览器持久化、CSRF/跨站策略和登录速率限制也待确认；当前 API 仅接受 Authorization Bearer，不设置 Cookie。

知识库列表默认 `limit=50`、`offset=0`，最大 `limit=100`、最大 `offset=1000000`；只查询认证主体拥有且 ACTIVE 的知识库。不存在、他人所有及已删除 ID 返回相同 404。删除立即标记知识库及其文档不可见并撤销未完成的索引任务；对象与向量物理回收由后续存储/清理任务接入。

## 内部入口与租约

内部接口不公开给浏览器；服务认证需在读取任务范围前验证。以下结构统一携带契约版本。

| 方向 / 候选入口 | 作用 | 校验与失败 |
|---|---|---|
| Java 内部调度器，数据库事务 | 原子领取候选任务，建立执行租约 | 仅一个当前有效租约；每次重试递增 fencing，写入新令牌哈希；不向 Python 开放通用领取权限 |
| Java → Python `GET /internal/v1/health` | 验证服务进程可接收内部 HTTP 请求 | 要求服务认证；返回 `InternalHealth`，回传 `X-Request-ID`；不触发模型、数据库或业务依赖探测 |
| Java → Python `POST /internal/v1/index-executions` | 派发已有租约的索引任务 | `IndexDispatch`；B 校验服务身份、执行范围和超时；文件通过受限服务读取，不接收任意 URL/本地路径 |
| Python → Java `POST /internal/v1/tasks/{task_id}/source` | 读取当前执行绑定的原始对象 | 请求体为 `SourceReadRequest`；路由 ID 必须匹配租约任务；成功响应为原始字节流及契约版本、格式、摘要、长度头，不返回 bucket/object key；最大 8 MiB |
| Python → Java `POST /internal/v1/tasks/{task_id}/index-batches` | 写入有界候选 Chunk/向量批次 | `IndexBatch`；最多 32 条且 JSON 请求体不超过 1 MiB；响应 `IndexBatchReceipt`；授权检查和全部写入在同一事务 |
| Python → Java `POST /internal/v1/tasks/{task_id}/heartbeat` | 延长当前租约 | `Heartbeat`；任务/版本/令牌/fencing/当前有效期均匹配；过期拒绝，延长值由 Java 决定 |
| Python → Java `POST /internal/v1/tasks/{task_id}/completion` | 提交成功或失败结果 | `Completion`；Java 自行核实索引数据，不信任结果计数；已删拒绝；相同已接收结果幂等应答 |
| Java → Python `POST /internal/v1/index-executions/{task_id}/cancel` | 取消指定的执行代次 | `CancelExecution` 必须匹配当前或刚被撤销的执行令牌、lease 与 fencing；旧取消不能影响后续代次；幂等返回 |
| Java → Python `POST /internal/v1/answers` | 使用可信快照检索/生成 | `TrustedScope` 只由 Java 构建；Python 在 SQL 层联合校验知识库、owner、文档可见性与活动版本 |
| Java → Python `POST /internal/v1/answers/stream` | 同一范围下流式生成 | 事件字段/顺序见下文；输出前 Java 复核，不信任 Python 自报“可访问” |

B 线 KF2-003 的 [运行记录](../docs/architecture/runtime-profile.md)确认候选 `BAAI/bge-m3` 和实测向量 1024 维；DeepSeek 请求别名为 `deepseek-flash`，不是不可变后端版本。模型标识/维度约束和合成报文会加入 Schema。生产超时、容量及文件限制仍不由短冒烟推导。

向 Python 不发放数据库写权限。索引写入由 Java 受控网关执行，每次事务绑定当前文档、候选版本和有效执行；Java 校验与所有行写入处于同一 PostgreSQL 事务，阻止旧 Worker 写已发布或替换的索引。

### draft.5 批次摘要与写入语义

`IndexBatch` 的每条 Chunk 包含 1024 个有限 JSON 数值、最多 800 个 Unicode 码点的原始文本、其 UTF-8 SHA-256 和精确 locator。Java 校验维度、有限性、文本摘要、范围形状、当前任务/文档/内容版本/候选索引、租约、执行令牌、fencing 和未过期时间；校验与批次写入处于同一 PostgreSQL 事务。Python 没有数据库写凭证。

批次序号从 1 开始连续递增；`chunk.sequence_no` 在同一候选索引内从 1 全局连续。一个执行的 `batch_id` 与批次序号永久绑定到摘要。相同执行身份、批次 ID、序号和摘要重放返回 `ALREADY_ACCEPTED`，不重复插入；同 ID/序号但摘要不同、重复序号或跳号返回 `409 BATCH_CONFLICT`。租约失效、文档删除或 fencing 不匹配返回 `409 LEASE_REJECTED` / `DOCUMENT_UNAVAILABLE`，不得修改任何行。

跨语言摘要向量固定为 `contracts/examples/protocol-cases.json` 的 `index-batch`。算法使用 SHA-256，输入为 UTF-8 字节：先写 `knowflow-index-batch-v1\n`，再按下列顺序写每个字段的 `十进制 UTF-8 字节数:字段值\n`：task、owner、knowledge base、document、content version、index version、lease、fencing、batch ID、batch sequence、chunk count；随后按 chunk sequence 写每项的 chunk ID、sequence、文本 SHA-256、locator kind、locator 的页码或 start/end/unit，最后写 1024 个向量值。向量值先以十进制精度量化到 6 位小数、`HALF_EVEN`，再格式化为固定 6 位小数字符串；Java 必须持久化同一量化值。request ID、执行令牌和 `batch_sha256` 本身不进入摘要。执行令牌不写日志或审计记录。

`Completion.outcome=SUCCEEDED` 只触发 Java 验收：Java 查询实际 Chunk 与向量数、连续序号、维度及批次清单摘要，不能采信 Worker 自报数量。验收通过后，在同一事务锁定文档和任务、核对未删除/当前内容版本/当前 fencing、将候选标记为 `READY` 并切换活动版本；旧活动版本随后标为 `RETIRED`。失败不得破坏已有活动版本。相同 completion 结果摘要可幂等应答但不再次发布，不同结果冲突。

租约默认 60 秒、心跳 15 秒、最多 3 次执行；服务器数据库时间是唯一租约时钟。排队失败按 5 秒、30 秒退避，耗尽后进入 `FAILED`。每次领取将 fencing 原子递增、替换 lease/令牌哈希；过期执行的写入、心跳和完成都被拒绝。崩溃重领创建新的候选索引版本，隔离前次部分 Chunk；当前活动索引保持可检索。

`SourceReadRequest` 仅携带路由 task ID 和完整 `LeaseContext`，不接受 object key、URL 或本机路径。Java 在一次读取中验证内部服务身份、任务范围、有效租约、执行令牌/fencing、文档/内容版本归属及未删除状态。成功响应是原始文件字节，使用 `X-Contract-Version`、`X-Request-ID`、`X-Source-Format`、`X-Source-SHA256` 和 `Content-Length` 描述，禁止重定向或返回存储凭据。

问答公开请求只包含问题。Java 从认证主体查询所有者知识库的 `READY` 活动索引，构造 `TrustedScope` 并调用 Python；客户端不能提交 owner、snapshot、索引范围或向量。Python 仅使用只读身份，按 owner/kb/document/content/index 联合过滤。回答最多 5 条引用；有答案必须有至少一个来源，无证据时返回 `has_answer=false` 和空来源。Java 在响应前重新核对来源仍可见，已删除或切换的索引不能返回原文。

## 错误与幂等提议

| 情形 | HTTP / code | 语义 |
|---|---|---|
| 请求结构或 Content-Type 不支持 | 400 / INVALID_REQUEST；415 / INVALID_REQUEST | 不回显敏感输入；415 保留框架 `Accept` 支持类型头 |
| 请求的 Accept 表示不受支持 | 406 / INVALID_REQUEST | 保留框架提供的支持类型 `Accept` 响应头 |
| 未认证或服务认证失败 | 401 / UNAUTHENTICATED | 无内部凭证细节 |
| 内部范围不符 | 403 / SCOPE_DENIED | 外部不可用资源仍统一 404 |
| 不存在/他人/已删的外部资源 | 404 / RESOURCE_NOT_FOUND | 防止枚举 |
| 服务路由不存在或不可用 | 404 / ENDPOINT_UNAVAILABLE | 不泄露路由内部细节 |
| 当前路由不支持该 HTTP 方法 | 405 / INVALID_REQUEST | 返回 `Allow` 响应头 |
| 旧、过期或被替换的执行租约 | 409 / LEASE_REJECTED | 不延长、不写状态、不发布 |
| 当前有效执行但资源已删除 | 409 / DOCUMENT_UNAVAILABLE | 内部专用；不恢复文档 |
| 已完成任务的不同结果 | 409 / COMPLETION_CONFLICT | 不重新发布、不覆盖第一次结果 |
| 模型或索引流水线失败 | 502 / AI_PROCESSING_FAILED | 返回脱敏失败类型及 request_id，不包含原文/密钥 |
| 请求或模型超时 | 504 / PROCESSING_TIMEOUT | 停止后续输出，触发取消 |

相同完成重放只有在“此前已接收的执行身份 + 相同规范化结果摘要”匹配，且文档未删除时返回 `200 ALREADY_ACCEPTED`；不重新延长租约或发布。此路径不要求旧的租约有效期仍在未来，但必须核实原执行令牌的身份。没有接收记录的过期租约一律 409。不同摘要拒绝。已删除优先拒绝，即使是之前成功的相同重放。完成结果和发布同事务记账，重试不得重复发布。

错误结构中的 `retryable` 表示当前请求是否适合重试，不授权 Python 自行创建业务重试任务；重试上限与退避属于 Java。

## SSE 与证据

候选事件：`started` → `delta`（零到多次）→ `sources` → `completed`；异常终止为 `error` 或 `cancelled`，只能有一个终态。所有事件关联 `request_id` 与单调 `sequence`。无答案可有零来源；有事实结论的成功回答需要可核验证据。首版不承诺 EventSource 断点重放，客户端不得因断线自动新建付费请求；重连/持久化策略在 KF2-031/033 前固定。

Java 在每个事件发送前检查整个快照/实际使用文档的当前可见性；删除后只可发送不含片段的终止事件。非流式在返回前做同一检查。删除前已到达客户端的数据无法撤回，检查与网络写出之间的并发语义需在实现和竞态测试中明确。

证据标识保留 document/content/index/Chunk；PDF 页码从 1 起，TXT/MD 字符区间按 Unicode 码点计数，从 0 起、右端不含。MD 偏移针对原始保存文本，不针对渲染 HTML。PDF 文本片段与页面文本映射由 B 提供，不编造坐标。Schema 可检查形状，`end > start`、片段与原文相符和版本归属必须运行时核验。

## 尚待决定

公开认证的令牌存放/刷新/退出与 CSRF 策略；完整分页与资源响应；B 的生产超时/容量；内部认证凭证轮换；索引写入 fencing 机制；快照与版本保留/清理；内容更新上传协议；SSE 可见性检查与取消；完整问答持久化幂等与费用记录。以上阻断 KF2-004 正式冻结，但不阻断独立运行的 KF2-006 骨架。
