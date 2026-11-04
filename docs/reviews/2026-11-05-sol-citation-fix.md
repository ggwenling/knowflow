# Citation 修复独立审阅

- 日期：2026-11-05
- Reviewer：Sol（独立评审）
- Target：`90e053cfb8e736ee3b1dcd4c9dc657e911cd0748`
- Verdict：**CHANGES_REQUESTED**
- 发现：P0 0 项，**P1 2 项，P2 2 项**。
- 范围：citation verifier、普通/流式调用、prompt、collector `_claim`、相关测试及 citation 设计笔记。仅写入本报告，未修改实现或测试，未 commit/push。

## P1-1：字符重合被当作完整支持，堆叠引用和错误断言仍会放行

位置：`services/ai/src/knowflow_ai/citation_verify.py:120-139`，尤其完整 chunk 比较及 `coverage >= 0.55` 的成功分支；`answering.py:509-520` 将其直接用于最终放行。

`citations_are_grounded` 确实逐个 marker 检查完整句，但 `_grounded` 只要求该句至少 55% 的字符 bigram 被来源覆盖。来源可以完全没有支持句子剩余部分，也可以与其矛盾。经真实 `_response_from_generated` 路径复现：

```text
answer = 生产环境支持批量导入，缓存关闭[s1][s2]。
s1 = 生产环境支持批量导入。
s2 = 生产环境支持批量导入，缓存关闭。
实际：has_answer=true，保留 s1、s2。
```

s1 的覆盖率为 `0.642857`，它没有说明缓存状态，却被当作独立支持完整复合断言的引用。把 s1 改成 `生产环境支持批量导入，缓存开启。` 仍然放行。因此现有只测“一长一短、短来源覆盖不足阈值”的负例不能证明堆叠问题已解决。

同一成功路径还接受以下新编合成反例：

| answer | 所引 s1 | 实际 |
| --- | --- | --- |
| `甲服务的并发上限为 8[s1]。` | `甲服务的并发上限为 4。乙服务的并发上限为 8。` | 放行错误主体/数值绑定 |
| `允许发布[s1]。` | `仅测试环境允许发布。` | 放行丢失适用条件的断言 |
| `生产环境允许发布[s1]。` | `生产环境不允许发布。测试环境允许发布。` | 放行错误环境/否定作用域 |

数字集合在整个 chunk 上检查，不能证明数值归属于当前主体；否定词有无的布尔比较也不能证明否定作用域。存在另一条高重合句时，遍历比较文本会进一步绕过前一条否定冲突。

影响：本次要修复的“不独立支持完整断言的引用”仍进入正式答案；sync 与 stream 均受影响。设计笔记 §4 明确将 n-gram 限为 shadow 诊断，但本提交已将其作为生产放行依据。

修复要求：不能以该覆盖阈值或 chunk 级数字/否定集合证明完整断言。对无法确认完整主体、条件、关系和数值绑定的情况保留 UNKNOWN；在获得可靠覆盖及误拒答证据前使用 shadow。若采用设计中的剪引用策略，只能在另一来源独立覆盖完整断言时剪去未验证 marker。补上上述反例，不通过降低/提高阈值或增加题目关键词处理它们。

## P1-2：URL 等非句界标点被拆成无引用事实，逐字原文也整答拒答

位置：`services/ai/src/knowflow_ai/citation_verify.py:27-37,49-69,153-155`；collector 对应规则位于 `evaluation/collector/prediction.py:40-63`。

新 verifier 对 marker 以外的每个 `.` 都切句，仅豁免两侧均为数字的小数点。合法 URL、邮箱和文件名因此被切成多个单元，前面的单元没有 marker，直接整答拒答：

```text
answer = 请访问 https://docs.example.test/start[s1]。
s1     = 请访问 https://docs.example.test/start。
实际：标准拒答，has_answer=false，sources=[]。
```

这是完全逐字、来源充分的答案，且 marker 已按新 prompt 放在句末标点前。verifier 实际得到 `请访问 https://docs`、`example`、`test/start` 三个单元，前两个没有引用。`联系 help@example.test[s1]。` 同样失败；`1. 索引就绪[s1]。` 则将列表编号 `1` 当作无引用事实。

collector 的现行 `_claim` 对上面的 URL 只提取 `test/start[s1]。`，对列表只提取 `索引就绪[s1]。`。两个实现虽然采用近似分隔符规则，却没有形成保留完整命题的契约；collector 的尾部片段无法代表服务拒绝掉的完整正文。点号 ID 与小数的新增测试不足以覆盖这一点。

影响：新引入的强制 verifier 会使带网址、邮箱、代码标识符或常见编号格式的正确答案退化为拒答。

修复要求：在切句前保护 URL、邮箱、版本/文件/代码标识符及列表语法，无法确定时保留较大的连续原文窗口。为 service 与 collector 建立共同的合成边界用例，覆盖 remap 前后并断言 collector claim 仍是最终 answer 的完整连续子串；不能仅验证两者截断结果相似。

## P2-1：数值字符串差异被误判为数值矛盾

位置：`services/ai/src/knowflow_ai/citation_verify.py:13,101-103,126-127`。

`_numeric_conflict` 直接比较 regex 提取的字符串集合，在任何支持性比较之前拒绝不同写法。合成复现：

| answer | s1 | 实际 |
| --- | --- | --- |
| `并发上限为 4.0[s1]。` | `并发上限为 4。` | 标准拒答 |
| `每分钟可处理 1000 个请求[s1]。` | `每分钟可处理 1,000 个请求。` | 标准拒答 |

这两个例子数量相同，没有引入新事实；第二例的高字符重合也无法挽救先行的数字拒绝。普通语义改写同样存在误拒答，例如 `缓存已关闭[s1]。` 相对于 `缓存已禁用。` 返回 false，说明当前“soft”判据并没有解决通用改写覆盖问题。本次合成探针不能推导其总体误拒答率。

修复要求：对明确数量上下文采用受控的数值等价比较，保留单位、属性及主体绑定；不要对版本号、标识符盲目套用数值归一化。不能把字符串不等直接称为语义矛盾。对改写 UNKNOWN 的强制拒答，应先补公开/合成的覆盖率和误拒答评估，不能以现有 103 个测试通过作为启用证据。

## P2-2：同步 verifier 越过 deadline 后仍可返回成功/completed

位置：`services/ai/src/knowflow_ai/streaming.py:337-343`；普通路径 `answering.py:485`，以及 verifier 对每次 marker 重复扫描来源的 `citation_verify.py:156-158`。

streaming 只在 `_response_from_generated` 之前检查 deadline，之后直接发 delta、sources、completed；普通路径也未在新增同步校验之后检查剩余时间。`asyncio.timeout` 无法抢占这段同步计算，异步生成器的 yield 在被立即消费时也不保证事件循环有机会运行 timeout 回调。

用合法尺寸的纯合成输入复现：800 字符来源 `索引就绪。` 重复 160 次；答案为 `索引就绪` 后跟同一个真实长度 UUID source marker 380 次再加句号，共 15,965 字符，唯一 source 只有一个。FakeLlm 无网络、无等待；仅将 `ANSWER_DEADLINE_SECONDS` 缩为 `0.02` 秒以验证相对时限行为：

```text
sync:   elapsed=0.1060s，response/verification=0.1058s，has_answer=true
stream: elapsed=0.1139s，response/verification=0.1062s
events: started, delta, sources, completed
```

缩短常量用于复现，不代表已证明正式 28 秒预算会被该输入整体耗尽；正式场景的触发条件是生成完成时剩余预算小于本地校验耗时。当前路径会把超时继续报告为成功。

修复要求：普通与流式在校验之后、返回答案/发任何 delta 之前显式检查绝对 deadline，超时保持 `PROCESSING_TIMEOUT`/error 终态。对来源规范化和重复 claim/source 组合做请求内缓存，并设置合理工作量上限；同步 CPU 段不能只依靠外层 asyncio timeout。补充“生成及时完成、校验跨过时限”的测试。

## 已验证行为与证据

1. 定向测试：

   ```bash
   services/ai/.venv/bin/python -m pytest -q \
     services/ai/tests/test_answering.py \
     services/ai/tests/test_streaming.py \
     services/ai/tests/test_rag_collection.py
   ```

   **103 passed，7.69s**。同时出现两条测试 PostgreSQL 假服务器线程的 ConnectionResetError warning，及一条 Starlette/httpx 弃用 warning；没有测试失败。

2. 独立运行 heuristic smoke：

   ```bash
   PYTHONDONTWRITEBYTECODE=1 services/ai/.venv/bin/python -m pytest -q \
     -p no:cacheprovider evaluation/smoke/test_heuristic_review.py
   ```

   **10 passed，0.02s**，另有 asyncio fixture loop scope 未配置的弃用提示。这些是 heuristic 回归结果，不能作为 citation 质量门禁。

3. 使用现有 `_citation_response` 测试辅助函数、真实 AnswerService verifier 和合成 evidence 执行上述放行/拒答探针；以仅产生内存 JSON 的 FakeLlm 流式适配器复核 8 组输入：部分支持堆叠、主体数值错绑、丢失条件、否定作用域、逐字 URL、普通改写、4/4.0、千位分隔。**8/8 的 sync/stream 最终 answer、has_answer、sources 相同，均只有一个 completed 终态**。它们证明两条产品路径一致地受到上述问题影响，不表示这些错误输出符合预期。

4. 现有 streaming 测试验证 provider 完成前没有 answer delta、校验拒答只发一次标准文案、伪造引用/坏 JSON/provider 错误终止，以及取消、provider 超时、HTTP 断开的资源关闭。缓冲正文的实现方向正确，正常拒答的最终 false/空 sources 也正确；P2-2 是未覆盖的本地同步校验超时分支。

5. prompt 保留核心问题证据不足的拒答规则，新增逐断言和标记前置于句末标点的要求；普通/流式共享生成提示和最终 verifier。source 身份/集合/作用域错误仍走原错误路径，没有通过 verifier 偷换成证据不足。

## 盲测边界、设计偏差及限制

- 在本次审阅的新增生产代码和测试中，未发现按 blind question ID、reference answer、私有路径、特定题目关键词或答案白名单进行的分支。verifier 输入只来自当前 answer 和所引 source 的 text_content；未新增模型、embedding、检索或 HTTP 调用。此结论是对提交内容的静态审阅，不是对开发数据来源的证明。
- 未读取盲测题面、私有预测或仓外私有运行产物；探针全部为本次新编合成数据。未运行真实采集、质量法官或付费 API，没有新的 citation/support/answer-rate 门禁结论。
- 设计笔记是历史设计提案，不能视为实现完成记录。本提交采用强制 bigram 判断，没有实现其中的 UNKNOWN/shadow、条件剪引用、公开覆盖率/误拒答验证和资源诊断方案；其中与本次具体缺陷相关的偏差已在上文指出。
- 现有测试通过且流式缓冲正确，仍不足以批准此修复。应先关闭两个 P1，并补齐数值等价及校验超时回归，再以独立公开/合成材料评估强制拒答的覆盖率；不使用受污染盲测调阈值。
