# 生产部署检查清单（草案）

状态：`DRAFT`。没有任何一项在真实生产环境执行过。逐项打勾时**必须写证据**，不能只写"通过"。

约定：

- `[ ]` 未做 / `[x]` 已做 / `[!]` 阻塞（写原因）
- 每项的证据栏至少包含：执行时间（HKT）、执行人、命令、原始输出或报告路径、绑定 SHA
- 任何一项 `[!]` 都不得进入下一阶段

---

## G0 — 前置决定（负责人签字，无技术门槛）

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| G0-1 | 目标形态已定：单机 Compose / 单机 + 托管 PG+对象存储 / K8s | [ ] | |
| G0-2 | 域名与 TLS 终止位置已定（仓库不含反代配置） | [ ] | |
| G0-3 | 备份目标、保留期、异地副本策略已定 | [ ] | |
| G0-4 | 真实 provider 预算门禁已通过（或书面批准软预算） | [ ] | 当前状态：未通过，`create_evaluation_app()` 保持 fail-closed |
| G0-5 | 明确本次上线是"演示"还是"真实用户可用" | [ ] | 若为演示，`KNOWFLOW_WEB_MODEL_MODE=synthetic` 可接受并须在界面标注 |

> 阻塞提示：G0-4 未通过时，生产环境不应配置真实 provider key。当前 `deploy/env/production.env.example` 预留了真实 key 的位置，填写即等于解锁真实调用。

---

## G1 — 代码与契约冻结

| # | 项 | 命令 | 状态 | 证据 |
|---|---|---|---|---|
| G1-1 | 目标提交 SHA 已记录且等于 `origin/local` | `git rev-parse HEAD origin/local` | [ ] | |
| G1-2 | 工作树干净（无未提交改动） | `git status --porcelain -uno` | [ ] | |
| G1-3 | 契约 schema 指纹匹配 | `sha256sum contracts/schemas/protocol.schema.json` = `20121f69…4883f` | [ ] | |
| G1-4 | 目标 SHA 的 CI 三 job 全绿 | GitHub Actions | [ ] | run 链接 |
| G1-5 | 打了不可变 tag | `git tag -a <name> <sha>` | [ ] | 当前仓库 **0 tag** |

---

## G2 — 构建与产物

| # | 项 | 命令 | 状态 | 证据 |
|---|---|---|---|---|
| G2-1 | 三镜像构建成功 | `docker compose -f deploy/compose.production.draft.yml build` | [ ] | |
| G2-2 | 记录每个镜像的 image ID + repo digest | `docker images --digests` | [ ] | |
| G2-3 | 基础镜像 digest 已固定（当前 6 处未固定） | `deploy/scripts/preflight.ps1` 的 `dockerfile-digest` 项 | [ ] | |
| G2-4 | 第三方声明随镜像分发 | `deploy/THIRD-PARTY-NOTICES.md` 打进 web / api / ai 镜像 | [ ] | 见 #14 A4-2 |
| G2-5 | （可选）镜像漏洞扫描已执行 | `trivy image <ref>` | [ ] | 当前 CI 无此环节 |

---

## G3 — 配置与密钥

| # | 项 | 命令 | 状态 | 证据 |
|---|---|---|---|---|
| G3-1 | 预检脚本全绿 | `deploy/scripts/preflight.ps1 -EnvFile <env>` | [ ] | FAIL/WARN 计数 |
| G3-2 | `KNOWFLOW_INTERNAL_SHARED_SECRET` 为随机 32+ 字符，api 与 ai 同值 | 预检项 `secret/*` | [ ] | |
| G3-3 | 数据库三角色密码互不相同，且 `KNOWFLOW_AI_DATABASE_URL` 内嵌密码与 `KNOWFLOW_DEV_AI_PASSWORD` 一致 | 人工核对 | [ ] | |
| G3-4 | AI 与 API 的 runtime profile 一致 | 预检项 `env/runtime-profile` | [ ] | |
| G3-5 | 密钥未进入版本控制 | 预检项 `secret/tracked-key-scan` | [ ] | 当前 **FAIL**：`services/ai/.env.example` 工作树含疑似真实 key（#14 B4） |
| G3-6 | 密钥轮换责任人与周期已定 | — | [ ] | |

---

## G4 — 数据层

| # | 项 | 命令 | 状态 | 证据 |
|---|---|---|---|---|
| G4-1 | 空库可迁移到最新版本 | `migrate` 服务 `--migrate-only` 退出码 0 | [ ] | |
| G4-2 | Flyway 版本记录符合预期 | `SELECT version FROM flyway_schema_history ORDER BY installed_rank` | [ ] | 当前最高 V8 |
| G4-3 | 角色权限复核：`knowflow_app` 无 DDL、`knowflow_ai` 只读 | `psql` 权限查询 | [ ] | 参考 `services/ai/docs/evidence/local-db-role-audit-draft6.json`（draft.6 时点） |
| G4-4 | 部署前基线备份已完成并校验 | `pg_dump` + MinIO 归档，记录 SHA-256 | [ ] | 方法见 `docs/operations/backup-restore-acceptance.md` |
| G4-5 | 恢复路径在隔离环境演练过 | `infra/backup_restore_e2e.py` | [ ] | 已有隔离证据，**不含生产目标环境** |

---

## G5 — 启动与冒烟

| # | 项 | 命令 | 状态 | 证据 |
|---|---|---|---|---|
| G5-1 | `docker compose config` 无错误 | `docker compose --env-file <env> -f deploy/compose.production.draft.yml config` | [x] | 2026-11-03 用一次性 env 文件解析通过，6 服务齐全；**未起容器**，需用真实 env 再跑一次 |
| G5-2 | 全部服务 healthy | `docker compose ps` | [ ] | |
| G5-3 | 冒烟：注册 → 建库 → 上传 TXT → READY | 手工或 `scripts/e2e-web.mjs` 改造 | [ ] | |
| G5-4 | 冒烟：提问 → SSE 流式 → 来源可打开 | 同上 | [ ] | |
| G5-5 | 冒烟：删除文档 → 索引与对象清理 | 同上 | [ ] | |
| G5-6 | 冒烟：用户 B 无法访问用户 A 的资源 | 两个账号 | [ ] | |
| G5-7 | 只有 `web` 端口对外，其余无宿主端口 | `docker compose ps --format '{{.Service}} {{.Ports}}'` | [ ] | |

---

## G6 — 上线后 24 小时

| # | 项 | 方法 | 状态 | 证据 |
|---|---|---|---|---|
| G6-1 | 日志抽样脱敏复核（#14 B5 未覆盖项） | 抽 200 行 `api`/`ai`/`web` 日志，人工确认无正文、无 token、无 Authorization | [ ] | |
| G6-2 | 日志体积与轮转生效 | `docker inspect` 查看 `LogConfig`，检查文件大小 | [ ] | |
| G6-3 | 错误率与 p95 延迟记录 | 网关或日志统计 | [ ] | |
| G6-4 | 资源占用记录（mem/cpu）与 `mem_limit` 是否合理 | `docker stats` 采样 | [ ] | 草案里的限额是估值 |
| G6-5 | 首次增量备份成功 | 备份任务日志 | [ ] | |

---

## G7 — 回滚就绪

| # | 项 | 状态 | 证据 |
|---|---|---|---|
| G7-1 | 上一版本镜像仍在本地/registry 可取回 | [ ] | |
| G7-2 | 回滚演练在隔离环境做过一次 | [ ] | 见 `UPGRADE-ROLLBACK.md`，当前**未做** |
| G7-3 | 已明确"数据库不降级"的边界并告知负责人 | [ ] | |

---

## 已知未完成（截至 2026-11-03）

1. `deploy/compose.production.draft.yml` 只通过 `docker compose config` 语法解析，**从未启动过容器**，资源限额未压测。
2. 生产反代 / TLS / 证书不在仓库内。
3. 无镜像漏洞扫描环节。
4. 无升级失败回滚的真实演练（`docs/operations/backup-restore-acceptance.md` 明确记录此项未覆盖）。
5. 真实 provider 预算门禁未通过，生产不应配置真实 key。
6. `services/ai/.env.example` 工作树含疑似真实密钥，未清理。
