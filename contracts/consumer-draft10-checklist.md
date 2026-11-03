# draft.10 三端消费确认

状态：IN_REVIEW；本文是待签收清单，不代表契约已冻结。当前共享 Schema SHA-256：`20121f69098c9fb0c8de59a813a398782070e9f6b9aa5a59e80d30568524883f`。验收时填写目标提交、验证结果及执行者；修复改变目标后重新复核受影响项目。

## 2026-11-03 本地证据（尚未签收）

- 验证代码基线：`local@bb25dc194fc1aeb3b0c21b7f57d364988308c8ea`；随后 `9c9b4a0` 增加备份证据，未改动代码。Schema 指纹如上。Web typecheck/lint/43 项单测通过，Docker production Web 镜像与全栈 Chromium E2E 1/1 通过；Java Maven/Testcontainers 83 项（1 skip），Python 324 项，Schema 85 项、OpenAPI 4 项通过。
- 浏览器 E2E 覆盖注册、上传至 READY、draft.10 SSE 问答、来源查看、owner 隔离、删除、PDF 和移动视口；这属于本地执行证据，不等于 M/项目负责人已签收。
- Java Testcontainers 新增 3 项实际 MVC wire 断言：Document 的空活动索引 ID 与 QUEUED Task 的空 failure code 确实不输出该键；processing 问答历史及过期来源的 nullable 字段显式输出 JSON `null`。OpenAPI 单测 4 项、Schema 85 structural cases 均通过。覆盖范围仅限这些已命名字段与端点。
- 这些检查未替代 Q 对当前提交的独立代码/契约审阅，也未逐项证明下方所有授权、租约、超时和数据保留断言。因此所有 Q/M 复核框继续保持未勾选，直至审核者在最终目标 SHA 上记录结论、阻断项和日期。
- 远端 CI 尚待推送本轮提交后核实。版本化 OpenAPI 候选的测试通过不等于 Q/M 已冻结契约。

## Java / API

- [ ] 记录目标 SHA、schema 指纹和完整 Maven/Testcontainers 结果；验证版本不匹配、身份、owner、内部凭证与租约/fencing 边界。
- [ ] 验证索引批次幂等、过期与重复 worker、删除/发布竞态、候选失败清理及活动索引保留。
- [ ] 验证同步和 SSE 问答、幂等提交、deadline/取消、profile、来源及历史记录持久化；删除或保留期后的来源不泄露原文。

## Python / AI

- [ ] 记录目标 SHA、固定 schema 指纹及完整测试结果；拒绝版本、结构和 runtime profile 不匹配。
- [ ] 验证来源范围、只读检索、向量维度、分批写入、重试及取消后不迟到写入；外部模型错误不会暴露凭证或正文。
- [ ] 验证无答案、同步/SSE 答案和来源均符合草案，Java 来源映射及失效语义跨服务一致。

## M / 前端与项目负责人

- [ ] 在目标 SHA 验证注册登录、隔离访问、上传、READY、更新/重建、任务恢复和文档分页。
- [ ] 验证流式问答、取消、历史分页、切库/刷新竞态、文本及 PDF 原文、来源失效、移动导航和键盘操作。
- [ ] 核对数据出站及错误提示，记录浏览器、环境、证据、执行者及日期。项目负责人完成签收。

## Q / 结论

- [ ] 审阅具体 base/target SHA、schema 指纹、变更和测试证据；记录发现、严重程度及复验结果。
- [ ] 阻断项关闭，版本化 OpenAPI 和三端确认齐全后，Q 给出明确结论。实测不足、远端 CI 未知或真实模型质量未评测时各自保持未完成。
