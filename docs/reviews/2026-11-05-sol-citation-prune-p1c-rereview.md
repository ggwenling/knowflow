**Verdict: APPROVE**

复审对象：`f00a17db144f7e579acce35d73283af91e8d7964`（`fix(ai): rescan quoted URLs after closing-delimiter truncate`）；对照 [P1b 复审记录](2026-11-05-sol-citation-prune-p1b-rereview.md)。检查时 HEAD 为目标提交，AI 实现及测试与该提交一致。

**P1b 的多引号 URL 重扫 P1 已修复；本轮未发现新 P0/P1。**

`services/ai/src/knowflow_ai/citation_verify.py:45-70` 将 `_URL.finditer` 改为带搜索起点的循环。每次保存原始匹配结束位置，完成闭合界定符、全角终止符及尾部标点截断后，从缩短后的 `end` 继续搜索。这样即使原始贪婪匹配跨过第一个闭合引号，第二个 URL 仍会独立获得内部标点保护。URL 至少包含协议前缀，截断后的结束位置仍大于当前匹配起点，搜索会持续前进。界定符外的分句符仍在保护跨度之外。

| 检查项 | 复审结果 |
| --- | --- |
| 双引号 / 反引号双 URL，第二个含 `?q=` / 路径分号 | 四种 P1b 阻塞输入均通过新增普通及流式回归，完整保留两个 URL、连接文字与引用 marker，不再只剩查询或路径参数尾部。 |
| 普通入口完整 answer | `test_answering.py:978-1004` 调用公开 `AnswerService.answer`，比较完整剪枝字典、精确 `response['answer']`、`has_answer=True` 和来源 ID，四种参数组合全部通过。 |
| 流式入口完整 answer | `test_streaming.py:152-176` 比较全部 delta 拼接后的完整答案，并检查来源、`has_answer=True` 和最终 `completed`，相同四种组合全部通过。 |
| 既有引号外 ASCII `;!?` 边界 | 双引号 / 反引号 × 三种分句符的普通及流式用例继续通过：删除无引用前言，保留 `缓存默认关闭[src-evidence-1]。`，移除不支持的来源 2。 |
| 既有 URL 内部标点、邮箱及其他引用边界 | 单 URL 的 `?q=` / 路径分号及 URL / 邮箱点号用例通过；citation 回归通过，覆盖原有剪枝、堆叠 marker、数字及否定等策略。 |
| 调用链及其他新 P0/P1 | 未发现。普通与流式继续共用 `_response_from_generated`；流式在完整生成并完成剪枝后输出 answer。此次修改未改变来源构造、marker 策略或流式协议。 |

本轮实际复跑（仓库根目录）：

- `services/ai/.venv/bin/python -m pytest services/ai/tests/test_answering.py services/ai/tests/test_streaming.py -q`：**107 passed**，3 条 warning（2 条数据库模拟线程 `ConnectionResetError`，1 条 Starlette/httpx 弃用提示），无失败。
- `services/ai/.venv/bin/python -m pytest services/ai -k citation -q`：**52 passed, 407 deselected**，1 条相同弃用提示。新增八个双 URL 普通/流式参数用例名称不含 `citation`，由上一条文件级测试覆盖。

验证已通过，无需继续修改。复审范围为本次 diff、相关调用链及上述仓库回归；未读取盲测题面，未调用外部模型。仅写本复审报告，不改实现或测试，不 push。

SOL_REVIEW_DONE verdict=APPROVE
