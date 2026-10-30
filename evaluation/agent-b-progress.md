# Codex-B 执行记录

仓库 `/workspace/knowflow`；分支 `java`，由用户指定，从 `origin/main` 的 `7d5095b8bc987c1c7e6f4106887d3355fa88d4c2` 创建。B 角色负责 Python/RAG，与分支名称无关。

已读 V0.2 项目计划、协作手册与全部 B 任务卡。仓库没有 AGENTS.md、V1.1 设计包、冻结契约或服务代码；未启动 A/M/Q，不声称其他 Agent 已完成任务。仅修改本次任务明确允许的运行基线、许可记录及 B 的 evaluation 范围。

## KF2-003 状态和历史准备

当前状态：**IN_REVIEW**。2026-10-30 10:39（Asia/Hong_Kong）python 分支再次真实调用成功；供应商 API 条款适用性、生产资源、Q 审阅和集成仍待完成。此前记录的阻断为历史状态，下文证据均保留。

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

以下顺序为 B 线任务图，不代表已领取或已实现。KF2-003 在 Q 审阅和集成前未关闭；网络阻断已解除。其他角色任务不因本表而认领。

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

## 追加执行（2026-10-30，本 Codex 会话承接）

用户另行要求 KF2-002、003、005 在 python 分支交付并 push。KF2-002 和 KF2-005 原负责人为 M，本会话按指派接管其文件范围；KF2-003 仍为 B。场景选择“项目规范与接口查询”。由已有 Q 会话独立审阅，本会话仅准备审阅包，不代填审阅结论。

执行提交及审阅 SHA 见 docs/tasks/execution-log.md 和 docs/reviews/KF2-002-003-005-review.md。KF2-002、003、005 当前均为 IN_REVIEW，未通过审阅或真实集成前不记 DONE。真实双模型冒烟在 python 分支重跑通过；合成试填不是真实用户证据。KF2-001 的 V1.1 设计包缺口未解除。

## JP-01 / KF2-007 开发交付（2026-10-30，Asia/Hong_Kong）

用户授权不等待现有 Q 复核，按共同计划继续 Python 开发。基线 150cd847a5750143fb6eb2c74c762962381952fe；分支 python；只写 services/ai、evaluation 和本线资料/研究目录。Java Windows wrapper 受既有换行属性影响被 Git 报差异，原始字节与 HEAD 完全一致，本线未修改或提交它。

KF2-007：FastAPI 可运行骨架、内部 Bearer 恒定时间认证、健康/请求 ID/统一错误、严格消费现有共享 Schema、模型/索引/检索接口类型、超时/取消/模型 ID 与向量校验边界；业务执行入口未注册。公共契约未修改，新增健康报文由 services/ai/docs/contract-consumption.md 提给 A 发布。依赖锁、哈希导出和 Linux 安装环境许可元数据齐备。

开发验证：11 项 Python 服务测试、39 个共享契约结构样例、既有 16 项模型离线回归通过；真实 Uvicorn 进程 8 项断言通过；全新 /tmp 虚拟环境按 frozen 锁安装后同一进程冒烟通过。首轮包构建因空模块尚未创建失败，补齐模块后安装成功；一次辅助脚本工作目录误设造成临时嵌套目录，已清理，未纳入提交。所有失败不冒充通过证据。

真实 Python 进程证据见 services/ai/docs/evidence/process-smoke.json，记录执行时父提交及 app 哈希。依赖元数据见 dependency-licenses.json；未安装平台依赖保留未知。Java verify 首次因 Maven 未使用会话代理而网络失败，已按环境技能配置会话代理继续验证；双服务证据另补，不把本轮 Python 进程冒烟冒充 Java WebClient。未调用外部模型，未写数据库/Java 状态。

状态 IN_REVIEW（开发验证通过；正式契约/Q/集成验收未完成）。KF2-007 target 由 git log -- services/ai 定位，后续交付汇总绑定具体 SHA。接下来按 JP-01 继续 KF2-010，再 KF2-016。

## JP-01 / KF2-010 开发交付（2026-10-30，Asia/Hong_Kong）

基于 KF2-007 提交 9f43750 顺序推进资料集。原创「青竹」合成资料 10 份（TXT/MD）、种子问题 15 道（12 有答案、3 拒答），与真实用户数据分开。每题答案要点、摘录、原始码点区间/行号、内容版本及来源哈希均可核验；资料 CC0-1.0，未引用/上传任何用户资料。作者逐题核对过原文；Q 独立抽查仍待进行。12 开发 / 3 留出，相关问题不跨分区；公开仓库留出不是盲测，质量分数未测。

验证：15 题全部来源/版本/哈希/位置检查通过；5 项数据回归（包括篡改原文、偏移、版本、分区泄漏）通过；生成器重复执行字节级一致。准确复现命令及标注规则见 docs/evaluation/dataset.md。状态 IN_REVIEW（开发验证通过），前序 002/003 的复核依赖未被伪报完成；用户按 JP-01 授权继续 KF2-016。

## JP-01 / KF2-016 开发交付（2026-10-30，Asia/Hong_Kong）

基于 KF2-010 提交 fc98d57 实现内部纯解析函数，不开放 HTTP、不获取 URL/文件路径、不写业务状态。TXT/MD 严格 UTF-8，保留 BOM/CRLF/Markdown/emoji 与原始码点偏移；PDF 选择并锁定 pypdf 6.21.4（BSD-3-Clause）作为首轮基线，保留物理页码、空白页及来源身份/文件哈希，不安装 PyMuPDF、OCR 或伪造坐标。003 阶段的“pypdf 候选未安装”是历史；本 016 才选择安装和验证。

验证：全套当前 33 项 Python 测试通过，包含 17 项解析测试场景（参数展开计数）；10 份合成资料的全部引用保持匹配、中文三页 PDF 的页码仍为 1/3 且空白页 2 被记录；扫描/图像无文本、空白、加密、损坏与大小/页数/字符限制失败样例通过。parser_smoke 保存 15 个样本的固定结果代码与哈希，不保存提取正文。资源限额是开发提议，不代表生产加固；CPU/内存展开与并发隔离留 KF2-035。

RAGFlow 研究固定 SHA 9b325bc10c423b1610a1e24596c028d0ffceb792，实际阅读 Go 路径 TextParser.ParseWithResult→charset.DecodeToUTF8→normalizeTextNewlines→NewTextJSONItem，已记录路径/函数/源码哈希和采纳差异；旧 Python 路径 404 后核对文件树，没有编造源码定位。未复制实现或运行其 OCR/版面模型。研究见 docs/research/ragflow/parse-chain.md。

uv.lock 与运行依赖哈希导出同步更新，开发生成 PDF 的 ReportLab/Pillow 与运行解析 pypdf 分开。状态 IN_REVIEW（开发验证通过；Q 和最终集成未完成）。后续 KF2-017/018 不属于本 JP-01 首批开发交付，018 仍需 A 的迁移与有界写入授权。

## JP-01 / 双服务开发联调（2026-10-30，Asia/Hong_Kong）

Java 网络首轮失败后，读取 cloud-environment-runtime 技能和当前网络状态，使用会话代理生成 /tmp Maven settings；TLS 验证保持开启，未保存代理/模型凭证到仓库。既有 Java Maven verify 的 11 项测试全部通过。

B 线工具 services/ai/tools/java_python_smoke.py 将原 Java 源码/构建输入复制到临时目录，附 B 自有测试探针，真实启动 Spring HTTP 服务、Uvicorn HTTP 服务，调用原 Java WebClient 配置。5 项集成测试通过：双方健康与 request_id、缺失/错误凭证、404/405 统一错误与 Allow、不可达连接、原 Java 30 秒 responseTimeout（慢目标为单独本地夹具）。两端日志未出现测试共享密钥；模型凭证不传入测试进程，未请求模型或数据库。证据绑定 Python app、Java 客户端配置和探针哈希；未修改 A 所有的 Java 源码、contracts、Flyway 或中央联调记录。

此为 B 提供的开发联调证据，不代替 A 的正式集成候选/Q。Java 对外网关尚无调用入口，上游异常到公开 502/504 的业务边界映射仍待 A 接入；不把 transport 异常检查说成公开网关已验收。KNOWFLOW_INTERNAL_SHARED_SECRET 共享方式与内部 health 路径仍是待 A 发布的新候选约定。

最终环境复现：全新虚拟环境 frozen 同步后 33 项 Python 测试通过，源码分发包和 wheel 构建成功；已有 39 项契约结构样例及 16 项模型离线回归通过。本轮所有模型线上调用次数为 0。三个 KF2 任务均 IN_REVIEW（开发验证通过），未伪报批准或正式 DONE。详细 SHA 和可复制命令见 evaluation/python-jp01-delivery.md。
