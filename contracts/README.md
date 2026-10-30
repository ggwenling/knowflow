# KnowFlow 公共契约（V0.2 重建基线；后端开发候选）

**状态：DRAFT 0.2.0-draft.6，未冻结、未发布；不能用于生产兼容性验收。** 当前 Schema SHA-256：`d64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1`。本机 `local` 集成分支已同步 Java/Python 消费端；全量 Java 与真实双进程验证待完成，Q 审阅和 M 消费确认未完成。

`0.2.0-draft.5` 补齐上传/任务状态报文、精确源文件读取、Java 受控批量写入、取消代次、摘要算法、租约和原子发布语义。`0.2.0-draft.6` 保留这些报文语义，只将 `embedding_model_profile_id` 改为独立标识规则，允许 `BAAI/bge-m3` 这样的供应商模型名包含 `/`；draft.5 Schema 会错误拒绝该真实配置，导致成功 completion 无法通过共享校验。当前 Java、Python 和结构样例固定为 draft.6；仍须由 Q 审阅、M 确认公开页面消费，并满足 KF2-004 正式冻结条件。

此前的 `0.2.0-draft.4` 包含 KF2-012/013 的注册、登录、8 小时 opaque Bearer session、logout/current-user 与个人知识库结构；密码使用 PBKDF2 哈希，数据库只存 token SHA-256，知识库 owner 只由认证身份派生。注册冲突返回通用错误，但 409 状态仍可能暴露邮箱冲突，须由 M/Q 评估验证邮箱或限速方案。

A 单写共享 API、错误码、身份与资源范围、任务租约、索引版本发布、证据定位、删除失效及历史来源语义。B/M 可提交消费场景、字段提议和样例，不另行发布不兼容版本。

用户已批准以 V0.2 为重建的新基线，不再等待缺失的 V1.1 设计包。旧设计兼容性和旧 `KF-*` 映射仍是明确未验证项；本次批准不表示它们已映射完成。KF2-001 记录决策和残留风险；Q 审阅后方可关闭执行记录。

- [状态与权限 ADR](../docs/architecture/ADR-001-state-and-contract-draft.md)
- [索引写入边界提案](../docs/architecture/ADR-002-index-write-boundary-proposal.md)
- [认证与 owner 隔离 ADR](../docs/architecture/ADR-003-auth-and-owner-boundary.md)
- [候选 API 与边界](./api-draft.md)
- [JSON Schema](./schemas/protocol.schema.json)：JSON Schema Draft 2020-12，引用局限于仓库。
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

本次合并只把契约从占位升级为审阅候选；本文件不表示 B 的待审任务已批准，也不表示 KF2-004 已冻结。
