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
