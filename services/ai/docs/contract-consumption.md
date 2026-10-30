# B 线契约消费及 A 交接（JP-01 / KF2-007）

开发基线：150cd847a5750143fb6eb2c74c762962381952fe。公共契约由 A 单写。本文件为 B 消费记录/提案，不是第二份正式契约。

当前明确升级消费 A 的提交 895a1ba4655d9e875730d5bbeb65e570853c8d01（当前联调 Java target ec5c71c9be5a8766540fc48e174f215c0cf388ac，含 A 的 406 修复）；版本 0.2.0-draft.4。Schema SHA-256：ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41。启动校验精确哈希；A 发布新候选后，B 必须明确升级消费者，不会静默接受不同文件。安装后用 KNOWFLOW_CONTRACT_PATH 提供同一只读文件。

| 项目 | 已实现 / 消费行为 | 尚未声明完成 |
|---|---|---|
| Error | 五字段、snake_case；400/401/404/405/500/502/504 脱敏；405 Allow；ErrorBody Pydantic 严格类型 | 业务权限/租约错误尚无执行端点 |
| 内部身份 | 与 Java 一致的 32–256 字符 Bearer 语法；恒定时间比较；重复 Authorization 拒绝 | 轮换、独立双向凭证和部署网络隔离待后续任务 |
| 请求 ID | X-Request-ID；合法 Identifier 原样透传，缺失/非法/重复生成 UUID | Java 自行生成边界仍由 Java 维护 |
| IndexDispatch / TrustedScope / Source / 模型报文 | 直接使用 A 的 JSON Schema 及 RFC3339 检查器；54 个正负样例消费回归 | 结构合法不证明授权，业务路由保持未注册；不接任意 URL/文件路径 |
| 定位 | text_range Unicode 码点 [start,end)；PDF page 1 起；另校验 end>start | 来源归属、内容/索引版本及数据库过滤待 017/018/021 |
| 模型边界 | ModelAdapter/Retriever/IndexExecutor Protocol；ID/维度/有限非零向量校验，30秒内 deadline/取消传播 | 尚无业务 Provider 实现或线上适配器验收；不以健康宣称模型可用 |

## 已消费的内部健康候选契约

本轮按 JP-01 提供 GET /health/live（200，只有 status=UP）和 GET /internal/v1/health（需内部凭证；status、contract_version、request_id）；响应头均有 X-Request-ID。前者仅限 GET 匿名，其他路径均先鉴权。健康不连接数据库、不读取模型密钥、不发外部请求。

A 已将内部健康响应纳入 InternalHealth Schema，B 使用该定义验证健康响应和新增正负例；公共契约与样例通过正常合并 A 原始提交获取，没有临时覆盖或手抄降级。候选仍未正式冻结。未实现 answers/index-executions 返回 404 ENDPOINT_UNAVAILABLE，不虚构任务已接收。当前无业务入口，因此不伪报业务 HTTP 版本协商已验收；版本/未知字段负例在消费者层执行。

## A 的 KF2-011 所需数据库输入

- 索引身份必须包含 owner、knowledge_base、document、content_version、index_version、pipeline_profile、lease、递增 fencing；Chunk 在 index_version 内以序号/稳定 ID 唯一。
- 向量固定 1024 维，模型配置 ID 与索引版本绑定；模型别名可变，不冒充不可变后端锁。Chunk 保留原文、PDF页码或码点区间，禁止使用渲染后 Markdown 偏移。
- B 不应获用户、授权、文档/任务状态、活动索引发布的 DML；不自行创建迁移或执行通用任务领取。
- 写入建议受控 SQL 或 Java 网关，每批按任务/文档/候选版本/当前 lease/fencing 验证；禁止直接无约束 INSERT/UPDATE Chunk。选型由 A 的 ADR 发布，B 待该接口实现后接入 018；当前 Python 无数据库客户端、无写权限申请。
- 检索授权必须联合 owner、知识库、文档可见性及活动版本快照；删除/过期执行不可恢复可见性。DDL 验证、真实数据库竞态与索引发布仍由后续任务证据证明。

## 联调交接

服务默认 loopback:8000；共享密钥仅进程环境注入；完整启动及进程冒烟见服务 README。升级探针直接调用 A 的 AiInternalHealthClient，正确 draft.4/状态/request ID 必须通过，旧 draft.2 夹具必须被拒绝；另外验证该客户端 5 秒总期限。隔离候选运行记录与版本 SHA 见 Q 修复包，不把它当作完整业务链验收。所有 Q 状态保持待审，不代填批准结论。

## Q 复核后的明确升级

旧 draft.2/哈希为 e4efd05 的历史消费基线，现已替换；不接受回退、忽略版本或放宽哈希。当前启动会拒绝旧版本及任何不同字节的 Schema；消费者拒绝 draft.2、draft.3、额外字段及缺失 request_id 的健康报文。B 侧 health 样例在 tests/fixtures/internal-health-draft4.json，仅是消费测试输入，不另行发布 Schema。A 的原始 54 个共享样例也纳入完整回归。
