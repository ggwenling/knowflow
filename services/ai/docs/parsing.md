# KF2-016 TXT / MD / 文本型 PDF 解析

开发实现已交付，状态 IN_REVIEW。依赖 KF2-007/010 为本轮已通过开发验证的候选输入；用户授权继续，不宣称已获 Q 批准。采用 pypdf 6.21.4（BSD-3-Clause，实际 wheel/依赖哈希与许可元数据见锁及 dependency-licenses.json）作为首轮 PDF 基线；未安装 PyMuPDF，不沿用其 AGPL/商业许可选择。KF2-003 时 pypdf 只是候选，本任务才明确安装并实测选用。

入口 knowflow_ai.parsing.parse_document(data: bytes, format, document_id, content_version_id, file_id, limits)。这是内部纯函数，不注册 HTTP 处理路由、不接任意 URL/磁盘路径、不读数据库、不发布索引。调用者后续必须在可信服务边界完成授权、来源哈希核验与租约检查，解析成功不等于任务有权执行或已 READY。

输出 ParsedDocument 保存三个来源身份、原始文件 SHA-256、格式、parser_profile、字符总量、总页数/空页及按序 TextBlock。TXT/MD 严格 UTF-8，保留 BOM、CRLF、原始 Markdown 和 Unicode 码点；块区间从 0 起、右端不含，未经归一化。PDF 提取非空页文本，页码从 1 起，空白中间页不使后续物理页号前移；没有页面坐标时不编造。PDF 字符顺序来自 pypdf，不宣称恢复了多栏阅读顺序。

固定失败代码：EMPTY_DOCUMENT、INVALID_UTF8、INVALID_TEXT、UNSUPPORTED_FORMAT、INVALID_INPUT_TYPE、INVALID_SOURCE_IDENTITY、FILE_TOO_LARGE、TEXT_TOO_LARGE、INVALID_PDF、PDF_ENCRYPTED、PDF_PAGE_LIMIT、PDF_NO_TEXT。PDF_NO_TEXT 仅表示没有可提取文字（包括扫描/图像和空白页），不能仅靠这个错误断言文件一定是扫描件。加密 PDF 即使可能用空密码打开也拒绝，不猜密码。错误不包含输入、路径或第三方异常正文；pypdf 诊断不传播到应用日志。

开发默认上限沿用待验证提议：8 MiB / 200 PDF 页 / 200,000 码点。测试覆盖边界拒绝，不把它当目标机器的容量承诺；PDF 展开、CPU/内存隔离、并发与硬超时尚未加固，属于 KF2-035。此组件当前不挂在可达的上传处理路由，未提供 OCR、DOCX、分段、Embedding、检索或生成。

回归使用全部 10 份种子文档核验偏移/答案摘录，并使用 5 个完全原创 CC0 PDF：中文三页（中间空白）、空白、图像、加密、损坏。生成源和 SHA 清单位于 tests/fixtures/pdf 和 tools/build_pdf_fixtures.py；加密包含随机性，提交的文件哈希是该样本版本，不宣称重复生成加密文件字节一致。ReportLab/Pillow 仅用于开发样本生成，不是运行解析依赖。

复现（仓库根）：

```sh
uv sync --project services/ai --frozen
uv run --project services/ai --frozen pytest services/ai/tests/test_parsing.py -q
uv run --project services/ai --frozen python services/ai/tools/parser_smoke.py
```

RAGFlow 研究见 docs/research/ragflow/parse-chain.md，固定具体提交/文件/函数；未运行其 OCR/布局模型，不把源码阅读当解析质量实测。未对生产文档、目标硬件或真实用户资料作结论。
