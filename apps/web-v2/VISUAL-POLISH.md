# KnowFlow web-v2 视觉精修：Round 3

本轮基于 `23301a2`（PR #18）与产品负责人实际浏览器反馈。实现焦点边界、侧栏收起、首页及设置重排；不修改数据契约、Three.js 场景或既有页面路由。未提交或推送。

## 五项反馈与结果

| 项目 | 实现 |
|---|---|
| 1. 输入框套输入框 | 首页问题、对话 composer、知识库 / 历史搜索、侧栏内联创建、知识库切换均标记 `data-composite-field`。内层 input / textarea / select 在普通与 focus / focus-visible 下统一 border 0、background transparent、shadow none、outline none；外框 focus-within 承载 2px #506E83 outline，偏移 3px。独立的登录输入只有一层可见边界，保留原焦点环。 |
| 2. ↵ 芯片 | 首页提示节点与样式已移除，保留真实发送箭头。对话辅助文字仍可用，kbd 取消边框、底色、圆角及阴影，呈现为安静的等宽文本；移动仍隐藏。 |
| 3. 侧栏收起 | >760px 展开宽 248px（≤1180px 226px）/ 收起 64px；有带 aria-expanded / aria-controls 的 toggle 与 ⌘/Ctrl+B，忽略按键 repeat / IME。收起只保留标记、图标导航和底部账户菜单；库 / 历史 / 输入隐藏。导航保留 accessible name，tooltip 支持 hover、focus、悬停内容、Esc 关闭；账户有邮箱说明。移动保留四项顶部导航与右上账户菜单，无 toggle。 |
| 4. 首页 | 更紧的英雄区、最长 800px 的单一提问表面，知识库选择在内置底栏；模型说明在框下作为辅助文案。快捷卡同主内容网格对齐，最近两个面板等宽、行高同为 76px，空态也使用相同高度基准。选择器独立 memo，避免每次输入重复渲染整棵 options 列表。 |
| 5. 设置 | 桌面左侧 156px 分区索引 + 右侧单列卡片，≤980px 索引变横向分段行。原生锚点 / URL hash 决定 aria-current，独立 SettingsNav 订阅，不重渲染事实卡。每卡有说明、label/value 网格；退出登录在单独的“危险操作”区，保留原文案 / 事实 / 动作。 |

## 偏好持久化、首屏与渲染边界

- localStorage 键：`knowflow.sidebar.collapsed`，值为 true / false 字符串。
- 根布局 head 的短固定脚本在绘制前恢复 html `data-sidebar-collapsed`。CSS 根据该属性直接决定轨道宽度和图标可见性，页面不先显示展开版再等待 effect。
- html 上的 suppressHydrationWarning 仅用于这个脚本写入的额外属性；子树不抑制 hydration 警告。SidebarToggle 使用稳定 serverSnapshot 与 useSyncExternalStore，服务端 / 水合标记一致。
- 只有 toggle 订阅偏好；AppShell、HomeView、StoreProvider、WorkspaceProvider 没有新增折叠 React 状态。主内容通过 CSS 获得释放的宽度。
- 同页通知与 storage 跨页事件同步状态；存储不可用时当前标签页仍能切换。创建知识库的入口先展开桌面轨道、再聚焦原输入；移动创建不改变桌面偏好。
- 对话输入增加只读宽度变化的 ResizeObserver：侧栏改变可用宽度时重新计算高度。宽度未变则跳过，避免高度反馈循环；无高度 React 状态，卸载清理 observer / listener。
- Modality 仅在键盘 / 指针类别改变时写 DOM 属性，键盘触发同时取消延迟，不在每个按键重复写全局属性。

## 纸面色与版式

源码全局仍为 #FFF / #F7F8F9 / #EEF0F2，没有增加全局米黄色或滤镜。内容纸面光统一由原有 bg-subtle 混合，避免多处硬编码色偏；R2 档案封面局部微暖灰保留。负责人浏览器的原始图片本轮没有提供，无法验证显示环境差异，因此没有再给整个产品叠加暖色。

首页保留 DM Serif Display 与所有原有场景选择器。Three.js 已有 ResizeObserver 会跟随真实 form / label 边界，场景源文件与 fallback 资产未改。

设置页继续展示全部既有邮箱、空间、知识库数量、模型模式、单轮问答、资料范围与未开放说明，没有增加虚假设置或开关。

## 动效与自审

| 元素 | 触发 / 时间 | Reduced motion / 键盘 |
|---|---|---|
| 侧栏网格 | 指针 toggle；220ms Expo `grid-template-columns`，可中断并重排主内容 | 立即完成 |
| Tooltip | hover 160ms 延迟、opacity 120ms；focus 立即；Esc 隐藏并保留焦点 | 键盘无延迟 / 动画 |
| 账户浮层 | 桌面从底部账户向上 / 向右展开；移动保持右上触发方向；沿用原 180ms opacity / transform | 纯淡入或即时 |
| 首页新发送按钮 | 按压 1px、120ms Expo | 不移动 |
| 原有路由 / 页头 / 列表 / 对话框 | 保留 R2 的时间与 reduced motion 规则 | 保持已有策略 |

### Review-animations findings

| Before | After | Why |
|---|---|---|
| 内外焦点边界叠加 | 只有外框的 2px focus-within，内层明确清空 | 保持同一焦点的可见性，消除嵌套输入错觉 |
| 纯 transform 收起仍占据原宽度 | 用户明确允许的 220ms grid-template-columns 过渡 | 主内容需要真实重排；这是本轮唯一布局属性过渡例外 |
| 收起后文字 / 控件可能继续进入键盘路径 | 仅桌面通过 CSS 隐藏整块区域，图标保留 aria-label / tooltip | 不留下看不见的 Tab 目标 |
| 每次输入重绘知识库 options | HomeScope memo + 稳定上下文 | 延续输入草稿的局部渲染边界 |
| 轨道切换时长问题高度过期 | Composer 内观察宽度、直接重测，不做 height 动画 | 排版正确，且不增加整页状态 |

静态复审通过，侧栏宽度例外来自本轮用户明确授权。未运行浏览器，不能宣称动效观感、CLS 或 render-count 的运行时结果已通过。

## 测试与验证

新增 [sidebar-and-composer.spec.ts](e2e/sidebar-and-composer.spec.ts)，共 **11 个测试实例**：

- 1440 / 900px 收起为 64px，主内容变宽，tooltip hover / focus / hoverable / Esc，reload 持久化，无 hydration 报错，两种快捷键。
- 带已有偏好的首屏属性、账户菜单 / 邮箱、创建时自动展开并聚焦。
- 390px 忽略桌面轨道偏好，不展示 toggle，保留导航 / 账户菜单且无横向溢出。
- 390 / 1440 首页与对话的内层 border / outline / shadow 清空，外框 2px 焦点；首页无 ↵ / kbd，桌面对话 kbd 扁平化。
- render probe 验证 toggle 不使 shell / home / composer 重渲染；创建链接仍聚焦。
- reduced motion 下会话三栏保留、轨道过渡为 0s，页面无横向溢出。
- 知识库搜索和两类知识库选择器焦点在外框。
- 390 / 1440 设置原生锚点当前状态、保留问答事实、独立危险区与退出动作。

更新 `a11y.spec.ts` 和 `agent-acceptance.spec.ts`：原来断言 textarea / search 本身 outline，现在验证对应外框的 2px outline；新测试另验内层 outline none。这是同一键盘焦点的等价可见指示，未放宽焦点可见要求。

本地结果：

- `npm run lint`：通过。
- `npm run typecheck`：通过，包含新 Playwright 测试的类型检查。
- `npm test`：5 个测试文件全部通过。
- `playwright test e2e/sidebar-and-composer.spec.ts --list`：成功发现 11 个测试；此命令没有启动 Chromium。
- 14 个 CSS 文件解析、64 条 hover 门控、27 条过渡属性审查与 git diff --check：通过。唯一布局过渡是本轮授权的 shell 网格宽度。
- **没有运行 Chromium、截图脚本、build、perf:budget 或浏览器测试**，由操作员在沙箱外验证；测试发现不等于测试通过。

## 文件、依赖与素材

没有新增依赖、字体或图片。沿用 R1 的 `archive-study.webp` 和 R2 的 `knowledge-contours.svg`。预算文件、Three.js 源文件、`docs/reviews/2026-11-05-sol-blind-v6-docs.md` 和 `eval-out/` 未触碰；未 commit / push。

采用现有 frontend-design / Emil / animate / choreograph / review-animations 技能原则：一个控件一条焦点边界、局部状态、可中断的明确反馈、键盘即时、hover 门控与减少动态效果。

本轮修改文件：

- [DESIGN.md](DESIGN.md)
- [VISUAL-POLISH.md](VISUAL-POLISH.md)
- [e2e/a11y.spec.ts](e2e/a11y.spec.ts)
- [e2e/agent-acceptance.spec.ts](e2e/agent-acceptance.spec.ts)
- [e2e/sidebar-and-composer.spec.ts](e2e/sidebar-and-composer.spec.ts)
- [src/app/globals.css](src/app/globals.css)
- [src/app/layout.tsx](src/app/layout.tsx)
- [src/components/chat/chat-view.tsx](src/components/chat/chat-view.tsx)
- [src/components/chat/chat.module.css](src/components/chat/chat.module.css)
- [src/components/chat/composer.tsx](src/components/chat/composer.tsx)
- [src/components/chat/history-rail.tsx](src/components/chat/history-rail.tsx)
- [src/components/home/home-composer.tsx](src/components/home/home-composer.tsx)
- [src/components/home/home-view.module.css](src/components/home/home-view.module.css)
- [src/components/home/home-view.tsx](src/components/home/home-view.tsx)
- [src/components/knowledge/bases-view.tsx](src/components/knowledge/bases-view.tsx)
- [src/components/knowledge/knowledge.module.css](src/components/knowledge/knowledge.module.css)
- [src/components/providers.tsx](src/components/providers.tsx)
- [src/components/settings/settings-nav.tsx](src/components/settings/settings-nav.tsx)
- [src/components/settings/settings-view.tsx](src/components/settings/settings-view.tsx)
- [src/components/settings/settings.module.css](src/components/settings/settings.module.css)
- [src/components/shell/app-shell.module.css](src/components/shell/app-shell.module.css)
- [src/components/shell/app-shell.tsx](src/components/shell/app-shell.tsx)
- [src/components/shell/sidebar-toggle.tsx](src/components/shell/sidebar-toggle.tsx)
- [src/lib/sidebar-preference.ts](src/lib/sidebar-preference.ts)

## 既有 R1 素材提示词（存档，R3 未重新生成）

> Use case: stylized-concept. Asset type: decorative editorial illustration for a premium knowledge workspace empty state and workflow panel. A small sculptural archive made of three thin folded sheets of pearl white paper, one graphite thread flows between their precise edges, subtly suggesting knowledge connecting. Architectural studio still life, orthographic three-quarter view, generous completely white negative space around a single centered object, very light contact shadow, delicate etched graphite contours, quiet tactile paper detail. Strict monochrome white and graphite, no color, no glossy plastic, no stock-photo aesthetic, no text, no letters, no symbols, no watermark. Landscape 3:2 composition. Intended to look refined at 240px wide on a white UI.

## Round C · Performance（2026-11-11）

保留 Round A+B 的纸墨排版、素材、交互与选择器；本轮不增加依赖，不修改预算，不执行 build / Chromium / commit / push。

- **共享 JS 回退**：现有 `.next` 的 client-reference manifest 显示，Round A 给 RecoveryView 增加的 `next/image` 进入普通 error、global-error 与共享 RSC 图。`3kpe7muluw9xa` / `1z9r3yub1tsbi` 两个约 17 KB raw 的 chunk 含重复 image runtime，`3pmmz5ib8sxjz` 与路由 chunk 也含 image 模块。这解释了各路由共同增长；字体为 CSS / WOFF2，BrandSeal 为小型纯 SVG，并非该 JS 增长的主要来源。atlas 素材改用统一的原生 StaticArt：保留 width / height、空 alt 与 lazy；auth art 独有 eager / fetchPriority=high。原图 1.3–3.8 KB（auth 26 KB），已按展示尺寸的约 1–2 倍输出，无需再经过 image client / optimizer。
- **进一步减少首载 JS**：cn 的全部调用只组合 CSS module 类，移除不需要的 tailwind-merge 执行路径。ConfirmDialog、SourceDialog 与移动资料 / 历史抽屉首次打开才加载；打开后保留组件，让关闭动效和焦点归还继续工作。Markdown、资料操作菜单维持已有 lazy 路径。预计共享 JS 减少约 20–30 KB gzip，涉及弹层的页面另有收益；需新生产构建确认，不能用旧 `.next` 宣称新预算已通过。
- **WebGL 离开首屏关键路径**：先绘制原 WebP fallback，等待 load、host 可见、页面前台及至少 1.8 秒绘制窗口，再通过 requestIdleCallback（1.2 秒 timeout；不支持时用 timer）挂载动态场景。两个场景均用具名 Three.js import，无 addons；compileAsync 完成并绘制首帧后以 260ms opacity 交叉淡入。保留原几何、shader、DPR 上限、暂停控制、离屏 / 后台暂停、reduced-motion 静帧及 context loss 回退 / 恢复；异步编译在卸载或 context 变化后不再启动渲染。暂停会立即完成交叉淡入，保证静帧稳定。预期减少 LCP 前下载、JS 求值与 shader 阻塞。
- **CLS**：移除依赖 `:has(canvas)` 改变 wave top / height 的规则。外层一次预留静态图与场景的联合范围，内层 canvas 始终为原 400 / 340 / 216px 高度；fallback 单独定位并保持原尺寸 / 位置。挂载、编译、淡入、context loss 不再改变 host 的几何。移动 `.home-art` 固定为 216px，原 168px fallback 在独立纸面层中；home-scene e2e 同时验证 mount / loss / restore 前后边界一致。
- **字体**：DM Serif Display 继续用既有 latin-only 文件并 preload / swap；DM Sans 两个正文权重按使用加载，显式启用 Arial metric fallback。中文标题子集改 optional，避免迟到的字形替换引起位移；不 preload，不把 next/font 的拉丁 Arial / Times 指标套用到系统中文衬线。既有构建只有四份 WOFF2（Sans 400/700、Serif Latin 400、Noto 中文子集），没有重复 fontsource CSS 下载。
- **CSS / 缓存**：按相同 selector + 相同 at-rule 上下文删除 93 个被后续覆盖的声明；删除无引用的旧规则与 keyframes，保留媒体条件和级联顺序。Tailwind 保留 Preflight，关闭未使用的 utility 扫描生成；场景样式只随 DeferredVisual 引入。next.config.ts 为 atlas / wave / ribbon / contours / grain 提供一年 immutable cache；替换素材内容时须更名，API proxy 的 no-store 未改。

验证：`npm run lint`、`npm run typecheck`、`npm test` 通过；CSS PostCSS / Tailwind 编译与静态资源 header 路径解析通过，API 路径未被缓存规则匹配。更新 home-scene 的固定 box / context loss 验证。浏览器 e2e、a11y、CLS、Lighthouse、perf:budget 待操作员在沙箱外用新生产构建重测；既有 `.next` 仅用于只读归因，没有运行 npm run build。
