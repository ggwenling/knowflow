**Verdict: CHANGES_REQUESTED**

审阅对象：`d077e6a9f66858418cb6679f020bf1209074f56a`，基线 `aea779a`。独立检查实现 diff、相关调用链及测试，未参考其他审阅结论，未读取盲测题面。需求依据为本次审阅 brief 和 `/workspace/knowflow-briefs/2026-11-05-luna-citation-prune.md`。本次仅新增审阅文档，不修改实现或测试，不 push。

**P0：无。P1：1 项。**

1. **[P1] 剪枝会删除带查询参数的受支持 URL，只留下参数并返回有答案。**

   位置：`services/ai/src/knowflow_ai/citation_verify.py:208-209`，与 `:243-248` 的答案重组共同触发；入口为 `answering.py:510-513`。

   `_protected_periods` / `_is_boundary` 仅保护 URL 内的点号，URL 中合法的 `?`、`;`、`!` 仍会被当作 claim 边界。旧版本虽也这样切分，但验证通过后返回原始 answer；本次开始丢弃无 marker 的片段并据此重组，因而将 URL 的协议、域名和路径一并删除。这是本次引入的可见答案回归，完整来源支持、单 marker 的普通输出也会受影响。

   最小合成复现（仓库根目录）：

   ```bash
   PYTHONPATH=services/ai/src services/ai/.venv/bin/python - <<'PY'
   from knowflow_ai.citation_verify import prune_ungrounded_claims
   print(prune_ungrounded_claims(
       "请访问 https://docs.example.test/search?q=cache[src-evidence-1]。",
       {"src-evidence-1": "请访问 https://docs.example.test/search?q=cache。"}))
   PY
   ```

   实际结果：

   ```python
   {'pruned_answer': 'q=cache[src-evidence-1]。',
    'kept_source_ids': ['src-evidence-1'], 'ok': True}
   ```

   期望保留完整原答案。相同输入已通过 `_response_from_generated` 和 `AnswerService.stream` 分别复现：两者都输出 `q=cache[src-evidence-1]。`，且 `has_answer=True`，流式正常以 `completed` 结束。`https://docs.example.test/items;view=all` 同样退化为 `view=all`。通过只读加载基线 verifier 确认，基线对上述输入返回 True，随后服务返回完整原答案。

   修复要求：将 URL 内部合法标点纳入边界保护，同时仍识别 URL 外的句末标点，避免把 URL 前缀当作独立无引用断言删除。补充带查询参数、路径分号的合成测试，直接断言最终 answer 保留完整 URL；至少覆盖普通和流式最终输出。现有 `test_answering.py:926-938` 仅覆盖 URL/邮箱点号，且未断言 response 的完整 answer，不能捕获此回归。

**逐项核查**

| 检查项 | 结论与依据 |
| --- | --- |
| 验证失败后剪除断言/引用 | 符合主路径要求：堆叠 marker 逐个筛选，无支持 marker 的 claim 整段丢弃；其他可保留 claim 继续输出。已有混合答案测试。 |
| 仅无可保留内容时拒答 | 在 brief 指定的判定策略下符合：`ok` 由最终 marker 非空决定；`answering.py:523-524` 仅在剪枝失败时标准拒答。原模型 `has_answer=False` 和结构/引用非法输入仍走原处理。P1 表明当前可能把 URL 残片误认作可保留答案。 |
| 堆叠 marker 独立完整覆盖 | 符合指定严格子串策略：每个来源分别匹配完整归一化 claim，不合并来源补齐断言。一个来源覆盖则仅留该 marker，全部不覆盖则丢 claim。 |
| 核心问题拒答 prompt | 保留，`answering.py:144-145` 未变化；原四段关键文案断言仍通过。剪后内容是否仍回答核心问题没有新增语义验证，本次 brief 只要求保留 prompt。 |
| sources 与 answer marker 集合 | 最终 IDs 从 `pruned_answer` 用同一 marker 正则提取、按首次出现顺序去重，服务按这些 IDs 构造 sources；所检查正常/剪枝/拒答路径集合一致。混合答案测试显式检查集合相等。 |
| URL、单 marker 回归 | URL 点号和单 marker 非空来源策略保留，现有相关测试通过；带查询参数或路径分号的 URL 存在上述 P1。单 marker 不做语义硬拒答是 brief 明确允许的既有策略，不作为新缺陷。 |
| brief 合成反例覆盖 | 已覆盖两来源仅一支持、全部不支持且无剩余、坏 claim 丢弃但好 claim 保留、正常单 marker、URL/邮箱点号、全无 grounding。缺少 URL 查询参数/分号的完整输出断言，以及流式剪枝专项用例。 |

流式路径已经缓冲生成结果，并于 `streaming.py:339-342` 调用同一个 `_response_from_generated` 后才发送 delta/sources，没有另走旧布尔拒答路径。没有新增二次模型调用或检索，也未改对外协议字段。

**实际验证**

- `services/ai/.venv/bin/python -m pytest services/ai/tests/test_answering.py services/ai/tests/test_streaming.py -q`：**78 passed**。有 2 条测试数据库模拟线程的 `ConnectionResetError` warning 和 1 条 Starlette/httpx 弃用 warning，未造成失败。
- `services/ai/.venv/bin/python -m pytest services/ai -k citation -q`：**41 passed, 389 deselected**，1 条相同弃用 warning。
- 额外运行原创合成只读探针，对照基线 verifier，并验证普通/流式 URL 截断。所有探针在进程内运行，未修改测试文件、未调用外部模型或真实数据库。

现有测试通过不能消除上述可复现的 P1；修复 URL 边界和补足输出回归测试后再审。

`SOL_REVIEW_DONE verdict=CHANGES_REQUESTED`
