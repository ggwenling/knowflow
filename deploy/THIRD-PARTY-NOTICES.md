# 第三方声明（草案）

状态：`DRAFT`。本文件是**义务清单 + 生成方法**，不是完整的许可证全文集合。发布前必须补齐第 3 节的全文。

依据：`docs/reviews/2026-11-03-license-log-redaction-audit.md`（#14）与本仓库 `docs/reviews/2026-11-03-dependency-inventory.json`（693 条依赖记录）。

> 本文件不构成法律意见。对外分发前由负责人确认。

## 1. 随镜像分发的组件与义务

### Web 镜像（`apps/web`）

| 组件 | 许可证 | 义务 |
|---|---|---|
| Next.js、React、React DOM 及其生态 | MIT | 保留版权声明与许可证全文 |
| sharp | Apache-2.0 | 保留 NOTICE（若有）与许可证全文 |
| **libvips 二进制（`@img/sharp-libvips-*`）** | **LGPL-3.0-or-later** | 保留声明；保持动态可替换；提供对应源码获取方式 |
| **caniuse-lite** | **CC-BY-4.0** | **必须署名**数据来源（caniuse.com） |
| Node 基础镜像（Alpine） | 各包各自许可 | 从镜像内 `/usr/share/licenses` 收集，本草案未包含 |

### API 镜像（`services/api`）

| 组件 | 许可证 | 义务 |
|---|---|---|
| Spring Boot / Spring Framework / Spring Security | Apache-2.0 | 保留 NOTICE 与全文 |
| Jackson、Tomcat、HikariCP、Flyway、SnakeYAML | Apache-2.0 | 同上 |
| PostgreSQL JDBC 驱动 | BSD-2-Clause | 保留版权与免责声明 |
| Apache PDFBox | Apache-2.0 | 保留 NOTICE 与全文 |
| **Logback** | EPL-2.0 **或** LGPL-2.1-only | 本项目按 **EPL-2.0** 使用：保留声明与全文 |
| jakarta.annotation-api | EPL-2.0 / GPL-2.0-CPE（双许可） | 按 EPL-2.0 使用 |
| jakarta.activation-api、jakarta.xml.bind-api | EDL-1.0（BSD-3 类） | 保留版权与免责声明 |
| LatencyUtils | Public Domain / CC0 | 无强制义务 |
| reactive-streams | MIT-0 | 无署名义务 |
| JRE 基础镜像（`eclipse-temurin:21-jre-jammy`） | GPL-2.0 + Classpath Exception | 随镜像保留 OpenJDK 声明；本草案未包含全文 |

### AI 镜像（`services/ai`）

| 组件 | 许可证 | 义务 |
|---|---|---|
| FastAPI、Starlette、Pydantic、jsonschema、anyio | MIT | 保留版权与全文 |
| httpx、httpcore、uvicorn、pypdf、idna、click | BSD-3-Clause | 保留版权与全文 |
| **psycopg / psycopg-binary** | **LGPL-3.0-only** | 保留声明；允许替换库；提供源码获取方式 |
| certifi | MPL-2.0 | 保留声明；修改该文件需开源该文件 |
| typing-extensions | PSF-2.0 | 保留声明 |
| pillow | MIT-CMU（HPND） | 保留声明 |
| Python 基础镜像（`python:3.12-slim`） | PSF-2.0 + Debian 各包 | 随镜像保留；本草案未包含 |

## 2. 没有强制义务的部分（已核实）

- 三栈运行时路径**无 GPL / AGPL / SSPL**。
- 测试与构建期依赖（JUnit、Testcontainers、Playwright、Vitest、lightningcss、axe-core）**不随运行镜像分发**，无需在 NOTICES 中出现；若将来把测试镜像交付给客户，需重新评估。

## 3. 必须补齐的许可证全文

分发前，`THIRD-PARTY-NOTICES.txt` 至少要包含下列全文（去重后约 10 份）：

1. Apache-2.0（含各组件 `NOTICE` 内容）
2. MIT
3. BSD-2-Clause
4. BSD-3-Clause
5. ISC
6. MPL-2.0
7. EPL-2.0
8. EDL-1.0
9. LGPL-3.0（psycopg、libvips）
10. CC-BY-4.0（caniuse-lite 署名）
11. PSF-2.0
12. GPL-2.0 + Classpath Exception（OpenJDK 运行时）

## 4. 生成方法

```bash
# Node（生产依赖）
cd apps/web
npx license-checker --production --json > /tmp/web-licenses.json
npx license-checker --production --plainVertical > /tmp/web-notices.txt

# Python（从已安装环境导出）
uv run --project services/ai python - <<'PY'
import importlib.metadata as md, json
rows = []
for d in md.distributions():
    meta = d.metadata
    rows.append({"name": meta["Name"], "version": meta["Version"],
                 "license": meta.get("License-Expression") or meta.get("License")})
print(json.dumps(rows, ensure_ascii=False, indent=2))
PY

# Java（license-maven-plugin 的 third-party 报告；需网络拉插件）
cd services/api
./mvnw -B license:add-third-party -Dlicense.outputDirectory=target/third-party

# 统一清单（本仓库自带的只读采集器）
cd ../..
uv run --project services/ai --frozen python scripts/audit-dependencies.py \
    --mvn-list /tmp/mvn-deps.txt --out /tmp/inventory.json
```

## 5. 分发形态建议

| 形态 | 做法 |
|---|---|
| Docker 镜像 | 在三个镜像内各放一份 `/usr/share/doc/knowflow/THIRD-PARTY-NOTICES.txt`，并在 `/usr/share/doc/knowflow/` 下放许可证全文目录 |
| 离线包 | 与镜像 tar 一起打包 `notices/` 目录 |
| Web 页面 | 在"关于"页提供可下载链接（可选，非必需） |

## 6. 待办

- [ ] 生成完整全文集合（第 3 节 12 项）
- [ ] 补 OS 基础镜像的包级声明
- [ ] 决定项目自身 LICENSE（当前仓库 **0 个** LICENSE 文件）
- [ ] 把 `THIRD-PARTY-NOTICES` 加入三个 Dockerfile 的运行时层
- [ ] 在 CI 增加许可门禁（依赖变更时重跑第 4 节）
