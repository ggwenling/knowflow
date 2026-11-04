**Verdict: CHANGES_REQUESTED**

复审对象：`75baab500be4e60ee5370f443fea89ec6e12d818`（`fix(ai): stop URL boundary protection at closing quotes`），父提交 `5fdc29f`；检查时 HEAD 正是目标提交。对照 `docs/reviews/2026-11-05-sol-citation-prune-p1-rereview.md` 的新 P1，检查本次 diff、剪枝调用链与普通/流式合成输出。未读取盲测题面，仅新增本复审文档，不改实现或测试，不 push。

**上一轮引号边界 P1 的六种输入已修复；新 P0：无，新 P1：1 项。**

1. **[P1] 缩短第一个引号 URL 的保护跨度后，没有重新扫描后续 URL，导致第二个 URL 被剪成参数残片。**

   位置：`services/ai/src/knowflow_ai/citation_verify.py:53-55`，与 `:45` 的 `_URL.finditer(text)` 扫描共同触发。

   `_URL` 的原始正则匹配可以跨过闭合引号、中文连接词及第二个 URL，一直匹配到引用 marker。本次只把局部 `end` 缩到第一个闭合引号，却没有改变正则迭代器已经消费的范围。因此，第二个 URL 不会获得独立匹配，其域名点号、查询问号或路径分号失去保护。剪枝随后删除没有 marker 的前半部分，仅保留带 marker 的参数尾部。

   这是本次新增回归：同一输入在父提交中完整保留，在目标提交中损坏；不涉及裸 URL 后 ASCII 标点的歧义，也不依赖堆叠引用的严格匹配。

   最小合成复现（仓库根目录）：

   ```bash
   PYTHONPATH=services/ai/src services/ai/.venv/bin/python - <<'PY'
   from knowflow_ai.citation_verify import prune_ungrounded_claims
   claim = '入口"https://docs.example.test/start"和"https://docs.example.test/search?q=cache"'
   print(prune_ungrounded_claims(
       claim + '[src-evidence-1]。',
       {'src-evidence-1': claim + '。'}))
   PY
   ```

   当前实际结果：

   ```python
   {'pruned_answer': 'q=cache"[src-evidence-1]。',
    'kept_source_ids': ['src-evidence-1'], 'ok': True}
   ```

   期望完整保留 `入口"https://docs.example.test/start"和"https://docs.example.test/search?q=cache"[src-evidence-1]。`，因为来源原文完整支持该断言。进程内只读加载父提交 verifier，确认其返回的正是完整答案、相同来源和 `ok=True`。

   已通过公开入口 `AnswerService.answer`（合成模型及检索器）和 `AnswerService.stream`（MockTransport，逐字符 provider 内容片段及每 7 字节 HTTP 分片）复现：两者最终 answer 均为 `q=cache"[src-evidence-1]。`，`has_answer=True`，流式正常以 `completed` 结束。把第二个 URL 换成 `https://docs.example.test/items;view=all`，则两者均只剩 `view=all"[src-evidence-1]。`；两个 URL 改用反引号包围也同样失败，共确认四种变体。

   另测本轮边界场景的扩展：`参考 "https://docs.example.test/start";请访问"https://docs.example.test/search?q=cache"[src-evidence-1][src-evidence-2]。`，其中来源 1 完整支持第二句、来源 2 无关，也只输出 `q=cache"[src-evidence-1]。`。外部分号虽然可以分句，后续 URL 的内部标点仍未受到保护。

   修复要求：在明确的闭合界定符处结束当前 URL 的保护时，继续识别其后的 URL，避免原始贪婪匹配吞掉后续候选。补充两个引号 URL 之间无空白、同一断言末尾引用的普通/流式回归，覆盖第二个 URL 的 `?q=` 与路径 `;`，直接断言完整答案和 sources；同时保留本次六种外部边界回归。

**逐项核查**

| 检查项 | 结论与证据 |
| --- | --- |
| 双引号/反引号 URL 后紧接 ASCII `;!?` | 上一轮六种输入均通过：URL 外分隔符不再被保护，无引用前言被删除，保留 `缓存默认关闭[src-evidence-1]。`，普通/流式均为 `has_answer=True`，来源仅剩来源 1。 |
| 原 `?q=` / 路径分号保护 | 原单 URL 输入仍通过。额外验证裸 URL、双引号 URL、反引号 URL，分别含查询参数、路径分号、混合 `a!b?x=1;y=2`，共 9 例，普通及流式完整答案均保留。连续文本中的第二个 URL 存在上述新 P1。 |
| 本次普通测试是否断言完整 answer | 是。`test_answering.py:960-975` 参数化六种组合，断言完整剪枝结果、`response['answer']` 精确值、`has_answer` 和来源；普通测试使用 `_response_from_generated`，本次额外探针验证了公开 `answer` 入口。 |
| 本次流式测试是否断言完整 answer | 是。`test_streaming.py:125-149` 覆盖相同六种组合，断言全部 delta 拼接精确等于期望答案，并检查 `sources`、`has_answer` 与 `completed`。 |
| 其他新 P0/P1 | 除上述新 P1 外，本次所审 diff 与调用链未发现其他新 P0/P1。普通和流式继续共用 `_response_from_generated`，未新增模型/检索调用或协议字段。 |

**实际验证**

- `services/ai/.venv/bin/python -m pytest services/ai/tests/test_answering.py services/ai/tests/test_streaming.py -q`：**99 passed**，3 条 warning（2 条数据库模拟线程 `ConnectionResetError`，1 条 Starlette/httpx 弃用提示），无失败。
- `services/ai/.venv/bin/python -m pytest services/ai -k citation -q`：**52 passed, 399 deselected**，1 条相同弃用提示。
- 额外合成外部边界矩阵：实现支持的 13 对界定符 × ASCII `;!?` × 4 种 URL（普通路径、查询参数、路径分号、混合内部标点），**156 例**在公开普通及流式入口均得到完整期望答案，来源及结束事件正确。
- 额外 **9 例**单 URL 内部标点保护通过；**4 例**连续双 URL 回归均完成父提交 verifier 对照及当前普通/流式复现，另验证上述分号分句扩展案例。探针仅在进程内运行，未修改实现或测试，未调用外部模型或真实数据库。

本次关闭了上一轮的具体阻塞案例，但新增了可见的 URL 内容丢失回归，故仍需修复后再审。

`SOL_REVIEW_DONE verdict=CHANGES_REQUESTED`
