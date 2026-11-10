# KnowFlow web-v2 视觉精修交付记录

分支：`feat/web-v2-visual-polish`。本次只修改前端视觉、交互微状态与相关规范。没有提交或推送。

## 逐页变化

| 页面 / 区域 | 最终实现 |
|---|---|
| 外壳 | 微冷侧栏、白色活动导航底板与蓝灰边标、分区与账户层级；移动四等分导航，知识库快捷区默认折叠。创建动作先展开再聚焦，桌面历史仍独立滚动。账户 / 通知支持外部点击关闭、Esc 返回焦点。 |
| 首页 | 提问框作为主要视觉对象：柔和环线、接触影与抬起影、聚焦蓝灰边框、Enter 提示；快捷卡与最近面板增加层次、调好间距与文字对比。现有 Three.js 不变。 |
| 对话首页 | 纸页空态、清晰问题示例、浅底历史栏、抬起的回答纸面与独立输入框。 |
| 问答详情 | 15px / 1.8 正文、独立问题工具行、阅读宽度约 70ch、等宽编号来源卡；右侧“本次引用”与正文引用顺序一致，点击打开同一个原文弹层。 |
| 流式状态 | 保留原有状态文本；依据实际收到的来源 / 正文显示阶段，不推测后台任务或伪造进度。仅首次正文淡入，不逐字动画。 |
| 知识库列表 | 桌面上下两段卡片，文件夹符号与更新时间有明确主次，移动紧凑横排；无结果与首次空库保持不同动作。 |
| 知识库详情 | 更完整的标题区、纸面上传区、计数滑动筛选、格式 / 文件名 / 状态层次；移动文档行将状态放到第二行，避免挤压长文件名；drag depth 避免跨子节点闪烁。 |
| 设置 | 编号账户 / 模型信息卡，宽屏并列、窄屏纵向排列；未开放功能放在次级浅底区，减少空散的信息行。 |
| 工作流 | 纸页插画 + 编号三步共用一张纸面、箭头与第三步蓝灰落点；保持“暂未开放”的真实边界。 |
| 登录 / 注册 | 保留 ribbon，缩紧品牌 / 标题 / 表单节奏、表单标签更轻、输入焦点更清晰、按钮有内高光与按压反馈；两页进入统一 260ms。 |
| 404 / error / global-error | 共用 RecoveryView，带品牌、等宽错误标识、说明与唯一主要行动。global-error 的 CSS 有静态值回退。 |
| 会话 / 页面加载 | 品牌 + 状态文字 + 三行扫光骨架；没有虚构进度条。 |

## 设计系统

完整规范见 [DESIGN.md](DESIGN.md)，源令牌见 [globals.css](src/app/globals.css)。

- 纸白 / 浅底 / 下沉：`#FFF` / `#F7F8F9` / `#EEF0F2` / `#F3F5F7`。
- 墨色：`#191C20` / `#555E68` / `#69727D`；发丝边框 `#E4E7EB`，强边框 `#CBD1D8`。
- 单一强调色：原 `#5C7A8F` 收深为 `#506E83`，浅底 `#EDF3F7`。成功 / 处理中 / 失败仍保留语义色、文字与点。
- `--surface-raised` / `--surface-sunken` / `--surface-overlay`；`--shadow-card` / `--shadow-raised` / `--shadow-pop`；`--highlight`。
- 字号角色：display / h1 / h2 / title / body / small / micro；系统等宽栈用于编号、元数据、kbd；全局 tabular nums。
- 4/8/12/16/24/32px 间距；既有 6/9/14/20px 圆角；2px 蓝灰焦点环。
- 120 / 180 / 260ms 与 expo / in-out / drawer 曲线；shell / popover / overlay / dialog / toast / skip 层级。
- Button 包含 loading / aria-busy / disabled / press；ConfirmDialog 保持 AlertDialog 语义；状态标签、空态、骨架、Sonner、输入和键盘提示一致。

## 动效清单

Expo = `cubic-bezier(.23,1,.32,1)`；Drawer = `cubic-bezier(.32,.72,0,1)`。
所有键盘操作都即时完成。DOM modality 监听没有 React 状态，不会让输入草稿或 SSE 触发外壳重渲染。

| 元素 | 触发 / 目的 | 时间与曲线 | 减少动态效果 |
|---|---|---|---|
| 页面 / auth 内容 | 挂载；避免跳变 | 260ms Expo，淡入 + 6px rise；没有路由退出等待 | 120ms 纯淡入 |
| 首页四个快捷卡 | 首次挂载；建立阅读顺序 | 200ms Expo，0 / 40 / 70 / 95ms 起始，总计 295ms | 同时淡入，无位移与 delay |
| 导航指示器 | 路由改变；定位 | 220ms Expo，纵向 / 横向 transform | 即刻到位 |
| 文档筛选底板 | 状态改变；定位 | 180ms Expo，translateX；可中断 | 即刻到位 |
| 卡片 / 箭头 | 精细指针 hover；反馈 | 180ms Expo，最多 2px；所有 hover 都有媒体门控 | 无位移 |
| 按钮 | 按下 / 释放；反馈 | 100 / 120ms Expo，1px | 无位移 |
| 对话框 / 确认框 | 打开 / 关闭；空间连续性 | 220 / 140ms Expo，8px 与 .985 缩放；遮罩 180 / 120ms | 120 / 100ms 淡入淡出 |
| 移动抽屉 | 打开 / 关闭；说明来源 | 220 / 140ms Drawer，底部 18px | 纯淡入淡出 |
| 原生账户 / 通知 | 打开 / 关闭；触发器方向 | 180ms Expo，4px 与 .97；`@starting-style` + discrete content-visibility，旧浏览器即时关闭 | 不移动；原生离场可直接关闭 |
| 资料操作菜单 | 打开 / 关闭；触发器方向 | 180 / 100ms Expo，4px 与 .97，Radix origin；菜单行不 stagger | 淡入 / 淡出 |
| 拖入上传区 | 文件 drag enter / leave；反馈 | 180ms Expo，仅图标 3px；边框与底色即时切换 | 不移动 |
| 骨架 | 初始读取；状态 | 1800ms linear，伪元素 translateX | 静态骨架 |
| 正文 / 阶段 / 光标 | 首段 / 数据变化；状态 | 首次淡入 120ms Expo；阶段无位移；状态点与光标 opacity | 静态点与光标 |
| Toast | 异步结果；反馈 | Sonner 原有堆叠管理，260ms transform / 180ms opacity，Expo | 仅 opacity 过渡 |
| Three.js | 既有场景 | 完全保留现有暂停 / 静帧策略 | 原有静帧 |

### Choreograph 时间关系

| 元素 | 角色 | 起点 | 时长 | 关系 |
|---|---|---|---|---|
| 页面内容（普通页面） | Lead | 0 | 260ms | 单一物体，内部不二次进入 |
| 首页快捷项 1 | Lead | 0 | 200ms | 首页容器静止 |
| 首页快捷项 2 | Support | 40ms | 200ms | overlap，开始提问 |
| 首页快捷项 3 | Support | 70ms | 200ms | overlap，上传资料 |
| 首页快捷项 4 | Support | 95ms | 200ms | overlap，次要入口 |
| 首页标题、最近列表 | Static | — | — | 避免三维场景和多个区块同时抢注意力 |
| 菜单行、历史条目、来源列表 | Static | — | — | 高频阅读，不让正文随流式更新移动 |

### Review-animations 自审

| Before | After | Why |
|---|---|---|
| 固定页面进入使用 eager `motion` 与 y shorthand | CSS page-enter；无 Motion runtime import | 固定进入无需 JS，避免加载期主线程动画与额外包体 |
| 首页进入 320ms、auth 500ms、快捷卡 500ms | 页面 260ms、快捷卡 200ms；组内总时长 295ms | 满足 UI 预算，不堆叠父子进入 |
| 未门控 hover 位移 / 色彩 | 全部 hover 限精细指针媒体查询 | 避免触屏残留 hover |
| 边框、底色、阴影过渡 | 这些属性即时切换；连续动画仅 transform / opacity | 避免逐帧重绘 |
| reduced motion 只把时长设成极短 | 页面 / 弹层淡入，取消位移 / stagger / 循环 | 减少运动而不是快速播放原运动 |
| 键盘与指针共享动画 | 键盘即时；指针保留有限反馈 | 高频键盘路径不等动画 |
| 移动设置页指示器可能落到隐藏的第 5 项 | 移动设置页不显示该指示器 | 避免越界产生横向滚动 |

静态代码复审：**Approve（代码层面）**。定位指示器采用 transition，可在中途切换目标；菜单由 Radix Presence 管理短离场；原生浮层用 transition。没有额外的逐帧 React 状态、bounce、逐字 stagger 或布局属性插值。

**观感验收尚未完成**：需要在可启动 Chromium 的环境录制并以 2–5 倍慢速检查快捷卡、导航快速切换、弹层关闭途中重开、Sonner 堆叠与真实触屏。代码审查不能替代运行时逐帧检查。

## 生成素材

| 文件 | 规格 | 使用位置 |
|---|---|---|
| `public/archive-study.webp` | 720×480，4,226 bytes（约 4.13 KiB），sharp WebP quality 76 | 知识库首次空态、对话空态、工作流顶部。next/image，有显式尺寸、空 alt，默认 lazy。 |

使用 built-in image_gen，原始素材保留在生成目录；工程只包含压缩后的 WebP。原有 home-wave / login-ribbon 素材与 three.js 源文件未变。

完整提示词：

> Use case: stylized-concept. Asset type: decorative editorial illustration for a premium knowledge workspace empty state and workflow panel. A small sculptural archive made of three thin folded sheets of pearl white paper, one graphite thread flows between their precise edges, subtly suggesting knowledge connecting. Architectural studio still life, orthographic three-quarter view, generous completely white negative space around a single centered object, very light contact shadow, delicate etched graphite contours, quiet tactile paper detail. Strict monochrome white and graphite, no color, no glossy plastic, no stock-photo aesthetic, no text, no letters, no symbols, no watermark. Landscape 3:2 composition. Intended to look refined at 240px wide on a white UI.

## 技能与研究

- `ck-frontend-design`：以“精密编辑工具”为明确视觉方向，保留衬线品牌与石墨艺术，避免通用彩色后台卡片。
- `fdp-landing-pages`：主行动权重、空态唯一下一步、首页与 workflow 的层次和移动内容优先。
- `emil-design-eng` / `animate`：频率、反馈目的、强 ease-out、按压、触发点方向、精细指针与 reduced motion。
- `choreograph`：单层进入、短且非均匀的首页 stagger、高频内容静止、没有退出队列。
- `review-animations`：上表的代码复审；没有宣称浏览器观感通过。
- `imagegen`：一张可复用的品牌插画，通过 sharp 优化。
- `cloud-environment-runtime`：尝试浏览器验证并记录具体环境阻碍；相关云环境工具在本会话没有提供。
- frontend-design 提到的辅助 `ck:ui-ux-pro-max` 技能在可用目录中不存在；没有安装新技能或组件库。此次不是截图克隆，不调用其截图复制 / 子代理工作流。

研究来源：[Linear 的 UI 层级与导航对齐](https://linear.app/now/how-we-redesigned-the-linear-ui)、[Vercel Geist](https://vercel.com/geist/introduction)、[Perplexity 的原始来源与核验](https://www.perplexity.ai/help-center/en/articles/10352903-what-is-pro-search)。具体选择为本项目的设计判断，不是对这些产品当前动效时长的测量。

## 验证结果与后续验收

- `npm run lint`：通过。
- `npm run typecheck`：通过。
- `npm test`：5 个测试文件全部通过。
- CSS：PostCSS 全量解析通过；静态复审无 `transition: all`、布局属性过渡、`scale(0)`、eager Motion 引入或未门控 hover。
- `git diff --check`：通过。
- `npm run build`：Turbopack 进入 compile 后超过 8 分钟无输出，诊断仍为 `buildStage: compile`；已终止（130），没有运行成功。
- `npm run perf:budget`：未运行。未完成新构建时，旧的 route-bundle-stats 不能作为本次预算证据。`performance/budgets.json` 未修改。
- 截图脚本：读取并尝试运行用户提供的 `shoot-all.mjs`，仅将截图目的地改为可写 `/tmp/knowflow-polish`。Chromium 启动失败：`FATAL:content/browser/sandbox_host_linux.cc:41 ... shutdown: Operation not permitted (1)`。因此没有 after 截图，Playwright 视觉 / 响应式 / render-count 验收未完成。
- 已查看用户附图和磁盘上的其余桌面 before 图；没有启动新 dev server。

外部环境需要完成：生产 build → perf:budget → Playwright（重点 responsive / a11y / optimization / performance-regressions / home-scene / history-layout），然后生成全部页面的 390 / 768 / 1180 / 1440 截图。尤其要复核桌面来源侧栏的滚动高度、移动快捷区展开与创建焦点、长标题，以及原生浮层离场在浏览器中的兼容性。

## 依赖与边界

没有新增依赖；优先 CSS，七处固定进入不再导入 Motion。没有修改路由、API 契约、SSE 缓冲、预算、字体资源或 three.js 场景。未修改测试选择器 / 原有中文状态文案。`docs/reviews/2026-11-05-sol-blind-v6-docs.md` 未触碰。未 git commit / push。

## 修改文件

- [DESIGN.md](DESIGN.md)
- [VISUAL-POLISH.md](VISUAL-POLISH.md)
- [public/archive-study.webp](public/archive-study.webp)
- [src/app/error.tsx](src/app/error.tsx)
- [src/app/global-error.tsx](src/app/global-error.tsx)
- [src/app/globals.css](src/app/globals.css)
- [src/app/not-found.tsx](src/app/not-found.tsx)
- [src/components/auth/auth-view.module.css](src/components/auth/auth-view.module.css)
- [src/components/auth/auth-view.tsx](src/components/auth/auth-view.tsx)
- [src/components/chat/answer-panel.tsx](src/components/chat/answer-panel.tsx)
- [src/components/chat/chat-view.tsx](src/components/chat/chat-view.tsx)
- [src/components/chat/chat.module.css](src/components/chat/chat.module.css)
- [src/components/chat/composer.tsx](src/components/chat/composer.tsx)
- [src/components/chat/current-sources.tsx](src/components/chat/current-sources.tsx)
- [src/components/home/home-composer.tsx](src/components/home/home-composer.tsx)
- [src/components/home/home-view.module.css](src/components/home/home-view.module.css)
- [src/components/home/home-view.tsx](src/components/home/home-view.tsx)
- [src/components/home/shortcut-grid.tsx](src/components/home/shortcut-grid.tsx)
- [src/components/knowledge/base-detail-view.tsx](src/components/knowledge/base-detail-view.tsx)
- [src/components/knowledge/bases-view.tsx](src/components/knowledge/bases-view.tsx)
- [src/components/knowledge/knowledge.module.css](src/components/knowledge/knowledge.module.css)
- [src/components/knowledge/upload-zone.tsx](src/components/knowledge/upload-zone.tsx)
- [src/components/providers.tsx](src/components/providers.tsx)
- [src/components/settings/settings-view.tsx](src/components/settings/settings-view.tsx)
- [src/components/settings/settings.module.css](src/components/settings/settings.module.css)
- [src/components/settings/workflow-view.tsx](src/components/settings/workflow-view.tsx)
- [src/components/shell/app-shell.module.css](src/components/shell/app-shell.module.css)
- [src/components/shell/app-shell.tsx](src/components/shell/app-shell.tsx)
- [src/components/ui/button.module.css](src/components/ui/button.module.css)
- [src/components/ui/button.tsx](src/components/ui/button.tsx)
- [src/components/ui/confirm-dialog.tsx](src/components/ui/confirm-dialog.tsx)
- [src/components/ui/dialog.module.css](src/components/ui/dialog.module.css)
- [src/components/ui/empty-state.module.css](src/components/ui/empty-state.module.css)
- [src/components/ui/empty-state.tsx](src/components/ui/empty-state.tsx)
- [src/components/ui/page-fallback.tsx](src/components/ui/page-fallback.tsx)
- [src/components/ui/recovery-view.module.css](src/components/ui/recovery-view.module.css)
- [src/components/ui/recovery-view.tsx](src/components/ui/recovery-view.tsx)
- [src/components/ui/skeleton.module.css](src/components/ui/skeleton.module.css)
- [src/components/ui/status-badge.module.css](src/components/ui/status-badge.module.css)
- [src/components/workspace/workspace-provider.tsx](src/components/workspace/workspace-provider.tsx)
- [src/components/workspace/workspace.module.css](src/components/workspace/workspace.module.css)
