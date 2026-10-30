# JP-01 Java → Python 开发联调记录

状态：JP-I1 draft.4 `DEV_PASS_Q_REVIEW_PENDING`；JP2 draft.5 `B_CONSUMPTION_PENDING`。draft.4 的真实双进程 health 证据有效，但当前 A draft.5 与 B `origin/python` 的 draft.4 不匹配，不能据此宣称 draft.5 联调或全业务闭环通过。

## 固定的提交与契约

- A Java 当前交付 target：`ec5c71c9be5a8766540fc48e174f215c0cf388ac`；其中 Q 406 修复代码 target：`24a07fd85c70cab3c522118697824727bf9651fe`。
- B Python 当前 target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`（代码/测试 target `2623a6282b2695a8ef96e3553a849729efd42403`）。B 已合入 A 的 draft.4 契约提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，消费者版本为 `0.2.0-draft.4`，Schema SHA-256 为 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 联调候选：`225124fbae8041efd67ee5e6ca5bf89fdbbe8884` 是真实联调运行提交，集成树 SHA-1 `7ea07ebe5d9763ef2e2b2d03b83815dc414dd07b`；其父提交分别为 B 代码 target `2623a62` 和 A Java target `ec5c71c`。当前 B target `b598f1d` 只在该代码树上增加交付/证据记录。

## 干净候选验证

在干净临时 worktree 执行，Python 3.12.14，依赖由 `uv sync --project services/ai --frozen` 安装。B 的版本化报告确认运行前后 worktree 均干净；临时 index 对已核对字节与 HEAD 完全相同的 `services/api/mvnw.cmd` 行尾属性误报设置 assume-unchanged，不改文件内容。

- Python：`uv run --project services/ai --frozen pytest services/ai/tests -q`，65 passed。
- Schema：`python3 contracts/validate.py`，54 个结构样例通过。
- 离线回归：`python3 -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`，16 passed。
- 双进程：`uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py --maven-settings /tmp/knowflow-maven-settings.xml --java-target ec5c71c9be5a8766540fc48e174f215c0cf388ac --require-clean --output /tmp/knowflow-jp01-clean-smoke.json`，8 tests、0 failure、0 error，运行前后 clean 均为 true。报告：[java-python-smoke-draft4.json](java-python-smoke-draft4.json)，来自 B 当前 target 的 clean-run evidence，SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`。

真实双进程场景包括：Java 健康客户端调用真实 Python health 并接受 draft.4/status/request ID；同一客户端拒绝 draft.2 fixture；实际 5 秒 deadline；凭证缺失/错误 401；404/405 与 `Allow`；进程不可达；独立慢响应夹具的 WebClient 超时。日志没有测试密钥；没有数据库或模型调用。

## Q 406 修复

Q review base `ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434` → 代码修复 target `24a07fd85c70cab3c522118697824727bf9651fe`。`HttpMediaTypeNotAcceptableException` 专用处理器保留 Spring 的 406 与支持类型 `Accept` 响应头，统一返回 `INVALID_REQUEST` JSON 错误体。回归测试使用 `Accept: application/xml`，断言 406、`Accept: application/json`、request ID 和错误体。`mvnw verify` 22 项通过；契约 54 项和离线回归 16 项通过。记录见 [A 线执行记录](agent-a.md) 与 [A 线 Q 审阅包](agent-a-review-package.md)。

JP-I1 的开发双进程门槛已通过；draft.4 仍待 Q 审阅和 M 消费确认，正式冻结/任务 DONE 条件没有代填。下一项 KF2-014 仍被 M 的 KF2-009 阻断；KF2-015 仍依赖 KF2-014。

## JP2 draft.5 Java target 与 B 消费状态（2026-10-30）

- A Java 代码 target：`489b746f9bfa8188041f12d9135cf98fe6846611`；Schema `0.2.0-draft.5` SHA-256：`3953784ab2bd2005cded12baa11caa99b6e47a79c77d5a1078b158f59f5639ef`。
- B 的真实 `origin/python` target：`b598f1d62cc2367a4bfd49fccd3c31b521abff23`，应用代码 target `2623a6282b2695a8ef96e3553a849729efd42403`。其 `services/ai/src/knowflow_ai/protocol.py` 仍将版本固定为 draft.4 和 SHA-256 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`；`app.py` 只有 health 路由，README 明确索引/检索/生成未启用。B 尚未消费 draft.5，也没有索引与问答业务端点。
- draft.4 真实 health smoke 仍可复核：A `ec5c71c9be5a8766540fc48e174f215c0cf388ac`、B `b598f1d...`、运行 target `225124fbae8041efd67ee5e6ca5bf89fdbbe8884`；8/8 通过，报告 SHA-256 `a3cc1355d1b9979dfdfbbb91d9bb176c9d63fbece1f4ab8ee2661d95cc356960`。它验证的是旧 draft.4 Java 客户端和固定 B 版本，不能当作当前 draft.5 联调。
- 当前 Java `RealPythonHealthSmokeTest` 在设置 `KNOWFLOW_REAL_AI_BASE_URL` / `KNOWFLOW_REAL_AI_SECRET` 后会真实调用 draft.5；本轮未设置变量，测试作为 1 个 assumption skip 记录。不能把实际 B draft.4 直接伪装成 draft.5 服务。
- A 的真实 PostgreSQL/MinIO 集成测试已覆盖 Java 侧上传、队列/索引写入与原子发布、问答证据校验 fixture、来源/文件和删除/迟到 Worker。全链路 A/B、真实模型质量/费用、Worker 跨进程中断恢复待 B 合入 B06/B09/B10/B12 并固定消费本 Schema 后再运行。

因此 JP2 的 A01–A11 可按 Java target 复核，A12 标记为跨服务阻塞；Q 审阅及 B 对 draft.5 的消费 SHA/测试结果待填。
