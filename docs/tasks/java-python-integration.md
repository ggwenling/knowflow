# JP-01 Java → Python 开发联调记录

状态：`BLOCKED_CONTRACT_VERSION`。两端真实进程的传输、认证、请求关联、错误响应和 Java 健康客户端超时边界均已验证；当前 Python 分支仍固定消费 draft.2，Java 客户端严格要求 draft.4，因此不能把这次联调记为当前候选的兼容通过或 JP-I1 完成。

## 基线与契约

- 共同计划基线：`150cd847a5750143fb6eb2c74c762962381952fe`。
- Java 分支 target：`3b76131071b88365d14237769a7d3d5d111b873a`。`AiInternalHealthClient` 调用 `GET /internal/v1/health`，发送内部 Bearer 与 `X-Request-ID`，5 秒内结束，无自动重试，并校验响应版本、状态及 request ID。
- Python 分支 target：`e4efd054880c506c1e57a76f28f6710e3d761016`；服务已可启动。其 `protocol.py` 固定 `0.2.0-draft.2` 与 Schema SHA-256 `edc9ada0bb5de23ddf69f96c9172b3fc3719f4b3111d5d35718f2717efae8087`，拒绝未声明升级的 Schema。
- 当前 Java 契约候选：`0.2.0-draft.4`；Schema SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。A 没有把候选降回 draft.2。
- 联调候选：`integration/jp-01`，Java target 与 Python target 的合并提交 `4c6a00032c2ca186c8278301edcc941620465e93`；仅供本地开发验证，不合并 main。

## 实际运行及结果（2026-10-30）

在独立联调工作树 `/workspace/knowflow-integration-jp01` 使用 Python 3.12.14、`uv sync --project services/ai --frozen` 安装锁定依赖。按未修改的合并候选直接运行 Python 测试时，25 项通过、8 项在应用构造时因 `CONTRACT_HASH_MISMATCH` 失败：B 代码仍锁定 draft.2，而合并树提供 Java draft.4。临时只用 `origin/python` 自带的 draft.2 Schema 与 examples 做基线复核后，B 全量 Python 测试为 33 项通过；这些文件随后全部恢复，未提交 B 所有文件改动。

用 B 的真实启动脚本启动 Uvicorn 和 Java Spring Boot，并使用 B 分支固定的 draft.2 Schema/example 进行兼容基线测试。B 原有 5 项真实进程检查通过：两服务健康、Java WebClient 到 Python 的认证与 request ID、缺失/错误凭证 401、已认证未知路由 404、错误方法 405 与 `Allow`、不可达端口，以及实际 WebClient 30 秒响应超时。测试密钥未出现在进程日志；未连接数据库或外部模型。

另外在一次性测试夹具中增加两项断言后，7 项全部通过：Java `AiInternalHealthClient` 收到真实 Python draft.2 health 后按设计拒绝不匹配的 draft.4 版本；同一 Java 客户端面对 36 秒慢响应在约 5 秒边界终止。新增用例及测试脚本改动均已恢复，没有提交到 B 文件范围。该拒绝是预期契约保护行为，证明当前版本组合不兼容。

## JP-I1 结论与解除条件

开发级真实 HTTP 传输已通过，但基于当前分支 target 的 Java→Python health 兼容尚未通过：B 的服务响应 `0.2.0-draft.2`，Java 客户端要求 `0.2.0-draft.4`。不能用 B 侧直连 WebClient 测试或本地 stub 替代该失败，也不能通过放宽 Java 版本检查或把 A 契约静默降级来掩盖差异。

解除条件：B 明确消费 draft.4 对应提交和 Schema 哈希，更新 Python 版本常量、精确哈希、共享样例/测试与消费记录；随后在未覆盖契约文件的干净集成候选上重跑 Python 全量测试及真实双进程探针，并让 Java `AiInternalHealthClient` 对正确版本的实际响应通过。Q 与 M 确认仍是正式冻结和 DONE 的独立条件。

KF2-011/012/013 的开发验证记录见 [A 线执行记录](agent-a.md)。当前下一项 Java 主任务 KF2-014 仍受 M 的 KF2-009 阻断；`origin/python@e4efd054` 中的 `infra/README.md` 仍声明没有 Compose、Dockerfile 或 CI 配置。JP-I1 契约升级和 KF2-009 交付前，不启动需要对象存储和上传基础设施的任务。
