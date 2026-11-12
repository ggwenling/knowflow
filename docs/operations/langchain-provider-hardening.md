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

排障先检查配置组合、custom 总 lane、用户 / 模型名额及冷却时间。不要记录或复制 provider 原始响应、密钥、完整 URL、prompt 或 completion。重试矩阵和结构化日志字段见下节。

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


## 安全结构化调用日志

仅使用 Python stdlib logging；没有 metrics stack、exporter、`/metrics` 或新增遥测依赖。`knowflow_ai.provider_observability` 在 INFO 级别输出单行 JSON：

```json
{"event":"llm_call","request_id":"request-123","protocol":"chat_completions","model_id":"example-model","duration_ms":1420,"first_token_latency_ms":180,"first_token_observation":"content_event","token_usage":{"input_tokens":80,"output_tokens":24,"total_tokens":104},"outcome":"success","failure_category":null,"call_id":"02897053b3a8438598c95694979c96e0","attempt":1,"purpose":"answer","provider_called":true}
```

一次物理 SDK attempt 对应一条记录：agent 工具下一轮、probe fallback / 工具结果下一轮各产生新的 `call_id`；同一 turn 的 retry 共用 `call_id`，`attempt` 从 1 递增。`purpose` 为 `answer` / `repair` / `probe`。probe 保留真实内部请求 id。构造、URL 配置校验、入口 / runtime busy 和 circuit 拒绝没有访问 provider，记录 `attempt=0,provider_called=false`。每次 built-in POST 的预算拒绝也按未调用处理。`ai_stage` / `provider_retry` 诊断继续保留，不计为额外 model attempt。

`duration_ms` 来自 monotonic，包含本 attempt 的读取与 SDK 解析，不含其他 attempt 或退避；`first_token_latency_ms` 从 dispatch 至底层首内容观测，流式为 `content_event`，非流式为 `body_byte`。完整缓冲后的 SDK callback 不作为首 token。没有收到内容时两个首内容字段均为 null；没有 usage 时 `token_usage=null`，不是伪造的 0。usage 只复制当前 attempt SDK metadata 中非负整数 `input_tokens` / `output_tokens` / `total_tokens`；嵌套 metadata、布尔值、负数和字符串均不输出。`last_usage` 使用相同白名单。

成功的 `outcome=success,failure_category=null`；取消为 `outcome=failure,failure_category=cancelled`。失败类别为封闭枚举，分类不包含 provider 的错误原文，也不改变公开错误码或重试策略：

| 类别 | 含义 |
|---|---|
| `http_4xx`, `auth`, `rate_limited`, `http_5xx` | 普通 provider 4xx、401/403、429、5xx |
| `connect_failure`, `connection_reset` | 连接失败、读写中断 |
| `connect_timeout`, `first_token_timeout`, `read_timeout`, `total_timeout` | 连接、首内容、SDK 读、整体期限耗尽 |
| `invalid_completion`, `model_mismatch`, `length_truncation`, `content_filter` | 协议 / SDK 解析失败、模型不符、长度截断、过滤 / refusal |
| `redirect`, `response_too_large` | 重定向、响应超过 1 MiB |
| `busy`, `circuit_open`, `cancelled` | 本地名额拒绝、熔断拒绝、主动取消 |
| `configuration`, `budget`, `unknown` | 配置 / 本地输入拒绝、预算拒绝、未识别错误 |

不输出 key、Authorization / x-api-key、任何 base URL / proxy URL、prompt、evidence、tool args、completion、provider error message、异常对象 / traceback 或配置 fingerprint。model id 最多 160 字符；含不可打印字符、userinfo / URL / key 形状或与当前 key 重合时使用 `[redacted]`。JSON 转义保证一行。请求 id 使用内部同一字符 / 长度规则，不合法值使用 `[redacted]`。

app 和模型初始化在真实 SDK / HTTP 日志源安装丢弃 filter：`openai._base_client`、response parser、`anthropic._base_client` / response parser / tracing diagnostics、`httpx` / `httpx2`，以及 `httpcore` / `httpcore2` 的 `connection`、`http11`、`http2`、`proxy`、`socks`。即使 DEBUG 开启也丢弃原始记录，不依赖字符串替换；父 logger 的 filter 不能替代这些源 filter。`knowflow_ai.*` 安全事件保留。LangChain agent、probe 和失败调用继续使用 `tracing_context(enabled=False)`。排障按 request id / call id、固定 category、attempt、耗时与 usage 关联，不打开原始请求 / 响应日志。

## 保存前连接测试与成功记录

自定义模型始终在能力测试全部通过后保存，没有绕过测试的保存入口。保存时使用固定短文本，可能产生少量费用；不携带用户问题或证据。此流程由 `model_probe.py` 编排，与 `/health/ready` 的 `provider_probe.py` 独立，不额外请求 GET `/models`。复用可信 owner header、admission、超时和每次物理调用的 `llm_call` 日志；Python route 总预算 10 秒，Java 等待 12 秒，内部调用使用已有 probe profile。custom 不做普通失败重试。

| 公开错误码 | 判断依据与公开 HTTP |
| --- | --- |
| `LLM_MODEL_URL_INVALID` | 本地 URL 拒绝；400 |
| `LLM_MODEL_AUTH_FAILED` | provider 401/403；422，不触发本站登录失效 |
| `LLM_MODEL_NOT_FOUND` | 明确 `model_not_found` / `invalid_model` 或 `param=model`；422 |
| `LLM_MODEL_ENDPOINT_NOT_FOUND` | 404/405 无明确模型证据；422 |
| `LLM_MODEL_UNREACHABLE` | DNS、TLS、connect、中断、出口拒绝、redirect；422 |
| `LLM_MODEL_TIMEOUT` | connect / first-content / total 或 route deadline；422 |
| `LLM_MODEL_RATE_LIMITED` | provider 429；公开 422 |
| `LLM_MODEL_PROTOCOL_ERROR` | 成功响应的 wire、返回模型或工具格式不符；422 |
| `LLM_MODEL_PROBE_FAILED` | 5xx、模糊 4xx、未知异常、Java→AI 通信或契约失败；422 |

本站 `LLM_MODEL_PROBE_LIMIT` 仍是每用户每分钟 5 次的 429，区别于 provider 限流。容量不足保留 `RESOURCE_LIMIT` / 429 的固定繁忙提示。HTTP 错误最多读取 1 MiB，只提取白名单 `error.code/type/param` 的已知机器值；不从 message 猜测，不回显 body、密钥或 URL。Anthropic `not_found_error` 和裸 404 都不能证明模型不存在。Java 同样限制 1 MiB，拒绝未知代码、不匹配的 envelope、缺失 boolean/status/UTC 时间的成功结果，使用固定失败原因。

只有 400/422 的 `param=tools` / `param=tool_choice` 才允许一次纯文本能力降级；501 还必须有 `not_implemented` / `unsupported_capability` 的机器 code/type，并明确指向 tools。先排除模型等明确错误。普通 400/422/501 或文字 “unsupported tools” 不触发降级；降级失败立即拒绝。降级成功允许 `supports_tools=false`。支持工具时验证 report_ready 的 id/name/空 args、tool-result 后最终非空文本及完整协议结束。

V10 只增加 nullable `last_probe_at` / `last_probe_status`。旧记录两列均 null，界面显示“尚无检测记录”；新成功保存将工具能力、UTC 检测时间、`success`、AES-GCM 密文和 revision 一起写入 INSERT / CAS UPDATE。失败新建无模型记录；失败编辑不改变旧配置、密文、工具能力、检测记录或 revision。尝试仍计入限流表。URL/协议改变必须重新输入密钥。公开 list/save 不含凭证；运行时 Connection 只含原六个字段，检测元数据不会进入 Python CustomModel。

排障使用界面固定原因与 request id 对照安全日志。核对选定协议、Base URL 和模型 ID；密钥/权限到服务商后台核对。模糊 404 使用组合提示，不能据此认定 key 或 model。不要打开 SDK 原始 DEBUG 日志或记录 provider body；无需新增 metrics stack。HTTPS 公网域名、443、无 userinfo/query/fragment、无 redirects、proxy fail-closed、全部 DNS 答案检查和 numeric-IP 拨号保持不变。
