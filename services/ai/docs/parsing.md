# KF2-016 TXT / MD / 文本型 PDF 解析

开发实现已交付，状态 IN_REVIEW。依赖 KF2-007/010 为本轮已通过开发验证的候选输入；用户授权继续，不宣称已获 Q 批准。采用 pypdf 6.21.4（BSD-3-Clause，实际 wheel/依赖哈希与许可元数据见锁及 dependency-licenses.json）作为首轮 PDF 基线；未安装 PyMuPDF，不沿用其 AGPL/商业许可选择。KF2-003 时 pypdf 只是候选，本任务才明确安装并实测选用。

入口 `knowflow_ai.parsing.parse_document(data, format, document_id, content_version_id, file_id, limits)` 是纯函数，本身不是 HTTP 路由、不接任意 URL/磁盘路径、不读数据库、不发布索引。draft.7 Python worker 由认证的 `POST /internal/v1/index-executions` 接收 Java 派发，按有效 lease 读取来源并核验 SHA-256 后再调用此解析函数；租约授权和 READY 发布仍由 Java 负责。

输出 ParsedDocument 保存三个来源身份、原始文件 SHA-256、格式、parser_profile、字符总量、总页数/空页及按序 TextBlock。TXT/MD 严格 UTF-8；仅由 Python str.isspace() 认定的 Unicode 空白（包括 U+00A0、U+3000、VT/FF 等）和 BOM 构成的内容返回 EMPTY_DOCUMENT。该检测只分类，不修改正文；有效文本保留 BOM、CRLF、原始 Markdown 和 Unicode 码点；块区间从 0 起、右端不含，未经归一化。PDF 提取非空页文本，页码从 1 起，空白中间页不使后续物理页号前移；没有页面坐标时不编造。PDF 字符顺序来自 pypdf，不宣称恢复了多栏阅读顺序。

固定失败代码：EMPTY_DOCUMENT、INVALID_UTF8、INVALID_TEXT、UNSUPPORTED_FORMAT、INVALID_INPUT_TYPE、INVALID_SOURCE_IDENTITY、FILE_TOO_LARGE、TEXT_TOO_LARGE、INVALID_PDF、PDF_ENCRYPTED、PDF_PAGE_LIMIT、PDF_NO_TEXT。PDF_NO_TEXT 仅表示没有可提取文字（包括扫描/图像和空白页），不能仅靠这个错误断言文件一定是扫描件。加密 PDF 即使可能用空密码打开也拒绝，不猜密码。错误不包含输入、路径或第三方异常正文；pypdf 诊断不传播到应用日志。

开发默认上限沿用待验证提议：8 MiB / 200 PDF 页 / 200,000 码点。KF2-035 增加了可终止子进程隔离：索引 worker 对解析子进程实施 15 秒墙钟限时，父进程限制输出最多 4 MiB，并在超时、请求取消或输出超限时杀死并回收子进程。Windows 使用 Job Object 限制子进程内存；其他平台使用 `RLIMIT_AS` 限制虚拟地址空间，若操作系统不支持限制则失败关闭。当前 Windows 开发机已实测 512 MiB Job Object 限制会使 600 MiB 分配触发 `MemoryError`，并测试了超时、取消、超限输出时的子进程清理，以及 TXT/PDF 隔离解析与原解析器结果一致。15 秒和 512 MiB 是本轮候选开发限额，不是生产容量或吞吐承诺；未在部署目标 Linux 主机验证 `RLIMIT_AS`，也未对生产文档、并发负载或目标硬件作测量。Python 内部索引路由不接收浏览器上传、不负责授权、任务状态或索引发布。解析器本身不提供 OCR 或 DOCX；分段、Embedding、检索和生成由 worker 后续组件负责。

回归使用全部 10 份种子文档核验偏移/答案摘录，并使用 5 个完全原创 CC0 PDF：中文三页（中间空白）、空白、图像、加密、损坏。生成源和 SHA 清单位于 tests/fixtures/pdf 和 tools/build_pdf_fixtures.py；加密包含随机性，提交的文件哈希是该样本版本，不宣称重复生成加密文件字节一致。ReportLab/Pillow 仅用于开发样本生成，不是运行解析依赖。

复现（仓库根）：

```sh
uv sync --project services/ai --frozen
uv run --project services/ai --frozen pytest services/ai/tests/test_parsing.py -q
uv run --project services/ai --frozen python services/ai/tools/parser_smoke.py
```

RAGFlow 研究见 docs/research/ragflow/parse-chain.md，固定具体提交/文件/函数；未运行其 OCR/布局模型，不把源码阅读当解析质量实测。未对生产文档、目标硬件或真实用户资料作结论。
