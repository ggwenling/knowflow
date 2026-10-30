# A 线 KF2-001、004、006 独立审阅包

审阅状态：待 Q 独立审阅。本包记录作者交付与可复核证据，不代表 Q 的审阅结论。

## 审阅范围

- 分支：`python`
- 整合基线：`0a19a7afc80fa778dd5b2e10e7a825360538a9f9`（已合入的 B/M 准备工作）
- KF2-001：base `0a19a7afc80fa778dd5b2e10e7a825360538a9f9` → target `9035f0625c606a18ef62d71b96dc6ba8803c0e99`
- KF2-004：base `9035f0625c606a18ef62d71b96dc6ba8803c0e99` → target `c67d0038d93a4af514bba4ee70ac49b1c1062318`
- KF2-006 原审阅 target：`83467d37f53e20d3262c02c441bc9efc47c846f8`；根据本轮审查发现修复后的 target：`eb88cc1fe40d91f2b4fe5b992e230779ad998daa`
- KF2-006 修复审阅范围：base `c67d0038d93a4af514bba4ee70ac49b1c1062318` → target `eb88cc1fe40d91f2b4fe5b992e230779ad998daa`
- 累计目标：`eb88cc1fe40d91f2b4fe5b992e230779ad998daa`
- 原任务卡：[V0.2 任务拆解](../planning/v0.2/KnowFlow_V0.2_任务拆解.md) 中 KF2-001、KF2-004、KF2-006。

后续审阅包/执行记录提交只补文档，不改变以上逐任务 target。旧 V1.1 设计和 `KF-*` 映射没有提供，用户已批准 V0.2 作为新工作基线；兼容性保持未验证。

## 交付说明

**KF2-001 — V0.2 基线决策。** [兼容性记录](../architecture/compatibility.md)说明新基线的批准范围、现有证据和未验证项。[映射 CSV](legacy-mapping.csv) 保留空记录，表示没有旧任务输入，并非映射通过。Q 请核对决策是否准确限定范围，以及旧基线未验证状态是否清楚。

**KF2-004 — 共享契约候选。** `contracts/` 将版本升为 `0.2.0-draft.2`，结合 B 线提交中的 `BAAI/bge-m3`、1024 维向量及 `deepseek-flash` 请求/响应证据，加入模型协议 Schema 和结构样例。模型别名仍可能变化；生产条款适用性、授权语义、模型语义匹配、真实服务/数据库行为未由 Schema 验证。B/M 消费同一版本的确认及 Q 审阅未完成，所以此交付是候选草案，尚未冻结。

**KF2-006 — 最小 Java 服务骨架。** [服务说明](../../services/api/README.md)和 `services/api/` 提供 Java 21 / Spring Boot 3.5.16 服务、锁定 Maven Wrapper、启动配置校验、请求 ID、统一错误响应、受限内部 Bearer 认证骨架及 WebClient。公开的 HTTP 路由只有最小健康检查；业务 API、登录、数据库和对 B 的真实调用尚未实现。M 的 KF2-005 仍待审阅，因此本项只验收隔离启动骨架，不把依赖或完整纵向集成算作通过。

## 首次审阅 target 验证证据（`83467d37f53e20d3262c02c441bc9efc47c846f8`）

在本次工作区执行：

```sh
python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
cd services/api
./mvnw -s /tmp/knowflow-maven-settings.xml verify
```

- 契约校验：39 项结构样例通过；不等同权限、旧 Worker、删除回调或数据库竞态验收。
- B 线离线回归：16 项通过；未重新调用供应商 API。
- Maven `verify`：Java 编译、测试和打包通过，共 8 项 Java 测试。此受限环境的 Maven 代理 settings 位于 `/tmp` 且未提交；其他环境可使用自己的 Maven `settings.xml`，不要提交代理凭证。
- 打包 JAR 进程冒烟：健康接口返回 `UP` 和服务端 request ID；业务与敏感 Actuator 路由返回未授权；仅进程内生成的测试密钥未出现在应用日志。WebClient 转发内部认证和 request ID 的验证通过本地 loopback stub 完成，没有调用外部模型或 B 服务。
- `git diff --check` 及 Markdown 相对链接检查通过。

## 审查发现修复（KF2-006 target `eb88cc1fe40d91f2b4fe5b992e230779ad998daa`）

- 未匹配路由现在返回 404 / `ENDPOINT_UNAVAILABLE`；不支持的方法返回 405 / `INVALID_REQUEST`、统一错误体及 `Allow` 响应头。测试分别携带有效内部凭证访问不存在的内部路由和对测试端点使用 POST。
- 内部共享密钥现在必须是 32–256 字符且符合 Bearer token 字符集；空白、CR、LF、Tab 和其他不安全字符在配置绑定时拒绝，避免应用健康但构造 Authorization 请求头失败。配置测试检查失败信息不包含密钥。
- 更新服务配置说明与 API 错误草案。复核构建：Maven `verify` 共 11 项测试通过；39 项契约结构样例通过。
- 打包 JAR 冒烟：有效测试 token 可启动且 health 为 `UP`；含换行测试 token 导致应用非零退出，启动日志不包含 token。

## 请 Q 核对

- KF2-001 的用户批准范围是否准确；旧 V1.1 和旧任务仍明确标为未验证，未把缺少资料表述成兼容通过。
- KF2-004 的模型 Schema 与 `0.2.0-draft.2` 样例是否忠实对应 B 线证据；检查权限/可信范围、状态单写者、重复/迟到回调、删除和失败样例的缺口，并判定当前是否仍须保持草案状态。
- KF2-006 的安全默认值、配置失败行为、敏感错误/日志边界、request ID 和路由暴露面；独立复现构建、启动及健康/封闭路由检查。
- 结合 KF2-005 审阅状态，明确哪些只是隔离骨架验收，哪些必须等契约冻结及 B/M 集成后再验。

## Q 独立结论（由 Q 填写）

- 审阅 base → target：
- 核查及复现证据：
- 阻断问题：
- 非阻断建议 / 未验证项：
- 结论：BLOCKED / CHANGES_REQUESTED / APPROVED
- 修复 SHA / 复核：
- 集成后差异与验证：
- 最终任务状态：

## JP-01 Java 增量审阅包（KF2-011 / KF2-004 candidate）

- 分支：`java`；base `150cd847a5750143fb6eb2c74c762962381952fe`；Java target `115931caaf99fe3fd9c473d2f0f1b6ebd9648ccd`。
- KF2-011 变更：Flyway `V1`、pgvector 1024 维 DDL、三种无默认密码的受限角色、独立迁移 CLI 和可选 `database` profile DataSource。AI 数据库身份只有所需查询表的 `SELECT`；运行角色无 DDL；索引写 fencing 只在 ADR-002 提案中，尚未实现或授权。
- KF2-004 candidate：`0.2.0-draft.3`，Schema SHA-256 `1b5133ddcdac4a6accb0faf4a88f2dda7204f5932151043168473d2d8574c5c5`。新增 `InternalHealth` 与 Java 消费客户端；候选未冻结，B 消费确认、M 确认及 Q 审阅缺失。
- 复核命令：`cd services/api && ./mvnw -s /tmp/knowflow-maven-settings.xml verify`（18 项 Java 测试）；`python contracts/validate.py`（41 项）；`python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`（16 项）；`git diff --check`。真实 PostgreSQL 16.12/pgvector 0.8.1 Testcontainers 覆盖迁移、重跑、CLI、约束、向量维度与角色权限。
- 联调证据见 [JP-01 Java→Python 记录](java-python-integration.md)：仅 Java loopback stub 通过。`origin/python@150cd847a5750143fb6eb2c74c762962381952fe` 没有可启动的 Python 服务，所以 JP-I1 等待 B target SHA。

请 Q 检查 `V1` 所有权/复合外键、迁移身份与历史 Schema、AI 读取范围、vector 扩展位置/维度、应用 profile 的启动边界，以及 ADR-002 的 Java 网关提案是否足以约束旧 Worker。真实 Python 行为、迁移旧库升级、租约/Fencing 和删除/发布竞态均未由本 target 证明。

## JP-01 G3 Java 审阅包（KF2-012/013）

- 分支：`java`；base `f2204a52f221e1b9691824cac845d0f75c6a2f29`；target `895a1ba4655d9e875730d5bbeb65e570853c8d01`。
- 变更：在 `database` profile 增加 PBKDF2 密码摘要、opaque 8 小时 Bearer session（只存 token SHA-256）、注册/登录/logout/current-user 及个人知识库 CRUD。每条 KB SQL 都从 principal 取 owner；含 owner 字段的 JSON 请求拒绝。删除同事务软删知识库/文档并取消活动索引任务。完整应用实现见 [ADR-003](../architecture/ADR-003-auth-and-owner-boundary.md)。
- 契约候选 `0.2.0-draft.4`，Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`；B/M/Q 尚未确认，不冻结。
- 复核命令：`cd services/api && ./mvnw -s /tmp/knowflow-maven-settings.xml verify`（21 项）；`python contracts/validate.py`（54 项）；`python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`（16 项）；`git diff --check`。认证/owner 的 HTTP 流程在真实 PostgreSQL 16.12 + pgvector 0.8.1 和 `knowflow_app` 角色上运行。
- 请 Q 检查密码 KDF 参数升级策略、session 哈希/到期/撤销、数据库 profile 的启动和过滤器边界、邮箱冲突 409 的枚举风险、owner ID 替换、软删/任务取消与删除/创建竞态。尚无登录限速、邮箱验证、密码重置、旧账户凭证补录和物理对象/向量清理；这些缺口不伪报通过。


## JP-I1 draft.4 双进程复核（最终 target，2026-10-30）

- A Java target `ec5c71c9be5a8766540fc48e174f215c0cf388ac`（包含 406 修复 target `24a07fd85c70cab3c522118697824727bf9651fe`）；B Python 当前 target `b598f1d62cc2367a4bfd49fccd3c31b521abff23`（代码/测试 target `2623a6282b2695a8ef96e3553a849729efd42403`）。B 已合入确切的 A draft.4 契约提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 双进程实际运行提交 `225124fbae8041efd67ee5e6ca5bf89fdbbe8884`，其父提交为该 B 代码 target 与 A target `ec5c71c`。干净 worktree 报告见 [java-python-smoke-draft4.json](java-python-smoke-draft4.json)，SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`；报告绑定 Java target 且运行前后 clean。
- B 全量 Python 测试 65 项、契约 54 项、离线回归 16 项通过；真实 Uvicorn + Spring Boot smoke 8/8 通过。测试实际调用 Java `AiInternalHealthClient.check()`，接受 draft.4/status/request ID，拒绝 draft.2 fixture，并验证实际 5 秒超时；同时覆盖凭证、404/405、Allow、不可达和慢响应。无模型/数据库调用，秘密未出现在日志。
- JP-I1 开发集成验证通过；Schema 仍为 DRAFT，Q 审阅和 M 消费确认尚未完成，不记录为 APPROVED 或 DONE。

## Q 复核修复：406 Content Negotiation（2026-10-30）

- Review base `ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434` → fix target `24a07fd85c70cab3c522118697824727bf9651fe`。
- `Accept` 无可用表示时，Spring 抛出的 `HttpMediaTypeNotAcceptableException` 不再落入通用 500 处理器。专用 handler 使用框架 status 与 headers，并返回标准 JSON 错误体；406 对应 `INVALID_REQUEST`，响应头保留 Spring 报告的支持媒体类型。
- 回归测试：携带有效内部凭证访问 JSON 端点并发送 `Accept: application/xml`，断言状态 406、`Accept` 包含 `application/json`、`X-Request-ID` 存在、错误体为 draft.4 JSON 且 code/message 固定脱敏值。
- 复核命令及结果：`cd services/api && ./mvnw -s /tmp/knowflow-maven-settings.xml verify`（22 项通过）；`python3 contracts/validate.py`（54 项通过）；`python3 -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`（16 项通过）；`git diff --check` 通过。
- 请 Q 复核此 target 和响应头断言；尚无批准结论。
