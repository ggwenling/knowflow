# Issue #14 日志脱敏审计

- 审计基线：`local@25c8dc392318f724b366cf2d76e13b1856dd0368`
- 审计日期：2026-11-03（Asia/Hong_Kong）
- 范围：AI 服务、解析子进程、AI 到 Java 网关交接，以及 Java API 中找到的请求阶段日志和上传存储失败日志。只使用代码审阅和已有合成测试证据；本报告没有调用真实模型、对象存储或生产服务。
- 结论：**发现一处应修复的日志内容暴露路径；其余所检查的 AI 阶段日志采用有限字段。未完成所有框架、反向代理及部署日志的运行时捕获验证。**

## 发现

### L1 · Java 上传失败日志直接写入存储异常消息

- 位置：`services/api/src/main/java/com/knowflow/api/document/DocumentService.java:69`
- 代码在 `ObjectStoreException` 处理分支中记录 `storageFailure.getMessage()` 和 cause 类名。异常消息来自存储适配器，当前接口没有在日志边界将该字段约束为固定错误码或经过过滤的字段。具体部署的 SDK/异常消息格式未在此基线下通过运行时捕获确定。
- 风险：如果底层异常消息包含请求 URL、对象键、服务端响应片段或其他诊断文本，日志会原样持久化该文本。当前日志调用没有记录文件正文或上传字节，但也没有证据证明异常文本必然不带敏感信息。
- 验证边界：`services/ai/tests/test_recovery_e2e.py` 的伪存储日志样例只覆盖通用 503/连接错误字符串；没有用唯一敏感标记注入异常消息并断言 Java 捕获日志不含该标记。因此这条路径判为静态发现，未声称已通过运行时脱敏测试。

## 已检查路径

| 路径 | 观察与证据 | 判定 |
|---|---|---|
| AI 请求鉴权与未处理异常 | `services/ai/src/knowflow_ai/app.py` 的 ASGI 中间件读取 Authorization 用于校验；异常处理分支注释说明不输出原始异常，并只在响应未开始时返回固定 `INTERNAL_ERROR`。 | 静态审查通过；未做完整 ASGI 日志捕获。 |
| AI 流式错误、取消与超时 | `streaming.py` 记录请求 ID、阶段、结果和固定错误码；通用异常分支不附加异常对象、问题文本或生成内容。 | 静态审查通过。 |
| AI 检索/生成/Embedding 阶段 | `answering.py` 与 `streaming.py` 记录请求 ID、阶段、时长、数量、usage 和 outcome；未看到将问题、上下文、模型响应或凭证作为日志参数。 | 静态审查通过；未模拟 provider 响应中的敏感标记。 |
| PDF 解析及子进程 | `parsing.py` 将 pypdf logger 的传播关闭并挂 `NullHandler`；`parser_process.py` 将子进程 stderr 指向 `DEVNULL`，解析失败映射为固定错误码。`test_parsing.py` 断言 pypdf 错误场景没有 caplog 记录，并检查错误不回显输入正文。 | 已有合成单测通过（见下方命令）；不覆盖所有第三方依赖自身日志。 |
| Python 解析失败日志 | `worker.py` 记录 `str(ParseFailure)`，解析器当前以固定错误代码构造这些异常。 | 静态审查通过，错误代码有限；未来新增异常消息需维持该约束。 |
| Java 问答错误路径 | `QuestionService.java` 记录 request ID、阶段、时长和规范化 failure code，不传入异常消息或 request/answer 内容。 | 静态审查通过。 |
| Java 框架错误响应 | `application.yml` 将 Spring error message、binding errors、stacktrace 和 exception 输出关闭。 | 配置静态审查通过；没有启动服务抓取全量框架及容器日志。 |
| Java 上传存储错误 | `DocumentService.java:69` 记录异常消息。 | **发现 L1。** |

## 验证命令与结果

- `services/ai/.venv/Scripts/python.exe -m pytest tests/test_parsing.py`（工作目录 `services/ai`）：**53 passed**，1.64 秒。覆盖固定解析错误和输入正文不回显断言。
- `git diff --cached --check`：对本报告暂存差异执行，通过，无空白错误。
- 未对 Java 服务启动合成对象存储失败注入，也未对 Python stream 的异常分支做全量 `caplog` 标记扫描。未验证反向代理、容器运行时、云日志采集器或运维平台的配置和保留策略。
- 无真实凭证、文档内容或用户输入写入报告。报告中不包含合成敏感标记原文。

## 修复建议及复测标准

- 对 L1，将日志字段限制为固定阶段、错误码和 cause 类型，或采用经过审查的结构化存储错误分类；不要直接记录不受控异常消息。
- 增加合成异常消息测试，注入独特标记并断言输出日志没有该标记，同时保留请求 ID、失败阶段和稳定错误分类。
- 对请求认证、通用异常、流式失败/取消、解析器失败及 Java 上传失败分别捕获日志，检查凭证、正文、问题、模型输出、URL 中的凭证和异常响应片段均不会出现。
- 此报告只记录审计基线上的现状；没有修改业务代码，L1 仍待修复和复核。
