# KnowFlow Web v2

新版工作台通过 Next.js 的同源代理接入现有 KnowFlow API。登录、知识库、文档索引、问答和原文均使用真实后端数据。Compose 本地模型仍是确定性验证用的合成模型。

界面规范见 [DESIGN.md](./DESIGN.md)：统一黑白编辑感外壳、四页核心链路、响应式与可访问性基线。

新增的前端运行时依赖（均为 MIT）：`motion`（页面与列表动效）、`sonner`（轻提示）、`react-markdown` + `remark-gfm`（答案排版，动态加载）。生产依赖许可清单见 [THIRD-PARTY-LICENSES.md](./THIRD-PARTY-LICENSES.md)；根清单仍只覆盖 `apps/web`，发行前需合并。

部署到非 localhost 时设置 `NEXT_PUBLIC_SITE_URL`（例如 `https://knowflow.example.com`），用于 OG/Twitter 分享图的绝对地址。

## 启动

从仓库根目录按 [Compose 开发说明](../../infra/README.md) 配置 `infra/.env`，再运行：

```powershell
docker compose --project-name knowflow-local --env-file infra/.env -f infra/compose.yml up -d --build --wait
```

默认入口为 http://127.0.0.1:3000。端口与绑定地址由 `KNOWFLOW_WEB_PORT`、`KNOWFLOW_WEB_HOST_BIND` 控制。容器内的 `KNOWFLOW_API_BASE_URL` 指向 API，`KNOWFLOW_WEB_MODEL_MODE` 标识模型运行模式。Compose 健康检查使用 `/api/mode`，完整链路通过浏览器验收。

## 验证

在此目录运行 `npm ci`、`npm run typecheck`、`npm run lint` 和 `npm run build`。安装 Playwright Chromium 后运行 `npm run e2e`。该命令使用独立 Compose 项目和临时卷，完成问答流契约检查和同一数据集上的旧版回退检查。

直接对已运行的 Compose 栈跑浏览器回归：

```powershell
$env:KNOWFLOW_E2E_STREAM_CAPTURE = "$env:TEMP\knowflow-stream.json"
npx playwright test
```

人工验收证据（凭据只从环境变量读取，不写入磁盘）：

```powershell
$env:KNOWFLOW_ACCEPTANCE_EMAIL = "<验收账号>"
$env:KNOWFLOW_ACCEPTANCE_PASSWORD = "<密码>"
node scripts/acceptance.mjs
```

产物写入 `eval-out/acceptance-20261108/`，包括 `manifest.json` 与 1440/768/390 截图。流程与签字表见 `docs/acceptance/2026-11-08-web-v2-manual-acceptance.md`。

## 交互约定

- 导航、知识库卡片、历史记录使用真实链接，支持 Cmd/Ctrl+click、中键与新标签打开。
- 知识库搜索 `?q=`、详情筛选 `?status=`、对话历史搜索 `?history=` 写入 URL，可深链与刷新恢复。
- 首页与登录页保留唯一高光动效；其余页面尊重 `prefers-reduced-motion`。
- Tab 首站为“跳到主要内容”，所有输入与按钮有可见焦点。

## 回退

从仓库根目录运行：

```powershell
docker compose --project-name knowflow-local --env-file infra/.env -f infra/compose.yml -f infra/compose.legacy-web.yml up -d --no-deps --build --wait web
```

回退仅重建 Web 服务。若已有环境使用不同的项目名，沿用原项目名以访问同一组卷。恢复新版时使用启动命令中的基础 Compose 文件重建 `web`。两个版本使用相同的 API、端口和数据卷。
