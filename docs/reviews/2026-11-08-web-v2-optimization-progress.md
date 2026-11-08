# Web v2 六阶段优化实施记录

最新检查点（2026-11-08T14:36:59Z）：按独立审阅修正 P1 深链详情文档/上传作用域错配及 P2 删除引起的 OFFSET 漏项。详情文档绑定路由 baseId，不再按分页缺席覆盖显式选择；删除成功取消旧分页并从第一页重读。可变数组四项专项回归及完整 mock **44 passed**，28 单元、typecheck/lint/build、原 9 路由包体预算通过。新构建 `CuSLIGgoxf1OWtyLk3pfX` 的代码绑定见收口报告顶部；下文 41 mock 与旧堆数据为较早检查点。本次全栈命令仍因 Docker Linux daemon 不可达而启动失败，未提交/推送/部署。

依据：2026-11-08-web-v2-frontend-audit-and-performance-plan.md。

后续接收复核见 [堆归因与发布收口报告](./2026-11-08-web-v2-release-closure-review.md)（2026-11-08T12:49:36Z 检查点）：补齐 0/60/180 heap snapshots 与两组观测对照，修复渐进分页期间删除项复活；最新 28 单元/41 mock 与静态检查、构建、预算通过。工作区首载较下述旧检查点各增 52 gzip bytes，仍在原 +5% 内。Docker daemon 当前不可达，本轮未重新通过隔离全栈/SSE/回退；下文原 41 全栈等结果为此前检查点，不覆盖这次新修复。

范围：按用户授权落实全部六阶段；保留接口 0.2.0、账户隔离、流式文本/Markdown、现有视觉与 WebGL 效果。已有未跟踪 .codebuddy/、eval-out/ 和审查报告不作清理。

## 执行计划

| 阶段 | 状态 | 工作与验收 |
|---|---|---|
| 1 正确性与可访问性 | 已完成 | 错误、上传接受语义、键盘上传/菜单、分页/搜索；精确浏览器回归 |
| 2 渲染性能 | 已完成 | 草稿直接订阅、领域 Context、稳定 action 与实体引用；输入不更新外壳/资料/历史 |
| 3 加载性能 | 已完成 | 鉴权门禁与局部加载分离、首批知识库、Three 调度与 Markdown 预取；慢历史不阻塞无关页面 |
| 4 运行时性能 | 已完成 | 限并发轮询、取消/可见性、合并终态刷新、PDF 单一路径；切换清理与分页保留 |
| 5 资源与交付 | 已完成 | 字体、长列表、上传内存、standalone；生产包体/trace/heap/RSS 与镜像评估 |
| 6 持续门禁 | 已完成 | CWV 与关键链路指标、包体预算、缺陷回归、CI；可重复对比与文档 |

## 阶段证据

- 阶段 1：新增 optimization.spec.ts 共 7 项通过（3.6s）；已有 workspace-regressions 7 项通过。覆盖具体错误、键盘文件选择、上传接受/失败索引、菜单键盘、侧栏分页、搜索旧记录和状态文字对比。首轮有一项因 Next 路由播报器也使用 role=alert 而发生定位器歧义，收窄到目标错误后通过。
- 阶段 1 检查点：typecheck、lint、生产 build 通过。
- 阶段 2–4：performance-regressions 6 项与既有 workspace-regressions 7 项全部通过（22.8s）。覆盖输入 10 字符无外壳/历史/资料更新、慢历史不阻塞设置、首批知识库呈现、任务终态后保留 60 个已加载文档、轮询并发 ≤4/退出停止、PDF 无额外 fetch 探测。
- 专项验证中修复了账户重置与深链答案加载的 effect 时序竞争；React 探针排除了复用 fiber 遗留 flags 的误计数。旧账户回归更新为验证局部加载和无泄漏，不再要求等待远程列表的全页门禁。

## 最终验证（已完成部分）

- `npm run typecheck`、`npm run lint`、`npm test`（25 项）、`npm run build`、`npm run perf:budget` 均通过。
- 当前完整模拟接口回归：40 passed（57.5s），包含 500 个知识库、1000 个文档、持续 delta 渲染隔离、相同轮询结果不触发订阅更新和 URL debounce 竞争。
- 最终隔离 Compose 全栈：41 passed（1.9m）；真实注册、上传、索引、问答、原文、归属隔离通过。SSE 捕获通过共享 Schema 与 lifecycle 校验：text/pdf/refusal 各 4 帧，error/cancelled/timeout 各 2 帧。旧版回退：1 passed（1.0s）。临时项目、卷与网络已由脚本清理；既有 knowflow-local 栈不作部署修改。
- 有一次最终复跑在容器健康后遇到宿主随机端口不可达，未进入用例；这一轮不算通过。E2E 启动探测增加最后一次错误原因，等待上限由 30s 改为 60s；随后使用新隔离项目完整复跑通过。无法据此断言端口失败的唯一根因。
- 原生 Radix 菜单首次异步加载时另行恢复键盘初焦点，覆盖方向键、Enter、Esc 和回焦。菜单模块从首载改为意图预取，详情路由回到原基线 +5% 门禁以内；没有上调预算掩盖增长。
- Impeccable 最终源码扫描仅命中原有原文引用左边线，人工确认是语义 blockquote，不作装饰性误修。已检查 390px 首页与 1440px 登录截图。

## 已测资源与运行时收益

| 指标 | 基线 | 优化后 | 说明 |
|---|---:|---:|---|
| 输入 10 字符引发 AppShell 更新 | 10 次 | 0 次 | 同时验证历史与资料不跟随更新；输入组件自身正常更新 |
| 相同轮询返回引发资料订阅更新 | 原实现仍重建状态对象 | 0 次 | 相同实体引用与部分状态均按 Object.is 保留 |
| 应用额外 PDF 探测 GET | 1 次 | 0 次 | 原生查看器必要的 Range 请求允许 |
| 上传缓冲 ArrayBuffer 采样峰值增量 | 16777216 bytes | 8388572 bytes | 8 MiB fixture，3 个独立进程中位数，带显式 GC |
| 文本摘录采样堆峰值增量 | 28086744 bytes | 3479328 bytes | 750000 码点 fixture，3 个独立进程中位数 |
| 同源代码交付镜像大小 | 1209858225 bytes | 306920039 bytes | 约下降 74.63%；相同 Node 基础镜像，仅交付方式不同 |
| 实际 next-server RSS | 113627136 bytes | 112840704 bytes | 20 次登录 GET 预热，3 次采样中位数，基本持平，不宣称显著下降 |

上传实验的 RSS 为 17563648 → 17498112 bytes 增量，基本持平；不能把 ArrayBuffer 减半包装成进程 RSS 减半。镜像实验记录源代码 fingerprint，脚本结束清理独立测试容器，benchmark 镜像保留以复查。

## 包体门禁与权衡

口径为每路由唯一首载 JS 的 gzip level 9 总和，不包含后续动态块或完整浏览器传输。

| 路由 | 审查前 bytes | 当前 bytes | 变化 |
|---|---:|---:|---:|
| / | 226759 | 234519 | +3.42% |
| /conversations | 245077 | 253714 | +3.52% |
| /knowledge-bases | 238233 | 246563 | +3.50% |
| /knowledge-bases/[baseId] | 239868 | 250144 | +4.28% |
| /settings | 222829 | 230314 | +3.36% |
| /workflow | 222810 | 230313 | +3.37% |
| /login、/register | 208211 | 202920 | −2.54% |

工作区因错误处理、请求调度、可访问性与观测能力增加而略增；公共首载 JS 并未全面下降，原方案探索性的 −15–25% 包体目标没有达成。已将 Redux 从公共根布局移到工作区，登录页减少负担；保留主要导航预取，关闭动态列表的投机详情预取。门禁基线保留原审查值，所有 9 个目标路由通过 +5% 预算。

## 性能采样与保留量复验

最终浏览器采样使用 Chromium 156.0.8078.4、生产构建、模拟 API、1440×1000、新上下文冷缓存、无 CPU/网络节流，每路由 3 次；这是本机验收，不是线上 P75。LCP 样本中位数：首页 152ms、对话 188ms、设置 168ms、登录 84ms；样本最大 CLS 约 0.003。没有足够真实交互数据证明线上 INP 达标，也没有用不同 fixture 的旧值计算加载时延收益。

同一页面会话 2 次预热后，进行 60 次首页/工作流 SPA 往返，每次等待 WebGL 挂载和卸载。GC 后分批采样：

| 往返次数 | JSHeapUsedSize bytes | documents | DOM nodes | JS event listeners |
|---|---:|---:|---:|---:|
| 0 | 7139172 | 1 | 406 | 375 |
| 20 | 8365964 | 1 | 406 | 376 |
| 40 | 8645480 | 1 | 406 | 375 |
| 60 | 8890984 | 1 | 406 | 376 |

DOM 数量没有增长，监听器在 375–376 间波动，没有逐轮累积；堆内存前 20 轮增加约 1.23MB，后续两批各增加约 0.28/0.25MB。**JS 堆并未完全稳定，不能声称“零泄漏”或把差值直接归因为业务泄漏/框架缓存。** 已有请求取消、信号监听器释放和无效订阅更新的确定性回归；长期保留量仍应结合后续 trace/heap snapshot 与线上运行持续观测，GPU 内存不在此采样口径内。

已生成并检查生产 Trace 与桌面/390px 截图；保留原波浪 shader、视差与减少动态效果的静态帧。字体复用原文件、原字重，通过 next/font/local 提前预加载；未为凑包体或内存数字移除动效或削弱契约校验。

## 持续门禁交付

- `.github/workflows/web-e2e.yml` 新增 `npm test` 与 `npm run perf:budget`，并上传逐路由包体比较。已有隔离全栈步骤自动包含新增 E2E；本轮本地实际执行通过，**没有推送或声称远程 GitHub Actions 已运行通过**。
- `performance/budgets.json` 保存审查前基线，+5% 门禁未上调；`scripts/performance/` 提供预算、浏览器 Trace/截图/保留量、算法内存和同源 Docker/RSS 的可重复脚本。
- `PerformanceReporter` 通过 Next 官方 hook 采集 CWV，另记录 API 响应头、问答首 delta/完成、上传接受、索引等待等数值。事件仅含白名单、固定路由模板与数值，不含邮箱、问题、原文、查询参数或私有 ID。
- 默认仅提供 `knowflow-performance` 本机事件；远程采集为构建时显式配置的同源端点。本轮未新建生产接收服务、数据存储或仪表盘，不能声称已有线上 RUM 数据。
- 资源报告口径与复测命令见 `apps/web-v2/performance/README.md`；应用 README 修正验收文档链接，DESIGN.md 同步实际文字对比令牌与字体加载方式。
- 新增文件均为源代码、测试、预算和说明；原有 `.codebuddy/`、`eval-out/` 及审查报告不作清理，未创建提交或部署到既有运行栈。

## 可复查证据

- `apps/web-v2/performance-results/bundle.json`：最终 9 路由包体结果。
- `apps/web-v2/performance-results/browser.json`、`home-trace.json`、`retention.json`、`*-1440.png`、`home-390.png`：最终浏览器原始样本。
- `apps/web-v2/performance-results/memory.json`、`containers.json`：内存和受控交付对比；镜像对比源代码指纹 `4993a98ea02ecd0db82b60f725db7db28517879d304f9f06537867ade3874ea9`。
- 本机日志 `C:/Users/31180/AppData/Local/Temp/web-v2-implementation.nuoXAL/`：`verified-e2e.log`（40 项）、`fullstack-recovery.log`（41 项 + Schema + 回退）、`sample-retention.log`、`design-final.json`；失败轮保留相邻日志，不混为通过。
- `performance-results/` 为已忽略的可再生产物；本实施记录保留关键数值，CI 包体产物用于后续逐次追踪。

## 验证策略

- 每阶段运行相关测试与静态检查；最终生产构建后重跑完整模拟接口 E2E。
- 为本轮缺陷、订阅范围、慢接口、取消/并发和 PDF GET 添加可重复回归。
- 性能样本标明生产/模拟接口、浏览器、视口、节流、压缩口径；不把本机单次样本当作线上 P75。
- 检查 Docker 与全栈依赖；能够运行则执行隔离全栈，遇阻记录真实原因。
- 最终记录变更、证据、实测收益和未验证边界；不以关闭功能或削弱校验满足预算。
