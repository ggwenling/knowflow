# JP-01 Java → Python 开发联调记录

状态：`DEV_PASS_Q_REVIEW_PENDING`。Java 与 Python 已在干净的双进程候选上共同消费 draft.4，真实 Java `AiInternalHealthClient` 接受正确 health 响应并拒绝旧版本；契约仍是候选，Q/M 的正式审阅条件未关闭。

## 固定的提交与契约

- A Java 当前交付 target：`ec5c71c9be5a8766540fc48e174f215c0cf388ac`；其中 Q 406 修复代码 target：`24a07fd85c70cab3c522118697824727bf9651fe`。
- B Python target：`2623a6282b2695a8ef96e3553a849729efd42403`。B 已合入 A 的 draft.4 契约提交 `895a1ba4655d9e875730d5bbeb65e570853c8d01`，消费者版本为 `0.2.0-draft.4`，Schema SHA-256 为 `ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41`。
- 联调候选：`integration/jp01-draft4-final@343ce4fdc2b6df72f023c9346f59a927374cdaf8`，集成树 SHA-1 `7ea07ebe5d9763ef2e2b2d03b83815dc414dd07b`；其中包含上述两个精确 target。此分支仅供开发验证，不合并 main。

## 干净候选验证

在独立 worktree `/workspace/knowflow-jp01-clean` 执行，Python 3.12.14，依赖由 `uv sync --project services/ai --frozen` 安装。工作树在运行前后均干净；为抑制已核对字节与 HEAD 完全相同的 `services/api/mvnw.cmd` 行尾属性误报，仅在临时 worktree 的 index 设置 assume-unchanged，不改文件内容。

- Python：`uv run --project services/ai --frozen pytest services/ai/tests -q`，65 passed。
- Schema：`python3 contracts/validate.py`，54 个结构样例通过。
- 离线回归：`python3 -m unittest discover -s evaluation/smoke -p 'test_*.py' -q`，16 passed。
- 双进程：`uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py --maven-settings /tmp/knowflow-maven-settings.xml --java-target ec5c71c9be5a8766540fc48e174f215c0cf388ac --require-clean --output /tmp/knowflow-jp01-clean-smoke.json`，8 tests、0 failure、0 error，运行前后 clean 均为 true。报告：[java-python-smoke-draft4.json](java-python-smoke-draft4.json)，SHA-256 `327c0b0b18d4be2a91e485828df41584fa6a5e0b1d1482023a82f3bb0d1a8307`。

真实双进程场景包括：Java 健康客户端调用真实 Python health 并接受 draft.4/status/request ID；同一客户端拒绝 draft.2 fixture；实际 5 秒 deadline；凭证缺失/错误 401；404/405 与 `Allow`；进程不可达；独立慢响应夹具的 WebClient 超时。日志没有测试密钥；没有数据库或模型调用。

## Q 406 修复

Q review base `ffd4d608c1c9b1d5799caef92a21e4fd9ebd2434` → 代码修复 target `24a07fd85c70cab3c522118697824727bf9651fe`。`HttpMediaTypeNotAcceptableException` 专用处理器保留 Spring 的 406 与支持类型 `Accept` 响应头，统一返回 `INVALID_REQUEST` JSON 错误体。回归测试使用 `Accept: application/xml`，断言 406、`Accept: application/json`、request ID 和错误体。`mvnw verify` 22 项通过；契约 54 项和离线回归 16 项通过。记录见 [A 线执行记录](agent-a.md) 与 [A 线 Q 审阅包](agent-a-review-package.md)。

JP-I1 的开发双进程门槛已通过；draft.4 仍待 Q 审阅和 M 消费确认，正式冻结/任务 DONE 条件没有代填。下一项 KF2-014 仍被 M 的 KF2-009 阻断；KF2-015 仍依赖 KF2-014。
