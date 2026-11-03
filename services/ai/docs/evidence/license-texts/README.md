# Python 许可证原文证据（#14 修复）

本目录保留从本机已安装的精确版本 distribution，以及本机 uv 缓存中的 `uv_build==0.12.23` distribution 复制出的 9 份上游许可证文件。没有改写其版权、条款或换行；`.gitattributes` 使用 `-text` 保证 Git blob 与采集哈希一致。

逐文件来源路径、SHA-256、原始 metadata 及版本见上级 `dependency-licenses.json`。适用实施基线为 `be958d4848285ebcc32a299079ed6dc94d149b08`；锁文件的跨平台 LF 指纹为 `d5b6adc8cdaae9511748cb5b181c207c75f7ac4e1eaaa3e156eb2a26292a8935`。Windows 原始 CRLF 指纹单独记录，不能与 Linux 原始字节哈希直接混用。

| 来源包 | 原始证据 | 处置 |
|---|---|---|
| colorama 0.4.6 | 上游 LICENSE.txt，包含版权、三个再分发条件与免责声明 | 保留原文；不再以宽泛 BSD classifier 代替许可证文本。 |
| psycopg / psycopg-binary 3.3.6 | 各自 LICENSE.txt 和 LGPL-3.0-only metadata | 分别留存，不能因库名相近省略 binary 分发包。 |
| tzdata 2026.6 | 版权声明与 LICENSE_APACHE 全文 | 两文件均留存，不只记录表达式。 |
| ReportLab 5.1.0 | dist-info/LICENSE 与 reportlab/license.txt | 两份均保留，原始版权年份差异不擅自改写。 |
| uv_build 0.12.23 | LICENSE-APACHE 与 LICENSE-MIT，metadata 表达式为 MIT OR Apache-2.0 | 属隔离构建依赖；来源为本机精确版本缓存，不误称运行时已安装。 |

这些是实现者采集的可核对证据，状态为“待独立审阅”。没有对全量运行镜像、wheel 内捆绑的 native 库、LGPL 对应源码、再链接／替换方式、完整 NOTICE 和产品再分发义务签收。`knowflow-ai` 未声明项目自身许可证，仍标“未完成”，须权利人决定。此目录不替代发行许可包，也不授权 KnowFlow 自身代码。
