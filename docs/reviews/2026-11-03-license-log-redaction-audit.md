# 依赖许可证与日志脱敏审计（#14）

- 审计时间：2026-11-03 17:25（Asia/Hong_Kong）
- 基线：`local@84681d4b6ec184bc067112627f4fd09660177401`（审计时 HEAD）
- 报告性质：**只读审计**。未改动任何业务代码、依赖清单、锁文件或配置；未调用任何真实模型 / 付费 API；未读取、输出任何凭据值。
- 产物：本报告 + `docs/reviews/2026-11-03-dependency-inventory.json`（清单证据）+ `scripts/audit-dependencies.py`（可重跑采集器，只读）

## 0. 结论

| 维度 | 结论 |
|---|---|
| 强 copyleft（GPL / AGPL / SSPL） | 运行时路径 **0 个** |
| 弱 copyleft（LGPL / MPL / EPL） | 运行时 **6 组**，全部可合规，但**当前仓库没有任何 NOTICE 载体** |
| 许可证证据时效 | **已失效**：既有 `dependency-licenses.json` 绑定旧 lock，且未覆盖新增的 LGPL 依赖 |
| 自动化门禁 | **无**（无 dependabot、无 license CI job） |
| 日志脱敏（代码层） | **通过**。28 个日志调用点全部为白名单字段，无正文、无凭证、无 Authorization |
| 日志脱敏（部署层） | **未就绪**。无日志驱动 / 轮转 / 留存策略，无生产日志采样证据 |
| 工作树密钥卫生 | **有风险**：`services/ai/.env.example` 的工作树版本含 2 个疑似真实 API key（未提交，HEAD 干净），见 B4 |

一句话：代码写得很干净，交付物不干净——能合规地发，但现在发出去会漏掉署名与 LGPL 义务。

---

# A. 依赖许可证

## A1. 方法与边界

| 栈 | 清单来源 | 许可证来源 | 条目数 |
|---|---|---|---|
| Python | `services/ai/uv.lock`（SHA-256 `a9bc533d…d357c2`） | 本机 venv 的 `dist-info` METADATA（`License-Expression` / `License` / `Classifier`） | 39 |
| Java | `mvnw dependency:list` 全量解析结果（130 条） | 本地 Maven 仓库中各 artifact 的 `pom.xml` `<licenses>`，缺失时沿 `parent` 链上溯 | 130 |
| Node | `apps/web/package-lock.json`（lockfileVersion 3） | lockfile 内 `license` 字段（524/525 条目自带） | 524 |

合计 **693** 条。Java 侧解析使用本机 `~/.m2/settings.xml` 指向的 `D:\Maven` 仓库，该仓库走阿里云镜像（`maven.aliyun.com/repository/public`）——**这是个人环境配置，不是仓库配置**，CI 与本地解析源不同，见 A5-4。

边界：这是**清单**不是法律意见。平台专属 wheel（未在本机安装）与 classifier artifact 保持 `UNKNOWN`，不做推测填充。

## A2. 许可证分布

**Python（39）**

| family | 数量 |
|---|---|
| MIT | 20 |
| BSD-3-Clause | 7 |
| Apache-2.0 | 4 |
| LGPL-3.0-only | 2 |
| BSD-3-Clause（vendor 写法 `OSI Approved / BSD License`） | 2 |
| BSD-2-Clause | 1 |
| MPL-2.0 | 1 |
| PSF-2.0 | 1 |
| UNKNOWN（本项目自身 `knowflow-ai`） | 1 |

**Java（130）**

| family | 数量 |
|---|---|
| Apache-2.0 | 99 |
| MIT | 11 |
| EPL-2.0 | 9 |
| BSD-3-Clause | 3 |
| BSD-2-Clause | 2 |
| EDL-1.0 | 2 |
| UNKNOWN（netty native classifier 行） | 2 |
| EPL-1.0 | 1 |
| Public-Domain（CC0） | 1 |

**Node（524）**

| family | 数量 |
|---|---|
| MIT | 418 |
| Apache-2.0 | 44 |
| ISC | 18 |
| MPL-2.0 | 13 |
| LGPL-3.0-or-later | 10 |
| BSD-2-Clause | 9 |
| BlueOak-1.0.0 | 4 |
| BSD-3-Clause | 3 |
| CC0-1.0 | 2 |
| 0BSD / CC-BY-4.0 / PSF-2.0 | 各 1 |

**按作用域**：Node 运行时（`dev=false`）57 个、开发依赖 467 个；Java 非 test 作用域 87 个（82 compile + 3 runtime + 2 native classifier）、test 43 个。

## A3. 有义务的依赖清单（运行时路径）

| 组件 | 版本 | 许可证 | 义务 | 是否进生产镜像 |
|---|---|---|---|---|
| `psycopg` / `psycopg-binary` | 3.3.6 | **LGPL-3.0-only** | 保留声明；允许用户替换库；分发修改版需开源该库 | 是（AI 服务） |
| `@img/sharp-libvips-*` | 1.3.4 | **LGPL-3.0-or-later** | 同上；以独立 `.so` 动态加载，满足"可替换"条件 | 是（Web 镜像，`next/image`） |
| `caniuse-lite` | 1.0.30001820 | **CC-BY-4.0** | **必须署名**（数据来源） | 是（Next 运行时依赖） |
| `logback-classic` / `logback-core` | 1.5.34 | EPL-2.0 **或** LGPL-2.1-only（双许可） | 选 EPL-2.0：保留声明，无源码开放义务 | 是（API 服务） |
| `jakarta.annotation-api` | 2.1.1 | EPL-2.0 / GPL-2.0-CPE（双许可） | 选 EPL-2.0 | 是 |
| `jakarta.activation-api` / `jakarta.xml.bind-api` | 2.1.4 / 4.0.5 | EDL-1.0（BSD-3 类） | 保留版权与免责声明 | 是 |
| `jna` | 5.13.0 | Apache-2.0 / LGPL-2.1-or-later | 选 Apache-2.0 | 否（Testcontainers） |
| `junit-jupiter*` | 5.12.2 | EPL-2.0 | 仅测试，不随镜像分发 | 否 |
| `junit` | 4.13.2 | EPL-1.0 | 仅测试 | 否 |
| `lightningcss*` / `axe-core` | 1.33.0 / 4.14.0 | MPL-2.0 | 仅构建期；若分发修改后的源文件需开源该文件 | 否（dev） |
| `LatencyUtils` | 2.0.3 | Public Domain / CC0 | 无 | 是（micrometer 传递） |
| `reactive-streams` | 1.0.4 | MIT-0 | 无署名义务 | 是 |

**结论：无 GPL / AGPL / SSPL。** 唯一需要认真对待的是 `psycopg`（LGPL）与 `sharp-libvips`（LGPL）——两者都是动态加载，合规路径清晰：随镜像附 NOTICE + 许可证全文 + 源码获取方式。

## A4. 缺口

### A4-1 既有许可证证据已失效（严重度：高）

`services/ai/docs/evidence/dependency-licenses.json` 记录：

| 字段 | 记录值 | 当前实际 |
|---|---|---|
| `lock_sha256` | `b19e93809daf…7c58a7` | `a9bc533d8a02…d357c2` |
| 包数 | 36 | 39 |
| 缺失包 | — | `psycopg`、`psycopg-binary`、`tzdata` |

即：**新增的 LGPL 依赖从未被任何已提交证据覆盖**。该文件不能作为"依赖许可已核对"的依据，只能作为历史快照。

### A4-2 仓库无 LICENSE / NOTICE / THIRD-PARTY 载体（严重度：高）

全仓库匹配 `LICENSE*` / `NOTICE*` / `THIRD-PARTY*` / `COPYING*` 的结果为 **0**。对内部开发无影响；一旦把镜像交给客户或部署到客户环境，A3 表里的署名与声明义务立刻变成实质缺口。

### A4-3 无自动化许可证门禁（严重度：中）

`.github/workflows/web-e2e.yml` 只有 `python-contract` / `java` / `web` 三个 job；无 dependabot 配置，无 license 扫描（如 `pip-licenses`、`license-maven-plugin`、`license-checker`）。依赖变更完全靠人工发现——A4-1 就是这么发生的。

### A4-4 基础镜像未固定 digest（严重度：中）

| Dockerfile | FROM | 固定方式 |
|---|---|---|
| `services/api/Dockerfile` | `maven:3.9.16-eclipse-temurin-21` | **digest 已固定** ✓ |
| `services/api/Dockerfile` | `eclipse-temurin:21-jre-jammy` | tag only |
| `services/ai/Dockerfile` | `python:3.12-slim`、`ghcr.io/astral-sh/uv:0.11.6` | tag only |
| `apps/web/Dockerfile` | `node:24-alpine` ×3 stage | tag only |
| `infra/compose.yml` | `pgvector/pgvector:0.8.1-pg16`、`bitnamilegacy/minio:2025.4.22` | **digest 已固定** ✓ |

四个未固定的基础镜像让"同一 commit 构建出不同产物"成为可能，也让许可证清单随上游漂移。建议全部 pin digest，并在升级时重跑 A1 采集。

### A4-5 本地与 CI 的 Maven 解析源不同（严重度：低）

本机 `settings.xml` 使用阿里云镜像，CI 直连 central。同一 `pom.xml` 在两边可能解析出不同来源的 artifact（内容哈希一般一致，但供应链可追溯性不一致）。建议在 CI 显式声明镜像与校验策略，或至少记录解析源。

### A4-6 工具已知限制（严重度：低）

- `mvn dependency:list` 对带 classifier 的行格式为 `g:a:type:classifier:version:scope`，采集器按 5 段解析，导致 2 条 netty native（`netty-resolver-dns-native-macos:osx-x86_64`、`netty-transport-native-epoll:linux-x86_64`，均 4.1.135.Final）被记为 `UNKNOWN`。其许可证与 netty 主体一致（Apache-2.0），已在 A2 中按 2 条 UNKNOWN 单列，未擅自填充。
- Python 侧 `reportlab`、`colorama` 的 METADATA 只写 `OSI Approved / BSD License`，上游实为 BSD-3-Clause。采集器保持原文，报告按上游归类。

---

# B. 日志脱敏

## B1. 方法

穷举三个服务的全部日志出口，逐条检查参数：

| 服务 | 日志出口 | 数量 |
|---|---|---|
| AI（Python） | `_logger.info/warning`（`answering.py` 4、`streaming.py` 5、`worker.py` 5、`http_client.py` 2） | 16 |
| API（Java） | `LOGGER.info/warn`（`QuestionService` 3、`IndexingScheduler` 3、`DeletionOutboxScheduler` 3、`DocumentService` 2、`AnswerStreamLifecycle` 1） | 12 |
| Web（TypeScript） | `console.*` | **0** |

另外检查：异常处理路径、过滤器、HTTP 客户端封装、容器日志配置。

## B2. 已验证的控制（全部通过）

| # | 控制 | 证据 |
|---|---|---|
| 1 | 日志字段白名单 | 28 个调用点参数只有 `request_id` / `stage` / `duration_ms` / `result_count` / `chunk_count` / `item_count` / `usage` / `outcome` / `code` / `task_id`。**无正文、无标题、无 URL、无用户输入** |
| 2 | 解析错误只暴露固定码 | `ParseFailure` 的 docstring 即 `Only a fixed non-sensitive error code`；`parser_process.py` 与 `parser_worker.py` 抛出的全部是 `PARSER_*` / `INVALID_*` 等常量，无 `str(exc)` 透传 |
| 3 | 异常不落原始堆栈 | `BoundaryMiddleware` 捕获异常后显式注释 `No raw exception logging`，只返回 `INTERNAL_ERROR` |
| 4 | 内部密钥比较不泄露 | `hmac.compare_digest(credential, self.secret)`，失败返回 401，无日志 |
| 5 | 代理配置只记固定 token | `http_client.py` 告警 `http_client_proxy_environment_ignored` / `http_client_socks_transport_unavailable`，**不写环境变量值** |
| 6 | 凭证不以明文存储 | `AuthService` 只落 `token_sha256`；密码经 `PasswordEncoder`；账号不存在时用 `DUMMY_PASSWORD` 哈希做等时比较 |
| 7 | Web 无服务端日志 | `apps/web/src` 内 `console.*` 计数为 0；代理路由不打印请求体或 token |
| 8 | 响应体不回声敏感字段 | 登录成功响应 `delete payload.access_token` 后才返回；token 只进 `HttpOnly` + `SameSite=Lax` cookie（生产加 `Secure`） |
| 9 | 错误响应不泄内部细节 | Spring `server.error.include-message/binding-errors/stacktrace/exception` 全为 `never`；actuator 只暴露 `health` 且 `show-details: never` |
| 10 | 有主动检测机制 | `recovery_e2e.py` 把所有长度 ≥16 的敏感值（含 harness 的 `sensitive_values`）在子进程日志里做子串扫描，命中即置 `LOCAL_SERVICE_SECRET_LOG_LEAK` 并让报告失败 |

第 10 条是关键：这不是"我读了代码觉得没问题"，而是**已有断言在每次恢复演练时自动检查**。

## B3. 残余风险

| # | 风险 | 严重度 | 说明 | 建议 |
|---|---|---|---|---|
| R1 | 容器日志无驱动 / 轮转 / 上限 | 中 | `infra/compose.yml` 所有服务用默认 `json-file` 驱动，无 `logging.options`。长跑后宿主磁盘可被日志吃满 | 部署模板里显式配 `max-size` / `max-file`，或接 stdout 采集 |
| R2 | 访问日志含客户端 IP 与资源 ID | 低 | AI 服务由 uvicorn 提供，默认 access log 会记录客户端 IP、方法、路径（路径含 document/knowledge-base UUID） | 生产明确保留期限与访问控制；需要时关闭 access log 改由网关记录 |
| R3 | `storageFailure.getMessage()` 进日志 | 低 | `DocumentService:69`。已核验：`S3ObjectStore` 抛出的消息全是固定串（`Object storage request failed` / `Object storage returned HTTP <code>`），不含 endpoint、bucket 或密钥 | 无需改动；新增存储异常类型时保持固定消息 |
| R4 | 测试口令字面量 | 信息 | E2E 使用 `KnowFlow-e2e-only-2026!` 一类固定口令 | 确保生产 env 不复用；已在 `.env` 忽略规则内 |
| R5 | 生产日志未采样核对 | 中 | 无生产环境，B2 全部为代码级 + 隔离演练级证据 | P2 部署时做一次真实日志抽样复核（见 `deploy/PRODUCTION-CHECKLIST.md`） |

## B4. 附带发现：示例文件工作树版本含疑似真实密钥（严重度：高，未提交）

- 现象：`services/ai/.env.example` 的**工作树版本**中，`EMBEDING_KEY` 与 `DEEPSEEK_API_KEY` 两行填有 `sk-` 前缀的长字符串。
- 提交状态：`git show HEAD:services/ai/.env.example` 中这两行为空——**HEAD 干净，历史未被污染**；`git log -- services/ai/.env.example` 的 3 个历史提交均无密钥。
- 扫描范围：对全部 485 个已跟踪文件做 `sk-[A-Za-z0-9]{24,}` 匹配，**仅此 1 个文件命中**，无其他泄漏点。
- 风险：`.gitignore` 对 `.env.example` 有 `!` 例外规则，该文件是**可被提交**的。工作树同时存在 1058 个未跟踪文件，任何一次 `git add -A` 都可能把它带进提交。
- 建议（需负责人执行，本轮未改动该文件）：
  1. 把真实 key 移到被忽略的 `services/ai/.env`（`.gitignore` 已覆盖），示例文件恢复为空值；
  2. 若这两个 key 曾用于任何真实调用，**轮换**；
  3. 在 CI 增加 `git grep -n "sk-[A-Za-z0-9]\{24,\}"` 守卫，命中即失败。

本报告与本次提交均未包含这两个值，也未把该文件纳入暂存区。

## B5. 未覆盖

1. 第三方库内部日志（`httpx` debug、AWS SDK、Tomcat access log）未逐一开启验证——当前默认级别下不输出请求体。
2. 生产环境实际日志样本：不存在。
3. 日志脱敏的**出站**维度（数据出境说明）不在本报告范围，属 P1 "数据出站说明"待办。

---

# C. 建议动作

| 优先级 | 动作 | 归属 |
|---|---|---|
| P0 | 把 `services/ai/.env.example` 工作树中的疑似真实 key 移入被忽略的 `.env` 并清空示例；若曾真实调用则轮换（B4） | 项目负责人 |
| P0 | 重新生成 `services/ai/docs/evidence/dependency-licenses.json` 并绑定当前 `uv.lock` SHA；或改由 `scripts/audit-dependencies.py` 统一产出 | #14 收尾 |
| P0 | 生产镜像附带 `THIRD-PARTY-NOTICES`（Apache-2.0 NOTICE、MIT/BSD 全文、LGPL 声明与源码获取方式、CC-BY-4.0 署名） | #15 |
| P1 | 基础镜像全部 pin digest | #15 |
| P1 | CI 增加 license 门禁 job（三栈各一） | 后续 |
| P2 | 确定项目自身 LICENSE（内部/私有需明确，否则外部交付无授权依据） | 项目负责人 |
| P2 | 生产日志驱动与留存策略写入部署模板 | #15 |

## 复现命令

```powershell
# 1) Java 依赖图（唯一需要网络的步骤）
cd services/api
.\mvnw.cmd -B -q dependency:list -DoutputFile=$env:TEMP\mvn-deps.txt

# 2) 三栈清单（只读，不联网）
cd D:\konwflow
uv run --project services/ai --frozen python scripts/audit-dependencies.py `
    --mvn-list $env:TEMP\mvn-deps.txt `
    --out docs/reviews/2026-11-03-dependency-inventory.json

# 3) 日志出口普查
git grep -n "_logger\.\(info\|warning\)" -- services/ai/src
git grep -n "LOGGER\.\(info\|warn\)" -- services/api/src/main
git grep -n "console\." -- apps/web/src
```
