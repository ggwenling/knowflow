# Issue #14 依赖许可证审计

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
