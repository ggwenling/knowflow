# 欠引用修复实现记录（2026-11-05）

依据：[`2026-11-05-blind-rounds-summary.md`](./2026-11-05-blind-rounds-summary.md) 的「Recommended next fix」。
本文件只记录**代码实现**与**未验证状态**。**没有**新采集、没有跑公开集门禁、没有付费法官，盲测包仍未通过 `answerable_answer_rate ≥ 0.90`。

## 1. 实现的改动

| 层 | 文件 | 行为 |
| --- | --- | --- |
| 校验 | `services/ai/src/knowflow_ai/citation_verify.py` | 新增 `prune_claims()`：在剪枝结果之外返回 `reason`（`grounded` / `empty_after_prune` / `no_cited_claims`）与计数（claims / kept / uncited / dropped / repaired / pruned_markers）。`prune_ungrounded_claims()` 保留为三键兼容投影。 |
| 校验 | 同上 | 零成本 claim 级修复：未被引用的断言、或栈式引用全部失配的断言，只有在**模型已声明**的某个 `source_id` 原文完整包含该断言时，才重新绑定到该来源。不新增来源、不放宽覆盖阈值、不改证据。 |
| 策略 | `services/ai/src/knowflow_ai/answering.py` | `_evaluate_generated()` = 原 `_response_from_generated` 逻辑 + 诊断；`_finalize_generation()` = 单次有界补问策略层；`_response_from_generated()` 保留为单次生成校验入口（同步测试与既有调用不变）。 |
| 补问 | `answering.DeepSeekAdapter.generate_repair()` | 同一批 evidence 上的第二次生成，附带上一版答案（截断 4000 code point）与格式指令；`provider_budget` 照常对每次尝试预约。 |
| 流式 | `services/ai/src/knowflow_ai/streaming.py` | `answer_events` 走同一 `_finalize_generation`，正文仍在引用校验完成后才作为 `delta` 发出。 |
| 评测/预算 | `evaluation/collector/guarded_adapters.py` | `GuardedLlm.generate_repair()`：补问与普通生成走**同一条**预约边界（真实 adapter 自己预约；fake adapter 由 guard 记账），无 `generate_repair` 的旧 adapter 回落为普通 `generate`，不会出现未预约的尝试。 |
| 观测 | `services/ai/src/knowflow_ai/answering.py`、`evaluation/collector/{results,collect,run}.py` | 每题剪枝结论写入评测 sidecar：capture 信封新增 `citation`（枚举 + 计数），`run.py` 落盘 `<predictions>.diagnostics.json`。预测行 schema 不变，因此 runner 与门禁不受影响；sidecar 不含题面、答案、断言或原文。 |

触发条件（全部满足才补问）：模型自报 `has_answer=true`、检索返回非空证据、剪枝后无任何可保留断言、剩余 deadline ≥ 6 秒。补问结果走**同一套** JSON / ID / 作用域 / grounding 校验；失败、超时、预算软停、仍不可落地 → 保持标准拒答，不转成 `error`。`KNOWFLOW_ANSWER_REPAIR=off` 可完全关闭（默认 `on`）。

## 2. 与计划的差异

| 计划项 | 状态 | 说明 |
| --- | --- | --- |
| 单次有界 re-ask | 已实现 | 上限 1 次/问题；非流式补问；`REPAIR_MINIMUM_SECONDS=6`。 |
| claim 级修复 | 已实现，但仅限「原文完整包含 + 已声明来源」 | 未采用 0.55 字符 n-gram 覆盖率放行，避免复活 v1 设计的「半句引用」漏洞。 |
| 硬拒答保留 | 已保留 | 空证据、`has_answer=false`、无 `declared_id` 三种情况不补问。 |
| 每问题剪枝原因码 | 已实现 | 结构化日志 `ai_stage stage=citation_verification` + 评测 sidecar `<predictions>.diagnostics.json`（`decision` / `reason` / 各计数 / `repair_attempt` / `repair_outcome`）。产品契约 `AnswerResponse` 未改字段。 |
| 只在 public seed-v2 dev→holdout 上定门禁 | 未执行 | 本轮没有真实模型调用。 |

## 3. 已知代价与风险

- 补问是**额外付费调用**，只在「本来就要拒答」的路径上发生（v3 为 8/20）。`RESERVE` 仍按 policy 上界预约，账本软停不受影响；软停时补问直接失败并回落到拒答。
- 补问提升的是**格式合规**，不是事实正确性。若模型在同样证据上第二次仍无法逐句引用，误拒答不会下降——门禁数据会直接暴露这一点。
- 未知风险已排除一项：Java `QuestionProperties.totalBudgetSeconds = 30`，Python 自限 28s，补问被限制在这个 28s 之内（`remaining ≥ 6s` 才尝试，且请求超时剩余 -1s），不需要改 Java。
- 反向风险：v3 的 `unanswerable refusal` 目前 1.000。若模型在不可答题上误报 `has_answer=true`，补问有机会把一段「原文可查但不回答问题」的句子变成可发布答案，从而把正确拒答换成错误回答。这是本改动唯一会动到已通过指标的路径，必须在 holdout 上单独统计 `unanswerable` 与 `answerable` 两个方向后再启用。
- claim 级修复可能把一句「被声明来源原文包含」的句子挂回引用；它不会让不支持的内容通过，但也**不**证明该句回答了核心问题。
- 单 marker 的宽松策略（`test_citation_verifier_allows_single_marker_when_source_text_is_present`）**未改动**：v3 里 citation/support 已过阈值，而 answerable 未过，收紧它只会加误拒答。v3 剩余的那条 support+citation 失败项因此不会被本修复覆盖。

## 4. 下一步（未执行）

1. 公开 seed-v2 `development` → `holdout`，双 LLM 法官，对比 `KNOWFLOW_ANSWER_REPAIR=on/off` 两组，报告 answered/refused/error、误拒答率、correct-citation 误剪率与延迟。补问会使延迟上限从「1 次生成」变成「2 次生成」，必须单独报告。
2. 只有在 holdout 上 `answerable_answer_rate ≥ 0.90` 且 citation/support 不退化，才考虑再取一次独立盲测包；不得用 v1/v2/v3 已判分结果调参。
3. 若补问无效，下一个可测方向是「检索强但答案空」时直接输出检索片段摘录（抽取式兜底），而不是继续放宽引用校验。

## 5. 本轮实际执行的验证

- `services/ai` 测试套件：`479 passed`（修复前 `458 passed, 1 failed`）。该失败项 `test_real_evaluation_service.py::test_real_app_uses_product_adapters_with_mock_transport` 为 Windows 专有：模块的网络禁闭 fixture 连 `socket.connect` 一并禁掉，而 Windows ProactorEventLoop 用 loopback `socketpair()` 建自管道。已改为只拦非 loopback 目标，该模块现 `27 passed`。
- 新增测试：`test_answering.py` 13 条（reason code、claim 级修复正/负例、补问成功/失败/畸形/无 headroom/开关关闭、`repair_outcome` 枚举、payload 形状），`test_streaming.py` 2 条（流式补问成功与流式拒答），`test_rag_collection.py` 3 条（guard 转发补问、旧 adapter 回落、capture 信封 `citation` 字段集合），`test_collection_run.py` sidecar 断言并入既有用例，`test_real_evaluation_service.py` 1 条（网络守卫仍拦外网）。
- 未运行：任何真实 provider 调用、公开集采集、法官评分、Web E2E。

## Sol P1/P2 修复

- 补问结果只有在引用校验通过且去除引用标记后的答案与问题存在内容 token 重叠时才可发布；检查只作用于补问接受路径，首次生成规则不变。无重叠时保留首次标准拒答，并记录 `failed_unrelated`。
- 剪枝/补挂后的答案超过 16,000 code points 时标记为不可发布；补问结果的 `InvalidMessage` 契约失败归一为受控失败并保留首次拒答。
- `pruned_markers` 现统计原始答案中实际删除的 marker 数；补挂新增的 marker 不计入该值。
- 本节仅记录代码与回归用例，没有产生新的门禁或盲测结果。
