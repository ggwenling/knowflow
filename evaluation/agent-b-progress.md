# Codex-B 执行记录

仓库 `/workspace/knowflow`；分支 `java`，由用户指定，从 `origin/main` 的 `7d5095b8bc987c1c7e6f4106887d3355fa88d4c2` 创建。B 角色负责 Python/RAG，与分支名称无关。

已读 V0.2 项目计划、协作手册与全部 B 任务卡。仓库没有 AGENTS.md、V1.1 设计包、冻结契约或服务代码；未启动 A/M/Q，不声称其他 Agent 已完成任务。仅修改本次任务明确允许的运行基线、许可记录及 B 的 evaluation 范围。

## 当前任务 KF2-003

状态：**IN_PROGRESS**。2026-10-30 10:28（Asia/Hong_Kong）新会话已解除网络/凭证阻断，真实模型冒烟通过；数据保留政策、部署资源、Q 审阅与集成验证仍待完成。下文旧失败记录保留为历史证据。

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

后续进展（2026-10-30，Asia/Hong_Kong）：用户提供两家供应商及凭证，并确认将误选的重排器改为硅基流动 `BAAI/bge-m3`（1024 维），LLM 为 DeepSeek `deepseek-flash`。冒烟已支持分别的 URL/凭证，独立 URL 不自动继承共享密钥；新增重排误配检查及 DeepSeek 非思考模式，离线回归现为 15/15 通过。

已按要求直接使用提供的凭证进行进程内真实尝试，Embedding 在连接阶段失败，没有继续调用 LLM。[失败证据](smoke/evidence/siliconflow-deepseek-live-attempt.json)绑定执行脚本哈希；[随后不带凭证的诊断](smoke/evidence/provider-connectivity.json)证明 `api.siliconflow.cn`、`api.deepseek.com` 均被云代理隧道 403 拦截。密钥未持久化、未进入证据或 Git，不能把网络错误当成密钥无效或模型不存在。

当时执行阻断是正式网络配置未放行两个 API 域名；该阻断现已解除，见下方新会话验证。目标硬件和数据保留政策仍待核验，官方价格已记录，实际费用需账单核对。细节及来源见 [供应商记录](smoke/provider-profile.md)。不能用虚拟模型或固定回答代替真实调用。

环境复查（2026-10-30 10:15，Asia/Hong_Kong）：用户表示已配置密钥与网络后，重新读取当前会话环境状态。观察为 spec revision `2`、`observations_current=true`、network policy `enforced`，但秘密绑定列表仍为空，生效允许列表仍无两个 API 域名。运行进程中也未检测到 `SILICONFLOW_API_KEY`、`DEEPSEEK_API_KEY` 或其他模型凭证变量名。两个不带凭证的 HEAD 连接均被代理隧道 403 拦截，未进行新的模型推理请求。记录只说明本会话当前运行实例的状态，不推断用户在配置界面是否已保存其他草稿。[本次证据](smoke/evidence/environment-recheck-20261030T101512.json)。状态保持 BLOCKED_NETWORK；需要将配置应用到本会话绑定的运行实例，而不是重复提供密钥。

## 新会话继承及验证（2026-10-30 10:27–10:28，Asia/Hong_Kong）

从原会话继承 B 职责，并取回 `java` 分支 `9ea732a`。新环境的 `EMBEDING_KEY`、`DEEPSEEK_API_KEY` 均 ready；网络 unrestricted/enforced，两个供应商的带鉴权 `GET /v1/models` 均返回 HTTP 200，选定模型均列在响应中。[脱敏鉴权证据](smoke/evidence/provider-auth-20261030.json)。当前 DeepSeek 变量为 `DEEPSEEK_API_KEY`，不是旧截图中的 `DEEPSEEP_API_KEY`。

首轮真实 Embedding 返回两条有效 1024 维向量；LLM 也成功返回，但未含汉字，触发 `CHINESE_ANSWER_MISSING`，保留[首轮证据](smoke/evidence/model-live-20261030.json)。将夹具问题明确为“包含汉字的完整中文句子”，未放松验证规则；重跑[真实冒烟通过](smoke/evidence/model-live-20261030-full-sentence.json)：Embedding 约 1.69 秒、33 tokens；LLM 约 1.55 秒、90 tokens，中文合成事实检查通过。两轮总计报告 223 tokens（Embedding 66、LLM 157），不是账单金额。每轮每端点一次、无自动重试。15 项离线回归通过；证据保留脚本/夹具哈希，`git_head` 为执行时父提交。

仅发送原创合成夹具，未输出或持久化密钥。`.env.example` 已改用当前绑定的变量选择器。模型别名可变，本次验证不代表生产容量、不可变模型版本或产品验收；KF2-003 不记 DONE，仍需核对数据政策和费用、完成 Q 审阅及按依赖集成。

## 后续按依赖推进

以下是阅读计划后的顺序，不代表已领取或已实现。当前只有 KF2-003 在处理；网络阻断已解除，尚未获得 Q 审阅与集成结论。当前没有可验收的下一个核心任务。

| 顺序 | B 核心任务 | 当前尚缺的硬依赖 |
|---|---|---|
| 1 | KF2-003 模型/隐私/依赖/资源 | 无前序；真实模型已通过，政策/费用与审阅集成待完成 |
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
