# Web v2 P0 agent 验收（2026-11-09）

结论：M1 7/7、M2 9/9、M3 4/4 PASS；清理 PASS。所有操作及签字由 gpt-6.1-sol agent 完成，无人工验收环节。

执行模型：`gpt-6.1-sol`（会话 turn_context 确认）；浏览器：Chromium 156.0.8078.4；环境：win32/x64; v24.22.1; http://127.0.0.1:3000；Docker Desktop / Compose `knowflow-local`。

实际执行时间：smoke 自 2026-11-09T09:08:35.429Z；模块 2026-11-09T09:08:55.934Z 至 2026-11-09T09:09:46.829Z（UTC，香港时间 +08:00）。本次未在原定 13:00–15:00 时段执行，不倒签。

依据：[2026-11-08 步骤模板](./2026-11-08-web-v2-manual-acceptance.md)。[独立证据文件](./2026-11-09-web-v2-agent-evidence.json)保存 manifest、实际执行模型、时间、源码和产物 SHA-256。基线 `bc5ed5adc61f5b76cd42ef03486da6a963c44441` 加所列工作区修改；仅将最终提交 CI 的结果用于提交级验证。

## 逐项执行签字

证据目录：`apps/web-v2/test-results/agent-acceptance-20261109-final/`。下表文件均相对此目录。10 张 smoke 截图及模块截图覆盖 390/768/1440；原始图片按仓库约定保留在本地，不提交二进制。

| 步骤 | 结果 | 截图 | agent 签字 |
|---|---|---|---|
| M1-01-register | PASS | `M1-01-register.png` | gpt-6.1-sol |
| M1-02-upload-ready | PASS | `M1-02-upload-ready.png` | gpt-6.1-sol |
| M1-03-pdf | PASS | `M1-03-pdf.png` | gpt-6.1-sol |
| M1-04-update | PASS | `M1-04-update.png` | gpt-6.1-sol |
| M1-05-rebuild | PASS | `M1-05-rebuild.png` | gpt-6.1-sol |
| M1-06-pagination | PASS | `M1-06-pagination.png` | gpt-6.1-sol |
| M1-07-isolation | PASS | `M1-07-isolation.png` | gpt-6.1-sol |
| M2-01-stream | PASS | `M2-01-stream.png` | gpt-6.1-sol |
| M2-02-cancel | PASS | `M2-02-cancel.png` | gpt-6.1-sol |
| M2-03-source | PASS | `M2-03-source.png` | gpt-6.1-sol |
| M2-04-pdf | PASS | `M2-04-pdf.png` | gpt-6.1-sol |
| M2-05-expired-source | PASS | `M2-05-expired-source.png` | gpt-6.1-sol |
| M2-06-history | PASS | `M2-06-history.png` | gpt-6.1-sol |
| M2-07-switch-refresh | PASS | `M2-07-switch-refresh.png` | gpt-6.1-sol |
| M2-08-responsive | PASS | `M2-08-responsive.png` | gpt-6.1-sol |
| M2-09-keyboard | PASS | `M2-09-keyboard.png` | gpt-6.1-sol |
| M3-01-mode | PASS | `M3-01-mode.png` | gpt-6.1-sol |
| M3-02-settings | PASS | `M3-02-settings.png` | gpt-6.1-sol |
| M3-03-service-error | PASS | `M3-03-service-error.png` | gpt-6.1-sol |
| M3-04-network | PASS | `M3-04-network.png` | gpt-6.1-sol |

| 模块 | 签字 | 日期 | 结果 | 证据 |
|---|---|---|---|---|
| M1 | agent:gpt-6.1-sol | 2026-11-09 | 7/7 PASS | modules-manifest.json M1；对应截图 |
| M2 | agent:gpt-6.1-sol | 2026-11-09 | 9/9 PASS | modules-manifest.json M2；对应截图 |
| M3 | agent:gpt-6.1-sol | 2026-11-09 | 4/4 PASS | modules-manifest.json M3；network-metadata.json |

签字原文：`agent:gpt-6.1-sol; executed 2026-11-09T09:09:46.720Z; M1 7/7, M2 9/9, M3 4/4; synthetic business model only`。这是一份实际 agent 执行记录，不声称具备外部可信启动器的加密证明。

## 操作与回归

- Docker Desktop 已启动；全栈重建及 healthy 检查通过，未删除本地卷。
- smoke：注册专用账号后运行 `scripts/acceptance.mjs`；manifest 六项 PASS；删除问答成功、删除库 204。
- 新增顺序全栈回归：注册/隔离、MD/PDF READY、更新/旧版本、重建、51 文档分页；真实 SSE、停止及延迟核验、文本/PDF、删除来源、56 条历史、切库/刷新、三尺寸抽屉、Tab/Enter/Escape；设置/出站、实际 API 停机及恢复。
- 来源失效原文泄漏、切库残留旧回答已先复现再修复；同时纳入本次所需的焦点返回、输入法 Enter、登录加载及窄屏修正。其余已有工作区修改未纳入 P0。
- 隔离契约：库页面拒绝访问、单文档 404；列表 200 空数组与不存在库响应一致，不泄漏是否存在。
- 网络证据仅记录 origin/path/method/type；不保存密码、Cookie、请求头、请求体或查询串。此结论只覆盖本地 synthetic 模式。
- 本轮回归前置 typecheck、lint、28 项单测及 Docker production build 通过。提交后必须另核对四个 CI job，旧 SHA 的成功不转移到新提交。

## 执行命令

```powershell
docker compose --project-name knowflow-local -f infra/compose.yml --env-file infra/.env up -d --build --wait --wait-timeout 240
cd apps/web-v2
$env:KNOWFLOW_ACCEPTANCE_MODEL = 'gpt-6.1-sol'
$env:KNOWFLOW_ACCEPTANCE_PROJECT = 'knowflow-local'
$env:KNOWFLOW_ACCEPTANCE_OUT_DIR = 'test-results/agent-acceptance-20261109-final'
node scripts/run-agent-acceptance.mjs
```

仅验收本地 synthetic 工程行为；真实引用质量、私有盲测、Java/Python 消费签收和 PRICE/POLICY/预算不在本次 P0 签字范围。未完成范围不勾选。
