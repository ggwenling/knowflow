# 全栈本地环境

`compose.yml` 启动 PostgreSQL/pgvector、MinIO、迁移任务、Java API、Python AI 服务与 Next.js Web。数据卷使用 Compose 项目名前缀隔离；只有 Web 在宿主机开放端口。Web 同时加入入口网络和内部服务网络，其余服务只加入内部网络。

从仓库根目录首次启动：

```powershell
Copy-Item infra/.env.example infra/.env
docker compose --project-name knowflow-local -f infra/compose.yml --env-file infra/.env up --build --wait
```

先为 `.env` 中的密码和内部共享凭证生成不同的随机值。默认页面为 `http://localhost:3000`，使用 `apps/web-v2`。旧版回退命令见 [Web v2 说明](../apps/web-v2/README.md#回退)。停止服务并保留本地数据：

```powershell
docker compose --project-name knowflow-local -f infra/compose.yml --env-file infra/.env down
```

只有明确要删除 `knowflow-local` 环境里的 PostgreSQL 与 MinIO 数据时，才给 `down` 添加 `--volumes`。不得把示例值用于实际凭证，也不要提交 `infra/.env`。

本 Compose 使用网络隔离的合成 AI 适配器，模型模式会在页面显示。真实 provider 质量、隐私条款与费用评测仍需独立执行。
