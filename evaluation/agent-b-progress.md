# Codex-B 执行记录

仓库 `/workspace/knowflow`；分支 `java`，由用户指定，从 `origin/main` 的 `7d5095b8bc987c1c7e6f4106887d3355fa88d4c2` 创建。B 角色负责 Python/RAG，与分支名称无关。

已读 V0.2 项目计划、协作手册与全部 B 任务卡。仓库没有 AGENTS.md、V1.1 设计包、冻结契约或服务代码；未启动 A/M/Q，不声称其他 Agent 已完成任务。仅修改本次任务明确允许的运行基线、许可记录及 B 的 evaluation 范围。

## 当前任务 KF2-003

状态：**WAITING_INPUT**。准备产物可审阅，真实模型验收未完成，Q 未审阅，集成未验证。

交付范围：`evaluation/smoke/`、`docs/architecture/runtime-profile.md`、`docs/architecture/parser-dependencies.md` 及本记录。未修改计划原始 JSON/CSV 中的状态，未改变其他角色的所有权。

已交付：标准库模型冒烟及原创中文夹具、10 项离线回归、真实环境配置预检、指定版本解析库 wheel/许可指纹、数据出站与日志边界、待验证资源提议。基线 SHA 和环境信息见模型预检；运行时脚本尚未提交时证据中的 `git_head` 指向集成基线，并不表示脚本已包含在该旧提交中。提交后由 Git 历史绑定候选产物，不能将旧证据冒充已提交代码的真实模型运行。

验证命令：

```sh
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
python evaluation/smoke/model_smoke.py --output evaluation/smoke/evidence/model-preflight.json
python evaluation/smoke/audit_dependencies.py --output evaluation/smoke/evidence/parser-licenses.json
git diff --check
```

结果：离线回归 10/10 通过；模型预检按预期退出 2、`WAITING_INPUT`，没有网络调用。许可核对首次被 64 MiB 下载边界拒绝，查明 Linux wheel 为 68,938,796 字节，将审计工具上限改为 80 MiB 后重跑；最终结果以证据文件为准。未运行真实 Embedding/LLM、解析回归、数据库、服务启动、E2E 或独立 Q 审阅。

阻断：项目负责人待提供具体外部供应商/模型/维度/已注入凭证名及网络配置；目标硬件和价格/保留政策未确认。已询问并获得“外部 API”模式选择，尚无具体配置。不能用虚拟模型或固定回答代替真实调用。

## 后续按依赖推进

以下是阅读计划后的顺序，不代表已领取或已实现。当前只有 KF2-003 在处理；它的准备工作结束后仍保留 WAITING_INPUT。当前没有可验收的下一个核心任务。

| 顺序 | B 核心任务 | 当前尚缺的硬依赖 |
|---|---|---|
| 1 | KF2-003 模型/隐私/依赖/资源 | 无前序；缺真实运行输入 |
| 2 | KF2-007 Python 服务骨架 | KF2-004、005；005 后可准备隔离骨架，004 后接口验收 |
| 3 | KF2-010 文档/种子题 | KF2-002、003；不提前声明人工标注或合法私有资料已具备 |
| 4 | KF2-016 TXT/MD/PDF 解析 | KF2-007、010 |
| 5 | KF2-017 分段/来源定位 | KF2-016 |
| 6 | KF2-018 Embedding/索引写入 | KF2-003、011、017 |
| 7 | KF2-021 受控向量检索 | KF2-018、019 |
| 8 | KF2-022 单轮生成/证据 | KF2-003、021 |
| 9 | KF2-030 流式生成/取消 | KF2-004、022 |
| 10 | KF2-035 解析边界 | KF2-016、026 |
| 11 | KF2-037 60 题评测/留出 | KF2-010、021、022、026 |
| 12 | KF2-038 延迟/资源/费用 | KF2-003、031、037 |

KF2-045、046、047、048、051、054 六项属于默认禁用的增强任务；保持未启动，不以用户要求“逐个完成 B 的任务”推断可以跳过前置 V1 门槛。按计划一次处理一个主任务，不积压待审代码；缺依赖时记录缺口与可做准备。

Q 审阅包需要具体 BASE_SHA → TARGET_SHA、依赖状态、测试及未执行项；当前不填写虚构审阅结论。合并由 A 协调，本分支不自行合并到 main。
