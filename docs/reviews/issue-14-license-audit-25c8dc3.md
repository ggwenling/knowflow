# Issue #14 依赖许可证审计

> 2026-11-03 Terra High 处置更新：原始正文保留 `25c8dc3` 审计事实；原“36/39、缺 3 包”的证据问题已重新采集处理。当前是**证据已补充，待独立审阅；全量发行许可证签收未完成**。见末尾更新，不把实现者采集等同独立批准。

- 审计基线：`local@25c8dc392318f724b366cf2d76e13b1856dd0368`
- 审计日期：2026-11-03（Asia/Hong_Kong）
- 范围：基线中的 Python AI 服务及其评估/解析工具直接依赖、`uv.lock` 解析依赖、开发依赖和隔离构建依赖。此报告核对仓库记录与本机安装元数据，不构成法律意见或对发行合规的批准。
- 未覆盖：Java/Maven 及 Web/npm 依赖的完整传递树与许可证文本；容器基础镜像和操作系统软件包；第三方模型、数据集及用户内容的权利。它们没有纳入下表的许可证结论。

## 结论

**未能完成全量许可证签收。** 当前锁文件包含 39 个 package 项，已提交的许可证证据 JSON 只有 36 项，且记录的锁文件 SHA-256 与基线文件不符。因此该 JSON 不能证明当前锁文件所有包均已核查。锁文件及元数据里存在许可证字段缺失或表达不明确的包，需在形成发行清单前核实上游实际许可证文本。

## 检查结果

| 项目 | 结果 |
|---|---|
| 直接运行依赖 | `services/ai/pyproject.toml` 固定 FastAPI、HTTPX、jsonschema、psycopg[binary]、Pydantic、pypdf、rfc3339-validator、uvicorn 版本。 |
| 开发依赖 | pytest、pytest-asyncio、ReportLab 与项目运行依赖分组记录于 `pyproject.toml` 和锁文件。报告须区分仅测试/评估用途的依赖与发行运行依赖。 |
| 锁定包数 | 39 个 `uv.lock` package 项。锁文件也含不同平台 wheel 和标记依赖，平台未安装不能从本机安装元数据推断其许可证。 |
| 现有证据覆盖 | `services/ai/docs/evidence/dependency-licenses.json` 有 36 行；其中 35 行标为已安装，1 行标为未安装。它的 `lock_sha256` 为 `b19e93809daf649e1b2050a29a1bc1e9ac4e39fc8699a7f95b28b1bfed7c58a7`，当前基线 `uv.lock` 的 SHA-256 为 `a9bc533d8a029a6d6c10297bddeaf83cea11420d80427fb824ee790894d357c2`。 |
| 缺少的锁定条目 | 证据 JSON 未列出 `psycopg==3.3.6`、`psycopg-binary==3.3.6`、`tzdata==2026.6`。未安装条目 `colorama==0.4.6` 标记为未核查。 |
| 未分类项 | 已安装的本地项目 `knowflow-ai==0.1.0` 无许可证表达式、许可证文本或分类器记录。已有证据中 `reportlab` 的许可证字段是自由文本，不是标准 SPDX 表达式。应保留上游原始许可文本再人工核验。 |
| 独立解析证据 | `evaluation/smoke/evidence/parser-licenses.json` 只涉及两个解析 wheel。该证据范围小于服务完整依赖树，不能补齐上述缺项。 |
| 构建依赖 | `pyproject.toml` 使用 `uv_build==0.12.23` 隔离构建。现有证据将其标记为 isolated build dependency，未提供该构建依赖实际安装包的许可证文件或哈希。 |

许可证 metadata 中可见 MIT、BSD-2-Clause、BSD-3-Clause、Apache-2.0、MPL-2.0、PSF-2.0、MIT-CMU 和 Apache-2.0 OR BSD-2-Clause 等标识。单凭这些标识不判断项目的 notice、源码提供、再分发或组合义务是否已履行。`uv.lock` 中的源分发与 wheel 哈希可用于定位工件，但哈希本身不是许可证审查。

## 证据与复核边界

- 基线提交：`git rev-parse HEAD` 为 `25c8dc392318f724b366cf2d76e13b1856dd0368`；远端 `origin/local` 在审计开始时为相同 SHA。
- 静态检查：核对 `services/ai/pyproject.toml`、`services/ai/uv.lock`、`services/ai/tools/audit_licenses.py`、`services/ai/docs/evidence/dependency-licenses.json`、`evaluation/smoke/audit_dependencies.py` 和解析许可证证据。
- 只读核算：TOML package 数 39；JSON 证据行数 36；比较 `(name, version)` 后发现上述 3 个锁文件条目缺失，未发现证据 JSON 的额外 package 条目；独立计算锁文件 SHA-256 后确认与 JSON 内哈希不符。
- 现有 `audit_licenses.py` 会覆盖仓库内 `services/ai/docs/evidence/dependency-licenses.json`。本次未运行该写入脚本，未改动基线证据文件。
- 本审计未从网络重新下载工件、逐个阅读所有上游许可证文本，亦未对 Java、Node、容器镜像执行 SBOM/许可证扫描。因此结论仅适用于报告列明的仓库元数据和本机证据。

## 待处理项

1. 重新生成并提交与实际 `uv.lock` 哈希绑定的完整 Python 运行、开发、平台标记及构建依赖证据，并说明未安装包如何检查。
2. 核实 `knowflow-ai`、`colorama`、`psycopg`、`psycopg-binary`、`tzdata` 和 ReportLab 的上游许可证文本，记录来源与人工判定。
3. 对 Maven、npm、容器基础镜像及系统包生成基于实际构建/部署图的许可证清单，再由项目负责人按发行场景确认通知和再分发义务。

## 2026-11-03 许可证证据处置（Terra High 实施，待独立审阅）

- 实施基线：`be958d4848285ebcc32a299079ed6dc94d149b08`；未修改 pyproject、依赖锁或计划候选 SHA。
- 已重采 `services/ai/docs/evidence/dependency-licenses.json`：**39 个 lock entry、39 行、39 个精确版本 metadata 匹配、38 个包有实际许可证文本**。新增并覆盖原缺失的 psycopg、psycopg-binary、tzdata；此前未核查的 colorama 当前也有安装的精确版本和文本证据。
- 构建依赖 `uv_build==0.12.23` 单独登记，从本机 uv 缓存的精确版本 `.dist-info` 读取 metadata、许可证文本和哈希，不误称已装入 AI 运行环境；MIT 与 Apache 两份原文均保留。
- 为 colorama、psycopg、psycopg-binary、tzdata、ReportLab、uv_build 留存 **9 份上游许可证原文**，位于 `services/ai/docs/evidence/license-texts/`；每份的源 distribution 相对路径、metadata SHA-256、原文 SHA-256 及仓库证据路径均在 JSON 中记录。目录内 `-text` 属性保留原始字节。不是根据 classifier 猜测后填入自造 SPDX 值。
- 修复采集器的证据边界：逐行校验已装版本与锁版本一致，不匹配／未安装仍列出并标未完成；记录实际 Windows / Python 环境，不再固定写 Linux；对运行／开发依赖仅作保守图分类，不声称已计算 Linux 发行裁剪图。新增回归覆盖错版、缺包、构建包名不符及 CRLF/LF 指纹一致性。
- **跨平台指纹说明**：原报告 `a9bc533d…d357c2` 是 Windows CRLF 工作树字节哈希；同一锁文件在目标 Git blob／LF checkout 的哈希为 `d5b6adc8cdaae9511748cb5b181c207c75f7ac4e1eaaa3e156eb2a26292a8935`。新 JSON 主字段 `lock_sha256` 使用明确声明的 CRLF→LF 归一化，并保留 `lock_worktree_sha256` 原始哈希；已与基线 Git blob 独立计算比对一致。没有通过改写锁文件来制造一致。
- 采集命令：`services/ai/.venv/Scripts/python.exe services/ai/tools/audit_licenses.py --base-sha be958d4848285ebcc32a299079ed6dc94d149b08 --build-metadata <本机缓存的 uv_build-0.12.23.dist-info> --export-dir services/ai/docs/evidence/license-texts`。只读本地安装／缓存元数据，不下载或调用模型。
- `knowflow-ai==0.1.0` 的项目自身许可证仍无文本或声明，**未完成**；不能由 Terra 擅自选定授权条款，需权利人决定。
- **仍未完成**：实际 Linux 镜像中 native 捆绑依赖的许可证据、Maven/npm 全传递工件的许可证原文及内容身份验证、基础镜像／系统包 SBOM、完整产品 NOTICE／对应源码获取和替换方式等发行证据、负责人及独立审核者签收。既有三栈清单只能作为后续核对输入，不能据此自动判定发行合规。

## 2026-11-04 NOTICE 初稿

- 已在仓库根新增 `NOTICE`，基于 `docs/reviews/2026-11-03-dependency-inventory.json` 与 `docs/reviews/2026-11-03-license-log-redaction-audit.md` 汇总 Python / Node 运行时弱 copyleft 及 Java EPL 组，并注明需署名组件与许可证原文位置。
- 本初稿**不是法律意见**；`knowflow-ai` 自身许可证仍待权利人声明；Maven/npm 全量 SBOM、镜像层及 Linux native 捆绑依赖证据仍未完成。
- **仍待独立审阅与负责人发行签收**；本注记不把 NOTICE 初稿表述为已完成全量许可证清理或发行批准。
