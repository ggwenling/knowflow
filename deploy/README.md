# deploy/ — 部署草案（#15）

- 分支：`agent/deploy-prep`（从 `local@84681d4` 拉出）
- 性质：**草案**。本目录只放文档与只读脚本，**未改动任何业务代码、依赖清单或现有 `infra/` 配置**。
- 状态：`DRAFT / NOT EXECUTED`。没有任何一条步骤在真实生产环境跑过。已执行的只有 `infra/` 下两套隔离 Compose 的备份恢复演练。

## 1. 这个目录解决什么问题

仓库现在只有**一套** Compose：`infra/compose.yml`。它是 E2E / 开发用的，不是生产形态：

| 事实 | 证据 |
|---|---|
| AI 服务跑的是合成 E2E 服务器，不是真实应用 | `infra/compose.yml` 中 `ai.command: ["python", "services/ai/tools/browser_e2e_server.py", ...]` |
| Web 处于合成模型模式 | `KNOWFLOW_WEB_MODEL_MODE: synthetic` |
| 凭证是 E2E 假 key | `KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY` / `KNOWFLOW_E2E_DUMMY_LLM_KEY` |
| 无重启策略、无日志上限、无资源限制 | 除 `migrate` 外全部缺省 |

所以"部署"这件事目前在仓库里**没有对应物**。本目录补的是形态与门槛，不是最终答案。

## 2. 目标拓扑（草案）

```
                    ┌──────────── 公网 ────────────┐
                    │                              │
              :443 TLS 终止（外部网关/反代，未在仓库内）
                    │
              ┌─────▼─────┐  web-edge 网络
              │   web     │  Next.js  :3000
              └─────┬─────┘
                    │ knowflow 网络（internal: true）
      ┌─────────────┼──────────────┬──────────────┐
      │             │              │              │
┌─────▼─────┐ ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
│   api     │ │    ai     │  │ postgres  │  │  minio    │
│ :8080     │ │ :8000     │  │ :5432     │  │ :9000     │
│ Spring    │ │ FastAPI   │  │ pgvector  │  │ S3 兼容   │
└───────────┘ └───────────┘  └───────────┘  └───────────┘
```

- **只有 `web` 有宿主端口**（默认绑 `127.0.0.1`，由前置反代对外）。
- `api` / `ai` / `postgres` / `minio` 不暴露宿主端口。
- `ai` 只接受带 `KNOWFLOW_INTERNAL_SHARED_SECRET` 的内部请求（`BoundaryMiddleware` 常量时间比较）。
- 数据库四角色：`knowflow_migrator`（只跑迁移）、`knowflow_app`（API 读写）、`knowflow_ai`（AI 只读检索）、`postgres`（仅初始化）。

## 3. 文件索引

| 文件 | 用途 | 是否可直接执行 |
|---|---|---|
| `README.md` | 本文件：范围、拓扑、边界 | — |
| `PRODUCTION-CHECKLIST.md` | 部署前/中/后逐项门槛与证据要求 | 人工执行 |
| `UPGRADE-ROLLBACK.md` | 升级与失败回滚路径（含"数据库不降级"的硬边界） | 人工执行 |
| `THIRD-PARTY-NOTICES.md` | 随镜像分发的第三方署名与许可证义务清单 | 直接随镜像分发 |
| `env/production.env.example` | 生产环境变量**名称**清单（全部空值） | 复制后填写 |
| `compose.production.draft.yml` | 生产形态 Compose 草案 | 已通过 `docker compose config` 解析，**从未起过容器，禁止直接上线** |
| `scripts/preflight.ps1` | Windows 侧只读预检 | 可执行，只读 |
| `scripts/preflight.sh` | Linux 目标机只读预检 | 可执行，只读 |

## 4. 明确不做的事

- 不改 `infra/compose.yml`（E2E 用途保持不变）。
- 不新增生产反代 / TLS / 证书配置（属基础设施团队边界）。
- 不引入密钥管理服务，只规定"变量从环境注入，不落盘、不入库"。
- 不声称任何步骤已验证。`compose.production.draft.yml` 只在 2026-11-03 用一次性 env 文件跑过 `docker compose config`（语法通过、6 个服务齐全），**没有启动过任何容器**。

## 5. 与其它任务的关系

| 任务 | 关系 |
|---|---|
| #11 分支卫生 | 本分支基于 `local@84681d4`，合并前需先确认 `local` 未被改写 |
| #14 许可/脱敏审计 | `THIRD-PARTY-NOTICES.md` 与 `PRODUCTION-CHECKLIST.md` 的日志抽样项直接来自该审计结论 |
| #9 真实评测 | 生产部署需要真实 provider 凭证；预算门禁未通过前，生产应保持 `KNOWFLOW_WEB_MODEL_MODE` 与 AI adapter 的 fail-closed 行为 |
| PR #3 | 本目录不阻塞也不依赖 PR #3；合并时作为独立 docs-only 增量 |

## 6. 下一步（需要负责人决定）

1. 目标环境形态：单机 Compose / 单机 + 外部托管 PG+对象存储 / K8s。
2. 域名与 TLS 终止位置。
3. 备份目标与保留期（现有演练只覆盖"隔离环境内的备份与恢复"，不含异地与保留策略）。
4. 是否允许在真实 provider 预算门禁通过前上线（当前建议：不允许）。
