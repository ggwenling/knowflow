# Q 修复验收：Java / Python

日期：2026-10-30 UTC。**上轮五项缺陷均已修复并通过定向验收；当前 main 的双服务集成仍为 BLOCKED。** 本结论只关闭列明的五项缺陷，不代表 A12 或完整产品交付验收通过。

## 验收目标

- Java：`26e1acac2c1faa2dd1ed972ace9e81c937c82158`；实现修复 `806190b07e71d028dcb3327fcd663a1ff625d01b`。
- Python：`b4639408fe73dadc2ac93764249ab43a54c691bc`。
- 已合入的 main：`0c3024a2b531e4a335440bbd6502839738194ab5`。

已重新查询远端确认三个 SHA。验收使用独立工作树；main 中 `services/api`、`contracts` 与上述 Java 目标一致，`services/ai` 与上述 Python 目标一致。Java 测试直接运行于 main；Python 分支测试运行于其自身 draft.4 工作树，不能混写成 main 的 Python 测试通过。

## 五项修复结论

| 原缺陷 | 状态 | 独立核对与验证 |
| --- | --- | --- |
| Q-B03-01：Provider 元数据违反内部结果 Schema | 已修复 | 显式白名单映射 index/embedding；带 object 和额外元数据的正常响应通过完整 EmbeddingResult 校验。 |
| Q-B03-02：注入客户端绕过超时及禁重定向 | 已修复 | 注入 timeout=60、follow_redirects=True 后，实际四类 HTTPX timeout 均为 settings 的 0.1；307 被拒绝，仅向原主机发一跳；调用方客户端未被关闭。 |
| Q-JP2-J01：来源 ID 替换破坏正文及其他引用 | 已修复 | 替换限定完整方括号标记；真实数据库/存储的问答用例验证普通正文中的 s1 保持、s1/s10 两个标记分别正确替换。 |
| Q-JP2-J02：存储正文读取超时无效、等待期间持锁 | 已修复 | 有界 BodySubscriber 和完整响应截止时间；读取移至事务外，读取后重新校验可见性/租约。独立原场景停滞正文探针在 10,654 ms 超时；并发回归验证等待存储期间心跳和删除可完成，删除后的文件内容不返回。 |
| Q-JP2-J03：MinIO 初始化阶段提前放行测试 | 已修复 | 两个 fixture 均等待最终启动日志及 ready；未经临时补丁的 Java 全量验证通过，原两项失败用例也通过。 |

## Q-INT-01 · P1：main 默认启动 Python 失败

目标：`main@0c3024a`。位置：`services/ai/src/knowflow_ai/protocol.py:10–11,31–32`；共享 Schema 为 `contracts/schemas/protocol.schema.json`。

Python 消费者固定 `0.2.0-draft.4` 与 SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`，而 main 合入的共享契约为 draft.5，SHA-256 为 `3953784ab2bd2005cded12baa11caa99b6e47a79c77d5a1078b158f59f5639ef`。Python 的默认 Settings 路径指向仓库中的该共享 Schema，`create_app` 构造 ContractConsumer 时立即失败。

独立复现：在 main 的源码路径中调用 `create_app(Settings(internal_secret=<有效合成测试值>))`，不覆盖默认 contract_path，得到 **ConfigurationError: CONTRACT_HASH_MISMATCH**。未使用真实凭证，也未调用模型。此时连 Python 健康路由也没有完成应用构建；因此不能用分支上的 100 项通过证明 main 可启动。

这不是原五项修复重新失败，而是当前合并结果尚未完成 A12 契约对齐的实际运行阻断。需要 B 按 A 的 draft.5 契约完成消费者和相关消息适配，保持哈希完整性检查，并在 main 上验证 Python 启动及双进程健康/契约交互；不能只跳过哈希校验或仅改版本常量来获得表面通过。

## 本次执行

- Java main：`./mvnw -B -ntp -s /tmp/knowflow-q-maven-settings.xml verify`，**49 项，48 通过，1 项可选真实 Python health smoke 跳过，零失败/错误；打包成功**。
- Python branch：`uv run --project services/ai --frozen pytest services/ai/tests -q`，**100 通过**；另有一条 Starlette 弃用提示。
- 独立 B03 验收脚本：[recheck_b03_adapter.py](recheck_b03_adapter.py)，全部通过，所有 Provider 请求由 MockTransport 截获。
- 独立 S3 停滞正文验收：[QS3ReadDeadlineAcceptance.java](QS3ReadDeadlineAcceptance.java)，通过，使用默认 10 秒截止时间。
- main 70 个契约结构样例、5 个批次摘要测试通过；Python branch 54 个契约样例、16 项模型离线回归通过。
- 两个修复区间 `git diff --check` 通过；两个验收工作树审阅前后均无已跟踪文件改动。

证据：[2026-10-30-Q-fix-acceptance.json](2026-10-30-Q-fix-acceptance.json)。日志：`/workspace/scratch/q-accept-java.log`、`/workspace/scratch/q-accept-python.log`；main 启动复现结果：`/workspace/scratch/q-accept-main-python-startup.json`。

本轮只新增/更新 `docs/reviews/` 下的审阅材料，没有修改业务实现、提交或推送分支。当前主工作区仍有未跟踪的审阅报告和复现程序，没有已跟踪业务文件改动；本轮没有代替作者关闭 A12。

最终工作区盘点：主工作区有 24 个未跟踪的审阅文件（含本轮新增四份材料）。另一个历史审阅工作树 `/workspace/scratch/knowflow-q-python-r3` 保留两项已跟踪证据 JSON 改动：`services/ai/docs/evidence/parser-smoke.json` 和 `process-smoke.json`；它们不是业务源码改动，本轮未覆盖或清理。其余工作树干净。
