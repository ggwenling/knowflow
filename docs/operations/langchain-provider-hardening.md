# LangChain 调用边界运维

当前边界是每个 app / 每个进程独立的内存状态。当前部署使用单 worker；增加 worker 或副本会放大容量和熔断状态，不能视为集群限流。自定义模型仍只走受控 HTTPS CONNECT 出口，不使用 built-in 的连接池、用户 lane 或 breaker；密钥加密、DNS 全地址校验和禁止重定向保持原约束。

## 超时配置

秒数必须有限，不接受 NaN、Infinity、布尔值；整数不接受小数或布尔值。非法配置启动失败，仅报 `LLM_LIMITS_CONFIGURATION_INVALID`，不回显输入。

| 环境变量 | 默认秒数 | 范围 |
|---|---:|---|
| `KNOWFLOW_LLM_CONNECT_TIMEOUT_MAX_SECONDS` | 5 | 0.1..10 |
| `KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_MAX_SECONDS` | 20 | 0.1..25 |
| `KNOWFLOW_LLM_TOTAL_TIMEOUT_MAX_SECONDS` | 25 | 1..25 |
| `KNOWFLOW_LLM_CONNECT_TIMEOUT_SECONDS` | 3 | 0.1..10 |
| `KNOWFLOW_LLM_FIRST_TOKEN_TIMEOUT_SECONDS` | 10 | 0.1..25 |
| `KNOWFLOW_LLM_TOTAL_TIMEOUT_SECONDS` | 25 | 1..25 |
| `KNOWFLOW_CUSTOM_LLM_CONNECT_TIMEOUT_SECONDS` | 3 | 0.1..10 |
| `KNOWFLOW_CUSTOM_LLM_FIRST_TOKEN_TIMEOUT_SECONDS` | 10 | 0.1..25 |
| `KNOWFLOW_CUSTOM_LLM_TOTAL_TIMEOUT_SECONDS` | 25 | 1..25 |

计算顺序为 `effective_total=min(requested_total,system_total_max)`、`effective_first=min(requested_first,system_first_max,effective_total)`、`effective_connect=min(requested_connect,system_connect_max,effective_first)`。系统 max 必须 `connect_max <= first_max <= total_max`。降低 max 会自动截断默认 profile，无需同时修改所有值。custom 配置来自部署 env，没有每模型 DB 超时字段或浏览器 override。

connect 覆盖到出口代理的连接及 TLS / CONNECT；两个 HTTP 库分别使用各自 Timeout 类型，read / write / pool 均不超过 total。流式首内容是首个非空 text、refusal 或工具名称 / 参数事件（`content_event`）；headers、注释、heartbeat、空 delta、usage-only 不满足也不重置时限。非流式以第一个非空 body byte 为边界（`body_byte`），不能等同于模型首 token。

调用仍先缓冲最多 1 MiB 并校验协议完成，再交给 SDK / 客户端，不提前公开未验证答案。total 从一个逻辑 model turn 开始，包含预算预留、所有 attempts、读取、SDK 解析和重试退避；agent 下一轮会重新申请 turn，检索不占模型 lease，所有轮次仍受 AnswerService 28 秒总预算限制。连接 / 首内容 / total 超时均为 504 `PROCESSING_TIMEOUT`。断连取消会关闭流、等待任务收尾并释放名额，不作为 provider 健康失败。

保存前 probe 每轮最多 5 秒，connect / first 再取 custom profile 与 total 的最小值；Python route 总共 10 秒，Java 等待 12 秒，能力降级及工具结果 roundtrip 共用 route 总预算。readiness 的 `KNOWFLOW_PROVIDER_PROBE_TIMEOUT_SECONDS` 是另一项配置。custom 不做普通自动重试；现有能力协商降级继续保留。

## 并发与熔断

| 环境变量 | 默认 | 范围 |
|---|---:|---|
| `KNOWFLOW_QUESTION_MAX_CONCURRENT` | 4 | 整数 1..32 |
| `KNOWFLOW_CUSTOM_LLM_MAX_CONCURRENT_REQUESTS` | 2 | 整数 1..32 |
| `KNOWFLOW_LLM_MAX_CONCURRENT_PER_USER` | 2 | 整数 1..16 |
| `KNOWFLOW_CUSTOM_LLM_MAX_CONCURRENT_PER_MODEL` | 1 | 整数 1..8 |
| `KNOWFLOW_LLM_BREAKER_FAILURE_THRESHOLD` | 3 | 整数 1..20 |
| `KNOWFLOW_LLM_BREAKER_COOLDOWN_SECONDS` | 30 | 有限秒数 1..300 |

Java 和 Python 都保留问答总上限；custom 问答与 probe 合计最多 `min(KNOWFLOW_CUSTOM_LLM_MAX_CONCURRENT_REQUESTS,total-1)`。开启 custom 且 total < 2 会启动失败，固定 `LLM_ISOLATION_CONFIGURATION_INVALID`；关闭 custom 时 total=1 有效。总量已满仍走既有总量过载行为（Python 503、Java 既有受控 AI 失败），不突破总上限。

LLM runtime 的 per-user 分为 built-in 和 custom 两个 lane；同用户跨 custom 模型共用用户名额，每个 `(owner UUID, custom UUID)` 另受 model cap。入口与模型限额均即时拒绝，不排队：429 `RESOURCE_LIMIT`，固定“模型请求繁忙，请稍后重试。”，`retryable=true`。busy 允许用户稍后手动重试，不进入 provider 自动重试。公开 busy 与历史分开映射，历史写 `AI_PROCESSING_FAILED`，遵守原 CHECK。

owner 只从 Java 已认证的可信 scope 获取；probe 的 `X-KnowFlow-Owner-ID` 必须是 UUID，Python 先校验内部 Bearer。请求 id 来自 Java RequestIdFilter，不能把浏览器 owner 或原始 request id 当成可信身份。

breaker 按逻辑 turn 的最终结果计连续失败：默认 3 次后 OPEN，冷却 30 秒；网络、超时、HTTP 和完成协议校验失败都计入。成功归零，本地配置 / 预算 / 容量拒绝、取消和能力协商不计失败。OPEN 时快速返回 503 `AI_PROCESSING_FAILED`，不预留预算、不访问 provider。冷却后 HALF_OPEN 只允许一个请求且仅一个物理 attempt；成功 CLOSED，失败重新冷却。half-open 取消也释放探测 token 并重新冷却，但不累计健康失败。generation token 防止旧请求迟到成功覆盖新的 OPEN。

built-in key 独立；custom key 通过进程随机盐 HMAC 覆盖 protocol / endpoint / model / key。更换配置后使用新的健康状态，稳定 UUID 并发上限仍有效。状态表最多 1024 项，空闲 600 秒可清理；未结束请求、未到冷却时间的 OPEN 和 HALF_OPEN 不会被驱逐。没有可回收条目时返回 busy。以上两项是内部资源常量。

排障先检查配置组合、custom 总 lane、用户 / 模型名额及冷却时间。不要记录或复制 provider 原始响应、密钥、完整 URL、prompt 或 completion。重试矩阵见下节；后续步骤将补充日志字段。

## 共享重试分类

LangChain、旧 DeepSeek adapter、embedding 与旧 streaming 共用标量分类函数。SDK 内置重试始终为 `max_retries=0`，只有 built-in 进入有界重试；custom 三种协议始终只有一次普通调用，不提供重试开关。probe 的一次能力协商降级不是 transient retry。

| 失败（尚无模型内容） | built-in 自动 retry | 对外映射 |
|---|---|---|
| HTTP 429 | 是，遵守剩余预算内的 `Retry-After` | 502 |
| HTTP 500..599，含 501 / 505 / 599 | 是 | 502 |
| connect failure、connection reset、读写连接中断 | 是 | 502 |
| connect / first-token / read timeout，total 尚有剩余 | 是 | 504 |
| HTTP 400..499 除 429，含 400 / 401 / 403 / 404 / **408** / 422 | 否 | 502 |
| HTTP 3xx | 否，不跟随重定向 | 502 |
| completion validation、wrong model、parse、garbage、size、encoding | 否 | 502 |
| filter、refusal、length truncation | 否 | 502 |
| invalid URL、unsupported protocol、预算 soft stop、admission、breaker | 否 | 保留原错误映射 |
| turn total / 外层 deadline 耗尽 | 否 | 504 |
| cancellation | 直接传播并收尾 | 保留取消语义 |

底层已收到有意义 provider 内容（`output_started`）或已交付 model 内容（`client_output_started`）时，无论 429、5xx、reset、timeout 都禁止下一 attempt。headers、SSE `started` 元数据、heartbeat 不算 model 内容。每次退避前及退避结束后重新检查输出、取消和剩余时间。未知 transport / 本地协议 / 解码错误不会笼统视为连接失败；旧 streaming 仍保留 emitted 防线。

| 环境变量 | 默认 | 范围 |
|---|---:|---|
| `KNOWFLOW_PROVIDER_RETRY_MAX_ATTEMPTS` | 3 | 整数 1..5 |
| `KNOWFLOW_PROVIDER_RETRY_BASE_SECONDS` | 0.5 | 有限秒数 0..5 |
| `KNOWFLOW_PROVIDER_RETRY_TOTAL_SECONDS` | 25 | 有限秒数 0..60 |

退避为指数增长，429 的合法 `Retry-After` 优先。effective retry cutoff 为 `min(turn_deadline, retry_started + retry_total_seconds)`；等待等于或超出剩余时间直接放弃，不裁成短延迟继续请求。`retry_total_seconds=0` 允许第一次 attempt，但不允许第二次。retry cutoff 只约束下一次调度，Step 2 的 total deadline 继续包住整个 turn（包含正在执行的 attempt 与退避），不会因重试重新开始或延长；所有 turn 仍受问答外层 28 秒限制。

每个实际 built-in POST 独立预留一次预算，失败也计入 ledger，soft stop 立即结束。breaker 的 half-open probe 无论重试默认值如何均只有一个物理 attempt；busy / breaker 快速拒绝不预留预算。
