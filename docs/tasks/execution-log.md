# KF2-002、003、005 执行记录

本记录与 V0.2 原始计划分开维护。执行者为本 Codex 会话；起始集成基线和分支均以 Git SHA 为准。原计划中的 V1.1 设计包未提供，当前没有冻结契约；这不阻止 002、003、005 的准备工作。

## 任务状态

| 任务 | 计划负责人 | 实际执行者 / 交接 | 状态 | Base SHA | Target SHA |
|---|---|---|---|---|---|
| KF2-002 | M | Codex 本会话承接 M 的场景/试用文档所有权 | SUPERSEDED | 5a3d84413f69437b23f2a38fcae032a4ddf8d326 | bab4d97348b84ef025c6539fb7fd020bb9a660b0 |
| KF2-003 | B | Codex 本会话，负责模型/隐私/运行基线 | SUPERSEDED | 5a3d84413f69437b23f2a38fcae032a4ddf8d326 | bab4d97348b84ef025c6539fb7fd020bb9a660b0 |
| KF2-005 | M | Codex 本会话承接 M 的仓库组织/协作文档所有权 | SUPERSEDED | 5a3d84413f69437b23f2a38fcae032a4ddf8d326 | 6e260de9e99b2e7a089edaad10cd451a6e9eb938 |

全部在 python 分支。三条早期文档任务的开放审阅已由后续收尾交付替代，状态仅为 **SUPERSEDED**，**不是 DONE**；原 Q 结论栏仍为空，不伪造 Q APPROVED。

**终态说明（2026-11-04）**：后续 P0 工程收尾、Sol 对 `cd68d7f` 的工程 APPROVED（[2026-11-03-sol-cd68d7f.md](../reviews/2026-11-03-sol-cd68d7f.md)）以及 `grok` 上真实公开集评测/文档体系（[2026-11-04-rag-real-public-seed-v2.md](../evaluation/2026-11-04-rag-real-public-seed-v2.md)），已覆盖并取代这三条早期文档任务的开放审阅。原审阅包 [KF2-002-003-005-review.md](../reviews/KF2-002-003-005-review.md) 的“Q 独立结论”仍未由 Q 填写，故走替代关闭而非 DONE；不据此宣称整体产品验收通过。

## KF2-002 — 项目规范与接口查询

交付：[场景说明](../product/scenario.md)和[试用协议](../product/pilot-protocol.md)。两道原创合成题分别练习接口参数查询及批准版本冲突判断。四行试填均明确标成 SYN-01 合成示例，不是用户观察。协议包含招募条件、匿名记录、对照顺序、计时规则、成功评分、指标、访谈及两周复用字段。没有招募或联系外部参与者。

验收检查：题目评分键可由协议中的合成来源复现；模板覆盖实际答案及文件、版本、章节和页码/行号定位。四条 SYN-01 合成试填附答案原文、来源摘录和可复核评分，均不作为真实用户结果。

## KF2-003 — 模型、隐私、依赖与资源

- 两个环境凭证 readiness 为 ready，既有 GET /v1/models 鉴权 HTTP 200；本分支再次执行双模型真实调用，证据见 [新冒烟结果](../../evaluation/smoke/evidence/model-live-20261030-python.json)。硅基流动两条有效 1024 维向量通过，DeepSeek 中文合成事实检查通过。
- 供应商政策、数据流及披露见[供应商记录](../../evaluation/smoke/provider-profile.md)和[运行基线](../../docs/architecture/runtime-profile.md)。按当前 DeepSeek 官方价目估算 USD 0.0000396；实际账单未知。硅基流动当前公开政策已列明 API 加速推理输入/输出短期处理、不长期存储及不用于训练/商业用途，并单独说明安全审查；具体账户适用性和安全审查记录保留期限仍待核。
- Q 指出响应模型 ID 不符仍报成功；runner 现要求 Embedding/Chat 返回模型 ID 必须匹配请求且不可缺失，离线测试覆盖错误和缺失 ID。当前 16 项离线回归通过；既有真实冒烟证据绑定修复前 runner，本次未重跑供应商 API。
- PyMuPDF 与 pypdf 许可证证据沿用 wheel SHA 审计，没有安装解析器或声称解析质量通过；生产硬件与文件资源上限继续标为待验证。
- 仅提交运行环境中的变量名和合成请求；提交文件不含凭证值。

## KF2-005 — 仓库组织与协作基础

建立 Java、Python、Web、基础设施、共享契约的所有权/启动占位说明；三端有不含密钥的本地配置示例；建立任务卡和 PR/Q 审阅模板；添加根 .gitignore、更新仓库说明。没有伪造可运行服务、冻结契约或 Compose/CI。后续服务依赖其列明的 KF2-004、006、007、008、009。

## 审阅和验证

- 分支：python；Base：5a3d84413f69437b23f2a38fcae032a4ddf8d326。
- KF2-002 Target：bab4d97348b84ef025c6539fb7fd020bb9a660b0（含 Q 修复）。
- KF2-003 Target：bab4d97348b84ef025c6539fb7fd020bb9a660b0（含 Q 修复）。
- KF2-005 Target：6e260de9e99b2e7a089edaad10cd451a6e9eb938；任务审阅包见 [KF2-002/003/005 Q 审阅包](../reviews/KF2-002-003-005-review.md)。
- 运行记录：16 项模型客户端离线回归通过；本分支既有真实双模型冒烟通过（其证据绑定原 runner）；许可证 wheel 哈希沿用既有核验；ignore、runner/fixture 哈希、敏感值扫描和 git diff --check 均通过。
- 未执行：真实用户招募/试用；产品服务、解析器、生产硬件、部署、迁移、E2E、实际账单读取；独立 Q 审阅和与 main 集成。

## M 主线 Web/基础设施推进（2026-11-01）

| 字段 | 记录 |
|---|---|
| 相关计划范围 | KF2-008、KF2-009、KF2-020、KF2-025、KF2-032、KF2-034 的 Web/Compose/CI 候选实现 |
| 计划负责人 / 实际执行者 | M / 当前 Codex 会话承接 M 范围；不代表真实 Muse Agent 已执行 |
| 状态 | IN_REVIEW；未替 Q 或项目负责人签署验收 |
| 分支 / Base SHA | `local` / `013fcf5a2de72b09599037fb997765443f5d61ee` |
| Target SHA | 未提交；代码仍在共享工作区 |
| 边界 | 保留工作区原有未提交改动；未切分支、提交、推送或合并 |

> 后续说明（2026-11-04）：该 M 主线 Web/基础设施工作后续已合入 `local`/`grok` 工程线并由 CI 验证；本日志不追溯改写旧 Target，仅标记该历史 IN_REVIEW 已被替代。

交付包括 Next.js 文档核验工作台、同源 Java API 代理、Docker Compose 全栈环境、合成模型浏览器 E2E 和 Web CI 工作流。工作台覆盖注册/登录、知识库、上传与索引状态、更新/重建/删除、流式问答、来源原文、历史、取消，以及文本/PDF 页码预览。代理将 Bearer 凭证留在 HttpOnly Cookie 与服务端；写操作校验浏览器来源，并限制请求大小和上游等待时间。Compose 使用独立项目卷、内外分离网络和显式合成 AI 适配器；E2E 使用随机本地凭证与独立 Compose 项目，结束后清理该项目的容器、网络和数据卷。

### 验证

- `cd apps/web && npm run typecheck`：通过。
- `cd apps/web && npm run lint`：通过。
- `cd apps/web && npm test`：2 个套件、7 项通过。
- `node scripts/e2e-web.mjs`：全栈容器构建/健康检查通过；Playwright 1 项通过，覆盖注册、索引、流式回答、原文引用、跨用户来源/文件 404、删除后失效和 PDF 页码预览；运行后测试容器、网络和卷已清理。
- `docker compose -f infra/compose.yml --env-file infra/.env.example config --quiet`：通过。
- `uv run --project services/ai --frozen pytest services/ai/tests/test_browser_e2e_server.py -q`：1 项通过。
- `.github/workflows/web-e2e.yml` 已加入，但本地未执行 GitHub 远程 CI。

联调中修正了 Web 入口网络、代理后的同源校验、合成运行时 profile、严格问答请求字段、SSE 事件解析和小写 PDF 格式判断。合成 E2E 只证明当前 Java/API/AI/Web 接线与授权/来源路径可运行，不代表真实模型质量、延迟或费用结果。

### 尚未关闭

- 独立 Q 对精确代码提交的审阅仍未由 Q 填写；相关 KF2 文档任务已标记 **SUPERSEDED**（非 DONE），不将相关任务表述为已完成整体验收。
- 真实 provider 评测、质量/隐私/费用核验、真实用户试用和生产部署仍需按各自依赖推进；本轮没有调用真实模型或外部参与者。
- 独立前端契约 Mock 是否仍属 KF2-008 的必需验收，应在 Q 复核时确认；当前 E2E 使用真实本地 API 与合成 AI 适配器。
