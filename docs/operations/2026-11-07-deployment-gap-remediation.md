# 生产部署缺口修复记录（2026-11-07）

本记录承接 [生产等价部署与回滚演练](./2026-11-07-production-deploy-rollback-drill.md)，只修配置与部署层，不改业务代码语义、不改契约、不提交 git、不输出密钥。所有验证都在同一个生产形态栈 `knowflow-prod` 上完成（端口 `127.0.0.1:3443`，数据卷沿用演练卷）。

## 1. 结论

| 缺口 | 修复结果 | 验证 |
| --- | --- | --- |
| G1 预算门禁三件套缺失 | 已纳入生产 compose 与 env 示例；删除临时 override | `config --quiet` 通过；容器内三变量存在；账本卷属主 10001；缺变量时 compose 直接失败（fail-closed） |
| G2 AI 无外网出口 / `internal: true` 一刀切 | 改为 internal `knowflow` + 独立 `provider-egress`，仅 `ai` 接入 | `api` 容器解析 provider 域名失败，`ai` 解析成功 |
| G3 `deepseek-flash` 500 | 完成真实响应取样，结论更新为 provider 侧容量/可用性故障 | 探针见 §7；未改别名、未改预算文件 |
| G4 Web 仅 HTTP / Secure cookie 不生效 | 新增 nginx TLS 终结入口 `edge`，Web 不再暴露宿主端口 | HTTPS 200；`Secure` + `HttpOnly` cookie 下发；HTTPS 冒烟通过 |
| G6 基础镜像未 pin digest | 全部 Dockerfile `FROM` 已 pin digest | 3 个 Dockerfile `docker build --check` 全部通过 |
| G7 预检端口误报无跳过参数 | 新增 `-SkipPortCheck`，端口检查改查 edge 端口 | 栈运行时默认 FAIL（预期）；加开关后 INFO，`FAIL=0` |
| G8 env 示例默认 `synthetic`、缺预算变量 | 默认改 `external`，补齐预算/TLS/出口变量 | 预检 `required-keys` 31 项齐全 |

## 2. 变更清单

| 文件 | 变更 |
| --- | --- |
| `deploy/compose.production.draft.yml` | 预算三件套 + `budget-init` + `budget-ledger` 卷；`provider-egress` 网络；新增 `edge` 服务；`web` 去掉宿主端口 |
| `deploy/env/production.env.example` | 新增预算三件套与 `KNOWFLOW_BUDGET_DIR`、TLS/edge、受控出口变量；`KNOWFLOW_WEB_MODEL_MODE` 默认 `external`；删除废弃的 Web 宿主端口变量 |
| `deploy/scripts/preflight.ps1` | 新增 `-SkipPortCheck`；端口检查改为 edge 端口；新增预算文件与 TLS 证书检查；基础镜像 digest 检查保持 |
| `deploy/scripts/production-smoke.ps1` | 新增 `-SkipCertificateCheck`，支持 HTTPS 入口 |
| `deploy/scripts/generate-self-signed-cert.ps1` | 新增：生成带 SAN 的本地自签证书 |
| `deploy/tls/nginx.conf` | 新增：TLS 终结与 Web 反向代理配置 |
| `apps/web/Dockerfile`、`services/api/Dockerfile`、`services/ai/Dockerfile` | 基础镜像 pin digest |
| `deploy/compose.production.budget.override.yml` | **已删除**（能力并入主 compose） |

`deploy/.env.production` 为本地 gitignored 文件，本次补了预算/TLS/edge/出口键，并移除已不再使用的 `KNOWFLOW_WEB_HOST_BIND`、`KNOWFLOW_WEB_PORT`。密钥值未打印、未提交。

## 3. 预算门禁（fail-closed）

### 3.1 正式配置

`ai` 服务现在强制读取三项：

```text
KNOWFLOW_BUDGET_LEDGER_PATH=/var/lib/knowflow-budget/budget-ledger.sqlite3
KNOWFLOW_BUDGET_PRICE_FILE=/etc/knowflow-budget/PRICE_FILE.json
KNOWFLOW_BUDGET_POLICY_FILE=/etc/knowflow-budget/POLICY_FILE.json
```

- 账本：独立命名卷 `budget-ledger` 挂到 `/var/lib/knowflow-budget`；一次性 `budget-init` 以 root 修正卷属主为 `10001:10001`，`ai` 再以 10001 启动。
- 价格/策略：宿主目录 `${KNOWFLOW_BUDGET_DIR}` 只读挂载到 `/etc/knowflow-budget`。文件来源是授权的 provider 价目/策略文件；仓库内对应文件位于 `.blindtest/config/`（已被 `.gitignore` 覆盖），**不得提交**，生产应使用当前有效的授权副本并在变更时替换目录内容。
- fail-closed 语义不变：三项任一缺失、文件不可读、策略过期或校验失败，`provider_budget.py` 都会拒绝调用（`BUDGET_CONFIGURATION_REQUIRED` → `AI_PROCESSING_FAILED` 503）。此外 compose 用 `:?` 把缺变量提前到部署期失败。

### 3.2 实测

```powershell
# 部署期 fail-closed：清空一个预算变量
$env:KNOWFLOW_BUDGET_PRICE_FILE=''
docker compose ... config --quiet
# error while interpolating services.ai.environment.KNOWFLOW_BUDGET_PRICE_FILE: required variable ... is missing a value
# guard_exit=1
```

```text
# 容器内（值脱敏）
HTTPS_PROXY=<set>
KNOWFLOW_BUDGET_LEDGER_PATH=<set>
KNOWFLOW_BUDGET_PRICE_FILE=<set>
KNOWFLOW_BUDGET_POLICY_FILE=<set>
-rw-r--r-- 1 10001 10001 40960 /var/lib/knowflow-budget/budget-ledger.sqlite3
-rwxrwxrwx 1 root root 965 /etc/knowflow-budget/POLICY_FILE.json
-rwxrwxrwx 1 root root 857 /etc/knowflow-budget/PRICE_FILE.json
```

账本摘要（累计值，包含演练期间记录）：

```text
paid_count=20
paid_total=204800 microyuan (CNY 0.2048)
zero_price_count=35
budget_stop_count=0
limit=(1, 10000000)  # CNY 10 硬上限
```

## 4. TLS 与 Secure cookie

### 4.1 入口

新增 `edge`（`nginx:1.27-alpine@sha256:65645c...`）作为唯一暴露宿主端口的服务：

```text
127.0.0.1:3443 -> edge:443 -> web:3000
```

- 证书固定为 `deploy/tls/fullchain.pem` 与 `deploy/tls/privkey.pem`；`*.pem/*.key` 已被 `.gitignore` 覆盖。
- 本地自签证书生成：

```powershell
pwsh -NoProfile -File deploy/scripts/generate-self-signed-cert.ps1
```

证书含 `DNS:localhost`、`IP:127.0.0.1`，有效期 365 天，仅用于本地/演练。

- 代理使用 `$http_host` 作为 `Host` 与 `X-Forwarded-Host`（保留端口），并把 `X-Forwarded-Proto` 固定为 `https`。否则 Web 的同源校验会把 `https://host:port` 误判为跨源。
- `web` 不再映射宿主端口，只 `expose 3000`。

### 4.2 实测

```text
https://127.0.0.1:3443/api/mode -> 200 {"mode":"external"}
http://127.0.0.1:3100/api/mode  -> 连接失败（旧 HTTP 入口已关闭）
register_status=201 has_session_cookie=True secure_attr=True httponly_attr=True
```

HTTPS 冒烟（`-SkipCertificateCheck`）通过 `register/login/me/创建库/上传/索引 READY`；问答受 §7 provider 故障影响。证据：`D:\konwflow-prod-drill\evidence\smoke-remediation-https.json`。

### 4.3 生产换正式证书

1. 从正式 CA（企业 CA、certbot/ACME 或云负载均衡）取得 `fullchain.pem` 与对应私钥。
2. 替换 `deploy/tls/fullchain.pem`、`deploy/tls/privkey.pem`；私钥权限保持 600，属主为部署账号。
3. 若由外部负载均衡终止 TLS，可删除 `edge` 并把 `web` 端口收回内网，但必须保证 `X-Forwarded-Proto: https` 与 `Host`（含端口）传到 Web。
4. 重载：

```powershell
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml exec edge nginx -s reload
```

5. 验证 `Set-Cookie` 仍带 `Secure`，并确认证书链、SNI 与主机名匹配。

## 5. AI 受控出口

### 5.1 拓扑

```text
                    ┌──────────── provider ────────────┐
                    │ api.deepseek.com / siliconflow   │
                    └───────────────┬──────────────────┘
                                    │ (受控 egress)
                            provider-egress (bridge)
                                    │
  web-edge ── edge ── web ── knowflow (internal: true) ── ai
                                    │
                     api / postgres / minio（无外网出口）
```

- `knowflow`：`internal: true`，承载所有服务间通信。
- `web-edge`：`edge ↔ web`。
- `provider-egress`：仅 `ai` 接入；`api/postgres/minio/web/edge` 都没有外网出口。
- 可选代理：`KNOWFLOW_EGRESS_HTTPS_PROXY` 注入为 `HTTPS_PROXY`。为空时 httpx 忽略；设置后仅外网 provider 请求走代理，内部 `http://api:8080` 不走代理。

### 5.2 实测

```text
knowflow_internal=true
provider_egress_internal=false
ai  -> api.deepseek.com / api.siliconflow.cn 解析成功
api -> api.deepseek.com: curl: (6) Could not resolve host（exit=6）
```

### 5.3 限制

Docker bridge 的 `provider-egress` 本身不做域名白名单，`ai` 仍可访问任意公网地址。生产必须在宿主机防火墙或正向代理上只放行 `api.deepseek.com`、`api.siliconflow.cn`（及实际使用的 provider 域名），或强制 `KNOWFLOW_EGRESS_HTTPS_PROXY` 指向白名单代理。DNAT/并发限制、出站审计不在本 compose 内。

## 6. 顺带处理

### 6.1 预检端口误报

`preflight.ps1` 现在检查 `KNOWFLOW_EDGE_HTTPS_PORT`（默认 3443），并提供 `-SkipPortCheck`：

```text
# 栈运行中，默认检查
host  port-3443  FAIL  已被占用；若栈已部署属预期，请加 -SkipPortCheck

# 加开关
host  port-3443  INFO  已按 -SkipPortCheck 跳过（用于已部署环境重复预检）
FAIL=0 WARN=1 PASS=18
```

唯一 WARN 是“已跟踪文件有未提交改动”（本次修复尚未提交，符合约束）。

预检还新增：

- `budget files`：`KNOWFLOW_BUDGET_DIR` 下必须同时存在 `PRICE_FILE.json` / `POLICY_FILE.json`。
- `tls cert-files`：证书目录必须同时存在 `fullchain.pem` / `privkey.pem`。

### 6.2 env 示例一致性

- `KNOWFLOW_WEB_MODEL_MODE` 默认由 `synthetic` 改为 `external`，并注明 synthetic 仅用于演示/E2E。
- 预算三件套与 `KNOWFLOW_BUDGET_DIR` 正式列入示例。
- 删除已废弃的 `KNOWFLOW_WEB_HOST_BIND` / `KNOWFLOW_WEB_PORT`，改为 `KNOWFLOW_EDGE_HOST_BIND` / `KNOWFLOW_EDGE_HTTPS_PORT` / `KNOWFLOW_TLS_DIR`。

### 6.3 基础镜像 digest

已 pin：

| 镜像 | digest |
| --- | --- |
| `node:24-alpine` | `sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8` |
| `python:3.12-slim` | `sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54` |
| `eclipse-temurin:21-jre-jammy` | `sha256:1eac8b8fee11ca7d6725a48bc5d41992ed1561504ebae25490d2d062847e8269` |
| `ghcr.io/astral-sh/uv:0.11.6` | `sha256:b1e699368d24c57cda93c338a57a8c5a119009ba809305cc8e86986d4a006754` |
| `nginx:1.27-alpine`（edge） | `sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10` |

`maven`、`pgvector`、`minio` 原本已 pin。验证：

```text
docker build --check -f apps/web/Dockerfile apps/web        -> Check complete, no warnings found
docker build --check -f services/api/Dockerfile services/api -> Check complete, no warnings found
docker build --check -f services/ai/Dockerfile .             -> Check complete, no warnings found
```

预检 `images / dockerfile-digest` 由 WARN 变为 PASS。

## 7. `deepseek-flash` 真实响应与结论

探针在 `ai` 容器内直连 `https://api.deepseek.com/chat/completions`，读取 `KEY_ENV` 指向的密钥，**不打印密钥**，响应体中的 `sk-*` 形态统一脱敏。原始记录：`D:\konwflow-prod-drill\evidence\provider-probe-2026-11-07.txt`。

关键观测：

```text
model=deepseek-flash  -> 200 / TimeoutError / 503 service_unavailable 交替
model=deepseek-chat   -> 200，响应 model 字段为 deepseek-flash
503 body: {"error":{"message":"Service is too busy. We advise users to temporarily
          switch to alternative LLM API service providers.","type":"service_unavailable"}}
无 HTTP 429，无 Retry-After
```

10 次连续 `deepseek-flash` 的状态序列：

```text
200, ERR(timeout), 503, ERR(timeout), 503, 503, 503, 503, 503, 503
```

同一窗口应用层问答：可答问题返回 502 `AI_PROCESSING_FAILED` 或 504 `PROCESSING_TIMEOUT`，未产出引用；6 次 HTTPS 冒烟复跑均为 BLOCKED。

**结论：**

1. `deepseek-flash` 别名**有效**，能返回 200，不是别名下线。
2. 不是限流：没有 429，也没有 `Retry-After`；503 原文明确是服务过载并建议临时换 provider。
3. 演练时看到的 HTTP 500 `internal_error` 是同一 provider 侧故障窗口内的瞬时错误；本次探针未复现 500，复现的是 503 与读超时。
4. 当前验收受阻的根因是 **provider 侧容量/可用性（service_unavailable）**，属于外部依赖故障，不是应用或回滚回归。

**可选方案（本次均未实施，避免改动业务语义/契约/预算）：**

- 应用侧对 5xx 与读超时做有限重试/退避（需业务代码变更与验收）。
- 临时切换到健康 provider 或模型（需同时改代码内固定模型校验、契约与预算价格/策略文件）。
- 降低并发或延长超时只能缓解，不能绕过 provider 过载。
- 发布门禁增加真实 provider 探活，探活失败不阻塞基础设施发布，但阻塞“带引用问答”验收签字。
- 与 provider 侧确认容量恢复时间；恢复后补跑可答问题与引用校验。

按约束，**未修改模型别名，未修改 `PRICE_FILE.json` / `POLICY_FILE.json`**。

## 8. 完整验证命令（可复现）

```powershell
# 1) 证书（首次）
pwsh -NoProfile -File deploy/scripts/generate-self-signed-cert.ps1

# 2) 配置校验（不打印内容）
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml config --quiet

# 3) 预检（up 之前）
pwsh -NoProfile -File deploy/scripts/preflight.ps1 -EnvFile deploy/.env.production

# 4) 启动/重建（保留卷）
$env:KNOWFLOW_RELEASE='2a7e68a'
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml up -d --wait --wait-timeout 300

# 5) HTTPS 冒烟
pwsh -NoProfile -File deploy/scripts/production-smoke.ps1 `
  -BaseUrl https://127.0.0.1:3443 -ContractVersion 0.2.0 -Label remediation `
  -SkipCertificateCheck -AllowProviderBlocked `
  -EvidencePath D:\konwflow-prod-drill\evidence\smoke-remediation-https.json

# 6) 已部署环境重复预检
pwsh -NoProfile -File deploy/scripts/preflight.ps1 -EnvFile deploy/.env.production -SkipPortCheck
```

实测：`up -d --wait` 重建 edge/budget-init/ai/web 共 37.1s，全部 healthy；`/api/mode` HTTPS 200；索引约 2.0s 完成。

## 9. 残余缺口

| 项 | 状态 |
| --- | --- |
| Provider 过载导致带引用答案未验收 | **已闭环**（2026-11-07 复测，见 §12.4） |
| 应用无 5xx/超时重试 | **已实现**有界重试（见 §12） |
| 无镜像仓库与不可变发布 tag | **已闭环**（本地 registry + `release.ps1`，见 §13.1） |
| Flyway 无 down 脚本 | **已闭环**（备份/恢复 + 迁移目标，见 §13.2；生产需异地备份承接） |
| 健康检查不探活 provider / 预算 | **已实现** `/health/ready`（见 §12） |
| `provider-egress` 无域名白名单 | **已闭环**（Squid CONNECT 白名单，见 §13.3；宿主防火墙仍属生产项） |
| 工作树有未提交改动 | 部署修复已提交为 `e79b838`；§12 的重试/探针改动另行提交 |
| 旧演练手册仍引用已删除的 override 与 3100 端口 | 本记录为准；旧手册保留历史证据 |

## 10. 清理

验证结束后仅停止栈，**不执行 `down -v`**，数据卷保留：

```powershell
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml stop
```

`knowflow-prod_postgres-data`、`knowflow-prod_object-data`、`knowflow-prod_budget-ledger` 均不会被 `stop` 或 `down` 删除。

## 11. 证据位置

- HTTPS 冒烟：`D:\konwflow-prod-drill\evidence\smoke-remediation-https.json`
- 问答复跑：`D:\konwflow-prod-drill\evidence\smoke-answer-retry-{1..6}.json`
- Provider 探针：`D:\konwflow-prod-drill\evidence\provider-probe-2026-11-07.txt`
- 账本：命名卷 `knowflow-prod_budget-ledger`（查询命令见 §3.2）
- TLS 证书：`deploy/tls/fullchain.pem`、`deploy/tls/privkey.pem`（gitignored）

## 12. Provider 韧性加固与带引用验收（2026-11-07 补测）

### 12.1 有界重试

`services/ai/src/knowflow_ai/provider_retry.py` 新增，接入 `answering.py`（非流式生成）、`embedding.py`、`streaming.py`（流式生成）：

| 类别 | 行为 |
| --- | --- |
| 5xx / 读超时 / 连接错误 | 可重试，指数退避 |
| 4xx（含 400/401/403/404） | 不重试，立即失败 |
| 429 | 按 `Retry-After`（秒数或 HTTP 日期）退避；无该头时用指数退避 |
| 流式 | 只在首片段发出前重试；已输出后重试会重复内容，立即失败 |
| 上限 | `max_attempts=3`（可配 1–5）、`base_seconds=0.5`（0–5）、`total_seconds=25`（0–60） |
| 预算 | 预留放在每次尝试内部；每次重试都是独立预留，软停/超限立即以非可重试错误停止 |

`total_seconds` 约束的是重试窗口（含退避等待）；单次在途请求仍受各适配器自身的 HTTP 超时约束，因此总耗时仍有硬上界（`max_attempts × 单次超时 + 重试窗口`）。

配置项（compose 与 env 示例均已登记）：`KNOWFLOW_PROVIDER_RETRY_MAX_ATTEMPTS`、`KNOWFLOW_PROVIDER_RETRY_BASE_SECONDS`、`KNOWFLOW_PROVIDER_RETRY_TOTAL_SECONDS`。

### 12.2 就绪探针

`services/ai/src/knowflow_ai/provider_probe.py` 新增，`app.py` 增加 `GET /health/ready`，`deploy/tls/nginx.conf` 转发该路径：

- `/health/live`：仅代表进程存活，保持原有的容器 healthcheck 语义。
- `/health/ready`：检查 `budget`（三件套路径与文件可读）、`llm`、`embedding`；全部 UP 才返回 200，否则 503 且逐项给出 `reason` / `provider_status`。
- 探针只调 `GET {base}/models`，不调 chat/completions 或 embeddings，不产生 token；结果 10s TTL 缓存。

配置项：`KNOWFLOW_PROVIDER_PROBE_TIMEOUT_SECONDS`（默认 5，1–15）、`KNOWFLOW_PROVIDER_PROBE_TTL_SECONDS`（默认 10，0–60）。

### 12.3 实测

单元/集成测试：受影响用例 65 passed；AI 全量 **712 passed**。

生产形态栈上（`knowflow-ai:2a7e68a` 重建）：

```text
/health/ready（provider 正常） -> 200 {"status":"UP", budget/llm/embedding 均 UP} 0.25s
注入无效 LLM key（真实 401）  -> 503 {"status":"UNAVAILABLE",
                                  llm:{"status":"DOWN","reason":"AUTH_REJECTED","provider_status":401}}
                                 同时容器内 /health/live -> 200 {"status":"UP"}
恢复真实 key                  -> 200 UP
容器内重试（预算账本前后 20 -> 26）：
  503 -> attempts=3，退避 100/200ms，provider_retry_exhausted reason=HTTP_503，retryable=True
  400 -> attempts=1，retryable=False
  429 + Retry-After: 0 -> attempts=2，随后成功
```

账本增量 6 与 3+1+2 次尝试完全一致，说明每次重试都计入预算。

### 12.4 带引用问答验收（HTTPS 全流程）

`production-smoke.ps1` 未使用 `-AllowProviderBlocked`，任一步失败即 FAIL。结果 **PASS**，证据：`D:\konwflow-prod-drill\evidence\smoke-acceptance-retry.json`。

| 步骤 | 状态 | 实际耗时 |
| --- | --- | --- |
| `/api/mode` | 200 `{"mode":"external"}` | 0.21s |
| register | 201 | 0.28s |
| login（HttpOnly cookie，token 不输出） | 200 | 0.13s |
| `/api/v1/me` | 200 | 0.03s |
| 创建知识库 | 201 | 0.04s |
| 上传文档 | 202 | 0.11s |
| 索引完成 | `SUCCEEDED` / `READY` | 2.07s（含 2s 轮询间隔） |
| 可答问题 | 200，`has_answer=True`，**sources=1** | 1.15s |
| 不可答问题 | 200，`has_answer=False`，`sources=0` | 1.15s |

可答问题实际答案：

```text
项目代号：QL-2026[c22a6590-6dec-3be5-9f5d-4d3d33c266fb]
```

引用条数 1，引用 ID 与索引版本 `5364872c-658d-4eaf-a84e-cc61618f32ab` 对应。不可答问题返回固定拒答文案且不附来源。整轮冒烟从 16:19:05.29 到 16:19:10.46，共约 5.17s。

### 12.5 残余

- 镜像仓库/不可变发布 tag、Flyway down、`provider-egress` 域名白名单已在 §13 闭环。
- 探针只验证 provider 的模型列表可达；它不能替代一次真实生成，发布门禁仍建议在验收阶段跑 §12.4 的完整冒烟。

## 13. 发布工程三项残留收口（2026-11-07）

### 13.1 镜像仓库与不可变 release tag

**方案**：compose 只引用 `<registry>/<repo>/<component>:<release>`，`release` 取提交 sha 或语义版本；同一 tag 不允许被覆盖。仓库内已有发布脚本入口，本次在其上扩展：`deploy/scripts/release.ps1`（新增文件，替代原先“本机 `knowflow-api:latest` + 手工 tag”的做法）。

compose 中三处镜像引用统一为：

```yaml
api / migrate : ${KNOWFLOW_IMAGE_REPOSITORY:-knowflow}/api:${KNOWFLOW_RELEASE:-local}
ai / budget-init: ${KNOWFLOW_IMAGE_REPOSITORY:-knowflow}/ai:${KNOWFLOW_RELEASE:-local}
web          : ${KNOWFLOW_IMAGE_REPOSITORY:-knowflow}/web:${KNOWFLOW_RELEASE:-local}
```

`release.ps1` 的行为：

| 步骤 | 说明 |
| --- | --- |
| 版本解析 | 默认 `git rev-parse --short=10 HEAD`；拒绝 `local/latest/dev/main`；要求 `^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$` |
| 干净提交门禁 | 已跟踪文件有未提交改动时拒绝构建（`-AllowDirty` 仅用于机制演练） |
| 构建与打 tag | `api`(services/api)、`web`(apps/web)、`ai`(根目录 + services/ai/Dockerfile) |
| 不可变检查 | 本地 registry 先 `HEAD /v2/<repo>/<component>/manifests/<release>`，200 即拒绝；本地同名镜像亦拒绝（`-AllowOverwrite` 仅演练） |
| 推送与记录 | `docker push` 后读取 `RepoDigests`，写 `release-<release>.json`（release、commit、仓库、创建时间、三个镜像的 reference+digest、`compose_env`） |
| 失败语义 | 任一构建/推送失败即非 0 退出；推送成功但读不到 digest 也视为失败（避免“无指纹发布”） |

本机 registry 为 `registry:2`（digest pin），监听 `127.0.0.1:5001`，卷 `knowflow-registry-data`，与 3443 入口端口互不冲突；compose 变量由 `.env.production` 的 `KNOWFLOW_IMAGE_REPOSITORY` / `KNOWFLOW_RELEASE` 提供。

**与回滚演练的配合**：每次发布会保留旧 release 的 tag 与 digest 清单。回滚=把 `KNOWFLOW_RELEASE` 改回旧值，然后：

```powershell
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml pull
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml up -d --no-build
```

因为 tag 不可变，`pull` 拉到的就是当初签发的镜像；digest 清单可用于事后核对“线上运行的镜像确实是这一份”。

**本机验证（`2a7e68a`，隔离 registry `127.0.0.1:5001`）**：

```text
push api/web/ai -> digest:
  api  sha256:20f4a3ae6a3d20e89003591a1c3cbcd142582e4eb04030d8709fcae573ca6d10
  web  sha256:760ffdab8274a992f5d9a15aeb0ba068e674bb01fea57e4eab4c0a32c834d1fa
  ai   sha256:c322d9594a0baf5018b40c275368c58a5d9af229bb7a8cf4bc9854825cc2e481
重复执行（不 -AllowOverwrite）-> exit 1:
  127.0.0.1:5001/knowflow/api:2a7e68a 已存在于 registry；不可变 tag 禁止覆盖
docker rmi 三个 registry tag 后 pull -> 三个 digest 与清单完全一致
  清单：D:\konwflow-prod-drill\releases\release-2a7e68a.json
```

注意：本机 Docker 使用 containerd 镜像存储，推送的是 OCI image index；不可变检查的 `Accept` 头必须同时声明 `application/vnd.oci.image.index.v1+json` 等四种类型，否则 `HEAD` 会误判 404（脚本已按此实现）。

**生产待承接**：registry 的认证/TLS、保留与垃圾回收策略、跨可用区复制/备份；远端 registry 的“禁止覆盖”需由仓库策略（如 Harbor immutable tags / ECR tag immutability）强制，脚本只做本地兜底。

### 13.2 Flyway 回滚策略

Flyway Community 无 undo，**不做反向 DDL 脚本**；回滚以“迁移前物理快照 + 恢复到快照”为唯一可靠路径，并保留正向迁移目标开关用于演练。

新增/扩展：

| 文件 | 作用 |
| --- | --- |
| `deploy/scripts/db-backup.ps1` | 迁移前 `pg_dump -Fc`；记录 `flyway_schema_history` 最大成功版本；生成 `.dump.json` 伴随文件（含 SHA-256） |
| `deploy/scripts/db-restore.ps1` | `-ConfirmRestore` 显式确认；校验伴随文件 SHA-256；冻结 api/ai/web/edge；`DROP DATABASE` + `CREATE DATABASE` + `pg_restore --exit-on-error`；核对 Flyway 版本与备份一致；按依赖顺序 `up -d --no-deps` 恢复服务 |
| `KNOWFLOW_MIGRATION_TARGET` | `DatabaseMigrationProperties` + `DatabaseMigrationConfiguration` 支持 Flyway `target`；值为数字点分版本（如 `2`、`2.1`），留空=最新；仅用于演练/受控回退，正式发布保持留空 |

备份/恢复流程：

```powershell
# 1) 迁移前（栈健康时）
pwsh -File deploy/scripts/db-backup.ps1 -ProjectName knowflow-prod -Label pre-release

# 2) 正常发布（migrate 跑到最新）
docker compose ... run --rm migrate

# 3) 需要回滚到迁移前
pwsh -File deploy/scripts/db-restore.ps1 -ProjectName knowflow-prod `
  -DumpPath D:\konwflow-prod-drill\backups\knowflow-<label>.dump -ConfirmRestore
```

**演练验证（隔离项目 `knowflow-migtest`，已完成 `down -v`）**：

```text
全新库 -> KNOWFLOW_MIGRATION_TARGET=2：
  Flyway "8 migrations validated, 2 applied"（V1、V2）
备份：pg_dump 0.04 MB，sidecar 记录 version=2
继续迁移到最新 -> V8，indexing_tasks 出现 accepted_lease_id 列
恢复备份 -> Flyway 版本回到 2，accepted_lease_id 不存在，表 owner=knowflow_migrator
再次 migrate -> V8，accepted_lease_id 重新出现
```

关键点：`pg_restore` **不能加 `--no-owner`**。第一次演练加上后，还原表的 owner 变成 `postgres`，后续 `migrate` 因 `knowflow_migrator` 无 ALTER 权限而 exit 1；去除该参数、保留原 owner/ACL 后复测通过。恢复脚本因此默认保留 owner。

**生产待承接**：本机演练的备份在宿主目录，生产必须落到异地/对象存储并做定期恢复抽检；`pg_dump` 是逻辑备份，恢复点=备份时刻，备份之后的写入会丢；RPO/RTO 需由生产备份体系（WAL 归档/PITR、保留策略、加密与访问控制）承接。回滚仍属“人工确认”动作，未接到自动化发布流水线。

### 13.3 `provider-egress` 域名白名单

**方案**：在 `provider-egress` 与 `ai` 之间加一层 Squid 正向代理，`ai` 只能经代理出网；代理只放行 CONNECT 到 provider 域名，其余一律拒绝。网络结构：

| 网络 | 成员 | 属性 |
| --- | --- | --- |
| `knowflow` | 全部内部服务 | `internal: true` |
| `egress-internal` | `ai`、`egress-proxy` | `internal: true` |
| `provider-egress` | 仅 `egress-proxy` | 保留为外网出口 |
| `web-edge` | `edge`、`web` | 入口与静态资源（非 internal，有外网出口） |
| `edge-ai` | `edge`、`ai` | `internal: true`；仅供 edge 转发 `/health/ready` |

新增 `deploy/egress/squid.conf`（关键规则）：

```conf
acl CONNECT method CONNECT
acl provider_domains dstdomain api.deepseek.com api.siliconflow.cn
http_access allow CONNECT provider_domains
http_access deny CONNECT
http_access deny all
```

`egress-proxy` 使用 `ubuntu/squid`（digest pin），只读挂载该配置，healthcheck 为 `squid -k check`；`ai` 的 `HTTPS_PROXY/HTTP_PROXY` 指向 `http://egress-proxy:3128`，`NO_PROXY` 只含内部服务名。代理为空即 `ai` 无外网出口（fail-closed），`preflight.ps1` 对空代理与缺失白名单均判 FAIL。

**验证方法（隔离项目 `knowflow-egresstest`，已完成 `down -v`）**：把 `ai` 镜像接入 `knowflow-egresstest_egress-internal`，容器内执行：

```text
经代理 GET https://api.deepseek.com/models -> STATUS 401（已穿过代理，缺认证属预期）
经代理 GET https://example.com           -> ProxyError: 403 Forbidden
不设代理 GET https://api.deepseek.com/models -> ConnectError（无外网路由）
```

三条结果同时成立，说明“只白名单可达 + 其余被代理拒绝 + 无代理时无直连出口”。日常复核可从运行中的 `ai` 容器重复上述两类请求；`preflight.ps1` 另提供静态检查（白名单含两个 provider 域名、代理变量非空）。

**生产形态栈复测时发现并修复的缺口**：`ai` 原本还挂在非 internal 的 `web-edge` 上（为了让 edge 转发 `/health/ready`），因此容器内**绕过代理直连** `api.deepseek.com` 得到 401——白名单可被绕过。修复：新增 internal 网络 `edge-ai`，只允许 `edge` 与 `ai` 加入；`ai` 的 `web-edge` 成员资格移除。复测：

```text
经代理 https://api.deepseek.com/models -> 401（可达）
经代理 https://example.com             -> ProxyError 403 Forbidden（拒绝）
直连（清除代理变量）api.deepseek.com    -> ConnectError: Temporary failure in name resolution
```

修复后 `edge-ai` 成员为 `ai`+`edge`，`web-edge` 仅 `edge`+`web`；`/health/ready` 仍经 edge 返回 200。

**生产待承接**：宿主/云安全组的出站防火墙规则（纵深防御第二层）、代理的高可用与访问日志留存、provider 域名变更时的白名单变更流程（改 `squid.conf` 并重启 `egress-proxy`）。本机未验证 TLS 出站审计与并发限流。

### 13.4 本机验证汇总与生产待承接

| 项 | 本机结果 | 生产必须承接 |
| --- | --- | --- |
| 本地 registry 构建/推送/digest | PASS（详见 §13.1） | registry 认证、TLS、保留策略、HA |
| 不可变 tag 拒绝覆盖 | PASS（exit 1，日志见 §13.1） | 仓库级 immutable 策略 |
| compose 拉取后启动 | PASS（`pull` + `up -d --no-build`，见 §13.5） | 发布流水线与审批 |
| 迁移前备份 + 恢复到 V2 | PASS（隔离库，见 §13.2） | 异地备份、PITR、定期恢复抽检 |
| Flyway 目标版本开关 | PASS（`KNOWFLOW_MIGRATION_TARGET=2`） | 正式环境保持留空 |
| 代理白名单放行/拒绝/无直连 | PASS（见 §13.3） | 宿主防火墙、日志审计、代理 HA |
| 端口/卷隔离 | 使用 3443/5001 与独立卷，未触碰既有环境的 5432/6379/6380；演练项目均 `down -v` | — |

### 13.5 端到端复核（干净提交后的真实发布）

**发布**：`05fbd6e`（`feat(release): immutable image tags, ...`）。发布时工作树干净（`release.ps1` 的脏工作树门禁通过），release 名为 10 位短 sha `05fbd6e51e`，清单 `D:\konwflow-prod-drill\releases\release-05fbd6e51e.json`。

| 组件 | tag | digest |
| --- | --- | --- |
| api | `127.0.0.1:5001/knowflow/api:05fbd6e51e` | `sha256:9d223327773477ec00b6f0ed5f9672d2129aec8791f540875458100dc3e45a54` |
| web | `127.0.0.1:5001/knowflow/web:05fbd6e51e` | `sha256:b934fdcc5ef53d915bde4618ee706d78fafc5e7b6243be6c2499b139ed3c02b1` |
| ai | `127.0.0.1:5001/knowflow/ai:05fbd6e51e` | `sha256:4ba1b73baedc476dd456f39d038fbc41134462c49929b845d89ecf356013c5db` |

**镜像拉取**：先 `docker rmi` 本机三个 release tag，再 `docker compose pull`，三个镜像均由 `127.0.0.1:5001` 拉取成功（layers 已缓存，manifest 从 registry 解析）。随后 `up -d --no-build --wait` 在 **58s** 内全部 healthy（migrate 一次性退出码 0）。

**就绪与冒烟**（`release-05fbd6e51e`）：

```text
/health/ready -> 200 {"status":"UP","checks":{"budget":"UP","llm":"UP","embedding":"UP"}} 0.57s
/api/mode     -> 200 {"mode":"external"}
```

完整 HTTPS 冒烟（未使用 `-AllowProviderBlocked`）：**PASS**，5.2s，证据 `D:\konwflow-prod-drill\evidence\smoke-release-05fbd6e51e-final.json`。

| 步骤 | 状态 | 结果 |
| --- | --- | --- |
| register / login / `/me` / 建知识库 | 201 / 200 / 200 / 201 | token 不落输出 |
| 上传文档 | 202 | `document_id=9a86f7ca-…` |
| 索引完成 | 200 | `SUCCEEDED` / `READY`，约 2.0s |
| 可答问题 | 200 | `has_answer=True`，**sources=1**，答案 `青岚项目的代号是QL-2026[0047257b-…]` |
| 不可答问题 | 200 | `has_answer=False`，`sources=0`，固定拒答文案 |

**Egress 实际拦截**（运行中的 `knowflow-prod-ai-1` 容器内）：

```text
经代理 https://api.deepseek.com/models -> ALLOWED_STATUS 401（可达）
经代理 https://example.com             -> ProxyError 403 Forbidden（非白名单拒绝）
清除代理变量直连 api.deepseek.com       -> ConnectError: Temporary failure in name resolution（无外网路由）
```

结论：非白名单域名**确实不通**，且 ai 无直连旁路（含 §13.3 的 `edge-ai` 修复）。

**Flyway 迁移前备份与恢复（隔离项目 `knowflow-migtest`，验证后 `down -v`）**：

```text
KNOWFLOW_MIGRATION_TARGET=2 -> validated 8 / applied 2，版本 v2
db-backup.ps1              -> 0.04 MB，sidecar flyway_version=2，SHA-256 d7c9a611…
migrate 到最新             -> applied 6，版本 v8，accepted_lease_id 存在（count=1）
db-restore.ps1             -> 版本回到 2，accepted_lease_id 不存在（count=0）
                             表 owner 仍为 knowflow_migrator
再次 migrate               -> applied 6，版本 v8，accepted_lease_id 重新出现（count=1）
```

**清理**：`knowflow-prod` 执行 `stop`（保留 `postgres-data` / `object-data` / `budget-ledger` 卷），`egress-proxy` 与入口随之停止，3443 释放；本机 registry 容器停止，5001 释放，`knowflow-registry-data` 卷保留。`knowflow-migtest`、`knowflow-egresstest` 已 `down -v`。

**遗留（本轮未处理，非本次范围）**：工作树中 `scripts/e2e-web.mjs` 有一处与本任务无关的本地改动（web-v2 试验），未纳入本次提交，也未参与 `05fbd6e` 构建。
