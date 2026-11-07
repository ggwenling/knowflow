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
| 无镜像仓库与不可变发布 tag | 仍未解决；回滚依赖本机镜像 |
| Flyway 无 down 脚本 | 仍未解决；跨迁移回滚需 `pg_dump` 恢复 |
| 健康检查不探活 provider / 预算 | **已实现** `/health/ready`（见 §12） |
| `provider-egress` 无域名白名单 | 需宿主机防火墙/代理补足，见 §5.3 |
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

- 镜像仓库/不可变发布 tag、Flyway down、`provider-egress` 域名白名单仍未解决（见 §9）。
- 探针只验证 provider 的模型列表可达；它不能替代一次真实生成，发布门禁仍建议在验收阶段跑 §12.4 的完整冒烟。
