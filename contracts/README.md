# KnowFlow 公共契约（V0.2 重建基线；0.2.0 冻结）

**状态：FROZEN 0.2.0（2026-11-07）。** Schema SHA-256：`a206d3aa00f4a932b4ea0d871e73350d9000b51cffcdba90008ac0da5999b4b1`。本版本保留更新/重建、版本留存及 SSE 行为，新增模型配置身份、问答历史与幂等提交。工程消费已核对；负责人人工签收项见[消费清单](./consumer-draft10-checklist.md)。

`0.2.0-draft.5` 补齐上传/任务状态报文、精确源文件读取、Java 受控批量写入、取消代次、摘要算法、租约和原子发布语义。`0.2.0-draft.6` 放宽模型配置标识，允许供应商模型名包含 `/`；`draft.7` 固定索引派发运行配置；`draft.8` 定义内容更新及同内容重建；`draft.9` 增加流式回答和版本保留；`draft.10` 增加问答历史、幂等提交、来源 tombstone 和非秘密模型配置身份。0.2.0 于 2026-11-07 冻结，版本常量与 Schema 哈希已同步 Java、Python 与 Web 消费方，并补齐 `KNOWLEDGE_BASE_NOT_READY` 公开错误码。

此前的 `0.2.0-draft.4` 包含 KF2-012/013 的注册、登录、8 小时 opaque Bearer session、logout/current-user 与个人知识库结构；密码使用 PBKDF2 哈希，数据库只存 token SHA-256，知识库 owner 只由认证身份派生。注册冲突返回通用错误，但 409 状态仍可能暴露邮箱冲突，须由 M/Q 评估验证邮箱或限速方案。

A 单写共享 API、错误码、身份与资源范围、任务租约、索引版本发布、证据定位、删除失效及历史来源语义。B/M 可提交消费场景、字段提议和样例，不另行发布不兼容版本。

用户已批准以 V0.2 为重建的新基线，不再等待缺失的 V1.1 设计包。旧设计兼容性和旧 `KF-*` 映射仍是明确未验证项；本次批准不表示它们已映射完成。KF2-001 记录决策和残留风险；Q 审阅后方可关闭执行记录。

- [状态与权限 ADR](../docs/architecture/ADR-001-state-and-contract-draft.md)
- [索引写入边界提案](../docs/architecture/ADR-002-index-write-boundary-proposal.md)
- [认证与 owner 隔离 ADR](../docs/architecture/ADR-003-auth-and-owner-boundary.md)
- [API 与边界](./api-draft.md)
- [JSON Schema](./schemas/protocol.schema.json)：JSON Schema Draft 2020-12，引用局限于仓库。
- [OpenAPI 0.2.0](./openapi-draft10.json)：描述 Java/Python 现有路由；`DocumentApiIntegrationTest` 运行时覆盖 Document/Task 可选字段省略，以及问答历史和过期来源的 nullable 字段序列化。正常 TXT/PDF SSE 帧已由浏览器 E2E 校验；错误/取消等未覆盖帧和完整消费语义仍待核验、负责人签收。契约已于 2026-11-07 冻结为 `0.2.0`。
- [结构校验样例](./examples/protocol-cases.json)：覆盖正常、失败、失权、旧租约、删除、重复完成及拒绝负例。
- [批次摘要算法](./index_batch_hash.py)：与 Schema 中 `index-batch` 样例配对，固定摘要序列化规则。
- [A 线执行记录](../docs/tasks/agent-a.md)记录 V0.2 基线决策、KF2-001/004/006 进度和各提交 SHA。
- [JP-01 Java→Python 联调记录](../docs/tasks/java-python-integration.md)区分本地 stub 与真实双进程证据。
- [B 线运行基线](../docs/architecture/runtime-profile.md)：真实调用已验证 `BAAI/bge-m3` 的 1024 维和 `deepseek-flash` 中文输出；提供商别名和生产容量仍按原记录说明。

## 本地验证

从仓库根执行：

```bash
python -m pip install -r contracts/requirements-validation.txt
python contracts/validate.py
python -m unittest contracts.test_index_batch_hash -v
git diff --check
```

检查 Schema、结构与字段格式，并验证共同批次样例的摘要。**结构合法不代表调用已授权**：租约状态、完成幂等和删除竞态仍需 Java 数据库事务验证。`jsonschema` 默认可能缺少日期时间检查器；脚本要求 RFC 3339 检查器可用，否则直接失败。

## 约定

- JSON 使用 `snake_case`；客户端不能提交 `owner_id` 或内部可信范围。owner 由 Java 按认证主体生成。
- 时间使用带时区 RFC 3339；服务器时钟判定租约。UUID/标识符不承担授权职责。
- Java 对缺失或格式不安全的 `X-Request-ID` 生成 UUID；符合 Schema 标识符字符集且不超过 128 字符的请求 ID 可原样关联响应头、错误体和内部调用。它仅用于诊断，不参与身份或授权。
- 内部服务凭证与执行令牌分离；凭证认证服务，任务/租约/递增 fencing/数据库状态共同授权执行。凭证不得写入日志。
- JSON Schema 的 `writeOnly` 不会自动脱敏；实现应过滤凭证、全文、向量和提供商密钥。
- 外部非存在、非所有者、已删除资源统一返回无资源细节的 404。未认证返回 401；内部可信范围不匹配返回 403，不透传给浏览器。
- 历史引用绑定来源的内容/索引版本。已删除或清理后的来源只返回状态，不返回原文、定位或对象下载地址。
- 模型 ID、1024 维向量与 B 线冒烟证据是契约候选输入；文件/上下文上限是待生产样本和目标硬件验证的建议值。

## 冻结条件

1. A 按 V0.2 建立身份、资源范围、错误、上传/状态、任务租约/回调、索引发布、问答、SSE、引用、历史和删除语义。
2. B 确认模型/检索请求和证据 Schema；M 确认页面字段、错误与 SSE 消费方式；M 的 KF2-005 仓库约定已在远端交付。
3. A 运行结构校验并提交版本化契约和 OpenAPI。Q 按具体 base/target SHA 审查越权、过期/重复 Worker、删除/发布并发及历史引用。
4. 处理阻断项、获得 Q 的具体 SHA 结论，并完成必要的 A/B Schema 对照后，A 更新冻结状态。不得用模型冒烟或结构校验代替三方消费确认与安全审阅。

0.2.0 已冻结；本文件不表示负责人人工消费签收与真实模型质量门已完成。
