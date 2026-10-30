# Python / JP-01 开发交付与 Q 复核包

此为 python@e4efd05 的历史交付。Q 指出的空白处理及 draft.4 消费升级已在后续修复，当前修复 SHA 和干净候选证据见 [Q 修复复核包](python-q-review-fixes.md)。

日期：2026-10-30（Asia/Hong_Kong）。分支 python；作者 B。本轮依据用户指令不等待旧复核，顺序交付 KF2-007、010、016 与 B 侧双服务联调。状态均为 **IN_REVIEW（开发验证通过）**，不是 Q APPROVED 或正式 DONE。

## 精确范围

- 共同基线 / BASE_SHA：150cd847a5750143fb6eb2c74c762962381952fe。
- 当前代码与集成测试 TARGET_SHA：7a99ddfe3b524ef47c4500a41db46fc0ae4c5f1f。
- 累计代码审阅范围：150cd847a5750143fb6eb2c74c762962381952fe..7a99ddfe3b524ef47c4500a41db46fc0ae4c5f1f。
- 后续本交付文档、任务记录及启动失败证据是纯记录补充，不更改运行代码；当前工作区消费代码和锁以以上 target 为准。

| 任务 | 首次交付提交 | 交付物 |
|---|---|---|
| KF2-007 | 9f43750766f301609b7890379356ab84ba5b21b3 | FastAPI、环境配置/密钥校验、内部认证、健康、请求 ID、统一错误、契约消费者、模型/执行适配边界、依赖与许可证记录 |
| KF2-010 | fc98d575d1a1b3095adaff867c5fa7a2edd1010f | 10 份原创合成资料、15 道中文问题、版本/哈希/原文摘录与码点/行号、12开发/3留出、3道无答案、可复现生成和校验 |
| KF2-016 | 8cd9139c71af47dae6d8b3bede2495539d7680c9 | 保留原文的 UTF-8 TXT/MD 及 pypdf 6.21.4 文本 PDF 解析、来源身份/页码、固定错误、5种PDF样本、RAGFlow固定提交研究 |
| JP-I1 B 侧 | 7a99ddfe3b524ef47c4500a41db46fc0ae4c5f1f | 原 Java Spring 服务/客户端与真实 Python HTTP 的 5 项集成检查；B 的临时副本测试工具 |

## 共享契约与所有权

消费 A 的 c67d0038d93a4af514bba4ee70ac49b1c1062318 / 0.2.0-draft.2，Schema SHA-256 edc9ada0bb5de23ddf69f96c9172b3fc3719f4b3111d5d35718f2717efae8087。39 个结构样例全部在 Python 消费者及共享校验器通过。启动检查精确哈希；部署需要挂载同一只读 Schema，不能升级文件却不升级消费者。

没有修改 contracts、Flyway、Java 源码、infra、前端或 main。内部 health 的路径/响应与 request ID 接受规则记录在 B 的 [消费提案](../services/ai/docs/contract-consumption.md)，仍待 A 纳入下一候选；本线未发布平行正式 Schema。B 的数据库字段/角色/fencing 需求在同一文件，Python 未申请无约束写权限、未写任务/活动版本状态。

## 实际验证

| 层级 | 结果与边界 |
|---|---|
| Python 服务/数据/解析回归 | 33 项通过；其中服务11、数据5、解析17（参数化展开）；全新临时虚拟环境 frozen 安装再次通过 |
| 配置与进程 | 真实 Uvicorn 8 项断言通过；另用真实子进程验证密钥缺失、过短、含控制字符的 3 种启动失败；均非零退出、固定错误且日志不含密钥 |
| 共享契约 | 39 项结构样例通过；不代替权限、租约/幂等和数据库事务验收 |
| 既有模型客户端 | 原 16 项离线回归通过；本轮线上模型调用次数 0 |
| 资料与来源 | 10 份/15题全部版本/哈希/摘录/码点/行号校验通过；生成器重复执行字节一致；作者逐题读原文核对，Q 复核未进行 |
| 解析进程内样本 | 10份语料 + 5类PDF，共15个样本断言通过；保存结果码/计数/哈希，不保存提取正文 |
| Java 原有回归 | Maven verify，11项测试通过；首次直连 Maven Central 失败，配置会话代理后成功，TLS校验未关闭 |
| 双服务 | 临时副本启动原 Java Spring HTTP 服务与真实 Uvicorn；5项 Java WebClient 检查通过，包括健康、request_id、401/404/405、不可达及原配置30秒响应超时 |
| 安装/包 | uv.lock frozen 全新环境安装通过；源码分发包和 wheel 构建成功；运行/传递依赖哈希及 Linux 实装许可元数据已记录，未安装平台包仍未知 |
| 仓库 | git diff --check通过；扫描仓库文件未发现环境实际绑定的两家模型凭证值 |

证据位于 [services/ai/docs/evidence](../services/ai/docs/evidence/process-smoke.json)：process-smoke.json、startup-failures.json、parser-smoke.json、java-python-smoke.json、dependency-licenses.json。各条保存执行时父提交或源码哈希；父提交不假装包含尚未提交的脚本。最终 target 的源码/契约/锁哈希与证据已核对一致。

## 复现

先阅读 [服务说明](../services/ai/README.md)，使用 Python 3.12、uv 0.12.23 及 Java 21；Maven Wrapper 为现有工程版本。启动真实服务时共享密钥通过运行环境注入，测试脚本自行生成临时合成密钥。

```sh
uv sync --project services/ai --frozen
uv run --project services/ai --frozen pytest services/ai/tests -q
uv run --project services/ai --frozen python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
python evaluation/data/tools/validate_seed.py
uv run --project services/ai --frozen python services/ai/tools/process_smoke.py
uv run --project services/ai --frozen python services/ai/tools/parser_smoke.py
uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py
# 有会话代理需求时，最后一条增加 --maven-settings /path/to/local-settings.xml
```

真实进程测试会更新本工作区的证据时间，Q 应在隔离工作区复现并保留原 target 的证据版本。原 Java verify 在 services/api 运行 ./mvnw verify（必要时使用本机 -s settings）。启动失败补充证据可通过将 KNOWFLOW_INTERNAL_SHARED_SECRET 依次设为缺失、过短、含换行，在真实 uvicorn factory 启动时核对非零退出/固定错误/日志脱敏来复现，不使用生产密钥。

## 未执行与明确限制

- 没有真实用户、生产文档、生产硬件、真实模型业务调用、数据库/受限写入、上传/索引/检索/问答、前端或 M1 验收。健康不是模型/数据库就绪检查。
- Java 对外业务网关尚无调用入口，上游异常到公开 502/504 的业务映射仍需 A 实现；本探针验证的是原 WebClient 传输异常与 Python 错误体。30秒测试目标是独立本地慢响应夹具，未伪造 Python 业务端点。
- pypdf 为首轮文本PDF基线；多栏顺序、更多字体、OCR、CPU/内存隔离、解压展开与并发加固未验证，留 KF2-035。默认大小/页数/字符上限只是开发候选，不是生产容量承诺。
- 留出参考答案公开，因此不是盲测或独立质量结论；未报告模型正确率或用户收益。种子资料只覆盖原创合成领域，后续037仍需独立60题及留出。
- 当前 TestClient 的 httpx 集成有上游弃用提示，33项测试仍通过；运行时没有使用 TestClient。
- 原 Java Windows wrapper 因基线换行属性在 Git 中显示纯换行差异，但原始字节与 HEAD 完全相同，本线没有提交该文件。

## A 下一步接入 / Q 核查

A 可合入本代码 target，在其集成候选记录双方 SHA，发布 health/request_id 的公共候选修订，并完善 Java 对外错误映射；按消费提案交付迁移/受限角色及执行 fencing 后，B 才接 KF2-018。根 README 的中央当前状态可由 A/M 在集成时更新为本 Python 交付，B 本轮保留其所有权边界。

Q 优先核查认证绕过/重复头、错误和日志泄密、错误模型/维度校验、未授权路由是否启用、原文偏移/空页、加密/扫描/异常PDF、数据许可与标注可复核性、依赖许可覆盖范围，以及各证据是否忠于真实执行层。Q 结论由 Q 按 SHA 填写，本交付不代填批准。
