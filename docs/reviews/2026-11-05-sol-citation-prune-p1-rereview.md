**Verdict: CHANGES_REQUESTED**

复审对象：`6ff107430a82684746063c5b02ae07445da467c5`（`fix(ai): preserve punctuation inside citation URLs`），相对 `d077e6a`；检查时 HEAD 为 `502bc9fe40440aa4bd42b0bf8dfcc5ffaaa940c6`，已确认修复提交是其祖先，之后仅新增原审阅文档。依据原审阅 `docs/reviews/2026-11-05-sol-citation-prune.md`、本次 brief 及原剪枝 brief 检查实现、调用链和合成测试。未读取盲测题面，仅新增本复审文档，不改实现或测试，不 push。

**原 P1 的两个复现已修复；新 P0：无，新 P1：1 项。**

1. **[P1] 引号或反引号包围的 URL 会吞掉 URL 外的分号，把可保留断言合并后整答拒答。**

   位置：`services/ai/src/knowflow_ai/citation_verify.py:44-53`，其中 `:52-53` 将 URL 匹配跨度内所有边界字符都加入保护集；与 `:14` 的宽松 `_URL` 匹配共同触发。

   `_URL` 不排除双引号或反引号。对 `"https://docs.example.test/start";缓存默认关闭`，匹配会越过闭合引号和 URL 外的 ASCII 分号，延伸到后续断言。本次只在中文全角终止符处截断跨度，且只从匹配尾部剥离标点，因而中间的分号被错误保护，两个 claim 合并。反引号包围的 URL 同样受影响，外部 `!`、`?` 也会被吞入。

   最小合成复现（仓库根目录）：

   ```bash
   PYTHONPATH=services/ai/src services/ai/.venv/bin/python - <<'PY'
   from knowflow_ai.citation_verify import prune_ungrounded_claims
   print(prune_ungrounded_claims(
       '参考 "https://docs.example.test/start";缓存默认关闭[src-evidence-1][src-evidence-2]。',
       {'src-evidence-1': '缓存默认关闭。',
        'src-evidence-2': '缓存默认开启。'}))
   PY
   ```

   当前实际结果：

   ```python
   {'pruned_answer': '', 'kept_source_ids': [], 'ok': False}
   ```

   期望丢弃无引用的 URL 前言，保留 `缓存默认关闭[src-evidence-1]。`。当前却把前言和后句合并成 `参考 "https://docs.example.test/start";缓存默认关闭`，两个来源均不能严格覆盖合并后的文本，于是全部删除。进程内只读加载 `d077e6a` 的 verifier 对照，返回的正是上述期望答案，`kept_source_ids=['src-evidence-1']`、`ok=True`。复现特意使用无查询参数、无路径分号的 URL，排除了原 P1 的干扰。

   已通过 `AnswerService.answer`（合成模型、检索器）和 `AnswerService.stream`（MockTransport、逐字符 provider 内容片段）验证：双引号和反引号两种输入在当前实现均返回 `没有足够的资料证据回答这个问题。`、`has_answer=False`、空 sources，流式以 `completed` 正常结束。这是修复引入的可见 false refusal：明明存在可保留的受支持断言，却因 URL 外分隔失败被整答拒绝，违背本次第 2 项检查及原剪枝目标。

   修复要求：URL 保护跨度应识别明确的闭合引号、反引号等外部界定符，保留 URL 内部合法标点，同时让 URL 外的 ASCII 分号、问号和感叹号继续分隔 claim。补充上述形式的合成普通/流式回归，直接断言剪枝后的完整答案与 sources；不能只验证中文句号或 `has_answer`。

**逐项核查**

| 检查项 | 结论与证据 |
| --- | --- |
| 原 `?q=` / 路径 `;` URL 截断 | 已消除。对原两个输入，直接剪枝、普通完整 `answer` 和流式 delta 拼接均完整保留 URL，`has_answer=True`、source ID 正确、流式 `completed`。额外合成 `https://docs.example.test/a!b?x=1;y=2` 也完整保留。 |
| URL 外句末标点 | 部分通过。28 个合成边界组合通过：两种原 URL × 中文 `。！？；` / 换行（有无空格），以及 ASCII `.!?;` 后有空格。紧邻闭合引号或反引号后的 ASCII `;!?` 失败，见新 P1。裸 URL 与无空格 ASCII 标点的歧义未用作判错依据。 |
| 合成回归是否断言完整 answer | 原 P1 覆盖合格。`test_answering.py:945-957` 对两个 URL 分别断言完整剪枝结果及 `response['answer'] == answer`；`test_streaming.py:107-122` 对两个 URL 分别断言全部 delta 拼接等于完整 answer，并检查来源、`has_answer` 与 `completed`。 |
| 外部标点测试覆盖 | `test_answering.py:979-983` 只覆盖 URL 后直接接中文句号和后续文字，没有覆盖被界定符包围的 URL 后接 ASCII 标点，因此未捕获新 P1。新增邮箱三例也直接断言完整 answer，均通过。 |
| 其他新 P0/P1 | 除上述新 P1 外，本次所审修复 diff 和调用链未发现其他新 P0/P1。普通与流式仍共用 `_response_from_generated`，未新增模型/检索调用或协议字段。 |

**实际验证**

- `services/ai/.venv/bin/python -m pytest services/ai/tests/test_answering.py services/ai/tests/test_streaming.py -q`：**87 passed**，3 条 warning（2 条数据库模拟线程 `ConnectionResetError`、1 条 Starlette/httpx 弃用提示），无失败。
- `services/ai/.venv/bin/python -m pytest services/ai -k citation -q`：**46 passed, 393 deselected**，1 条相同弃用提示。
- 额外合成探针验证普通服务入口、逐字符 provider 流式最终输出、28 个 URL 外边界组合，以及新 P1 的修复前后对照。仅在进程内运行，未修改实现或测试，未调用外部模型或真实数据库。

原阻塞项的具体输入已修复，且新增完整输出断言有效；但 URL 保护范围仍会越过明确的闭合界定符，产生新的可复现 P1，故本次不批准。

`SOL_REVIEW_DONE verdict=CHANGES_REQUESTED`
