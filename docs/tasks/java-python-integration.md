# JP-01 Java → Python 开发联调记录

状态：`WAITING_B_SERVICE`。本文件区分 Java 本地边界测试与两进程联调；本地 stub 不记为真实跨服务集成。

## 基线与依赖

- 共同计划基线：`150cd847a5750143fb6eb2c74c762962381952fe`。
- Java 分支：`java`；本地健康客户端调用 `GET /internal/v1/health`，使用 `KNOWFLOW_INTERNAL_SHARED_SECRET` 与 `X-Request-ID`，5 秒内无自动重试，并校验响应契约版本、状态和 request ID。
- 契约候选：`0.2.0-draft.3`；Schema SHA-256：`1b5133ddcdac4a6accb0faf4a88f2dda7204f5932151043168473d2d8574c5c5`。
- 当前 `origin/python`：`150cd847a5750143fb6eb2c74c762962381952fe`。该提交的 `services/ai/` 只有 `.env.example` 与 README，没有 FastAPI 入口或可启动内部 health 路由；因此没有 B target SHA 可供真实联调。

## 已验证的 Java 侧场景

`services/api` 的 `ApiSecurityIntegrationTest` 使用仅监听 loopback 的本地 HTTP stub 验证 Java 请求认证头、request ID 透传、JSON 反序列化及 health 响应中的版本/状态/request ID 一致性。该证据验证 Java 消费边界，不证明 Python 接口已实现。

同一测试类覆盖 Java 自身统一 404/405 错误、`Allow` 响应头、认证及 request ID 行为。它们不是对 Python 404/405 的验证。

## 待真实双进程运行

收到 B 的服务提交和准确启动命令后，A 需记录 B target SHA、Java target SHA 及服务实际地址，并验证：

1. 正确密钥下 health 返回 200 且响应 request ID 原样匹配。
2. Python 缺失/错误密钥返回统一 401 错误，未知路由返回 404、错误方法返回 405 且有 `Allow`。
3. 不支持契约版本及无效 health 报文按版本化 Schema 拒绝。
4. Python 进程不可达和超时在 Java 5 秒调用边界内终止；无自动重试。

在这些场景均对真实进程执行前，JP-I1 保持待办。B 的缺席不会阻断当前 KF2-011 数据库交付。
