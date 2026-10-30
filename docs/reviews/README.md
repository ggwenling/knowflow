# Q 审阅与验收记录

审阅结论绑定具体提交。历史报告保留当轮发现和验证范围，修复状态以后续验收为准。

## 当前验收

- [Java / Python 修复验收](2026-10-30-Q-fix-acceptance.md)：Java `26e1aca`、Python `b463940` 的五项缺陷均已修复；`main@0c3024a` 的 Python 默认启动仍因 draft.4 / draft.5 契约哈希不一致而阻断。
- [验收证据 JSON](2026-10-30-Q-fix-acceptance.json)：测试计数、提交 SHA、独立探针结果和工作树检查。

## 本轮原始审阅

- [Java A01–A11 / draft.5](2026-10-30-Q-java-jp2.md) 与[证据](2026-10-30-Q-evidence-java-jp2.json)。
- [Python B02 / B03](2026-10-30-Q-python-b02-b03.md) 与[证据](2026-10-30-Q-evidence-b02-b03.json)。
- [Java 提交获取阻断记录](2026-10-30-Q-java-unpublished.md)：历史状态，后续已取得提交并完成审阅。

## 复现材料

- [B03 原问题复现](repro_b03_adapter.py)和[修复验收](recheck_b03_adapter.py)。
- [S3 原停滞正文探针](QS3ReadDeadlineProbe.java)和[修复验收](QS3ReadDeadlineAcceptance.java)。
- [Java 问答与 MinIO 集成探针补丁](2026-10-30-Q-java-jp2-probes.patch)。

这些程序供独立审阅工作树使用，不属于业务实现。HTTP Provider 复现均使用 MockTransport；存储超时复现使用本地 HTTP server。执行环境的 `/workspace`、`/tmp` 路径是当轮证据位置，其他环境需要替换为自己的目录；原始运行日志未作为业务文件提交。

## 历史轮次

- [初始记录](initial.md)、[首轮](2026-10-30-Q-review.md)、[第二轮](2026-10-30-Q-review-r2.md)、[第三轮](2026-10-30-Q-review-r3.md)、[第四轮与 main 集成记录](2026-10-30-Q-review-r4.md)。
- [KF2-002 / 003 / 005](KF2-002-003-005-review.md)。
