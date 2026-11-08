# Web v2 前端审查与性能优化方案

审查范围：`apps/web-v2`，并核对根目录 CI、接口契约与后端问答超时配置。审查日期：2026-11-08。

## 结论与证据边界

实现一致性结论：产品结构与黑白编辑风格一致，分层基本清楚；存在影响键盘操作、失败反馈、分页和持续运行成本的问题，建议修复 P1 后再评估发布。没有发现需要整体重写或更换技术栈的证据。

本轮仅新增本报告，没有修改业务代码、CSS、依赖或测试。检查使用已有依赖；启动独立 `127.0.0.1:3300` 生产实例，未操作原有 3000 端口。运行时探针均使用模拟 API，不能证明真实后端、模型、CDN或生产网络的性能。以下标记：**实测**＝浏览器或命令复现；**静态**＝源码可确定的行为；**风险**＝存在触发条件，尚未完成独立复现。优化收益与预算均为待验证目标。

### 检查结果

| 检查 | 本轮结果 | 范围限制 |
|---|---|---|
| `npm run lint` | 通过，退出码 0 | 不代表异步生命周期、无障碍或业务正确性全部通过 |
| `npm run typecheck` | 通过，退出码 0 | TypeScript 不校验服务端实际 JSON |
| `npm run build` | 通过，退出码 0 | Next.js 16.4.3，生产构建 |
| 现有模拟接口 E2E | 22 passed，22.4s | 8 个 spec；未运行真实全栈 knowledge-desk 与 rollback |
| 生产依赖审计 | 官方 npm registry 返回 0 已知漏洞 | `npm audit --omit=dev --registry=https://registry.npmjs.org --json`；不是安全认证，也不覆盖 devDependencies |
| Web Interface Guidelines | 已抓取本轮规则并逐项核对相关实现 | 不能代替真实读屏器和设备验收 |
| Impeccable 源码检测器 | 1 条命中，人工核对后排除 | 原文引用的左边线是有语义的 blockquote 样式，不是需要删除的装饰卡片 |

默认 npmmirror 的 audit 接口返回 404/NOT_IMPLEMENTED，已使用命令级 registry 参数重试官方源，未修改 npm 配置。

采用 Impeccable 技术审查标尺的编辑性评分如下；这不是自动性能分数或 WCAG 认证。

| 维度 | 分数 / 4 | 主要依据 |
|---|---:|---|
| 可访问性 | 2 | 有 skip link、Radix 弹层、焦点环，但上传入口键盘不可达、部分文字对比不足 |
| 性能 | 2 | 有动态加载、50ms 流式缓冲，但全局更新范围和数据门禁较大 |
| 主题与规范 | 3 | 有 DESIGN.md 和令牌；仍有色值、字重、尺寸漂移；产品明确为浅色，未将缺少暗色主题计为缺陷 |
| 响应式 | 3 | 390/768/1440 回归通过；仍需验证文字放大、真实触屏与安全区 |
| 实现一致性 | 2 | 产品风格连贯，但失败反馈、分页和后台任务处理存在多处不一致 |
| 合计 | 12 / 20 | 需要集中补齐实现细节，无整体重写依据 |

## 逐文件问题清单

严重级别：P0＝阻断性问题；P1＝发布前优先修复；P2＝下一轮修复或优化；P3＝低优先级完善。共 **29 项：P0 0、P1 7、P2 19、P3 3**。这是本轮确认与识别的问题数量，不声称穷尽全部缺陷。

### src/components/workspace/workspace-provider.tsx

- `src/components/workspace/workspace-provider.tsx:18` — **R01 / P1 / 性能 / 实测**：Provider 订阅输入草稿，再将会话、知识库、文档、历史、流式答案和草稿放进单个 Context。输入 10 个字符产生 10 次提交，AppShell 在每次提交中都被标记为执行了渲染。流式刷新与轮询也会扩大消费者更新范围。**改进**：草稿由输入组件直接通过现有 Redux selector 订阅；按会话、实体、历史、答案拆订阅和稳定 actions。仅给整个 value 加 useMemo 无法解决字段持续变化的问题。验收：输入不再使外壳、资料列表与历史列表跟随刷新。
- `src/components/workspace/workspace-provider.tsx:107` — **R02 / P1 / 加载与结构 / 静态**：所有工作区页面都等知识库与历史 ready 后才显示，即使设置、工作流不依赖完整历史；知识库 hook 又串行取完全部分页才 ready。首屏形成 `/me → 知识库全部分页 + 历史 → 页面`，文档还依赖选中知识库。**改进**：保留会话鉴权门禁；只取必要首页数据，其余区域使用现有骨架局部加载，完整列表后台渐进补齐。不得为了提前显示而展示前一账户数据。

### src/hooks/use-documents.ts

- `src/hooks/use-documents.ts:185` — **R03 / P1 / 正确性与交互 / 实测**：upload 等待 poll 后才释放 working；poll 在任务 FAILED、CANCELLED 或请求失败时不会把失败结果传回 upload，upload 仍可能返回 ok。模拟索引 FAILED 时，页面同时出现 `INDEX_FAILED`、失败文档行，以及“已上传，正在建立索引”成功提示。**改进**：明确“文件已接受”与“索引完成”两阶段；上传接受后结束上传 busy，索引交给行级后台任务。若继续等待终态，poll 必须返回判别结果，禁止终态失败后报成功。保留用户可继续操作和明确失败原因。
- `src/hooks/use-documents.ts:101` — **R04 / P1 / 生命周期 / 静态风险**：effect 没有卸载 cleanup；poll 仅比较 generation/baseRef，组件卸载本身不改变这两个值，未结束的任务可能继续轮询；timer、请求也不能立即取消。**改进**：每个作用域统一 AbortController；卸载、账户切换、知识库切换、任务结束时取消 fetch 和等待定时器，并使旧 generation 失效。代次校验仍需保留，abort 不能替代过期结果隔离。验收：卸载后无新轮询请求、在途请求取消、无旧结果提交。
- `src/hooks/use-documents.ts:79` — **R08 / P2 / 网络与运行时 / 静态**：每个活跃任务每轮并发查 document 和 task，没有总并发限制或页面隐藏暂停；N 个任务约产生 2N 个请求/轮。4s 退避上限下，50 个任务理论约 25 次请求/秒，未计网络耗时、终态刷新和失败重试；这不是线上实测 QPS。**改进**：统一调度器、限制总并发、抖动退避、隐藏页暂停；终态列表刷新合并一次。未经证明不能删掉文档请求，它可能承载当前行的状态变化。
- `src/hooks/use-documents.ts:55` — **R09 / P2 / 分页正确性 / 静态**：refresh 总是只取第一页并整体替换 documents；任务完成与问答结束都会触发它。已加载的第二页会消失，offset 重置。**改进**：实体 upsert 与分页游标分离；保留已加载页，按 mutation 定位更新或重新验证已加载范围。分页追加去重改用 Set，避免 previous.some 的 O(n×m) 扫描。删除后同时验证分页边界。

### src/components/chat/chat-view.tsx、answer-panel.tsx

- `src/components/chat/chat-view.tsx:168` — **R05 / P1 / 错误反馈 / 实测**：页面仅展示 documents.notice；stream.notice 未显示，AnswerPanel 也未显示 failure_code。模拟问答 503 时，只看见通用“处理失败”，接口返回的“模型服务暂不可用，请稍后重试。”没有出现。删除失败同样可能缺少可见解释。**改进**：提供答案级错误区域，使用 role=alert/status，展示安全的原因和下一步；取消单独处理；显式重试才能再次提交，保持幂等键及不自动重发语义。
- `src/components/chat/answer-panel.tsx:14` — Markdown 已动态加载，流式期保持纯文本，属于应保留的正确实现。可在首次提问成功建立连接后预取排版模块，减少结束瞬间“正在排版…”间隙；不得改成每个 delta 全量解析 Markdown。此项作为 R17 的优化步骤，不重复计数。

### src/components/knowledge/upload-zone.tsx、knowledge.module.css、chat.module.css

- `src/components/knowledge/knowledge.module.css:288`、`src/components/chat/chat.module.css:808` — **R06 / P1 / 键盘可访问性 / 实测**：文件 input 设置 display:none，外层 label 不可聚焦。探针确认 label.tabIndex=-1，input 无可见布局框；鼠标能点“选择文件”，键盘无法从正常 Tab 顺序进入。**改进**：使用真实 button 打开隐藏文件 input；或采用可聚焦的原生 file input 与视觉隐藏样式，并为外层提供 focus-within。上传区、空态和对话资料栏三处一起修复。标准：键盘可操作性。
- `src/components/knowledge/upload-zone.tsx:20` — **R21 / P2 / 校验与反馈 / 静态**：拖拽会检查后缀，但不支持的文件被静默忽略；选择器路径和其他上传入口没有共用同一规则，accept 也不能替代校验。**改进**：在上传服务/hook 统一大小、扩展名规则，所有入口共享；显示拒绝原因；后端继续作为最终校验者。PDF 页数等规则若前端无法低成本判断，应明确交给服务端，避免为校验而首屏引入 PDF 解析库。

### src/app/globals.css、src/components/ui/status-badge.module.css

- `src/components/ui/status-badge.module.css:20` — **R07 / P1 / 文字对比 / 静态计算**：12px 状态文字直接使用成功色 #5f8a73、警告色 #b0804a、取消色 #8c8c8c；白底对比分别约 3.91:1、3.48:1、3.36:1，低于普通文字 4.5:1。辅助说明也大量使用 #8c8c8c。**改进**：为文字定义更深的语义 token，小圆点可保留现有状态色；逐场景验证实际背景。设计规范中的“至少 #8C8C8C”不能代替对比度要求。
- `src/app/globals.css:41` — **R23 / P2 / CSS 与规范维护 / 静态**：--radius 重复声明；CSS Modules 中仍散落重复背景、边框、字号和局部控件样式，chat.module.css 达 1182 行。长文件本身不是性能缺陷，但会扩大修改和回归范围。**改进**：去掉重复定义，明确令牌别名；按 history/answer/composer/source 拆局部样式，优先复用已存在的 Button、Dialog、StatusBadge。以视觉快照约束改动，避免借“统一规范”重设计。

### src/hooks/use-knowledge-bases.ts、src/hooks/use-questions.ts

- `src/hooks/use-knowledge-bases.ts:66` — R02 的关键来源：串行拉完全部知识库后才 setBases/setReadyFor；循环中也未逐页检查当前代次。先显示首批，并在继续请求前检查有效性；停止无效账户请求，保留最终列表完整性。
- `src/hooks/use-questions.ts:77` — R09 的同类开销：追加历史用 previous.some 去重；规模增长后改用 Set/Map。不要为只包含几十行的数据机械增加 memo 或索引。

### src/components/shell/app-shell.tsx

- `src/components/shell/app-shell.tsx:55` — **R10 / P2 / 功能与网络 / 实测**：recent 永远 slice(0,5)，但仍提供“加载更多问答”。模拟返回第 51–60 条后，侧栏仍只显示原先 5 条；用户付出了请求和渲染成本却看不到新增内容。**改进**：若保留“加载更多”则扩大当前可见数量；若产品意图仅预览 5 条，则改为去完整历史的真实链接。两者需要以既有产品约定选择，不能只去掉请求而保留误导按钮。

### src/components/chat/history-rail.tsx

- `src/components/chat/history-rail.tsx:27`、`:76` — **R11 / P2 / 搜索正确性 / 实测+静态**：只筛选已加载 history；query 非空时又隐藏加载更多，导致旧页数据永远无法被当前搜索发现。**改进**：当前契约无服务端搜索参数时，保留分页入口并明确“在已加载记录中搜索”；渐进补齐后更新结果。若未来增加服务端搜索，应单独变更契约，不把未知参数当成现有能力。保持 ?history= 深链和刷新恢复。

### src/components/chat/source-dialog.tsx

- `src/components/chat/source-dialog.tsx:72` — **R12 / P2 / 文件加载 / 实测**：先 GET 文件识别 content-type，识别为 PDF 后又把同一路径交给 iframe；本轮记录到 2 次文件 GET。第一次 body 未明确消费或取消。不能据此断言任意大小 PDF 都完整下载两遍，但重复请求及潜在额外带宽已确认。**改进**：先利用经校验的文档元数据确定预览分支，PDF 直接 iframe，文本只 fetch 一次；类型不明确时设计可取消的探测。若用 HEAD，须先验证上游支持并显式补齐代理方法；不能假定当前只有 GET/POST/DELETE 的代理已支持 HEAD。保留版本一致性校验、Range、页码与原始文件 MIME 安全要求。
- `src/components/chat/source-dialog.tsx:90` — **R13 / P2 / 内存与处理 / 静态**：为了截取来源，先读取全文，再 Array.from(text) 将全部 Unicode 码点展开为数组。大文本会产生额外数组、字符串与主线程工作。**改进**：按 locator 所声明的单位单次扫描，只保存目标区间；不能直接改用 JS 字符下标 slice，避免破坏非 BMP 字符的码点定位。按账户/版本限制短期预览缓存，退出时清理。引入 Worker 之前先测扫描耗时与复制成本。
- `src/components/chat/source-dialog.tsx:130` — **R15 / P2 / PDF 键盘使用 / 实测属性**：iframe tabIndex=-1，原文弹层只有引用和关闭，没有替代的“打开 PDF”链接。正常 Tab 流程无法进入原生 PDF 控件。**改进**：测试各浏览器原生查看器的焦点行为，允许进入查看器或提供带可访问名称的同源新窗口链接；继续保证 Esc 和关闭后回到引用触发按钮。

### src/components/knowledge/document-list.tsx、src/components/ui/confirm-dialog.tsx

- `src/components/knowledge/document-list.tsx:69` — **R14 / P2 / 菜单与异步状态 / 实测+静态**：自制 role=menu 仅处理鼠标外点关闭，缺少打开后焦点、方向键、Esc、回到触发器。探针在打开后按 Esc，菜单仍存在。ConfirmDialog 的原生 Action 会自动关闭，不能仅靠 busy 属性推断弹层会等异步完成；答案删除还未传入忙碌状态。**改进**：使用已有 Radix 包的 DropdownMenu 完成菜单键盘行为；为异步确认统一明确的关闭策略、防重入、失败反馈和焦点恢复。标准：角色行为与键盘操作一致。

### src/components/login-ribbon.tsx、src/components/home-wave.tsx

- `src/components/login-ribbon.tsx:77`、`:102` — **R16 / P2 / 动效运行成本 / 静态**：登录 ribbon 持续 requestAnimationFrame，每次全局 pointermove 都读取 getBoundingClientRect；没有首页已有的 IntersectionObserver、显式 document.hidden 判断与 contextlost 恢复处理。不能把浏览器自身的后台 rAF 节流误认为应用已实现暂停。**改进**：抽取共同生命周期管理，离屏/隐藏暂停，回到前台保持时间连续；指针事件只收集最新坐标，每帧最多一次读取或在 resize/scroll 后更新矩形。保留原 shader、速度、视差、粒子/线条外观与低动态模式的静态帧。

### src/components/home/home-view.tsx、src/components/auth/auth-view.tsx

- `src/components/home/home-view.tsx:14`、`src/components/auth/auth-view.tsx:12` — **R17 / P2 / 加载顺序与包体 / 实测**：Three.js 已动态分包，但 Wave/Ribbon 在页面显示时立即挂载，动态分包不等于避开首屏竞争。共享 Three chunk 为 542445 bytes，gzip 估算 132018 bytes；首页进入稳定可用状态前实际加载的 JS 共 1277235 decoded bytes，含框架、页面与 Three。**改进**：先保留现有静态图布局，表单/主体可交互后尽早加载 Three，避免其初始化与关键交互竞争；对布局和完整动画启用时间分别设预算。不要通过删除动画、降低可见质量或永久使用图片来宣称功能等价。分析 Motion 与公共依赖的具体模块后再拆分，禁止仅凭包名改 import。

### src/app/layout.tsx

- `src/app/layout.tsx:2` — **R18 / P2 / 字体与排版一致性 / 静态+资源实测**：仅加载 DM Sans 400/700，但样式使用 500/550/600/650；字体匹配会使用已有实例，目标字重不能被精确表达。字体虽已自托管且 font-display:swap，但 CSS 发现后才请求，没有显式关键字体预加载。**改进**：先视觉对比现有实际字形，选择少量必要字重或变量字体；若补齐字重改变外观，应单独验收。只预加载首屏真正需要的 WOFF2，避免全部字体同时抢带宽。本轮 3 个字体文件 decoded 合计 53292 bytes。

### src/hooks/*、src/components/workspace/workspace-provider.tsx

- `src/components/workspace/workspace-provider.tsx:25` — **R19 / P2 / 可维护性 / 静态**：hook 返回的多个操作与对象每次渲染重建，settle 依赖整个 documents/questions 对象；ChatView 通过 loaded ref 防止 effect 重复加载，其他位置禁用 exhaustive-deps。大量 generation/ref/busy token 解决了真实竞争问题，但维护成本高。**改进**：先统一稳定 action、请求作用域、实体状态和判别结果；effect 依赖稳定函数与原始 ID。将加载状态建模为明确状态而非更多布尔组合。现有 Redux 只管理 draft，不应在没有证据时再引入第二套全局状态库。

### src/services/api.ts

- `src/services/api.ts:48`、`:60` — **R20 / P2 / 接口健壮性与测试 / 静态**：普通 api<T> 依赖类型断言；复杂 SSE 状态机和 JSON 校验与通用 fetch 混在同一文件，没有对应的独立单元测试。**改进**：对关键响应建立轻量运行时守卫或契约生成校验；拆分 transport/errors/contracts/stream parser。必须保留当前 0.2.0、sequence、request_id、事件顺序与 sources 的校验强度。优先对分块边界、CRLF、多字节字符、错误终态、重复/乱序事件写确定性测试。

### src/lib/query-state.ts

- `src/lib/query-state.ts:19`、`:32` — **R25 / P2 / URL 状态竞争 / 静态风险**：URL 变化只更新本地值，没有取消未提交的 debounce timer；同一组件保持挂载时，用户后退/前进或另一路更新查询参数，旧 timer 可能把旧输入再次写回。**改进**：在外部 URL/path 改变时失效旧提交，区分自身提交回显；用包含多参数、后退/前进和 200ms 内连续操作的用例验证。保留输入即时反馈和 URL 深链。

### src/components/knowledge/*、src/components/shell/app-shell.tsx

- `src/components/knowledge/document-list.tsx:56`、`src/components/knowledge/bases-view.tsx:89`、`src/components/shell/app-shell.tsx:112` — **R26 / P2 / 长列表渲染 / 静态**：文档/知识库/侧栏可持续增长并完整 map；只有对话历史行已使用 content-visibility:auto，不能重复声称项目完全没有列表优化。**改进**：先隔离订阅、使用稳定行组件并测量；中型列表补内容可见性 containment，数千项且仍超预算时再虚拟化。保证键盘定位、链接、中键打开、焦点、加载更多和滚动恢复。多次载入后显示“已加载 N”而非把页内数量当成全部。

### src/app/api/v1/[...path]/route.ts

- `src/app/api/v1/[...path]/route.ts:43`、`:55` — **R24 / P2 / 服务端运行时 / 静态**：上传先存 chunks，再分配等长连续数组拷贝；峰值同时持有约 2B 请求正文，另有运行时开销。当前 9 MiB 上限有意义，不能直接删除。**改进**：先测并发上传下 RSS、GC 和排队；优先限制上传并发及及时取消。若改为计数限流的流式转发，须在超限时取消上下游，验证 multipart、断连和“后端未接受非法内容”语义。不要为了省内存引入半次提交副作用。

### e2e/*、playwright.config.ts、.github/workflows/web-e2e.yml

- `e2e/a11y.spec.ts:32`、`playwright.config.ts:10` — **R22 / P2 / 可验证性与监控 / 静态+本轮回归**：已有 22 个模拟用例通过、CI 也有完整栈步骤，但当前基础无障碍测试仅验证 skip link、少数 focus 和 URL，不涵盖上传 Tab、菜单 Esc、对比、PDF 控件；没有项目级 CWV 采集、包体预算、轮询 QPS 或内存门禁。**改进**：为本报告复现点补精确回归；独立测试 parser、代理和 hooks 并发；增加 Chromium/Firefox/WebKit 的关键流程与真实设备抽查。Mock API 不应替代真实栈问答、来源失效、断连取消和旧版回退。

### 界面细节与文档

- `src/components/knowledge/knowledge.module.css:278`、`src/components/chat/chat.module.css:610`、`src/components/auth/auth-view.tsx:73` — **R27 / P3 / 规范一致性 / 静态**：部分控件文字 11.5px，低于 DESIGN.md 的 12px 下限；占位符规则不统一；部分装饰图标未显式 aria-hidden。**改进**：统一对应 token、补装饰标记；占位符按中文/英文语义处理，不机械添加省略号。28px 控件不自动等于 WCAG 失败：移动端应优先扩大到舒适触控范围，再按目标间距检查最低要求。
- `README.md:40` — **R28 / P3 / 文档可维护性 / 静态**：验收文档写成 apps/web-v2 下的 docs/acceptance 路径，但文件实际位于仓库根 docs/acceptance；新成员从子目录按说明定位会失败。**改进**：使用正确相对链接，并明确命令工作目录、模拟/真实栈差别、性能复测步骤。
- `Dockerfile:17`、`next.config.ts:2` — **R29 / P3 / 交付体积 / 静态**：runner 复制整个 .next 后再安装全部 production 依赖，未采用 standalone 产物。**改进**：测量实际镜像和冷启动，再评估 standalone；保留 public/.next/static、动态资源、健康检查与非 root 用户。该项主要改善交付，不应承诺提升浏览器 LCP。

## 性能基线

### 包体与资源

来源：本轮 `.next/diagnostics/route-bundle-stats.json` 与实际生成文件。gzip 是本地逐 chunk 压缩估算，不是 CDN Brotli 大小，也不是浏览器总传输量。

| 路由 | 构建首载 JS，未压缩 bytes | gzip 估算 bytes |
|---|---:|---:|
| / | 730694 | 226759 |
| /conversations | 786670 | 245077 |
| /knowledge-bases | 764901 | 238233 |
| /knowledge-bases/[baseId] | 769897 | 239868 |
| /settings | 718501 | 222829 |
| /workflow | 718125 | 222810 |
| /login、/register | 673606 | 208211 |

首页加载完整波浪后，浏览器资源记录为 **18 个 JS 请求、1277235 decoded bytes（约 1.22 MiB）、368414 transfer bytes（约 359.8 KiB，含协议开销）**。构建首页首载数字不包含额外的 4096-byte 波浪模块和 542445-byte Three chunk；不能把两类口径混用。Three 并未被证明会在所有工作区路由都下载。

这是本机 Chromium、1440×1000、生产构建、模拟接口、无网络/CPU节流下的样本；可用于定位请求和包体，不代表线上移动端速度。没有可靠的线上 LCP/INP/RUM 数据，本报告不提供虚构 Lighthouse 分数、P75 或优化百分比。

### 已复现的运行时行为

| 场景 | 结果 | 对应问题 |
|---|---|---|
| 首页逐次输入 10 字符 | 10 次提交，每次 AppShell 均参与渲染 | R01 |
| 侧栏加载第二页 | 前后可见记录均为 Question 0–4 | R10 |
| 上传后索引 FAILED | 失败行/错误提示与“已上传，正在建立索引”同时出现 | R03 |
| 打开文档菜单后按 Esc | 菜单仍存在 | R14 |
| 问答接口 503 | 通用失败可见，具体错误不可见 | R05 |
| 历史搜索非空 | 加载更多按钮不存在 | R11 |
| 打开 PDF 来源 | 2 次文件 GET，iframe tabindex=-1 | R12、R15 |

探针通过临时 DevTools hook 观察 React 提交与 fiber 的执行标记，没有改动生产 bundle；它用于确认更新传播，不提供 render duration 或 CPU 节省值。精确耗时须用 profiling build 与浏览器 trace 复测。

## 全方位优化方案

### A. 优化边界与功能等价约束

1. 保留现有路由、真实链接、Cmd/Ctrl+click、中键、URL 查询状态、分页顺序与滚动恢复。
2. 保留 Three.js 的可见波形、视差与交互；减少动态效果仍显示静态帧；WebGL 不可用仍使用现有 WebP。首屏加载调度可以优化，最终视觉效果不可被永久静态替换。
3. 保留流式纯文本、50ms 合并、完成后 Markdown、引用顺序和文本码点定位。
4. 保留 SSE 0.2.0 契约、sequence、request_id、sources 校验、显式取消及“失败不自动重发”。
5. 所有用户缓存以 userId + baseId + resource/version 为边界；401、退出、账户切换清空或失效，禁止跨用户复用。
6. 保留同源代理、HttpOnly Cookie、来源校验、9 MiB 请求上限、8 MiB 文件限制、Range 和来源失效语义。
7. 必须区别修复缺陷和性能调优：修复“失败仍报成功”等行为是恢复正确语义，不属于需要保持的现状。

### B. 加载性能

| 环节 | 具体落地 | 预期作用 | 验证方式 |
|---|---|---|---|
| 初始化 | 仅鉴权作为全页门禁；知识库首批、历史首批、局部文档按依赖加载；其余页面不等待无关数据 | 缩短首屏关键链，避免账户数据量线性拖慢所有页面 | 给 /me、每页接口注入延迟，检查设置/工作流不再被历史阻塞 |
| 分页 | 知识库首批即呈现，其他页后台渐进；完整搜索继续可达 | 避免取完所有数据才显示 | 0/1/50/500/5000 项验证列表完整性及搜索 |
| 模块 | 分析每路由公共 chunk；避免 Auth 页承担不需要的工作区状态依赖；Three 在主体可交互后加载；提问期间预取 Markdown | 减少关键 JS 竞争及答案结束时排版等待 | 生产资源瀑布与 analyzer 对比，分别统计初始和完整动画阶段 |
| 动画依赖 | 对简单进入动画评估 CSS 或按需 Motion；以实际模块归因为准 | 缩小 JS 或初始化成本 | 保持相同 easing、duration、reduced-motion 和中断响应的视觉对比 |
| 字体 | 只预加载首屏必要 WOFF2；保留 swap；核实真实字重需求 | 减少字体发现等待与样式漂移 | 冷缓存瀑布、字体 ready、跨系统截图；不能因补字重改变现有外观而不验收 |
| 图片 | 保留 WebP 与已稳定的容器尺寸；关键 fallback 图按实际 LCP 元素决定是否预加载 | 避免误抢带宽和布局变化 | 无 WebGL、低动态、弱网三组 LCP/CLS 对比 |
| 网络缓存 | 保留私有 API no-store；客户端仅做账户隔离的去重和短期内存复用；静态哈希资源核对 immutable 压缩策略 | 避免重复请求及隐私缓存错误 | 检查响应头、退出清理和跨账户探针 |
| 预取 | 保留主要导航的体验；对大量列表链接先测 RSC 预取请求，再决定范围 | 防止长列表引发不必要流量 | 数百行滚动下请求数、导航响应和中键打开回归 |
| 交付 | 后置评估 standalone 镜像、资源缓存和冷启动 | 降低部署成本 | 镜像大小、RSS、启动健康检查，单列服务指标 |

不建议一开始把所有页面迁为服务端组件。若后续要服务端初始化会话，须另行验证 Cookie 转发、私有数据隔离、缓存与水合一致性；它是结构性选项，不是本轮必须前置的改造。

### C. 渲染性能

1. 先修 R01：输入草稿在 HomeComposer/Composer 的 selector 本地读取；AppShell 只订阅 user、导航、知识库和所需最近历史；AnswerPanel 只订阅当前答案，DocumentsPanel 只订阅文档。稳定 actions 与实体引用。
2. 以现有 Redux 能力或分离的小型 Context 实现，选一种清晰方案；不要同时新增 Zustand、React Query、SWR 再保留全部手写缓存。只有当共享数据缓存的收益明确时才引入查询层。
3. 轮询仅 upsert 变化的实体，未变化的行保留引用；为确实昂贵且输入稳定的行使用 memo。过滤/分组仅在数据或查询改变时重算，不对简单布尔值和字符串全面 useMemo。
4. 保留流式 50ms 合并。分离答案更新后测量提交耗时；输入跟随、停止按钮等紧急动作不能被 transition 延迟。
5. 长列表先内容可见性 containment 与稳定行组件；仍超预算再虚拟化。避免“少渲染”改变键盘位置、页面查找、读屏器和滚动高度。
6. Markdown 保持终态一次解析；大代码块、表格、长 URL 与异常长问题分别测量。内容大小上限应和后端一致，不靠前端随意截断答案。

### D. 运行时、网络与内存

1. **统一请求作用域**：每个 user/base/view 维护 AbortController 与代次；在 unmount、切换和取消时处理 fetch、timer、buffer、observer。旧请求不允许重置新请求的 busy。
2. **轮询调度器**：以 taskId 去重、配置总并发、维持当前退避范围并加入抖动；隐藏页暂停，重新可见时立即重验证；连续失败进入可恢复错误态。任务终态刷新按批合并；不将任务完成时的全表刷新放大为 N 次。
3. **上传与索引解耦**：传输成功即结束上传中状态，后台任务以行级状态追踪；重建、更新、删除对每行管理 pending；保存“stale”结果，不对下一个账户发成功 Toast。
4. **PDF 单一加载路径**：避免先下载探测再交 iframe；保留分段加载和页码，验证失效来源与无权限。
5. **文本原文**：扫描目标码点区间，限制并发与缓存容量；大文件测长任务与峰值堆内存，必要时用 Worker，避免全文重复复制。
6. **WebGL 生命周期共用**：离屏/隐藏暂停、恢复不跳跃、销毁资源、context loss 回退、DPR 与尺寸监听；每帧最多一次指针处理。不要只把 rAF 降为固定 30fps，就认定互动效果完全一致。
7. **代理运行时**：RSS/GC、并发上传、断连取消、SSE 传输背压分别测量；40s 代理上限不要盲目提高。后端 QuestionProperties 当前总问答预算最大 30s，不能把 40s 本身误报成已确认的超时缺陷。
8. **可观测性**：采集路由、LCP、CLS、INP、答案首帧/完成时长、流中断率、轮询次数、上传接受至 READY 时长；只记录必要标识，禁止记录问题正文、原文或凭据。上传/索引/模型时延需分开归因。

### E. 代码质量、组织与规范

建议渐进形成以下边界，先抽纯逻辑，再迁组件；无需一次性移动所有文件：

```text
src/services/transport.ts       # 同源 fetch、取消、统一错误
src/services/contracts.ts       # 0.2.0 类型、状态、运行时守卫
src/services/question-stream.ts # 可独立测试的 SSE parser
src/hooks/                      # 页面请求编排与生命周期
src/components/workspace/       # 小范围订阅、稳定 actions
src/components/chat/            # history/answer/composer/source 局部样式
src/components/ui/              # 按钮、弹层、菜单、上传入口的原生语义
```

- 将 contractVersion、任务终态、状态文案、上传限制集中管理；使用状态判别联合，避免多个文件各自维护 string 集合。
- 统一 `{status: accepted/failed/stale}` 等操作结果；accepted 与 succeeded 的语义不能混用。
- 统一错误展示责任：API 负责安全错误结构，hook 负责状态，组件负责可见反馈；不要同时在多个层 Toast，又在另一路径吞错。
- effect 依赖稳定函数；代次与取消逻辑抽为可测模块，减少通过禁用 lint 和微任务隐藏状态时序。不能删除目前已有的账户隔离保护。
- CSS 与 DESIGN.md 同步：文字对比、实际字重、控件最小字号、断点和动效时长均用实际渲染复验；不将所有硬编码值一概视为错误。
- 小型通知/账户 details 若约定支持 Esc，需要显式测试与实现，不能假定原生 details 自动具有菜单键盘语义。

## 分期执行与验收

| 阶段 | 内容与依赖 | 完成标准 |
|---|---|---|
| 0：建立基线 | 保存生产包体、同一 mock 数据集、固定视口和冷/热缓存脚本；真实栈另测 | 所有前后对比可重复，明确 fixture/网络/CPU/浏览器版本 |
| 1：正确性与可访问性 | R03/R05/R06/R07、菜单、分页、搜索、PDF 重复 GET | 新增精确回归全部通过；键盘可完成上传和原文查看；失败只报告正确语义 |
| 2：状态与启动链 | R01/R02/R19；依赖阶段1回归保护 | 输入不再渲染无关外壳；无关慢接口不阻塞设置/工作流；跨用户 0 泄漏 |
| 3：后台任务与文件 | R04/R08/R09/R12/R13/R16/R24 | 卸载无后续轮询；并发遵守预算；页数不丢；PDF 不再有多余探测 GET |
| 4：资源与交付 | R17/R18/R26/R29；以 analyzer 和 trace 为依据 | 包体和初始化成本下降；最终视觉与交互验收通过 |
| 5：持续门禁 | R20/R22/R25、文档与预算 | CI 包含关键回归、包体差异与可重复性能样本；生产持续观测 |

### 建议预算（待基线验证，不是已实现指标）

| 指标 | 建议目标 | 口径 |
|---|---|---|
| 真实用户 CWV | P75 LCP ≤2.5s、INP ≤200ms、CLS ≤0.1 | 目标，须在真实用户或匹配实验环境验证；不能用单次 localhost 值认证 |
| 首页初始 JS | 探索比当前 gzip 估算 226759 bytes 降 15–25% | 同版本构建工具、同口径；完整动画阶段单独统计；达不到则报告实际结果，不牺牲功能凑数 |
| 高频输入更新 | 连续输入时 AppShell、历史、资料无仅由 draft 引发的提交 | 稳定数据集、排除合法状态更新；输入组件自身更新正常 |
| UI 响应 | 4× CPU 实验中核心输入/停止交互的长任务受控 | 提交 duration、浏览器 trace 和交互延迟联合验证，不用 render 次数冒充耗时 |
| 请求取消 | 卸载/账户或库切换后不再开始旧作用域请求 | 至少等待两个原轮询间隔；在途取消与服务端取消分别核对 |
| 轮询 | 建议先将并发控制在 4–6，最终取值由真实服务压测确定 | 统计客户端总并发、每任务次数、页面隐藏时的行为 |
| 预览 | 单次 PDF 打开无应用额外探测 GET；原生 Range 分段请求允许 | 不把浏览器 PDF 查看器必要的分段读取误判成重复下载 |
| 内存 | 连续打开/关闭与路由往返后无持续保留的 timer、reader、WebGL 资源 | 20 次循环后的 heap/RSS 趋势；GC 后对比，区分浏览器缓存 |
| 包体回归 | 暂定路由初始 gzip 增长超过 5% 需解释 | 基线稳定后再作为强制阈值，不把合法功能增加一律判失败 |

### 功能与交互等价回归矩阵

- 登录、注册、重试、401、退出、账户切换；慢 /me 与快速认证竞争；缓存不得包含上一账户数据。
- 创建、删除知识库；0/1/50/500/5000 项、长中文名与长连续字符；当前页/跨页搜索、后退前进、刷新恢复。
- TXT/MD/PDF 上传、更新、重建、删除；8 MiB 边界、超限、无效后缀、取消选择、无效拖拽、索引 FAILED/CANCELLED、任务永久运行和网络中断。
- 索引进行时切换库、退出、卸载；旧请求失败不能关闭新请求 busy；并发终态不能抹掉已加载页。
- SSE 正常、拒答、error、cancelled、断流、乱序、重复事件、request_id 不符、错误版本、UTF-8/CRLF 分块、重复点击和显式重试。
- 流式纯文本到 Markdown、表格/代码/链接、答案复制、删除失败与防重入；首帧、停止反馈和完成排版分别计时。
- 文本码点定位（中文、emoji、代理对）、PDF 指定页、Range、文档删除、历史版本过期、401/404；关闭回焦、键盘进入 PDF 与替代链接。
- 390/768/1440 及 200% 文字缩放；Tab/Shift+Tab、Enter、Esc、方向键、IME 输入、真实触屏、安全区。现有视口测试不能冒充真实触摸与设备验证。
- 首页与登录 WebGL：正常、低动态、离屏、后台、恢复、resize、context loss、无 WebGL；相同视觉帧或时间段对比并保留静态回退。
- 阶段完成后重跑现有 22 项模拟用例，再运行仓库已有隔离全栈 `npm run e2e`，覆盖真实问答、原文、所有权和旧版回退。

## 保留的优点与排除的误报

- App Router 页面薄，业务组件、hooks、services、UI 已分层，TypeScript strict 与 Next ESLint 配置启用，CI 已有 typecheck/lint/build/full-stack 步骤。
- 私有 API 同源代理，Cookie 为 HttpOnly，写请求校验来源，限制正文大小，SSE 透传 no-transform 与 X-Accel-Buffering。不能为了静态缓存或省内存削弱这些边界。
- SSE 状态校验严格、50ms 缓冲、生成期纯文本和终态 Markdown 已实现；这不是需要重新发明的优化点。
- generation、working token 与 stale 结果已有账户切换保护；优化应补取消和状态边界，不能删保护换取更少代码。
- 导航主要使用真实 Link；有 skip link、Radix 焦点陷阱、全局 focus-visible、URL 搜索同步。不能声称项目没有这些基础能力。
- 首页波浪已有可见性暂停、DPR/绘制数量控制和 WebGL 资源释放，登录页应复用同样成熟度。
- 历史行已有 content-visibility；字体已自托管且 font-display:swap；图片已使用 WebP。报告没有把这些已实现优化重复列为“完全缺失”。
- 检测器对 `.sourceQuote` 左边线的唯一命中已核对为语义引用样式，排除，不建议删掉。没有产品暗色主题要求，缺少 dark mode 也不单列为缺陷。

## 参考与复测入口

- 本轮 Web Interface Guidelines： https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md
- 项目设计约定：`apps/web-v2/DESIGN.md`。
- 接口约定：`contracts/api-draft.md`；问答预算：`services/api/src/main/java/com/knowflow/api/config/QuestionProperties.java`。
- CI：`.github/workflows/web-e2e.yml`；脚本：`scripts/e2e-web.mjs`。
- 本机临时日志与探针：`C:/Users/31180/AppData/Local/Temp/web-v2-review.novPvC/`，含 lint/typecheck/build/e2e 日志、runtime-review.cjs、runtime-results.json、design-detector.json、npm-audit-official.json；临时目录不是永久仓库证据，关键结论和数值已写入本报告。
- 可选分步技能：`/impeccable harden`（异步/错误/边界）、`/impeccable optimize`（状态与资源）、`/impeccable adapt`（键盘与响应式补验）、最后 `/impeccable polish`（规范细节），完成后重新 `/impeccable audit`。这些是可选执行入口，本报告没有自动开展修复。
