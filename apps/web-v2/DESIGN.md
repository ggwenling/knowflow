# KnowFlow Web v2 · 黑白极简 / Monochrome minimal

适用范围：`apps/web-v2` 全部页面与状态。Round D（2026-11-11）基于 `05bde01`，按用户反馈“ 不做这种黄色，我想保留原来的黑白极简风格 ”撤回 Round A 暖纸配色。参照 `b7fd541` 的白底结构，进一步移除蓝灰强调色：纯白、中性灰、石墨黑构成全部界面和语义状态。保留 Round 3 布局、Round B 无障碍和 Round C 性能优化。

## 1. 设计立场

像一本排版精确的产品手册，而不是通用后台。

- DM Serif Display 仅用于 KnowFlow 品牌与英文展示标题；中文标题、正文与控件使用 DM Sans + 系统中文无衬线。细线与留白建立秩序。
- 强调色、焦点、来源序号与图标均为石墨黑；KF 标记为黑底白字。侧栏活动项用黑点与浅灰表面；页头取消装饰方块。状态由明确文字与图标表达，成功、处理中、失败及危险操作也使用中性灰，无彩色表面。
- 首页与登录页保留既有 Three.js 波浪。其余动效为反馈、定位与状态服务，120–260ms，无弹跳。
- 允许轻微环线 + 分层软阴影、抬起表面的 1px 内高光、英雄区极淡径向光。禁止重阴影、强玻璃、霓虹与多色卡片。浮层可用 98% 白色表面，不增加背景模糊。
- 工作区保持中文；登录/注册保留英文品牌语气。

## 2. 设计令牌

定义在 `src/app/globals.css`。

| 类别 | 值 |
|---|---|
| 背景 / 下沉表面 | `--bg: #FFFFFF`、`--bg-subtle: #FAFAFA`、`--bg-muted: #EEEEEE`、`--surface-sunken: #F5F5F5` |
| 浮起 / 覆盖表面 | `--surface-raised: #FFFFFF`、`--surface-overlay: rgba(255,255,255,.98)` |
| 文字 | `--ink: #171717`、`--ink-2: #525252`、`--ink-3: #626262` |
| 边框 | 装饰分隔 `--line: #E5E5E5` / `--line-strong: #D4D4D4`；控件 `--control-line: #808080`，均为 1px |
| 强调 / 焦点 | `--accent` / `--focus-ring: #171717`，选中浅底 `--accent-soft: #F0F0F0`；反白文字 `#FFFFFF`，深色 hover `#303030` |
| 状态 | 成功点 `#525252`、处理中点 `#626262`；成功 / 警告 / 危险文字 `#525252`，危险边界 `#737373`，所有状态浅底 `#F5F5F5` |
| 圆角 | 4 / 6 / 10 / 14 / 999px |
| 间距 | 4 的倍数；区块间距 18–30px；页面左右 24–52px |
| 动效 | `--dur-fast: 120ms` / `--dur: 180ms` / `--dur-page: 220ms` / `--dur-slow: 260ms` |
| 曲线 | `--ease-out-expo` / `--ease`: `cubic-bezier(.23,1,.32,1)`；`--ease-in-out`: `(.77,0,.175,1)`；抽屉 `--ease-drawer`: `(.32,.72,0,1)` |
| 层级 | `--z-shell:5` / popover:20 / overlay:40 / dialog:50 / toast:60 / skip:100 |
| 抬起表面 | `--shadow-card`：极淡环线 + 2px 接触影 + 8px 环境影；`--shadow-raised`：4px + 16px；`--shadow-pop`：8px + 24px，均为低透明度墨色 |
| 内高光 | `--highlight: inset 0 1px 0 rgba(255,255,255,.8)` |
| 间距令牌 | `--space-1/2/3/4/6/8`: 4 / 8 / 12 / 16 / 24 / 32px |
| 布局 | 侧栏展开 `248px`（≤1180px 为 226px）、收起 `64px`；内容最大宽度 `1280px` |
| 字体 | `DM Sans` + `PingFang SC` / `Microsoft YaHei` 用于中文标题、正文及控件；`DM Serif Display` 仅用于品牌 / 英文展示标题；无中文字体下载 |

## 3. 排版

| 角色 | 字号 | 用法 |
|---|---|---|
| 品牌 / 页面主标题 | `--type-h1`（30–40px），首页约 54–84px | 品牌衬线 400；中文页面标题无衬线 600、`letter-spacing: -.025em` |
| 登录主标题 | 桌面 52–84px，移动 52px | 衬线、行高 1 |
| 区块标题 | 13–15px / 600 | 无衬线，句子式大小写 |
| 正文 | 13–15px / 1.7–1.9 | 无衬线 |
| 辅助信息 | ≥12px | `--ink-3`；只有格式、大小、序号、ID、kbd 用系统等宽栈 |
| 英文目录标签 | 11–12px / 600 | 无衬线，页头 `.055em` 字距；无装饰方块 |
| 控件文字 | 不低于 12px | 按钮、标签、筛选 |
| 数字 | `font-variant-numeric: tabular-nums` | 时间、计数、大小 |

衬线字体用于品牌与英文展示标题；页面 h1、中文区块标题、知识库名称、回答标题和弹层统一无衬线，来源序号用等宽。中文标题子集、loader 和生成脚本已移除，系统中文直接绘制。系统等宽栈为 `ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace`，不下载字体。

字号角色令牌：`--type-display` 56–84、`--type-h1` 30–40、`--type-h2` 20、`--type-title` 15、`--type-body` 14、`--type-small` 12、`--type-micro` 12px。回答正文 15px / 1.8，最长约 70ch。移动输入统一不小于 16px，避免聚焦时浏览器放大。

字体通过 next/font/local 复用既有 DM Sans 400/700 与 DM Serif Display 400 文件，使用 swap；只 preload 拉丁展示字体，正文按使用加载，保留 Round C 的 Arial metric fallback。新增字重必须另做视觉与资源预算验收。

## 4. 外壳与响应式

`src/components/shell/app-shell.tsx`

- 桌面：固定 248px 侧栏，包含品牌、主导航（首页/对话/知识库/工作流/设置）、知识库快捷入口与内联创建、最近问答、账户区。支持按钮与 ⌘/Ctrl+B 收起到 64px 图标轨道，toggle 的 aria-expanded / aria-controls 与状态一致；账户菜单在底部，展开 / 收起均可使用。
- 收起后隐藏品牌文字、库 / 历史 / 创建区域与账户文字；导航保留 aria-label，并在 hover / focus 展示可悬停、Esc 可关闭的 CSS tooltip。邮箱 tooltip 关联账户菜单说明。移动 ≤760px 不展示 toggle，不使用收起样式，保留顶栏账户菜单与原导航。
- 偏好键为 `knowflow.sidebar.collapsed`。根布局的短内联脚本在绘制前设置 html data-sidebar-collapsed；仅 html 对该额外属性启用 suppressHydrationWarning，子树不抑制。SidebarToggle 独立 useSyncExternalStore 订阅，使用稳定的服务端快照；不向 AppShell / WorkspaceProvider 增加状态。支持 storage 事件与存储不可用时的当前页回退。
- 新建知识库的所有聚焦入口先展开桌面侧栏，再打开快捷区并聚焦输入，移动创建不修改桌面偏好。
- 主内容：使用 `<main id="main-content" tabIndex={-1}>`，最大 1280px 居中，上内边距由 `--page-top` 统一为桌面 40px / 移动 26px；页头规则线到工具栏或内容的间距由 `--page-gap` 统一为桌面 28px / 移动 24px。详情页返回链接单独占 40px 行及 16px 间隔；页面首个可聚焦元素是“跳到主要内容”。非首页使用统一 `workspace-header` 页头带：标题 / 一句说明 / 行动底部对齐、24px 底部留白与发丝分隔线；移动自然换行，不省略说明。大面积表面不叠加径向光或纸粒。
- 导航、知识库卡片、历史记录必须是 `<a>`/`Link`，支持 Cmd/Ctrl+click、中键与新标签；创建、上传、提问、停止、删除等动作保持 `<button>`。
- `≤1180px`：侧栏 226px，内容留白 28px，对话资料栏收窄。
- `≤980px`：对话页隐藏独立历史栏与资料栏，改为“历史记录”“资料”抽屉。
- `≤760px`：品牌 + 四等分导航 + 可展开的“工作区快捷入口”；快捷区默认折叠，首页和对话页隐藏快捷区。创建知识库的动作会先展开、再聚焦输入，保留键盘路径；展开后可访问知识库横条、内联创建与最近问答。设置入口在账户菜单中。
- 导航使用同一个 CSS 表面指示器：桌面纵向、移动横向滑动；移动设置页不显示越界的导航指示器。桌面分区、账户持续可见，历史区独立滚动。
- `390px`：无横向滚动；表格类内容改为纵向堆叠；次要说明可隐藏。

## 5. 页面规范

### 5.1 首页 `/`

- 衬线 `KnowFlow`（不加浮动句点）+ 12px 深色英文目录标签 + 一句定位语 + 单行提问框，下方保留 Three.js loom；无 WebGL 时回退 `home-wave.webp`。
- 单一提问外框由问题主行与底栏组成，知识库选择整合到底栏；不保留首页 ↵ 芯片。内部输入与 select 无边框 / 背景 / 阴影 / outline，外框以 focus-within 提供 2px 焦点环。模型模式文案作为英雄区的安静辅助文字。
- 四个快捷操作：创建知识库、新建对话、上传文档、创建工作流；四项都落到真实路由或明确的占位页。创建知识库使用明确的墨色主卡，其余白底；每张都有独立图标瓷片、说明与 hover 箭头。桌面上下排版，移动双列紧凑横排。
- “我的知识库”“最近问答”采用等宽两栏、相同的 76px 行基准；快捷卡、面板与主内容网格边线一致，英雄区提问框最长 800px 居中。窄屏单列面板、紧凑快捷卡；40px 行图标与 ≥12px 元数据，空态保留唯一下一步。
- 通知与账户浮层使用原生 `details`，点击外部关闭；Esc 关闭并回到触发器。支持 `::details-content` 的浏览器保留离场过渡，旧浏览器直接关闭。
- 空问题、初始数据未到、没有 READY 资料或生成中均禁用发送。禁用按钮无填充、虚线边界、无阴影；箭头半透明。启用按钮为实心墨色。保留原生 disabled 与原提交校验。

### 5.2 登录 / 注册 `/login`、`/register`

- 左侧表单，右侧独立 artPanel 同时容纳 `atlas-auth.webp` 与 ribbon。整个容器左边缘渐隐 30%，插画顶部渐隐，ribbon 在插画 folio 上方渐隐，禁止横穿表单。`≤700px` 插画隐藏，ribbon 收为顶部窄带；保留 `.loginFlow`、`.loginCanvas` 与 `login-ribbon.webp` 回退。
- 输入框桌面 58px / 移动 54px 高、6px 圆角；提交按钮 56px 高、6px 圆角。更紧的英文眉题、较轻的表单标签与清晰焦点，注册 / 登录分两个重叠节拍：标题与说明 220ms / 4px，表单与链接 180ms / 4px，延迟 40ms；品牌和 ribbon 保持静止，不等待旧页面退出。页脚用 12px / 600 无衬线与 .06em 字距。
- 错误以明确的中性深灰文字出现在表单内，`role="alert"`；字段使用 aria-invalid / aria-describedby 关联错误，注册密码说明也关联字段；提交中按钮显示 `Please wait…` 并禁用。
- 已登录访问 auth 页自动回到 `/`。

### 5.3 对话 `/conversations`、`/conversations/[questionId]`

- 桌面三栏：历史 216px、问答自适应、资料 258px（≤1270px 为 180 / 自适应 / 208px）；历史按今天/昨天/更早分组，支持搜索与加载更多；搜索词写入 `?history=`，可刷新恢复。
- 答案：问题行 + 独立状态工具行；流式期间纯文本 + 光标，完成后 Markdown 渲染。阶段只从已收到的来源 / 正文推导“检索资料 / 已找到 N 段依据 / 生成回答”，不做计时器假进度；保留“正在检索并生成回答…”状态文案。引用最多 5 条，等宽编号、位置与摘录组成可点卡片。资料侧栏顶部按同一来源顺序展示“本次引用”，桌面持续可见，移动抽屉内复用；CurrentSources 独立订阅，SourceLinks memo 不随正文片段更新。
- 原文弹层：标题“原文依据”，首焦点为“关闭原文”，Esc 关闭并回到触发引用；PDF 用 iframe `#page=N`，文本用 `pre`。
- 提问框在答案列底部占独立布局空间，`Enter` 发送、`Shift+Enter` 换行；生成中显示“停止生成”。单行起步并随内容增长，桌面最大 144px、移动最大 120px；移动把提交按钮放在同一行，隐藏 kbd 提示，空输入约 58px 高。
- 对话页采用受视口约束的 flex 布局：实际页头占多少，剩余区域就分给答案与输入框，不再猜测页头高度。答案底部留 44–48px 可滚动余量；输入框上沿 20–24px 静态渐隐，焦点滚动也有底部留白。输入高度测量只在 Composer 内，不增加 React 状态或订阅整页。
- 单轮问答必须明示“每次提问独立检索”，不得伪装多轮上下文。
- 空态提供三条示例问题；失败/取消显示“此问答状态：…。可在历史记录中查看。”。
- `≤980px` 历史与资料改为抽屉，抽屉内复用同一组件与数据。

### 5.4 知识库 `/knowledge-bases`

- 页头：标题（有库为“我的知识库”，无库为“开始整理你的资料”）、说明、主行动“新建知识库”。桌面两列“档案封面”卡片：SVG 等高线与 KF 列表序号、图标、真实名称 / 更新时间与“打开”入口。去掉 4px 假书脊，外框统一 1px；移动单列、封面压缩至 76px。网格内有虚线“新建知识库”按钮，进入同一展开 / 聚焦创建路径。
- 搜索按名称过滤并写入 `?q=`；卡片为链接（细线 + 文件夹图标 + 名称 + 更新时间 + 箭头）；删除按钮保留包含知识库名称的 accessible name；细指针设备仅 hover / focus-within 显示，触屏 / 混合输入设备始终可见，40×40px。点击仍进入确认对话。
- 空态：说明价值与下一步，主行动聚焦侧栏创建输入。
- 列表接口不返回每个知识库的文档数，因此不展示编造的数量；文档数在详情页展示。

### 5.5 知识库详情 `/knowledge-bases/[baseId]`

- 返回、标题、`N 份资料 · M 份可用于问答`、私有空间标识。其下是紧凑的全部 / 已就绪 / 处理中 / 失败计数带，完全复用已加载资料的实际状态；分页尚未加载完整时明确提示“已加载”口径。取消归入失败，与既有筛选口径一致。
- 上传区：浅色纸面、虚线细框与独立上传图标，支持拖拽与选择；TXT/MD/PDF，最大 8 MiB，PDF 200 页。拖入时虚线伪元素只做 opacity 呼吸、图标上移 3px；空闲时完全静止。用 drag depth 计数避免跨越子元素闪烁。
- 筛选：全部 / 已就绪 / 处理中 / 失败，带等宽计数与同一滑动底板；筛选写入 `?status=`，非法值回退到“全部”。移动四等分，不横向滚动。
- 文档行：格式徽标、名称、大小、状态点 + 文案、操作菜单（更新资料、重建索引、删除资料）。
- 删除走确认对话；轮询 1.5s 起指数退避至 4s，切换知识库或卸载时判旧退出。
- 无权限/不存在时展示 `role="status"` 的中文 404 文案，不泄漏资源是否存在。
- 文档接口不返回更新时间，因此文档行只展示大小与状态。

### 5.6 设置 `/settings`

- 桌面为左侧 156px 分区导航 + 右侧单列内容，最大 1040px，列间距 32px。账户 / 模型与数据 / 暂未开放使用原生锚点，当前状态跟随 URL hash，支持浏览器返回 / 前进与可聚焦目标；导航独立订阅，不使事实卡重渲染。
- 卡片标题下有一句说明，信息行按 label / value 网格对齐，展示登录邮箱、空间、知识库数量、模型模式、问答方式、资料范围。退出登录放在账户卡底部的独立“危险操作”区，保持原动作与文案。
- ≤980px 分区导航变为横向分段行，移动 label / value 使用 72px / 自适应列，长值自然换行。未开放功能使用次级浅底区，不制造可操作控件。
- 退出登录为危险按钮；明确“自助找回密码、团队协作、账单与导出暂未开放”。

### 5.7 工作流 `/workflow`

- 诚实的占位页：三步说明（上传资料 → 建立索引 → 带引用回答），明确“工作流功能暂未开放”，并提供前往知识库/对话的行动。
- 三步共享同一纸面，以编号、连接方向与第三步的较深纸面落点呈现顺序，插画移到“当前可用能力”区域，避免移动端插画占据整个首屏；页头只保留轻量“开发中”标识。移动纵向排列。
- 不使用假开关、假进度或假运行记录。

### 5.8 全局状态

- 会话加载：品牌 + “正在检查登录状态…” + 三行骨架；失败：抬起卡片 + “重试连接”。重用 PageFallback，不添加全局进度状态。
- 404 与渲染错误共用 RecoveryView：无外框的编辑排版、品牌、结实的错误标识、发丝线与单一行动。完全移除灰色径向光晕与浮卡阴影。global-error 使用有静态回退值的 CSS，不依赖根布局的字体 / 令牌成功加载。
- 未登录访问工作区自动跳转 `/login`；401 触发全局会话失效提示并清理。

## 6. 组件

| 组件 | 路径 | 规则 |
|---|---|---|
| Button | `ui/button.tsx` | primary / secondary / ghost / danger / text；桌面高度 32/38/46，移动至少 40px；loading 显示小型指示并禁用、aria-busy |
| Dialog | `ui/dialog.tsx` | Radix；桌面居中、移动端底部抽屉；焦点陷阱与 Esc |
| ConfirmDialog | `ui/confirm-dialog.tsx` | 危险操作；标题说明后果，主按钮“确认删除” |
| EmptyState | `ui/empty-state.tsx` | 图标 + 一句标题 + 一句说明 + 唯一下一步 |
| Skeleton | `ui/skeleton.tsx` | 低对比扫光，只用于首屏列表 |
| StatusBadge | `ui/status-badge.tsx` | 5px 点 + 12px 文案 + 中性灰浅底；成功/处理中/失败/取消/中性，颜色不独立承载意义 |
| Toast | `sonner` | 仅用于异步操作结果，文案短、可关闭 |

按钮文字使用动词；同一动作在按钮、Toast、确认框中保持同名。导航用链接、动作用按钮；不要用 `div` 模拟控件。

表单补 `name`、`autoComplete`、`spellCheck`；占位符以 `…` 结尾并展示示例格式。输入、选择器与 textarea 必须有可见焦点环。带外壳的复合字段统一标记 `data-composite-field`：内部控件在普通 / focus / focus-visible 下均无 border、background、box-shadow 与 outline；2px 焦点环放在外壳的 focus-within，不能内外叠加。独立的登录输入仍保留自身焦点环。非空问题草稿在应用内路由切换时保存在 Redux，关闭 / 刷新窗口时提供原生 beforeunload 提示；guard 独立订阅 dirty 布尔值，不使外壳随输入重渲染。kbd 只用等宽文字、无边框 / 底色 / 阴影，不伪装成按钮。

## 7. 动效

- 仅页头 ink-settle 220ms / 4px、首页品牌 240ms；transform + opacity，取消 blur。默认内容可见，动画使用 backwards；列表与来源序号不重复进入。
- Auth 标题遵循 ink-settle，表单 180ms / 4px，重叠 40ms；品牌与 artPanel 静止。
- 键盘输入通过 DOM `data-input="keyboard"` 即时完成动画；不以 React 状态广播按键。减少动态效果时页头只淡入 120ms，无位移；Three.js 静帧，无循环。
- 两个 Three.js 场景均提供原生暂停按钮与 aria-pressed。暂停保持当前画面及 canvas，只停止 rAF 调度；恢复不重建 renderer / geometry。后台标签页、离屏、context loss、卸载仍按原策略暂停 / 清理。
- 导航底板 220ms、筛选底板 180ms，transform 过渡可中断；黑色圆点是导航底板的伪元素，一起移动。收起轨道中也放在底板内部。
- 既有侧栏 `grid-template-columns` 220ms 是保留的布局过渡例外：它让阅读区真实获得空间，不是假收起。键盘及 reduced motion 即时完成。本轮没有新增布局动画。
- 弹层进入 220ms / 退出 140ms；浮层从触发点 180ms / 100ms 退出，菜单行静止。hover 位移仅 fine pointer，最多 2px；按压 1px / 100–120ms。
- 50ms SSE 缓冲与完成后一次 Markdown 解析保持不变；骨架 / 生成指示用于真实等待状态，reduced motion 下静止。

## 8. 可访问性

- 焦点环统一 `2px var(--focus-ring)`（`#171717`），偏移 3px。复合字段的焦点环由外框承载，内部 outline 为 none 是有意的等价焦点行为；内联创建框保留足够左右余量以免被侧栏裁切。
- 图标按钮必须有 `aria-label`；菜单使用 `role="menu"` / `role="menuitem"`。
- 弹层使用 Radix Dialog：焦点陷阱、Esc 关闭、关闭后回到触发元素。
- 流式答案容器 `aria-live="polite"`；加载/错误使用 `role="status"` / `role="alert"`。
- 键盘可完成：登录、提问、打开引用、关闭弹层、切换知识库、打开移动抽屉。
- 对比度：正文 `#171717` / `#525252` 于白色和中性灰表面；辅助与状态文字在实际背景上达到普通文字 4.5:1，状态圆点使用中性灰，不承载唯一状态信息。
- 弹层与抽屉设置 `overscroll-behavior: contain`；可点区域设置 `touch-action: manipulation`；不要禁用缩放。
- 历史列表超过 50 项使用 `content-visibility: auto` 与 `contain-intrinsic-size`，避免一次性布局全部行。

## 9. 数据与接口边界

- 契约冻结 `0.2.0`；前端只通过同源代理 `/api/v1` 访问，不直连后端。
- 保留 SSE 事件序号、顺序、`request_id`、契约版本校验，不因界面放宽。
- 删除知识库复用 `DELETE /api/v1/knowledge-bases/{id}`；删除前明确“资料将不可见且无法恢复”。
- 不编造统计、更新时间、文档数或模型能力；合成模型必须显示提示。

## 10. 验证

```powershell
npm run typecheck
npm run lint
npm run build
npx playwright test
```

- `e2e/dashboard.spec.ts`：首页波浪、快捷操作、移动端与减少动态效果。
- `e2e/login-rendering.spec.ts`：无 WebGL 回退、移动端登录、无横向溢出。
- `e2e/history-layout.spec.ts`：桌面历史滚动、分页、账户退出可见。
- `e2e/session.spec.ts`：会话失败重试与 401 清理。
- `e2e/knowledge-desk.spec.ts`：真实注册、创建、上传、READY、流式问答、引用弹层、停止、归属隔离、删除与 PDF 预览。
- `e2e/chat-flow.spec.ts`：模拟 SSE 下的 Markdown、引用、复制与键盘关闭。
- `e2e/responsive.spec.ts`：390/768/1440 无横向溢出、移动抽屉、桌面三栏。
- `e2e/a11y.spec.ts`：skip link、main 地标、链接导航、焦点环、URL 状态刷新恢复。
- `scripts/acceptance.mjs`：真实栈登录/创建/上传/READY/问答/引用/截图/清理，产出 `eval-out/acceptance-20261108/manifest.json`；人工签字仍由负责人完成。
- Round B 复用 `/workspace/knowflow-polish/rA-*.png`，全部 20 张。沙箱不能启动 Chromium，因此不能声称修改后截图 / E2E / 动效观感已通过；实际本地命令结果见 VISUAL-POLISH.md。

## 11. 素材与表面

- 保留 `home-wave.tsx` loom 与 `login-ribbon.tsx` canvas、两张静态 webp 回退、现有渲染 / context loss 测试。Round D 只将场景颜色改为中性石墨，保留几何、shader 运算、pause 与 Round C 的延迟加载 / 异步编译 / 固定尺寸。
- 原位转换 `atlas-auth.webp`、`atlas-empty-{bases,documents,history}.webp`、`atlas-workflow.webp`、`atlas-recovery.webp` 为中性灰度并提白背景；两张场景回退也去色。保留原尺寸、透明通道与文件名，无新依赖。StaticArt 使用原生 img，空 alt 与明确尺寸，auth eager / high priority，其余 lazy。
- `knowledge-contours.svg` 为中性灰封面几何线条。移除纹理文件及其 CSS 引用，所有表面保持清洁。素材 URL 带 `?v=monochrome-d`，维持一年 immutable 缓存并避开旧素材缓存；后续替换内容须更新版本参数。
- 移除 Round A 中文衬线子集、独立许可 / 字形清单及无引用的生成脚本，减少 25,056 字节字体资源。保留两份 DM Sans 和一份 DM Serif Display。

## 12. Round B 验收边界

- 全量 Vercel prefetched guidelines 源码审查；Impeccable critique / audit / polish 思路与 AI tells 手工审查；Emil ink-settle 复审。没有运行 Impeccable launcher、hooks、detector、安装器或子代理；这不是完整自动 critique 命令报告。
- 390px 点击区域至少 40px，输入至少 16px；导航、账户、资料操作、弹层关闭、设置索引与 auth 辅助链接均覆盖。viewport-fit cover 与安全区域内边距配合；不禁用缩放。
- `node scripts/contrast-audit.mjs` 读取当前 CSS token 并断言文本 ≥4.5、焦点 / 控件边界 ≥3。完整矩阵、例外说明与验证状态见 VISUAL-POLISH.md。
- 预算文件不得修改；生产 JS 按原 `npm run perf:budget` 的每路由 +5% 上限验收。浏览器测试在可启动 Chromium 的环境运行。

## 13. Round D 验证与性能边界

- `npm run lint && npm run typecheck && npm test` 全部通过，5 个测试文件通过。
- 对比度脚本同时断言全部颜色令牌 R=G=B，并新增成功 / 处理中点颜色检查；所有普通文字 ≥4.5:1，焦点 / 控件边界 ≥3:1。辅助文字最低 5.26:1，控件边界最低 3.40:1。
- 源码 / SVG 的 hex、rgb、hsl、oklch、GLSL 与 Three.js 颜色自查：无非中性色，无需语义色例外。WebP 从灰度源压缩，解码 RGB 最大通道差 1/255（编码舍入），展示层 grayscale(1) 保证中性显示；透明回退 alpha 保持原值。
- Round C 原生 StaticArt、首次打开才加载弹层、延迟 WebGL、保留场景尺寸、字体 preload 限制与 immutable 缓存继续保留。预算、依赖、选择器、accessible names 与业务逻辑未改。
- 按本轮要求未运行 build / 浏览器 / perf:budget；新生产构建的截图、E2E、CLS、Lighthouse 和预算由操作员执行，不能将源码核查当作浏览器验收。
