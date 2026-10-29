# KF2-003 解析依赖许可核对草案

本次核对仅覆盖两个直接候选，不等于服务完整依赖清单。机器证据与实际时间见 [parser-licenses.json](../../evaluation/smoke/evidence/parser-licenses.json)，可用 [核对脚本](../../evaluation/smoke/audit_dependencies.py)重现。下载 wheel 仅为核对，不安装或复制实现。

| 候选/固定核对版本 | PyPI 及 wheel 证据 | 许可及工程决定 |
|---|---|---|
| PyMuPDF `2.0` | [版本元数据](https://pypi.org/pypi/PyMuPDF/2.0/json)；Linux x86_64 `cp311-abi3-manylinux_2_28` wheel；`pymupdf-2.0.dist-info/COPYING` | 元数据及 COPYING 均为 `Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License`。保留为计划候选；选用前需确认项目分发/服务方式及适用许可义务或商业授权。尚未安装或验证解析质量。 |
| pypdf `6.21.4` | [版本元数据](https://pypi.org/pypi/pypdf/6.21.4/json)；`py3-none-any` wheel；`pypdf-6.21.4.dist-info/licenses/LICENSE` | 元数据 `BSD-3-Clause`；实际 LICENSE 已阅读，要求保留版权和许可/免责说明，不可借作者名背书。仅登记替代候选，尚未证明中文质量、页码与资源特性满足要求。 |

两个 wheel 的 SHA-256 与 PyPI 公布摘要匹配，许可文件哈希也记录在证据中。PyMuPDF 的 wheel COPYING 是简短双许可声明；它本身不构成已核对所有 AGPL 条款、商业合同及 MuPDF/字体等附带组件的证据。若选用，KF2-007 的依赖锁和完整许可清单需包含传递依赖、二进制附带组件及适用的完整许可材料。

当前冒烟代码只用 Python 标准库；运行时是 Python `3.12.14`。FastAPI、Uvicorn 和模型 SDK 尚未引入，不能将包仓库最新版本的元数据当成生产版本锁或兼容性测试。KF2-007 再锁定实际服务依赖并检查对应许可，不能靠此次两个候选的下载检查认定“三端可启动”。

采纳结论：许可风险已明确登记；**解析器最终选型待样本实验和独立审阅**。不在 KF2-003 中实现 KF2-016 的解析模块，也不改变公共契约或数据库迁移。
