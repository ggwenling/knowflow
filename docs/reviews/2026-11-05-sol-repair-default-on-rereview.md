# 补问默认开启独立复审（第 2/3 轮）

- Reviewer：Sol High；独立审阅，未修改实现。
- HEAD：`87bcefda3c9e3fa262bd11b8d3227748308a3638`（审阅开始及写报告前实跑 `git rev-parse HEAD`，一致）。
- 差异：`git diff edff2ee..HEAD`；对照[第 1 轮 CR](2026-11-05-sol-repair-default-on.md)及[设计 A6](../design/2026-11-05-answer-repair-default-on.md#L97)。
- 规则：`repair-v1`。
- Verdict：**APPROVED，明确批准本轮有界补问路径的 default-on 安全变更。** P1-1 两变体均已关闭，历史 N0–N4 与 P0/P1 未回退；本次审阅未发现新的 P0/P1。

此次批准针对当前 HEAD 的默认开启实现及安全闸；不沿用历史 default-off 的批准，也不代表公开集质量指标或后续盲测指标已经通过。

## P1-1 关闭证据

生产差异仅收紧 [`_relevant_evidence_context()`](../../services/ai/src/knowflow_ai/repair_gate.py#L246)：

1. 无法完整解析的其他来源，只要包含所问主体字面名就返回 `unsupported_context`；删除了必须同时命中连续关系锚词的条件（:272）。
2. 能完整解析、同主体同关系但约束不同的来源返回 `unsupported_context`（:259）；同约束而值/类型/单位不同仍返回 `conflicting_evidence`。
3. 完整解析为其他主体/关系的来源仍可判为无关；未增加切句、截取局部事实、版本优先级或模型裁判。设计 :99 同步收紧了这一边界。

这不是只加入两个缓存词条：所有已有 target 都走同一保守扫描。相对基线，原有拒绝分支仍保留，新增分支只缩小可接受集合；A1–A5 与 A7 没有被放宽。覆盖率代价是同主体的未解析背景、以及不同年份/条件的事实也可能导致拒答，符合修订后的设计。

独立探针没有调用新增的 `append_repair_context()` 测试 helper，而是自行构造第三条 source/chunk/locator。其余 request、首次生成和补问生成沿用公开 `repair_scenario("P1")`，与第 1 轮复现输入一致。每组先调用真实 `_evaluate_generated()`，确认首次确为标准拒答、`empty_after_prune`、`claims>0 / kept_claims=0`，再执行完整 `answer()` 或 `stream()`。未覆盖服务私有 `_repair_enabled`。

下表每格均独立验证同步和 SSE，两变体共 **12 组**，加两条对照共 **24 组**，全部通过：

| 第三条同批 evidence | unset × sync/SSE | on × sync/SSE | off × sync/SSE |
| --- | --- | --- | --- |
| `2027 年缓存的默认状态为开启，并非关闭。` | 标准拒答；1 / failed_unrelated / unsupported_context | 同 unset | 标准拒答；0 / not_attempted |
| `2027 年缓存 默认开启。` | 标准拒答；1 / failed_unrelated / unsupported_context | 同 unset | 标准拒答；0 / not_attempted |
| `原始资料说明 2027 年缓存默认开启。` | 标准拒答；1 / failed_unrelated / conflicting_evidence | 同 unset | 标准拒答；0 / not_attempted |
| `预测草案：2027 年缓存默认开启。` | 标准拒答；1 / failed_unrelated / unsupported_context | 同 unset | 标准拒答；0 / not_attempted |

三项依次为 repair_attempt / repair_outcome / repair_gate_reason；off 的 gate 实际为 `not_checked`。开启时模型恰好首轮一次、补问一次；off 时只有首轮、零补问。所有拒答正文逐字等于 `没有足够的资料证据回答这个问题。`，`has_answer=false / sources=[]`，保留首次 refused diagnostics。

所有 SSE 均严格为 `started → delta → sources → completed`；只有一个 delta，内容精确等于标准拒答，sources 事件为 false/[]，没有首次生成或补问候选片段，也没有 error 事件。

## 历史回归与相邻边界

独立执行 **238 组**：17 个真实环境开关设置 × 7 个场景 × 同步/SSE。设置与第 1 轮一致：unset、`""`、`" \t "`、`sometimes`、`on`、`" ON "`、`true`、`1`、`yes`、`off`、`" OFF "`、`false`、`" FALSE "`、`0`、`no`、`" No "`、`unknown-secret-value`。每组均先证明首次真实剪空。

| 场景 | 开启配置，两路 | 关闭配置，两路 |
| --- | --- | --- |
| N0 零重叠 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N1 共享公司 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N2 共享缓存背景 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N3 年份加背景 | false / 1 / failed_unrelated | false / 0 / not_attempted |
| N4 “有多高” | false / 1 / failed_unrelated | false / 0 / not_attempted |
| P0 索引状态门槛 | true / 1 / answered | false / 0 / not_attempted |
| P1 缓存默认状态 | true / 1 / answered | false / 0 / not_attempted |

三项依次为 has_answer / repair_attempt / repair_outcome。正例精确发布补问正文及指定单一 source，gate=passed；负例与 off 全部标准拒答、空 sources；SSE 仍为上述四事件且正文与最终选择一致。

另独立执行 **72 组**相邻上下文对照：12 条第三来源 × unset/on/off × 同步/SSE，全部符合预期。缓存覆盖 tab、换行、无连续关系锚词的预测草案、否定、2028 年完整事实、无年份完整事实；索引覆盖否定、无原关系锚词的改写、预测草案、2028 年完整事实。上述 10 条在开启时均 `failed_unrelated / unsupported_context`，off 不补问。另两条为相同缓存事实、完整解析的其他主体/关系净利润事实，在开启时仍 `answered / passed`，off 保留拒答。

合计 **334 组独立完整服务探针通过**（238 + 24 + 72），未调用真实 provider。

## 现有测试与静态复核

- 聚焦 pytest：**257 passed, 67 deselected，17.17s**，退出码 0。覆盖全部 `test_repair_gate.py`，`test_answering.py` 的引用/剪枝、开关、触发、单次补问、失败回落、长度、契约、余量和取消测试，以及 `test_streaming.py` 的增量解析、补问矩阵、长度/契约回落、补问取消和空证据测试。
- 在本 HEAD，用内存 collection plugin 选择：`test_answering.py` 起始行 770–1099 或 ≥1170 的用例，排除唯一依赖 caplog 的未知值告警测试；`test_streaming.py` 起始行 ≤90、295–561，另选 `test_stream_without_evidence_uses_no_provider`。其余 67 项未执行。未知值告警另用内存 logging handler 独立确认：返回 true、记录有限枚举 `unrecognized_kept_enabled`，不泄漏原始值。
- 使用现有 `services/ai/.venv/bin/python -B`，`PYTHONDONTWRITEBYTECODE=1`、`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；pytest 参数为 `-q -s --noconftest -p no:cacheprovider -p no:logging -p pytest_asyncio.plugin`。
- pytest 和 334 组正式探针均安装 audit hook，阻止 socket connect/sendto/getaddrinfo、写模式 open、文件/目录增删改名/链接、SQLite 连接及子进程；另禁止读取 `evaluation/data/`。没有运行会落盘预算文件/账本的 autouse fixture；不声称完整套件或真实预算集成通过。
- 静态复核 `answer_repair_enabled()`、触发白名单、A1–A7、同步/SSE 共用 `_finalize_generation()` 的发布链。仅显式 off/false/0/no 关闭，未知/空/unset 默认开启；旧 overlap 不参与补问接受授权。本次生产差异未修改预算、guard、取消或模型资源关闭链。
- `git diff --check edff2ee..HEAD` 通过。最初独立 harness 曾把同步完整响应与仅含 answer/has_answer/sources 的字典直接比较而失败；修正为提取这三个字段后得到正式 334 组结果。该失败是 harness 的字段比较问题，不是产品失败，也未修改业务代码。

## 信息边界与结论范围

审阅开始工作树干净；写报告前再次确认工作树仍干净、HEAD 未变。唯一持久写入为本报告；未修改实现、测试或设计，未提交或推送。仅使用公开合成 fixture、公开评审/设计和真实 contract；未读取或探测盲测私有题面、答案、引用正文或私有产物。

本轮没有运行公开 development/holdout 的 provider on/off 成对质量评测，不能据合成测试宣称 answerable_answer_rate ≥0.90、全量审核或后续盲测指标达标。此项与本轮 **default-on 安全批准**分别记录。结论限定于现有 `repair-v1` 的封闭主体/关系/完整事实语法及上述验证范围，不推导对任意自然语言、别名或文档格式的通用语义证明能力。

**最终结论：APPROVED（default-on）。** 第 1 轮 P1-1 两变体均已关闭，对照、历史负例、正例、off 及同步/SSE 契约保持，未发现新的 P0/P1。

## 独立探针复现

仓库根目录执行以下命令，可重跑正式 334 组矩阵；使用内存假模型和真实服务/contract，不调用 provider，不落盘：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/ai/src:services/ai/tests services/ai/.venv/bin/python -B - <<'PY'
import sys, os, asyncio, json, logging
from collections import Counter
def audit(event,args):
    if event in {'socket.connect','socket.sendto','socket.getaddrinfo','sqlite3.connect','subprocess.Popen','os.system','os.remove','os.rename','os.rmdir','os.mkdir','os.link','os.symlink','os.truncate','os.chmod','os.chown'}:
        raise RuntimeError('review audit blocked '+event)
    if event=='open':
        path,mode,flags=args
        if (isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            raise RuntimeError('review audit blocked write')
        if isinstance(path,(str,bytes)) and '/evaluation/data/' in os.fsdecode(path):
            raise RuntimeError('review audit blocked evaluation data')
sys.addaudithook(audit)
from knowflow_ai.answering import AnswerService, REFUSAL
from test_answering import FakeRetriever, _contract
from repair_test_fixtures import MatrixRepairModel, repair_scenario
logging.getLogger().setLevel(logging.ERROR)
contract=_contract()
counts=Counter()
async def run_case(setting,route,name,context=None,reason=None,accept=None):
    if setting is None: os.environ.pop('KNOWFLOW_ANSWER_REPAIR',None)
    else: os.environ['KNOWFLOW_ANSWER_REPAIR']=setting
    request,evidence,first,repaired=repair_scenario(name)
    if context is not None:
        evidence.append({**evidence[0],'source_id':'src-context-3','chunk_id':'chunk-context-3','text_content':context,'locator':{'kind':'text_range','start':0,'end':len(context),'unit':'unicode_code_point'}})
    model=MatrixRepairModel(first,repaired)
    service=AnswerService('unused',contract,retriever=FakeRetriever(evidence),llm_factory=lambda:model)
    initial,d0=service._evaluate_generated(request,evidence,first)
    assert initial['answer']==REFUSAL and initial['has_answer'] is False and initial['sources']==[]
    assert d0['reason']=='empty_after_prune' and d0['claims']>0 and d0['kept_claims']==0 and d0['decision']=='refused'
    if route=='sync':
        raw=await service.answer(request)
        response={k:raw[k] for k in ('answer','has_answer','sources')}
    else:
        events=[e async for e in service.stream(request)]
        assert [e['event'] for e in events]==['started','delta','sources','completed'],events
        response={'answer':events[1]['delta'],'has_answer':events[2]['has_answer'],'sources':events[2]['sources']}
    disabled=setting is not None and setting.strip().lower() in ('off','false','0','no')
    accepted=not disabled and ((name in ('P0','P1') and context is None) if accept is None else accept)
    d=service.last_diagnostics
    assert model.generate_calls==1 and model.repair_calls==int(not disabled)
    assert d['repair_attempt']==int(not disabled)
    assert d['repair_outcome']==('not_attempted' if disabled else 'answered' if accepted else 'failed_unrelated'),d
    if accepted:
        assert response['has_answer'] is True and response['answer']==repaired['answer'],response
        assert [s['source_id'] for s in response['sources']]==repaired['source_ids']
        assert d['repair_gate_reason']=='passed'
    else:
        assert response=={'answer':REFUSAL,'has_answer':False,'sources':[]},response
        assert d['decision']=='refused' and d['reason']==d0['reason'] and d['kept_claims']==0
        if not disabled and reason is not None: assert d['repair_gate_reason']==reason,d
    return {'has_answer':response['has_answer'],'attempt':d['repair_attempt'],'outcome':d['repair_outcome'],'gate':d['repair_gate_reason']}
async def main():
    settings=[None,'',' \t ','sometimes','on',' ON ','true','1','yes','off',' OFF ','false',' FALSE ','0','no',' No ','unknown-secret-value']
    for setting in settings:
        for name in ('N0','N1','N2','N3','N4','P0','P1'):
            for route in ('sync','sse'):
                await run_case(setting,route,name)
                counts['historical_switch_matrix']+=1
    contexts=[
      ('rewrite','2027 年缓存的默认状态为开启，并非关闭。','unsupported_context'),
      ('whitespace','2027 年缓存 默认开启。','unsupported_context'),
      ('parsed_conflict','原始资料说明 2027 年缓存默认开启。','conflicting_evidence'),
      ('prediction_draft','预测草案：2027 年缓存默认开启。','unsupported_context')]
    for label,context,reason in contexts:
        for setting in (None,'on','off'):
            for route in ('sync','sse'):
                result=await run_case(setting,route,'P1',context,reason,False)
                print(json.dumps({'case':label,'setting':setting or 'unset','route':route,**result},ensure_ascii=False))
                counts['P1_1_and_controls']+=1
    adjacent=[
      ('P1','2027 年缓存\t默认开启。','unsupported_context',False),
      ('P1','2027 年缓存\n默认开启。','unsupported_context',False),
      ('P1','预测草案：2027 年缓存的默认状态为开启。','unsupported_context',False),
      ('P1','2027 年缓存不是默认关闭。','unsupported_context',False),
      ('P1','原始资料说明 2028 年缓存默认开启。','unsupported_context',False),
      ('P1','原始资料说明缓存默认关闭。','unsupported_context',False),
      ('P1','原始资料说明 2027 年缓存默认关闭。','passed',True),
      ('P1','原始资料说明公司 2027 年净利润为 100 万元。','passed',True),
      ('P0','2027 年索引并非 READY 后才可检索。','unsupported_context',False),
      ('P0','2027 年索引达到就绪状态之前也可搜索。','unsupported_context',False),
      ('P0','预测草案：2027 年索引 READY 后才可检索。','unsupported_context',False),
      ('P0','原始资料说明 2028 年索引 READY 后才可检索。','unsupported_context',False)]
    for name,context,reason,accepted in adjacent:
        for setting in (None,'on','off'):
            for route in ('sync','sse'):
                await run_case(setting,route,name,context,reason,accepted)
                counts['adjacent_context_matrix']+=1
    print('PASS',json.dumps(dict(counts)),'total=',sum(counts.values()))
asyncio.run(main())
PY
```

SOL_REVIEW_DONE verdict=APPROVED round=2
