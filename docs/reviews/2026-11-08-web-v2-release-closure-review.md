# Web v2 接收复核、堆归因与发布收口

## 2026-11-08 14:36 后续 P1/P2 修正

独立审阅 `2026-11-08-web-v2-independent-code-review.md` 指出的两处问题成立；上一轮删除集合与末页选择兜底没有完整处理非一致性 OFFSET 分页。本次按用户要求修正，不更改独立审阅原文或代签 APPROVED。

- P1：取消末页仅凭列表缺席改选首库的逻辑；WorkspaceProvider 中的文档作用域优先取详情路由 baseId，其他页面仍使用共享选择。文档读取、上传、更新、删除、重建和轮询共用该路由绑定作用域，不新增一套重复的文档 hook。
- P2：删除成功后，取消/失效旧分页并从 OFFSET 0 重读；移除已不足以保证完整性的短期删除集合。删除结果与重新读取失败分别反馈，保留账户与代次保护。
- 回归替换为可变服务端数组：第一页后插入新 B 并打开合法深链、旧问答迟到改变共享选择、51 项删除后在当前数组执行 OFFSET 50、旧分页快照迟到。覆盖列表/路由/标题/文档及实际上传 POST 的作用域，删除后确认全部 50 个剩余项和末项可见。旧构建的反例失败记录和 Trace 保留。

本次验证：typecheck、lint、28 单元、生产 build、9 路由原 +5% 包体门禁通过；完整 mock 浏览器回归 **44 passed（58.2s）**，含四项专项回归。`npm run e2e` 再次实际执行，在启动阶段因 Docker Linux daemon pipe 不存在 exit 1；本次全栈/SSE/旧版回退仍未通过。临时 3300 服务已关闭，端口实测空闲；未提交/推送/PR/合并/部署。

新构建 ID `CuSLIGgoxf1OWtyLk3pfX`；88 文件应用清单 SHA-256 `32695434cf803b867e936e0661294d214710f81bc052bdd3ddfe2357e0b36c95`。79 文件代码/测试/交付范围清单 SHA-256 `a7526bc0d2b8cf7b219364747e6f2fa041b8b51b6b0b2e1d47c70bf75a05a3d3`；tracked patch SHA-256 `b43e0b1d109a687bbc75dd8cf706049ce4a58e6ee289d540b671ba005c66029e`。证据位于已忽略的 `apps/web-v2/performance-results/kb-scope-offset-20261108/`（before.log、before-traces/、checks.json、各检查日志与 source-state.json）。新增构建未重跑长时间堆采样，不把旧堆证据写成新构建结果。

下文原 41 mock、旧哈希、旧包体数字和堆实测属于 **12:49 历史检查点**，不覆盖本次 P1/P2 修正；恢复 Docker 后须在新构建上重新验证隔离全栈/SSE/回退。

日期：2026-11-08。执行范围：接收 `.context/ai-handoff.md` 后，对当前未提交六阶段优化重新复核，补充堆快照证据并修复一处确定性分页竞争。本文是本机工程复核，不是人工签收或发布批准。

## 结论

当前首页/工作流合成往返场景的主要堆增长有了具体证据：V8 编译代码/反馈元数据增长明显，浏览器性能缓冲、DevTools 网络记录和自动化注入脚本也参与保留。没有发现该场景中业务对象逐轮累积的证据；仍有后段增长，不能宣布零泄漏、完全稳定或 GPU 内存已释放。

独立于原实施过程，本会话复核发现一处 P1 正确性回归：知识库第一页可操作后，删除其条目，而迟到的第二页会重新发布包含已删除项的累积列表。已先用浏览器回归复现失败，再做局部修复。

发布验证仍被环境阻断：Docker Linux daemon 不可达，实际全栈命令启动失败。本轮不能继承此前 41 项隔离全栈、SSE 捕获及旧版回退的通过结论。人工、生产 RUM、版本化与远程新 SHA CI 仍有各自门禁。

## 工作树与证据绑定

- 根目录 `D:/konwflow`，分支 `local`，HEAD `e216fe3f4ce3f24973b7654bb723db667a3b74ae`，机器 `wenling`。接收时 branch/HEAD/机器/改动文件归属与交接一致；根、apps、web-v2 及其祖先未发现 CLAUDE.md/AGENTS.md。
- 接收按 `ready → accepted → in_progress` 执行，Docker 阻断后改为 `blocked`。没有重置、清理、stash、切分支、提交、推送、创建 PR、合并或部署。
- 本轮新增：`e2e/base-pagination-mutations.spec.ts`、`scripts/performance/retention.mjs`、`scripts/performance/heap-summary.mjs`、`tests/heap-summary.test.mjs`（均相对 `apps/web-v2`）；另新增本报告。局部更新 knowledge-base hook、package scripts、性能说明、实施记录与交接。
- `.codebuddy/`、`eval-out/` 保持原归属，不读取私有评测/凭据或 `data/raw/`，不打包进建议提交。
- 最终生产构建 ID：`8VNj8mM7O53LxWKdePB0B`；三组运行均使用该构建，应用清单 SHA-256 一致：`33ef8ffc96b330ed01fd04109a5bbb8b86d4c4dd3c809e9df0dc3349295d83c7`。该清单为 88 个 src/配置/锁文件的路径及内容哈希，不等于完整制品/SBOM 哈希。
- 当前代码/测试/交付范围（`apps/web-v2`、根 Web CI 和 E2E 脚本）有 79 个修改或新增文件，逐文件当前内容清单 SHA-256：`1bf109a6e60729f238e7e197c97342d2e564158a6cd8da1eab5710f5d056f0a9`；原始 tracked patch SHA-256：`46ef68b6578770de7c6b2b1cbaa597a0fe6ca72de744e7e7ba8b6efe64e47505`。清单与补丁在已忽略的 `apps/web-v2/performance-results/release-review/`，不包含 docs/交接或用户产物；报告后续编辑不改变该代码绑定。

## Diff 复核与修复

复核以实际 `git diff` 和新增源码/测试为依据，覆盖领域 Context/草稿订阅、鉴权与账户重置、渐进列表、文档请求作用域/分页/轮询、SSE parser 与流取消、PDF/Unicode 原文、受限正文、异步确认/菜单、WebGL 调度/释放、字体、指标、standalone、CI/预算和测试。额外只读审查子进程因连接/路由发现超时未形成报告，不计作第二审阅者通过；本文结论由接收会话直接核对。

### P1：渐进加载期间删除项复活（已修复，集成验证待 Docker）

触发顺序：第一页响应并显示 → 第二页挂起 → 删除第一页知识库且收到 204 → 第二页返回 → `load()` 把早先累积的第一页重新发布。

- 修复前回归真实失败：`base-pagination-before.log`，最终断言应为 0 个删除按钮，实际为 1。失败 Trace/上下文另存 `performance-results/base-pagination-before/`，保留失败证据。
- `src/hooks/use-knowledge-bases.ts` 为当前分页读取保存短期删除集合；成功删除加入集合，后续发布过滤已删除 ID。集合只属于本次列表读取，完成即清空，不引入长期跨账户缓存。
- 完整列表取完后重新校验当前选择是否仍存在，恢复原完整加载时的选择兜底；不在第一页尚未包含选中项时提前替换后续页的合法选择。
- 精确回归只使用可见 UI 与受控迟到响应，验证删除前后及第二页发布后状态。没有通过禁用删除按钮或等待全列表完成来规避竞争。

本轮没有确认其他必须立即修改的高置信度回归；这不等于所有 R01–R29 探索项或生产条件均已验收。普通 API JSON 仍主要依赖类型断言；浏览器/原生 PDF、长期真实任务、异常服务端响应与生产监控须继续独立验证。

## 堆采样条件

- Windows `10.0.26200`，Intel i7-13700H，Node `v24.22.1`，Chromium `156.0.8078.4`，生产构建与固定合成 API（一位用户、一个知识库、空资料/历史）。不使用真实账号或生产服务。
- 独立 `127.0.0.1:3300`，1440×1000，CPU rate 1，无网络节流。每组新 context，组内同页 SPA。Playwright 请求拦截会禁用 HTTP 缓存；这些数据不能代表冷热 HTTP 缓存对照。
- 保留原等待口径：每次首页等待 canvas 可见，离开等待 canvas 移除；预热 2 次，再运行 180 次，每 20 次显式 GC。没有把 DOM 不增长作为内存结论。
- 三组顺序运行，不与构建或浏览器回归并发：snapshots 组启用 CDP Performance，保存 0/60/180 快照；metrics 组不拍快照；minimal 组关闭该 Performance 域，改读 Runtime heap。三组均仍有 Playwright/CDP 和 HeapProfiler，不能称无探针用户环境。
- 没有 React DevTools hook、无限保存的自定义指标数组或 console 对象引用。三组 pageerror 均为空。最初探索组保留，但以下只使用最终修复后的三组，不能混算前后收益。

### GC 后 JS 堆（bytes）

| 往返 | snapshots | metrics（无快照） | minimal（关闭 CDP Performance） |
|---:|---:|---:|---:|
| 0 | 7175348 | 7139776 | 7149944 |
| 20 | 8478668 | 8433440 | 8403140 |
| 60 | 9006836 | 8961848 | 8952324 |
| 120 | 9384652 | 9299872 | 9303360 |
| 160 | 9513600 | 9432440 | 9432192 |
| 180 | 9602168 | 9512120 | 9523600 |

三组走势相近，不能把主要增长归咎于拍快照或 CDP Performance 域本身。snapshots 组 0→180 增加 2426820 bytes，60→180 增加 595332 bytes，最后 20 次仍增加 88568 bytes；增长趋缓但未完全稳定。该组采样 DOM 始终 406，监听器 375–377，终点 376；另两组存在短暂卸载计数下降，没有单调积累。计数只描述采样时刻。

### 对象、dominator 与保留链

分析器根据快照 metadata 解码 node/edge，排除 weak edge，使用 Lengauer–Tarjan 求 immediate dominator，再累计强图 self-size。测试包含环/菱形/弱边，以及 60 个固定种子图与“删除节点后可达性”的独立 oracle。该算法未实现 Chrome ephemeron/native 归属语义；下表和 retained size 是诊断口径，不能直接与 JSHeapUsedSize 相加、相减或冒充 DevTools 精确 retained size。

| 对象/类别 | 0 次 | 60 次 | 180 次 |
|---|---:|---:|---:|
| 快照全部节点 | 171970 | 183342 | 186791 |
| code 类 self bytes | 3923980 | 5526504 | 6067436 |
| object 类数量 / self bytes | 13391 / 369384 | 13811 / 378316 | 13811 / 378316 |
| closure 数量 / self bytes | 9416 / 274692 | 9416 / 274692 | 9416 / 274692 |
| React fiber 结构计数（tag/return/child/alternate） | 541 | 541 | 541 |
| HTMLCanvasElement JS 包装对象 | 2 | 2 | 2 |
| WebGL2RenderingContext JS 包装对象 | 1 | 1 | 1 |
| AbortController native / AbortSignal native | 6 / 6 | 6 / 6 | 6 / 6 |
| IntersectionObserver native / ResizeObserver native | 3 / 1 | 3 / 1 | 3 / 1 |
| Map / Set / Promise JS 对象 | 1471 / 84 / 50 | 1471 / 84 / 50 | 1471 / 84 / 50 |
| native PerformanceResourceTiming | 47 | 107 | 227 |
| detachedness 标记为 2 的节点 | 0 | 0 | 0 |

证据与解释：

1. code 类增加 2143456 self bytes。InstructionStream 从 1287→2471（+1430848 bytes），TrustedByteArray +351580 bytes，ProtectedFixedArray +132640 bytes，Code +85248 bytes，FeedbackVector +76924 bytes。代表性强链为 `Window → TURBOPACK.push 闭包 → 模块 Map → SharedFunctionInfo/BytecodeArray → Code → InstructionStream`，另有 React 共享上下文及自动化工具函数的代码。这支持编译/JIT/反馈元数据是本场景主要增长来源；尚未逐函数精确分摊全部 bytes，也未证明最终上界。
2. 一个同 ID 的模块 Map 在三张快照的强图 retained size 均为 351925 bytes。该具体缓存没有随往返扩张，不能据此泛化所有 Next/React 缓存都已稳定。
3. `InjectedScript → utils.asLocator → context` 的强图 retained size 在 60/180 次为 344652/375860 bytes；起点已存在约 332296 bytes 的注入 Script 支配子树。自动化自身参与编译与保留，不能把整段堆差归给业务。
4. `DevToolsSession → InspectorNetworkAgent → NetworkResourcesData` 保留网络资源记录；Performance 对象的原生缓冲保留 PerformanceResourceTiming 与布局/绘制条目。最短路径部分经过 Playwright UtilityScript 的 builtins.performance；这只是其中一条根路径，不证明 Performance 对象由工具独占。ResourceTiming 47→227 与 180 次新增请求相符。原生观测开销与 JS heap 口径必须分开。
5. object/closure 在 60→180 数量与 self bytes 均不增长，相关业务生命周期对象计数不累积。本场景未确认业务泄漏，因此没有添加机械 memo、清空框架缓存、删除动画或移除功能来压低数字。

边界：这里只覆盖合成首页/工作流；未覆盖长时间上传/重建、真实 RSC 数据、账户大量切换、原文持续开关、数小时会话、原生/GPU 分配。后续应以 500–1000 次和 30–60 分钟运行、稳定等待窗口、3 个独立进程重复、业务 fixture 和设备实际负载继续观察；若后段业务对象增长，再沿具体保留链最小修复。

## 本轮验证与失败记录

| 检查 | 本轮结果 / 边界 |
|---|---|
| typecheck / lint | 最终代码重新通过 |
| 单元测试 | 28 passed；含新增 3 项堆分析器验证 |
| production build | 通过，构建 ID 见上 |
| 包体预算 | 9 路由全部通过原基线 +5%；未抬高门限 |
| 浏览器精确回归 | 41 passed（1.1m），含新增分页竞争用例；修复前失败证据保留。mock 命令显式排除真实全栈与旧版回退两个用例，其验证单列 |
| 堆诊断 | 最终三组各 180 次通过，0/60/180 快照及分析生成，pageerror 为空 |
| 隔离全栈 / SSE / 回退 | `npm run e2e` exit 1：Docker Linux daemon pipe 不存在；未进入容器测试，不能算通过 |
| 额外审查子进程 | 连接/路由发现超时，未产出结论，不计作独立审阅签字 |
| 远程 CI | 未提交/推送，未触发或验证覆盖本轮代码的新 SHA CI |

包体的修复增量为工作区路由较上一实施检查点各 +52 gzip bytes。最终：首页 234571（+3.45%）、对话 253766（+3.55%）、知识库 246615（+3.52%）、详情 250196（+4.31%）、设置 230366（+3.38%）、工作流 230365（+3.39%）、登录/注册 202920（−2.54%）。这是逐路由唯一首载 JS gzip level 9，后续动态资源另计；原探索性 −15%–25% 目标依旧未实现。

可再生证据均相对 `apps/web-v2/performance-results/`：`receive-checks.json`、`receive-final.json`、`receive-*.log`、`final-*.log`、`bundle.json`、`retention/final-{snapshots,metrics,minimal}-180/report.json`、三张 `.heapsnapshot`、对应 `.summary.json` 与 comparison。快照/Trace/缓存不提交、不放入交接；本报告保存必要统计。

## 后续验证矩阵

以下为明确待验证项，本轮没有用 localhost 无节流样本替代它们。

| 环境/场景 | 固定条件与验收证据 | 状态 |
|---|---|---|
| Chromium 4× CPU + 弱网 | 固定同版本构建/fixture；建议 RTT 150ms、下行 1.6Mbps/上行 750Kbps；分别记录表单可交互、LCP、CLS、长任务、首 delta/完成、停止反馈和 Trace | 待执行；这些是计划参数 |
| 冷/热 HTTP 缓存 | 新 profile 首访与同 profile 再访；固定服务与缓存头。改用独立合成 API/真实请求，不通过 Playwright routing 混淆缓存；私有 API 继续 no-store | 待执行 |
| 有效交互 INP | 真实输入/点击/停止/菜单/引用操作；记录 interactionId、事件时序、交互次数和 final INP；每条件重复并保留分布 | 待执行；加载样本无资格证明 INP/P75 |
| Firefox / WebKit | 同一合成及真实隔离栈；登录、分页删除竞争、流取消、菜单焦点、PDF/Range、Unicode、WebGL/回退 | 待执行；不能以 Chromium 结果代替 |
| 真实移动设备 | iOS Safari / Android Chrome，触摸、软键盘、安全区、横竖屏、恢复前台、低动态/无 WebGL | 待负责人设备验收 |
| 200% 文本与无障碍 | 真实文本缩放而非仅缩窄 viewport；Tab/Shift+Tab、方向键、Esc、IME；NVDA/VoiceOver 等真实读屏器 | 待人工执行与留证 |
| 长稳/业务保留量 | 500–1000 往返或 30–60 分钟，3 个进程重复；上传/重建/原文/切账户；JS/native/GPU 分口径 | 待执行；不承诺固定零增长阈值 |
| 真实后端与恢复 | 恢复 Docker 后执行隔离全栈、共享 SSE 捕获校验和旧版回退，保留失败轮与新轮环境 | 当前环境阻断 |
| 生产 RUM | 接收端、留存、采样、权限、告警和仪表盘；真实设备/网络用户分布与足够样本 | 待生产负责人；目前只有本机事件能力 |

## 提交拆分草案与发布顺序

仅为可审阅建议，未执行任何 Git 发布写操作。Context 迁移必须包含所有消费者，不按 hook 与组件机械拆开。涉及共同 package.json 的脚本需按组分块暂存，逐组验证依赖闭合。

| 建议提交 | 范围 | 提交前验证 |
|---|---|---|
| 1. fix(web-v2): harden workspace lifecycle and interactions | 全部互相依赖的 src 迁移、错误/键盘/分页修复、代理/stream 纯逻辑、对应单元和 mock E2E；包含本轮删除竞争 | typecheck/lint/unit/build + mock；真实核心链路全栈恢复后通过 |
| 2. build(web-v2): ship standalone runtime | Dockerfile、next.config、dockerignore 与发行许可证复制 | 相同源码构建镜像、健康检查、隔离全栈与回退；不能复用旧镜像指纹 |
| 3. test(web-v2): add performance budgets and diagnostics | performance/、性能脚本与 heap 测试、package perf scripts、Git ignore、CI/根 E2E 探测、性能说明 | 单元与预算；同构建三组采样；Linux CI 确认 Node/Chromium/Compose 路径 |
| 4. docs: record optimization evidence and release gaps | 原审查、实施记录、本报告、README/DESIGN；交接是否入库另由负责人确认 | 来源/版本/链接检查，敏感信息和大产物检查 |

恢复 Docker 后先重跑 `cd apps/web-v2 && npm run e2e`，解决任何真实失败；再由用户明确授权提交/推送/PR。每次代码调整后重新构建、计算清单/预算，CI 必须绑定最终准确 SHA；旧 run `42456844122` 不覆盖本轮未提交工作。远端状态未核验，不断言旧 PR 或旧 token 仍有效。

## 人工与生产门禁

已重新阅读人工验收、消费签核与 production-gap-closure。M1/M2/M3 签字仍空；Java/Python/Web 完整消费签收、真人引用审核、私有盲测、PRICE/POLICY/硬 cap 或获批预算、真实用户试用仍须对应负责人执行。不能用本轮单元/mock/堆分析替代。

生产需负责人提供 registry/TLS/不可变 tag、网络/egress、日志脱敏/留存、告警通道演练、异地备份/PITR 与恢复、限流/容量、审批流水线及回滚证据；生产 RUM 接收/存储/仪表盘尚未建立。本轮未创建生产配置、未处理密钥、未代签、未批准旧版退役。发行许可/SBOM 和旧版回退窗口也须按项目流程核实。

## 收尾记录

2026-11-08T12:49:36Z 最终本机验证结束：typecheck/lint、28 单元、build、9 路由预算、三组各 180 次采样、堆分析与 41 项 mock 浏览器回归全部 exit 0。新增删除竞争用例通过（1.0s），失败前轮及 Docker 失败日志保留。独立 3300 服务已关闭并实测端口空闲；branch/HEAD 未改变，未执行 Git 发布写操作。

当前握手为 `blocked`，精确阻断为 Docker daemon 不可达，安全下一步是恢复本机 Linux engine 后原样重跑隔离全栈。同机 Codex→Codex，无需传输；后续启动可使用：

```sh
codex -C D:/konwflow "读取 .context/ai-handoff.md，核对工作区后按接收协议继续；恢复 Docker 后优先重跑隔离全栈，不提交、不推送、不部署。"
```
