# KnowFlow Web

面向研发人员的个人文档核验工作台。前端通过 Next.js 同源 API 代理访问 Java，不向浏览器返回 Bearer token。页面包含注册/登录、知识库、上传和索引状态、单轮流式问答、来源预览及历史问答。

## 本地启动

先安装 Docker Desktop 并准备 `infra/.env`（见 [基础设施说明](../../infra/README.md)），再从仓库根目录启动隔离的全栈环境：

```powershell
Copy-Item infra/.env.example infra/.env
docker compose -f infra/compose.yml --env-file infra/.env up --build --wait
```

为 PostgreSQL 迁移/应用/AI 角色、MinIO 和内部服务凭证分别生成新的随机值并填写到 `infra/.env`。不要提交该文件。页面仅监听 `127.0.0.1:3000`。

## 检查

在 `apps/web/` 安装依赖后，运行 `npm run typecheck`、`npm run lint`、`npm test` 和 `npm run build`。`npm run e2e` 会用随机本地凭据和独立 Compose 项目启动完整栈、执行 Playwright 测试，随后清理该测试项目和卷；它需要本机 Docker 与 Playwright Chromium。

本地 Compose 固定使用确定性合成模型，用于检验授权、索引、流式事件和原文链路，不用于评价真实模型质量或费用。它只暴露 Web 端口；Web 同时加入入口网络和内部服务网络，PostgreSQL、MinIO、Java 和 Python 只加入内部网络。
