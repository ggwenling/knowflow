# KF2-016：RAGFlow 一条解析调用链的核对与采纳

核对日期：2026-10-30（Asia/Hong_Kong）。仓库 infiniflow/ragflow，固定 SHA `9b325bc10c423b1610a1e24596c028d0ffceb792`。通过 GitHub API 获取该提交完整文件树及 raw 文件，源码哈希见 [来源证据](parse-source-evidence.json)。初次按旧 Python 路径请求返回 404；文件树核对发现该提交相关实现已在 Go 路径，因此没有编造旧 naive.py 的函数定位。

实际读取的文本调用链：

1. [TextParser.ParseWithResult，text_parser.go:49](https://github.com/infiniflow/ragflow/blob/9b325bc10c423b1610a1e24596c028d0ffceb792/internal/parser/parser/text_parser.go#L49) 接收字节输入并调用 charset.DecodeToUTF8。
2. [charset.DecodeToUTF8，charset.go:247](https://github.com/infiniflow/ragflow/blob/9b325bc10c423b1610a1e24596c028d0ffceb792/internal/parser/charset/charset.go#L247) 处理编码；TextParser 再调用 [normalizeTextNewlines:67](https://github.com/infiniflow/ragflow/blob/9b325bc10c423b1610a1e24596c028d0ffceb792/internal/parser/parser/text_parser.go#L67)，将 CRLF/CR 转为 LF。
3. [NewTextJSONItem，parse_result.go:105](https://github.com/infiniflow/ragflow/blob/9b325bc10c423b1610a1e24596c028d0ffceb792/internal/parser/parser/parse_result.go#L105) 把完整文本构造为解析单元，包在 [ParseResult:46](https://github.com/infiniflow/ragflow/blob/9b325bc10c423b1610a1e24596c028d0ffceb792/internal/parser/parser/parse_result.go#L46)。文本解析器注释明确分段边界属于后续 GeneralChunker，不在这个函数中按预算截断。

额外读取 MarkdownParser.ParseWithResult / parseWithState（markdown_parser.go:98/107），它对 Markdown AST 和图片有更复杂处理；PDF Parser.ParseRaw（internal/deepdoc/parser/pdf/parser.go:87）按引擎、页面与布局管线处理。未运行 RAGFlow 或其 OCR/版面模型，不声称 KnowFlow 已实现同等质量。

采纳：把解析输出与分段/索引分离，传入 bytes、返回结构化解析结果；本次 TXT/MD 一个原文块、PDF 一个非空页面一个块，后续分段属于 KF2-017。保留来源身份、文件哈希、PDF 物理页码和明确的空页记录。

调整：KnowFlow 当前只支持严格 UTF-8，且来源契约要求原始文本码点偏移，所以不采用通用编码猜测和 CRLF 归一化；BOM、CRLF、emoji、Markdown 标记原样保留。Markdown 不抓取远程图片、不渲染 HTML，不引入新的网络/路径读取面。PDF 初始解析采用 pypdf 6.21.4，直接报告不可提取/加密/异常文档，不增加 OCR、布局模型或伪造坐标。

源码页面与仓库 LICENSE 观察为 Apache-2.0。本记录只是路径/函数和设计思想研究，没有复制其实现或引入其代码依赖；本项目运行依赖的许可记录另见服务 evidence。本轮测试只证明合成样本的中文原文/页码/边界，真实多栏、字体、扫描质量和资源加固仍属于后续 KF2-035。
