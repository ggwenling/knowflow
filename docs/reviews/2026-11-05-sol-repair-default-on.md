# 补问默认开启独立审阅（第 1/3 轮）

- Reviewer：Sol High；独立只读实现审阅。
- HEAD：`bdea488ddc28b5e3a5fb35abae0fe656d636ac2e`，实跑 `git rev-parse HEAD`。
- 对照：`git show --stat HEAD`、`git diff b918d12..HEAD`、[设计](../design/2026-11-05-answer-repair-default-on.md)及公开 rereview3。
- 规则：`repair-v1`。
- Verdict：**CHANGES_REQUESTED**。发现 **1 类可复现 P1**：A6 将未命中字面关系锚词的相关证据当成无关，默认开启时可选择性发布存在明确冲突的答案。未发现 P0。

历史 N0–N4 已关闭，rereview3 的“有多高”不再漏放；这些通过结果不足以批准 default-on。下述 P1 经真实服务构造、首次真实剪空、同步和 SSE 发布路径复现，不能按历史默认 off 时的非阻断 P2 处理。

## P1-1：关系锚词漏匹配使冲突证据被忽略

位置：[`repair_gate.py:246`](../../services/ai/src/knowflow_ai/repair_gate.py#L246)，尤其 `:267` 的相关性筛选及 `:59` 的 `default_cache_state` 锚词；最终发布点为 [`answering.py:613`](../../services/ai/src/knowflow_ai/answering.py#L613)。

`_relevant_evidence_context()` 对不能完整解析的其他来源，仅在同时含目标主体和关系锚词时拒绝。缓存关系的唯一锚词是连续字符串 `缓存默认`。以下普通陈述包含相同主体、年份、默认状态关系以及相反值，但没有该连续字符串，因此被忽略：

```text
2027 年缓存的默认状态为开启，并非关闭。
```

候选自身的完整事实、单引用、逐字来源和问题槽绑定均通过后，A6 返回无疑点，最终标记 `passed / answered`。这使系统在没有版本或优先级依据时，只选择有利来源发布“默认关闭”。来源可逐字支持候选，仍不能证明整个批次没有冲突。

设计 §3.2 A6 的字面锚词细则本身也包含这一近似；实现遵循该细则并不能满足 A6 的“上下文和冲突不含疑点”目标。按设计 §6.2 及本轮标准 6，能导致 default-on 误发布的残留启发式仍是 P1。需要一并收紧该设计边界，不能仅新增本例词条后宣称所有未知相关上下文已安全。

### 精确复现输入

使用公开 `repair_scenario("P1")` 的合法 request/scope/locator 和以下三条同批 evidence；第三条有独立 source_id、chunk_id，未被候选引用：

| source_id | text_content |
| --- | --- |
| `src-evidence-1` | 原始资料说明索引 READY 后才可检索。 |
| `src-evidence-2` | 原始资料说明 2027 年缓存默认关闭。 |
| `src-context-3` | 2027 年缓存的默认状态为开启，并非关闭。 |

问题：`2027 年缓存默认关闭吗？`

首次生成（原始 `has_answer=true`、声明 s1/s2）：

```json
{"answer":"索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-1","src-evidence-2"]}
```

补问生成：

```json
{"answer":"原始资料说明 2027 年缓存默认关闭[src-evidence-2]。","has_answer":true,"source_ids":["src-evidence-2"]}
```

先独立调用 `_evaluate_generated()`，实际得到标准 REFUSAL、空 sources、`empty_after_prune`、`claims=1 / kept_claims=0`，再通过 `answer()` 或 `stream()` 运行完整请求。

| 配置 / 路径 | 实际最终结果 | 必须达到的结果 |
| --- | --- | --- |
| unset × 同步/SSE | `has_answer=true`，发布上述关闭答案和 s2；`attempt=1 / answered / passed` | 标准拒答、空 sources；`attempt=1 / failed_unrelated`，gate=`unsupported_context`（若新增完整冲突解析，可为 `conflicting_evidence`） |
| 显式 on × 同步/SSE | 与 unset 相同，误发布 | 与 unset 的拒答期望相同 |
| 显式 off × 同步/SSE | 标准拒答；`attempt=0 / not_attempted` | 保持现状 |

SSE 误发布的实际事件仍为 `started → delta → sources → completed`，delta 为候选全文，sources 的 `has_answer=true`。修复后应保持同一事件顺序，唯一 delta 精确等于 `没有足够的资料证据回答这个问题。`，sources 为 `has_answer=false / []`，无候选片段、无 error。

将第三条换成 `2027 年缓存 默认开启。`，unset/on × 同步/SSE 同样误发布，off 同样拒答。两个缓存变体共复现 **8 次实际误发布**。此处空白并未使证据变成无关。

对照：第三条为 `原始资料说明 2027 年缓存默认开启。` 时，两路均 `failed_unrelated / conflicting_evidence`；改为 `预测草案：2027 年缓存默认开启。` 时，两路均 `failed_unrelated / unsupported_context`。因此缺口是未解析相关证据的筛选，非整个冲突分支失效。

### 可直接运行的复现

从仓库根目录执行；仅使用公开 synthetic fixture、真实 contract 和真实 `AnswerService`，不覆盖 `_repair_enabled`，不调用 provider：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src:services/ai/tests services/ai/.venv/bin/python -B - <<'PY'
import asyncio
import os
from knowflow_ai.answering import AnswerService, REFUSAL
from test_answering import FakeRetriever, _contract
from repair_test_fixtures import MatrixRepairModel, repair_scenario

async def main():
    for setting in (None, "on", "off"):
        if setting is None:
            os.environ.pop("KNOWFLOW_ANSWER_REPAIR", None)
        else:
            os.environ["KNOWFLOW_ANSWER_REPAIR"] = setting
        for route in ("sync", "sse"):
            request, evidence, first, repaired = repair_scenario("P1")
            text = "2027 年缓存的默认状态为开启，并非关闭。"
            evidence.append({
                **evidence[0], "source_id": "src-context-3",
                "chunk_id": "chunk-context-3", "text_content": text,
                "locator": {"kind": "text_range", "start": 0,
                            "end": len(text), "unit": "unicode_code_point"},
            })
            model = MatrixRepairModel(first, repaired)
            service = AnswerService("unused", _contract(),
                retriever=FakeRetriever(evidence), llm_factory=lambda: model)
            initial, diag = service._evaluate_generated(request, evidence, first)
            assert initial["answer"] == REFUSAL
            assert initial["has_answer"] is False and initial["sources"] == []
            assert diag["reason"] == "empty_after_prune"
            assert diag["claims"] > 0 and diag["kept_claims"] == 0
            if route == "sync":
                response = await service.answer(request)
                print(setting or "unset", route, response)
            else:
                print(setting or "unset", route,
                      [event async for event in service.stream(request)])
            print(service.last_diagnostics)

asyncio.run(main())
PY
```

建议：对于包含目标实体、却不能完整解析或证明与所问关系无关的来源，采用保守拒绝；或缩小可发布范围。不能把“未命中连续关系短语”当成“没有相关疑点”的证明。本轮不修改实现或设计。

## 必核项结果

| 标准 | 结果与证据 |
| --- | --- |
| 1. 开关 | **通过**。真实构造服务并执行完整同步/SSE；unset、空串、空白、未知值开启，仅 `off/false/0/no` 关闭，含大小写及首尾空白。未知值告警不含原始值。 |
| 2. 触发白名单 | **通过**。检查 `_repair_trigger_eligible()` 及 `_evaluate_generated()`：仅两种 reason、原始 has_answer=true、非空 evidence、refused、claims>0、kept=0、空 kept IDs、有 dropped/uncited 才可进入；另需全题解析及开关。model_declined、空 evidence、超长、零断言、未知 reason 均不补问。`no_cited_claims` 的有断言合法入口不可达部分按设计使用 policy 测试，未放松 ID 校验。 |
| 3. A1–A7 | **不通过：A6 有 P1**。A1 检查原候选/最终响应的一事实一引用、无剪枝、无多余事实；A2 全来源逐字绑定；A3–A5 主体/关系/限定/值槽完整匹配；A7 两路共用最终选择出口。以上检查未发现新的独立缺口。`_has_question_content_overlap` 已删除，不参与授权。 |
| 4. 精确负例与正例 | **通过**。N0–N4（含“有多高”）在各开启设置两路均标准拒答、1/failed_unrelated；P0/P1 均修复成功。每组先独立证明首轮真实剪空。 |
| 5. 显式 off | **通过**。所有精确负例及 P0/P1 均标准拒答、0/not_attempted，正例也不修复。 |
| 6. 无新 P0/P1 | **不通过**。P1-1 在 unset 默认开启时可稳定误发布；历史默认 off 的批准不覆盖它。 |
| 7. 只读与信息边界 | **通过**。未修改实现、测试或设计；唯一写入为本报告。未读取盲测私有题面、答案、引用正文或私有产物。 |

### §5 精确矩阵

独立复核 **238 组全部符合该矩阵期望**：17 个真实构造配置 × 7 个场景 × 同步/SSE。配置为 unset、`""`、`" \t "`、`sometimes`、`on`、`" ON "`、`true`、`1`、`yes`、`off`、`" OFF "`、`false`、`" FALSE "`、`0`、`no`、`" No "`、`unknown-secret-value`。没有写入服务私有开关。

| 场景 | 开启配置两路 | 关闭配置两路 |
| --- | --- | --- |
| N0 零重叠 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N1 共享公司 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N2 共享缓存背景 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N3 年份加背景 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N4 “有多高” | false / 1 / failed_unrelated | false / 0 / not_attempted |
| P0 索引状态门槛 | true / 1 / answered | false / 0 / not_attempted |
| P1 缓存默认状态 | true / 1 / answered | false / 0 / not_attempted |

表中三项依次为 has_answer / repair_attempt / repair_outcome。所有负例正文精确等于标准 REFUSAL、sources=[]；拒绝候选后保留首次 refused diagnostics。所有 SSE 均校验四事件顺序且无候选泄漏。

另执行 **28 组相邻负例**（14 场景 × unset × 同步/SSE），全部标准拒答、1/failed_unrelated：全词重叠无金额、年份冒充金额、错主体、错年份并附正确年份背景、12027、缺失缓存条件、错引来源、跨源拼接、截取错误示例、显式否定、同槽金额冲突、半答案剪枝、指令注入、未解析草案背景。对应 gate 分别落在 missing_value、subject_mismatch、constraint_mismatch、unsupported_context、no_verbatim_fact、conflicting_evidence、candidate_incomplete 等有限枚举。

## 验证范围与限制

- 聚焦现有 pytest：**202 passed, 96 deselected，14.39s**，退出码 0。覆盖 `test_repair_gate.py`、`test_answering.py` 的补问/剪枝/引用回归及 `test_streaming.py` 的精确列名补问、超长、契约、取消、空证据测试，包含现有 126 组服务矩阵。
- 独立探针：上述 238 组开关/精确矩阵、28 组相邻负例，以及 30 组上下文对照（缓存两变体、索引否定疑点、精确缓存冲突、带锚词草案，分别 unset/on/off × 两路）。P1 主要证据为两个缓存变体的 8 次误发布；未将索引探针另计为独立问题。
- 使用现有 `.venv`、Python `-B`、`PYTHONDONTWRITEBYTECODE=1`；pytest 关闭插件自动加载、capture、logging、cache，显式加载 pytest_asyncio，并 `--noconftest`，用内存 collection plugin 选择范围。未知值告警由独立内存 logging handler 核验。
- pytest 和独立探针均安装 audit hook，禁止 socket connect/sendto/getaddrinfo、写模式 open、文件/目录增删改名/链接和 SQLite 连接；仅 FakeRetriever/内存模型，零真实 provider 调用。没有运行创建临时预算文件及账本的全套 autouse fixture。
- 首次按行号选测试时误包含依赖预算 fixture 的 provider cancellation 用例，得到 1 个 harness 超时；改为精确函数名选择后得到上述正式结果，未改变业务代码或测试。该准备失败不作为产品缺陷。
- 预算/guard 入口及资源关闭链已静态检查，相关文件无本次生产改动；补问取消、恰好 6s、余量不足、长度扩张、契约失败和至多一次调用回归通过。未独立重跑需落盘的真实账本/guard 集成，不声称完整套件或真实预算评测通过。
- `git diff --check b918d12..HEAD` 通过。审阅开始工作树干净，未提交、推送或运行公开/盲测 provider 评测。公开 development/holdout 的 on/off 成对质量门禁仍未验证，不能据合成测试宣称 answerable 指标已达标。

本轮必须先关闭 P1-1，并保持历史精确负例、正例、off 和同步/SSE 契约后再申请第 2 轮。默认开启安全批准尚未取得。

SOL_REVIEW_DONE verdict=CHANGES_REQUESTED round=1
