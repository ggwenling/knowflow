# Q 修复复核包：Unicode 空白与 draft.4 消费升级

日期：2026-10-30（Asia/Hong_Kong）。原审阅目标：python@e4efd054880c506c1e57a76f28f6710e3d761016。当前状态 IN_REVIEW，作者只报告修复及实测，不代填 Q/A 的批准结论。

## 提交与共同版本

| 用途 | 精确 SHA |
|---|---|
| 合入 A 已发布 draft.4 的合并提交 | c7537d205bf04be59c2d087f42b04ec52827070f |
| B 修复提交（本次主要复核 target） | **2623a6282b2695a8ef96e3553a849729efd42403** |
| B 专属修复差异 | c7537d205bf04be59c2d087f42b04ec52827070f..2623a6282b2695a8ef96e3553a849729efd42403，仅 services/ai |
| A 的 draft.4 发布提交 | 895a1ba4655d9e875730d5bbeb65e570853c8d01 |
| A 最新交付 target（含 406 修复） | ec5c71c9be5a8766540fc48e174f215c0cf388ac（运行代码修复 24a07fd） |
| 实际干净集成候选 | **225124fbae8041efd67ee5e6ca5bf89fdbbe8884**，合并 B 修复与上述 A target |

共同消费版本 `0.2.0-draft.4`；Schema SHA-256 **ca66965155ff3e23209de18a44823a74429a8590df5adbd458571ef52b524e41**。A/B 使用的是 A 发布的同一文件；候选与 A target 的 contracts 和 services/api 逐路径差异为空。没有临时覆盖 Schema/examples、降低版本、忽略哈希或修改 A 的健康客户端。

## Q 问题一：纯空白 TXT/MD

旧实现 strip 的显式字符列表只覆盖 BOM、普通空格、Tab、CR/LF，漏掉 Unicode 空白及 VT/FF。修复改为逐码点判断：若所有字符均为 Python str.isspace() 空白或既有 BOM 允许字符，则返回 EMPTY_DOCUMENT。该判断不生成替代正文，不执行 strip/换行归一化/Unicode 归一化。

新增 22 个纯空白负例（TXT/MD × 11 类：U+00A0、U+3000、VT、FF、NEL、EM SPACE、Unicode 行/段分隔符、ASCII、BOM、混合 BOM）和 6 个有效正文回归（TXT/MD × 3 类边缘空白）。有效文本含中文/emoji，逐项核验正文原样、完整区间、码点数、原始文件 SHA、正文及 emoji 切片位置。原 10 份语料及 PDF 来源测试继续通过。

修复前只运行新增空白/正文测试，实际结果为 **18 failed / 10 passed**，复现 Q 指出的问题；修复后全部通过。源码与用例见 [解析模块](../services/ai/src/knowflow_ai/parsing.py)、[解析测试](../services/ai/tests/test_parsing.py)。[28 项断言证据](../services/ai/docs/evidence/unicode-whitespace-qfix.json)保存解析源码哈希、输入类别/文件哈希与固定结果，不保存正文。

## Q 问题二：明确升级 Java draft.4

版本常量和精确 Schema 哈希已升级，契约通过正常合并 A 原始提交引入；依赖锁未变化。保留缺失/错误 Schema 启动失败，并新增旧 draft.2、draft.3 和同 JSON 不同原始字节 Schema 的拒绝测试；不存在 legacy/忽略校验开关。

消费 A 的全部 **54** 个共享正负例；另新增 B 侧 **5** 个 InternalHealth 夹具（正确 draft.4、拒绝 draft.2/draft.3、额外字段、缺少 request_id），HTTP 健康输出也经 A 的 InternalHealth 定义验证。B 夹具是测试输入，不发布第二份 Schema。服务说明、消费记录及 Java 探针预期版本同步升级。

## 实际联调及结果

在独立 worktree `/workspace/knowflow-jp01-qfix` 的候选 225124f 上 frozen 安装并运行全部测试。Java 的代码/契约与 A target 原样一致。真实探针使用同一候选的 Java 源码/构建输入在临时目录启动原 Spring HTTP 服务，与真实 Uvicorn 进程连接；实际注入并调用 A 的 **AiInternalHealthClient**，不是只调用裸 WebClient。

新增关键断言：真实客户端成功接收实际 Python draft.4/UP/相同 request ID；同一客户端拒绝本地夹具的 draft.2 响应；保留其真实 5 秒总期限（测试验证超时根因及 4–7.5 秒范围）。原健康、401、404/405、不可达及 30 秒传输超时检查保留，总计 **8 项 Java 双服务集成测试通过**。

| 候选验证 | 实际结果 |
|---|---|
| Python 全量 | **65 passed**（含 32 个新增参数化/消费回归）；1 条既有 TestClient 上游弃用提示 |
| 公共契约 | **54 个结构样例通过** |
| 既有模型离线回归 | **16 项通过** |
| 真实 Java/Python 集成 | **8 项通过**，实际 AiInternalHealthClient 接受正确 draft.4；旧版本保护和 5 秒期限保留 |
| 候选干净性 | 工具 `--require-clean` 在运行前后均检查 git status 为空；Schema/样例/客户端/消费者源码哈希记录在证据 |
| 外部模型/数据库 | 本次集成均为 **0 次**；不作为数据库、真实模型或完整业务链验收 |

[实际 draft.4 集成证据](../services/ai/docs/evidence/java-python-draft4-qfix.json)记录 A target、候选 SHA/tree、准确源码哈希和干净性断言。新证据单独保存，不覆盖 e4efd05 的旧 draft.2 历史报告；旧报告不能代表升级后的消费版本。

本次使用 A 远端原始提交与最新修复进行配对，未改 A 所有的文件，也未代填其中央联调记录/批准。当前跨会话消息工具不可用；共享关系通过双方远端提交、合并候选和已推送的本复核包交接。A 可据相同候选复核并更新自己的记录。原 BLOCKED_CONTRACT_VERSION 对本候选已通过开发验证，但契约正式冻结与 Q/M 批准仍独立保留。

## 复现

检出候选 225124f 的独立干净工作区，从仓库根执行：

```sh
uv sync --project services/ai --frozen
uv run --project services/ai --frozen pytest services/ai/tests -q
uv run --project services/ai --frozen python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -q
uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py --require-clean --java-target ec5c71c9be5a8766540fc48e174f215c0cf388ac --output /tmp/draft4-qfix-result.json
```

Maven 需要会话代理时，最后一条加 `--maven-settings /path/to/local-settings.xml`，保留 TLS 校验且不提交代理凭证。候选工具强制使用本候选仓库的 Schema，不沿用外部 draft.2 文件。

此基线的 mvnw.cmd 以 CRLF 原始字节入库却声明 text 转换，普通检出可能产生纯换行假差异。隔离 clone 在确认工作文件原始字节与 HEAD blob 完全一致后，仅用本机 `.git/info/attributes` 的 `services/api/mvnw.cmd -text` 防止重复转换；未修改文件、索引或提交内容，未使用 assume-unchanged 隐藏改动。候选与 A 的 services/api 差异检查为空。复现者如遇同一问题，先核对原始字节再配置本地属性，不能以此忽略真实代码差异。

Q 请针对修复 SHA 和候选分别复核：空白分类/原文定位、精确契约升级/负例、实际 Java 客户端成功，以及证据绑定关系。本次没有声称 A 的全部数据库回归、生产容量或正式 DONE 已完成。
