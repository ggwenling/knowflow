# 生产等价部署与回滚演练（2026-11-07）

> 后续修复（2026-11-07）：预算门禁、TLS 入口、受控出网等缺口已由
> [部署缺口修复记录](./2026-11-07-deployment-gap-remediation.md) 处理。
> 本文中的 `compose.production.budget.override.yml` 与 `http://127.0.0.1:3100` 入口
> 已废止，保留作演练历史证据；当前部署形态以修复记录为准。

本手册记录一次在 Windows 本机执行的生产等价部署、冒烟测试与回滚演练。所有命令均可复现；文中不包含任何密钥值，密钥仅从被 `.gitignore` 覆盖的本地文件或环境注入读取。

## 1. 结论

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 生产形态部署 | 成功 | PG / MinIO / Flyway / AI / API / Web 全部健康；首次 `up --wait` 44.7s |
| 健康检查 | 通过 | Web `/api/mode` 200、API `/actuator/health` 200、AI `/health/live` 200 |
| 登录取 token | 通过 | register 201、login 200、`/me` 200；token 只以 HttpOnly cookie 形式使用，未输出 |
| 上传并等索引完成 | 通过 | 上传 202，任务 `SUCCEEDED`，文档 `READY`，耗时约 2s |
| 带引用问答 | **受阻** | API 返回 502 `AI_PROCESSING_FAILED`，根因为 LLM provider 对 `deepseek-flash` 返回 HTTP 500（见 §9-G3） |
| 不可答问题拒答 | 通过（最终复跑） | 200，`has_answer=false`、`sources=[]`、回答“没有足够的资料证据回答这个问题。”；无证据短路拒答不依赖 LLM |
| 回滚到上一版本 | 成功（应用/基础设施层） | `d5abfe2` 三镜像 40.6s 全健康；数据库计数完全一致；原文档仍为 `ACTIVE`；新上传索引成功 |
| 恢复到 `2a7e68a` | 成功 | 40.5s 全健康；数据完整；新上传索引成功；问答仍受同一 provider 阻塞 |
| 生产部署与回滚手册 | 本文 | `docs/operations/2026-11-07-production-deploy-rollback-drill.md` |

结论边界：基础设施、数据库迁移、认证、文档上传与索引链路已在生产形态下验证通过；**带引用答案生成未能完成验收**，不是应用或回滚回归，而是 LLM provider 模型别名不可用。拒答在最终复跑中通过，证明“无证据短路”分支可用；若拒答需要经过 LLM 判断，则同样受 G3 影响。不得用 synthetic/开发配置冒充答案项通过。

## 2. 环境与版本

- 主机：Windows 11 专业版；PowerShell 7.6.9；Docker 29.8.2；Docker Compose v5.6.0
- 当前版本：`2a7e68a`（`main` 与 `local` 同一提交；契约 `0.2.0`）
- 回滚版本：`d5abfe2`（`2a7e68a` 的直接父提交；契约 `0.2.0-draft.10`）
- 数据库迁移：`V1`–`V8`，两个提交之间**没有任何迁移文件差异**
- 镜像（本地 tag，按 release 名区分）：

| 镜像 | 2a7e68a | d5abfe2 |
| --- | --- | --- |
| `knowflow-api` | `20f4a3ae6a3d` / 489MB | `dc2b55e12dda` / 489MB |
| `knowflow-ai` | `b7d4a0de76c8` / 385MB | `6e8ec3a8440f` / 385MB |
| `knowflow-web` | `760ffdab8274` / 1.32GB | `4180b3816931` / 1.32GB |

## 3. 隔离设计（不触碰开发环境）

| 维度 | 本次演练 | 开发环境（未使用） |
| --- | --- | --- |
| Compose 项目名 | `knowflow-prod` | `infra` 等 |
| 宿主机端口 | `127.0.0.1:3100`（仅 Web） | `8080/8000/55432/59000` |
| API/AI/PG/MinIO 宿主端口 | 不暴露 | 各自暴露 |
| 容器名 | `knowflow-prod-{web,api,ai,postgres,minio}-1` | 其他 |
| 数据卷 | `knowflow-prod_postgres-data`、`knowflow-prod_object-data`、`knowflow-prod_budget-ledger` | 其他 |
| 网络 | `knowflow-prod_knowflow`（internal）、`knowflow-prod_web-edge`、`knowflow-prod_provider-egress` | 其他 |

全程未执行 `down -v`，未删除任何数据卷。

## 4. 配置与预检

### 4.1 生产配置来源

使用仓库的生产等价文件，**不是** `infra/compose.yml`，也没有使用任何 dev profile：

- `deploy/compose.production.draft.yml`
- `deploy/env/production.env.example`
- `deploy/scripts/preflight.ps1`

生成被 `.gitignore` 覆盖的 `deploy/.env.production`。变量分组（值不在此记录）：

- PostgreSQL：superuser / `knowflow_migrator` / `knowflow_app` / `knowflow_ai` 四套凭据
- 对象存储：endpoint、bucket、access/secret key
- 服务鉴权：`KNOWFLOW_INTERNAL_SHARED_SECRET`（≥32 字符）
- 服务寻址：`KNOWFLOW_AI_BASE_URL`、`KNOWFLOW_JAVA_BASE_URL`、`KNOWFLOW_API_BASE_URL`
- 运行时档案：`KNOWFLOW_RUNTIME_PROFILE_ID=runtime-default`，且 `KNOWFLOW_INDEXING_RUNTIME_PROFILE_ID` 一致
- Embedding：`https://api.siliconflow.cn/v1`、`BAAI/bge-m3`、1024 维
- LLM：`https://api.deepseek.com`、`deepseek-flash`
- Web：`KNOWFLOW_WEB_MODEL_MODE=external`、`NODE_ENV=production`
- 隔离：`KNOWFLOW_RELEASE=2a7e68a`、`KNOWFLOW_WEB_HOST_BIND=127.0.0.1`、`KNOWFLOW_WEB_PORT=3100`

密钥取自本机 `services/ai/.env`（`EMBEDING_KEY`、`DEEPSEEK_API_KEY`）并写入 `deploy/.env.production`；未打印、未提交。

### 4.2 必须对齐 `KEY_ENV`

生产 compose 注入的是 `KNOWFLOW_EMBEDDING_API_KEY` / `KNOWFLOW_LLM_API_KEY`，而开发 `services/ai/.env` 的 selector 是 `EMBEDING_KEY`。若直接照抄开发 selector，容器内不存在对应变量，索引会以 503 / `AI_PROCESSING_FAILED` 失败。生产配置必须使用：

```dotenv
KNOWFLOW_EMBEDDING_KEY_ENV=KNOWFLOW_EMBEDDING_API_KEY
KNOWFLOW_LLM_KEY_ENV=KNOWFLOW_LLM_API_KEY
```

### 4.3 预检

```powershell
pwsh -NoProfile -File deploy/scripts/preflight.ps1 -EnvFile deploy/.env.production
```

部署前结果：17 PASS / 1 WARN / 0 FAIL。WARN 为 6 处 Dockerfile 基础镜像未 pin digest。部署后再次运行会因 `port-3100` 已被本栈占用而 FAIL（脚本没有跳过端口检查的参数），属预期；预检应在 `up` 之前执行。

Compose 配置校验，并定义后续命令复用的参数数组：

```powershell
$dc = @(
  '-p','knowflow-prod',
  '--env-file','deploy/.env.production',
  '-f','deploy/compose.production.draft.yml',
  '-f','deploy/compose.production.budget.override.yml'
)
docker compose @dc config --services
```

## 5. 部署

### 5.1 构建镜像

```powershell
$env:KNOWFLOW_RELEASE='2a7e68a'
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml `
  -f deploy/compose.production.budget.override.yml `
  build
```

构建产物见 §2。构建在后台执行，未逐段计时；镜像完成时间分别为 AI 15:02:32、Web 15:04:06、API 15:04:13。

### 5.2 启动

`budget.override.yml` 的必要性见 §9-G1/G2：

```powershell
$env:KNOWFLOW_RELEASE='2a7e68a'
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml `
  -f deploy/compose.production.budget.override.yml `
  up -d --wait --wait-timeout 300
```

实测 `exit=0 elapsed=44.7s`。`docker compose ps` 显示 `postgres/minio/ai/api/web` 均 `healthy`；`migrate`、`budget-init` 为一次性成功退出。

### 5.3 健康与迁移证据

```powershell
# Web 边缘
Invoke-WebRequest http://127.0.0.1:3100/api/mode -UseBasicParsing   # 200 {"mode":"external"}

# API / AI 仅容器网络可达
docker compose @dc exec -T api curl -fsS http://127.0.0.1:8080/actuator/health
docker compose @dc exec -T ai  python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health/live').read().decode())"
```

Flyway 日志：

```text
Successfully validated 8 migrations
Current version of schema "knowflow_flyway": 8
Schema "knowflow_flyway" is up to date. No migration necessary.
```

数据库角色存在 `knowflow_migrator`、`knowflow_app`、`knowflow_ai`；`knowflow_ai` 只有只读授权。

## 6. 冒烟测试

统一通过 Web 边缘 `http://127.0.0.1:3100` 验证，不额外暴露 API/AI 端口。可复用脚本：

```powershell
pwsh -NoProfile -File deploy/scripts/production-smoke.ps1 `
  -BaseUrl http://127.0.0.1:3100 -ContractVersion 0.2.0 -Label deploy `
  -EvidencePath D:\konwflow-prod-drill\evidence\smoke-deploy.json `
  -AllowProviderBlocked
```

实际步骤与结果（最终复跑证据时间 2026-11-07 15:28:31–15:28:49，`smoke-deploy-final.json`）：

| 步骤 | HTTP | 结果 |
| --- | --- | --- |
| `GET /api/mode` | 200 | `{"mode":"external"}` |
| register | 201 | 用户创建，cookie token 已获取（脱敏） |
| login | 200 | 新 token 下发（脱敏） |
| `GET /me` | 200 | `user_id=21876f7c-f7c1-4401-bd1b-310e339a3552` |
| 创建知识库 | 201 | `knowledge_base_id=60b42525-ee2b-4b13-bbd1-8a73700ef2f1` |
| 上传 txt | 202 | `document_id=47f0fa34-3525-4684-a8e4-b0af8adbe353` |
| 轮询任务 | 200 | `task_status=SUCCEEDED`、`document_status=READY`，约 2s |
| 带引用问答 | **502** | `AI_PROCESSING_FAILED`；未产生答案/引用，不能判定为通过 |
| 不可答问题 | 200 | `has_answer=false`、`sources=0`、回答“没有足够的资料证据回答这个问题。”，拒答通过 |

说明：首轮冒烟（15:11–15:13）对已索引文档提问“火星基地氧气储量”曾返回 502，因为该请求进入了 LLM 判断分支；最终复跑命中无证据短路，返回 200 拒答。因此拒答可用性取决于是否短路，依赖 LLM 的拒答分支仍受 §9-G3 影响。

补充探测：空知识库提问返回 409 `KNOWLEDGE_BASE_NOT_READY`（设计如此），不能替代“不可答问题拒答”用例。

## 7. 回滚演练

### 7.1 回滚前记录与备份

```powershell
# 数据快照（JSON 见 D:\konwflow-prod-drill\evidence\data-snapshot-before-rollback.json）
{"users":4,"knowledge_bases":4,"documents":4,"content_versions":4,
 "index_versions":8,"chunks":1,"chunk_embeddings":1,"questions":1,
 "question_sources":0,"flyway_version":"8"}

# 逻辑备份（文件含业务数据，仅放仓库外）
docker compose @dc exec -T postgres pg_dump -U postgres -d knowflow -Fc --file=/tmp/knowflow-before-rollback.dump
docker compose @dc cp postgres:/tmp/knowflow-before-rollback.dump D:\konwflow-prod-drill\backup\knowflow-before-rollback.dump
```

记录版本：`HEAD=2a7e68a`，运行镜像 `knowflow-{api,ai,web}:2a7e68a`。

迁移回退策略：Flyway 只有正向迁移，无 down 脚本。`d5abfe2 → 2a7e68a` 的差异提交没有新增/修改迁移（`git diff --name-only d5abfe2 2a7e68a -- services/api/src/main/resources/db/migration` 为空），schema 完全兼容，因此回滚到旧镜像时旧 Flyway 只做校验并输出 `No migration necessary`。若未来版本新增迁移，回滚必须使用本次备份恢复数据库，不能只换镜像。

### 7.2 构建上一版本镜像

```powershell
git switch --detach d5abfe2
$env:KNOWFLOW_RELEASE='d5abfe2'
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml `
  -f deploy/compose.production.budget.override.yml build
git switch local            # 恢复到 2a7e68a 工作树；镜像 tag 保留
```

### 7.3 执行回退

```powershell
$env:KNOWFLOW_RELEASE='d5abfe2'
docker compose @dc up -d --wait --wait-timeout 300
```

实测 `exit=0 elapsed=40.6s`。`ps` 显示 `ai/api/web` 镜像均为 `:d5abfe2` 且 healthy；PG/MinIO 未重建。

迁移日志：`Current version of schema "knowflow_flyway": 8`、`No migration necessary`。

### 7.4 回滚后验证

- 数据计数与回滚前**完全一致**（见 `data-snapshot-after-rollback.json`）。
- 回滚前索引的原文档 `a39cdd51-ea39-4755-83fc-e2bb645f7b0a` 仍为 `ACTIVE`，`active_index_version_id=edb5c68c-0540-48fa-93c1-40313fefa2f0`。
- 回滚后新链路（旧契约 `0.2.0-draft.10`）：register 201、login 200、`/me` 200、创建知识库 201、上传 202、索引 `SUCCEEDED`/`READY`（约 2s）。
- 问答请求 504 `PROCESSING_TIMEOUT`（15:21:16–15:21:47），根因与 §9-G3 相同，不是回滚回归。

### 7.5 恢复到 2a7e68a

```powershell
git switch local
$env:KNOWFLOW_RELEASE='2a7e68a'
docker compose @dc up -d --wait --wait-timeout 300
```

实测 `exit=0 elapsed=40.5s`；`ai/api/web` 镜像均回到 `:2a7e68a` 且 healthy。数据计数保持完整；原文档仍 `ACTIVE`。恢复后再次执行冒烟（契约 `0.2.0`）：register/login/`/me`/创建库/上传/索引全部通过，问答仍为 502（同一 provider 阻塞）。

## 8. 耗时汇总

| 动作 | 实测 |
| --- | --- |
| 首次 `up --wait` | 44.7s |
| 回滚 `up --wait` | 40.6s |
| 恢复 `up --wait` | 40.5s |
| 上传→索引 READY | 约 2s |
| 带引用问答（provider 故障返回） | 约 15s（新版本 502）/ 30s（旧版本超时 504） |
| 最终复跑冒烟（含拒答） | 15:28:31–15:28:49，合计约 18s |
| 镜像构建 | 后台执行；完成时间见 §2（未单独计时） |

## 9. 暴露的缺口（按严重度）

### G1（阻断）生产配置缺少 provider 预算门禁三件套

`services/ai/src/knowflow_ai/provider_budget.py` 对每次真实 provider 调用强制读取：

- `KNOWFLOW_BUDGET_LEDGER_PATH`
- `KNOWFLOW_BUDGET_PRICE_FILE`
- `KNOWFLOW_BUDGET_POLICY_FILE`

`deploy/compose.production.draft.yml` 与 `deploy/env/production.env.example` 均未声明，也没有 ledger 卷。缺失时所有 provider 调用 fail-closed：

```text
provider_budget_stopped reason=BUDGET_CONFIGURATION_REQUIRED
→ 索引 INDEX_WRITE_FAILED，问答 503 AI_PROCESSING_FAILED
```

本次演练用 `deploy/compose.production.budget.override.yml` 补齐：只读挂载仓库授权的 `PRICE_FILE.json` / `POLICY_FILE.json`（复制到仓库外 `D:\konwflow-prod-drill\budget`），ledger 使用独立命名卷，并由一次性 `budget-init` 修正卷属主。预算仍受代码内固定上限约束：soft CNY 8、hard CNY 10，且无可配置项。生产上线前必须把预算配置与额度策略纳入正式部署清单。

### G2（阻断）AI 服务无外网出口

生产 compose 把 `ai` 只接入 `knowflow`（`internal: true`）。实测容器内访问 `api.siliconflow.cn`：

```text
ConnectError: [Errno -3] Temporary failure in name resolution
→ 索引 MODEL_FAILURE
```

本次用 override 增加 `provider-egress` bridge 网络并挂到 `ai`。这会削弱原有隔离意图；正式方案应提供受控 egress 代理/DNS 策略，而不是简单加公网网络。

### G3（阻断问答验收）LLM 模型别名不可用

应用运行时把模型硬校验为 `deepseek-flash`，provider 对该请求返回 HTTP 500；同一 key 使用 `deepseek-chat` 返回 200，且响应中的 `model` 字段仍是 `deepseek-flash`。实测（容器内直连，脱敏）：

```text
POST /chat/completions model=deepseek-flash  status=500 internal_error
POST /v1/chat/completions model=deepseek-chat status=200 model=deepseek-flash
```

因此“带引用答案”无法完成，依赖 LLM 判断的拒答分支也不可用；无证据短路拒答仍可返回 200。由于 `LlmSettings` 固定 model、`PRICE/POLICY` 也只覆盖 `deepseek-flash`，仅改配置无法同时满足代码校验和预算校验；需要 provider 侧修复别名或由契约/代码变更引入可配置别名。本演练未改代码、未改契约。

### G4（交付阻断）生产 Web 仅 HTTP，session cookie 为 Secure

`NODE_ENV=production` 时 Web 代理写入 `Secure` session cookie，但 compose 只暴露 `http://127.0.0.1:3100`，没有 TLS 终止。浏览器在纯 HTTP 下不会回传该 cookie。本次冒烟通过脚本手动重放 `Set-Cookie` 才能继续。正式交付必须提供 HTTPS/TLS 终止（反向代理或负载均衡）。

### G5（流程缺口）无数据库回滚脚本

Flyway 仅正向迁移。本次 `2a7e68a ↔ d5abfe2` 无迁移差异，app 回滚安全；未来带迁移的版本回滚只能依赖 pg_dump 恢复。手册已给出备份命令，但“恢复备份”本身未在本次演练中执行（不需要）。

### G6（可复现性）基础镜像未 pin digest

预检 WARN：6 处 Dockerfile 基础镜像未固定 digest（`node:24-alpine`、`eclipse-temurin:21-jre-jammy`、`python:3.12-slim`、`ghcr.io/astral-sh/uv`、`maven` 等）。同一 release tag 重建可能得到不同底层。

### G7（文档/运维陷阱）预检端口检查与部署顺序

`preflight.ps1` 的 `port-3100` 检查在本栈运行时会 FAIL，且脚本没有 `--skip-port` 之类的开关。预检必须在 `up` 之前执行；对已部署环境重复预检会产生假 FAIL。

### G8（文档一致性）生产 env 示例未覆盖预算，且默认 synthetic

`deploy/env/production.env.example` 未列出 §G1 三个预算变量；同时把 `KNOWFLOW_WEB_MODEL_MODE` 默认写成 `synthetic`。真实部署必须显式改为 `external`，否则问答走合成模式，不能代表生产链路。

### G9（发布工程）无镜像仓库与发布 tag 规范

本次回滚依赖本机 `knowflow-*:{commit}` 本地镜像。正式交付应推送到镜像仓库并保留不可变 tag/digest；否则换机或清理本地镜像后无法复现回滚。

### G10（验收覆盖）健康检查不覆盖外部依赖，引用链路未验收

各服务均有容器健康检查，但 AI `/health/live` 不探测 provider 可用性；API 只依赖 AI healthy。G3 的 provider 故障不会让栈变 unhealthy，需在发布门禁中增加真实 provider 探活与预算探活。本次最多只验证了拒答；带引用答案与引用来源校验仍未验收，provider 恢复后必须补跑。

## 10. 证据位置

- 数据快照：`D:\konwflow-prod-drill\evidence\data-snapshot-before-rollback.json`、`data-snapshot-after-rollback.json`
- 数据库备份：`D:\konwflow-prod-drill\backup\knowflow-before-rollback.dump`（含业务数据，禁止提交）
- 冒烟证据 JSON：`D:\konwflow-prod-drill\evidence\smoke-deploy-final.json`；以及临时目录中的 `knowflow-prod-rollback-*.json`、`knowflow-prod-restore-*.json`
- 账本摘要（脱敏，演练结束时）：6 笔付费预留，合计 61,440 microyuan（CNY 0.06144）；14 笔零价 embedding；`budget_stops` 为空
- 一次性配置适配：`deploy/compose.production.budget.override.yml`

## 11. 清理

演练栈当前仍在运行，便于复核。仅停止（**不要** `down -v`）：

```powershell
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml `
  -f deploy/compose.production.budget.override.yml stop
```

若确认要删除本演练的容器与网络但保留数据卷：

```powershell
docker compose -p knowflow-prod --env-file deploy/.env.production `
  -f deploy/compose.production.draft.yml `
  -f deploy/compose.production.budget.override.yml down
```

数据卷 `knowflow-prod_postgres-data` / `knowflow-prod_object-data` 不会被 `down` 删除；只有 `down -v` 才会删除，本演练禁止使用。
