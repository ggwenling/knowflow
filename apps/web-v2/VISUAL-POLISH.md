# KnowFlow web-v2 视觉精修：Round 2

本轮依据操作员提供的真实 Chromium `r1-*.png`，处理第二轮艺术指导反馈；保留 PR #17 场景、API、SSE、键盘路径与外壳的性能边界。未提交或推送。

## 验收上下文

- **Round 1 已由操作员在沙箱外验证**：commit `bc14238`；build 通过；perf:budget 通过，各路由首载 JS 较预算基线降低约 9%–21%；Playwright 51/53 通过，两个依赖真实 Docker 的失败在基线上同样存在。这是操作员提供的 R1 结果，不代表 R2 已重新运行。
- **Round 2 本地验证**：lint、typecheck、npm test 全部通过（5 个测试文件）；14 个 CSS 文件解析、60 条 hover 门控、22 条过渡属性与 git diff --check 检查通过。
- 按本轮指示，**没有尝试启动 Chromium、截图脚本或开发服务器**；没有重复启动已知会停滞的沙箱生产构建。R2 的运行时截图、build / perf / e2e 需操作员外部复核。
- 已查看附带的桌面 / 移动截图，并额外查看设置、工作流、知识库详情的移动 R1 图。390px 的修改依据截图和实际 CSS/JSX 推导，不宣称已生成 R2 截图。

## 对应十项反馈

| 项 | 修改 |
|---|---|
| 1. 眉题与元数据 | 眉题使用 DM Sans 11px / 600 / .12em，页头有短引导线；页脚 12px / 600，无衬线。时间、大小、状态、序号、kbd 等元数据下限 12px。`--ink-3` 收深至 #626C77。 |
| 2. 页头带 | 对话、知识库列表 / 详情、设置、工作流统一 `workspace-header`：140px 桌面基准带、主标题 / 描述 / 行动底部对齐、24px 下留白与发丝线。移动自适应换行。首页保留自身英雄版式。内容区增加极淡宽幅纸面光。 |
| 3. 首页 | 创建知识库采用有意的墨色主卡、浅色文字；其余白色卡。四卡都有图标瓷片与 hover 箭头，移动紧凑横排。最近列表扩大行留白和图标、元数据升至 12px，并添加整行 hover。 |
| 4. 知识库列表 | 两列档案封面卡，轻量 SVG 石墨纹理、真实名称 / 更新时间、“打开”入口。增加虚线创建卡，复用展开 / 聚焦创建逻辑，独立 aria-label 避免与页头按钮冲突。首 4 张卡短错开，其余长列表静止。 |
| 5. 知识库详情 | 增加真实的全部 / 已就绪 / 处理中 / 失败计数带，复用筛选口径；未加载完整时明确标注“已加载”。空闲上传区静止，拖入时只有虚线伪元素 opacity 呼吸和图标 3px 反馈。 |
| 6. 对话与输入框 | 页头与内容使用受视口约束的 flex 布局，按实际页头高度分配阅读空间。答案底部保留 44–48px，输入框上沿有 20–24px 静态渐隐。输入框独占布局空间；移动单行起步、发送按钮同排、隐藏 kbd，空输入约 58px。自动增长仅在 Composer 内直接测量 DOM，输入与窗口尺寸变化时更新，不增加 React 状态。 |
| 7. 错误页 | 完全移除灰色径向光云和浮卡边框 / 阴影，改为白底、品牌、发丝线与编辑式排版；全局错误依旧有 CSS 静态回退。 |
| 8. 登录 / 注册 | 保留主体排版与 ribbon；标题 / 说明 200ms、表单 / 链接 180ms 延迟 40ms，重叠进入；外层静止。沿用 2px 焦点环，修正页脚字体。 |
| 9. 客户端导航 | 新增 `(workspace)/template.tsx`，只重建路由内容。AppShell、StoreProvider、WorkspaceProvider 保留在 layout；不新增导航状态 / 路由 effect。路由 220ms 淡入 + 6px，无退出等待。知识库列表是页头 / 卡片并列进入，避免父子二次动画。 |
| 10. 移动 | 保留顶部导航，压缩输入框和知识库封面；文档状态 / 按钮自然换行；工作流插画移到能力区并缩至 112px，避免阻挡首屏步骤。卡片链接焦点环不被封面裁切；输入框 resize 监听有清理。 |

## 对比度与设计令牌

完整设计规范：[DESIGN.md](DESIGN.md)。本轮新增 `--dur-page: 220ms`，`--type-micro` 统一 12px；保留原有颜色语义、阴影、圆角和字体文件。

`#626C77` 的静态 sRGB 对比度计算：白底 **5.34:1**、`#F7F8F9` **5.02:1**、`#EEF0F2` **4.68:1**、`#EDF3F7` **4.77:1**，均超过普通文本 AA 4.5:1。装饰纹理不承载信息；墨色主卡的说明使用浅色文字。

## Motion / Choreograph 时间表

Expo = `cubic-bezier(.23,1,.32,1)`。键盘路径沿用 DOM modality（包括带修饰键的导航），立即完成；不新增 shell 订阅或状态。进入只用 backwards 填充延迟前的初态，完成后释放动画，避免持有卡片 transform 或多余合成状态。

| 元素 | 角色与关系 | 时间 / 属性 | Reduced motion |
|---|---|---|---|
| 普通路由内容 | 一个整体，内部静止 | 220ms Expo，opacity + 6px rise | 120ms 纯淡入 |
| 知识库页头 | Lead，模板容器静止 | 220ms Expo | 120ms 淡入 |
| 首 4 张知识库卡 | Support，并列 overlap | 180ms Expo；0/40/70/95ms 起始；总计 275ms | 同时淡入，无位移 |
| 第 5 张及以后的卡 | Static | 无进入动画，保留 content-visibility | 静止 |
| 首页快捷卡 | 随路由整体进入，取消旧子层 stagger | hover 最多 3px 箭头 / 2px 卡片 | 无位移 |
| Auth 标题 / 说明 | Lead，品牌静止 | 200ms Expo / 6px | 同时淡入 |
| Auth 表单 / 链接 | Support，overlap | 延迟 40ms，180ms Expo / 4px | 同时淡入 |
| 上传虚线 | State indication，仅拖入期间 | 800ms 自定义 in-out，opacity .25–.8 循环 | 固定 .7，无循环 |
| Composer 高度 | 功能性排版 | 即时 DOM 高度调整，不做 height 过渡 | 相同 |
| 渐隐、纸面光、封面 | Decoration | 静态，无动画 | 相同 |

导航 / 筛选底板、Dialog / Drawer、原生浮层、Sonner 的 R1 动效继续保留。所有 hover 效果限精细指针；连续过渡仅 transform / opacity。

### Review-animations 自审

| Before | After | Why |
|---|---|---|
| 页面组件各自进入，客户端复用时不保证重放 | Next template 提供稳定的导航进入边界 | 语义明确，不向外壳添加状态 |
| 父容器进入再叠加卡片进入 | 知识库模板容器静止，页头 / 卡片是并列节拍 | 一个容器一层进入 |
| 长列表可能有数百个动画 | 只动画前 4 张 | 限制合成与持续时间 |
| 输入框硬切阅读区、移动过高 | 布局独占空间、软边界、底部留白、移动同排 | 首先解决布局，不用动效掩盖裁切 |
| 输入高度可被误做动画 | 不做 height 过渡，不使用 React 高度状态 | 只处理必要排版，不让键入引发整页重渲染 |

**静态代码复审：Approve；运行时观感待外部截图。** 仍需在外部检查快速路由切换、滚动到最后一张引用、长中文问题增长至上限、窗口缩放，以及 390/768/1180/1440 的实际布局。没有宣称 R2 的 render-count / Playwright 已运行。

## 素材

| 文件 | 规格与用途 | 生成方式 / 提示词 |
|---|---|---|
| `public/knowledge-contours.svg` | **新增**，800×200，**1,407 bytes**；知识库封面，纯装饰 CSS 背景 | 原生 SVG，28 条三次贝塞尔石墨轮廓；没有 image_gen 调用或图片提示词 |
| `public/archive-study.webp` | R1 保留，720×480、4,226 bytes；知识库 / 对话空态、工作流能力区 | R1 built-in image_gen，sharp WebP quality 76；原提示词如下 |

本轮没有新增 AI 生成图片。既有 `home-wave.webp`、`login-ribbon.webp` 和 两处 Three.js 场景源文件未修改。

> Use case: stylized-concept. Asset type: decorative editorial illustration for a premium knowledge workspace empty state and workflow panel. A small sculptural archive made of three thin folded sheets of pearl white paper, one graphite thread flows between their precise edges, subtly suggesting knowledge connecting. Architectural studio still life, orthographic three-quarter view, generous completely white negative space around a single centered object, very light contact shadow, delicate etched graphite contours, quiet tactile paper detail. Strict monochrome white and graphite, no color, no glossy plastic, no stock-photo aesthetic, no text, no letters, no symbols, no watermark. Landscape 3:2 composition. Intended to look refined at 240px wide on a white UI.

## 技能、依赖与性能边界

- 使用 `ck-frontend-design`：以档案封面、明确墨色主行动与编辑式错误页加强方向；`fdp-landing-pages`：行动权重、移动内容优先与空态。
- 使用 `emil-design-eng` / `animate` / `choreograph` / `review-animations`：限频率、单层进入、短重叠节拍、键盘即时、reduced motion 与精细指针门控，并做上述自审。
- **没有新增依赖**、字体、Motion import、业务 API 请求或全局状态。新图形只增加 1.4KB SVG；template 是服务器组件，不引入新的动效运行时。尚未重新测量 R2 包体。
- 没有更改路由、API 契约、SSE 缓冲、预算文件或测试选择器。`docs/reviews/2026-11-05-sol-blind-v6-docs.md` 与已有 `eval-out/` 未触碰。
- 未 commit / push。本轮验证结果不能替代操作员的外部 build / perf / e2e。

## 本轮修改文件

- [DESIGN.md](DESIGN.md)
- [VISUAL-POLISH.md](VISUAL-POLISH.md)
- [public/knowledge-contours.svg](public/knowledge-contours.svg)
- [src/app/(workspace)/template.tsx](src/app/(workspace)/template.tsx)
- [src/app/globals.css](src/app/globals.css)
- [src/components/auth/auth-view.module.css](src/components/auth/auth-view.module.css)
- [src/components/auth/auth-view.tsx](src/components/auth/auth-view.tsx)
- [src/components/chat/chat-view.tsx](src/components/chat/chat-view.tsx)
- [src/components/chat/chat.module.css](src/components/chat/chat.module.css)
- [src/components/chat/composer.tsx](src/components/chat/composer.tsx)
- [src/components/home/home-view.module.css](src/components/home/home-view.module.css)
- [src/components/home/shortcut-grid.tsx](src/components/home/shortcut-grid.tsx)
- [src/components/knowledge/base-detail-view.tsx](src/components/knowledge/base-detail-view.tsx)
- [src/components/knowledge/bases-view.tsx](src/components/knowledge/bases-view.tsx)
- [src/components/knowledge/knowledge.module.css](src/components/knowledge/knowledge.module.css)
- [src/components/providers.tsx](src/components/providers.tsx)
- [src/components/settings/settings-view.tsx](src/components/settings/settings-view.tsx)
- [src/components/settings/settings.module.css](src/components/settings/settings.module.css)
- [src/components/settings/workflow-view.tsx](src/components/settings/workflow-view.tsx)
- [src/components/shell/app-shell.module.css](src/components/shell/app-shell.module.css)
- [src/components/ui/recovery-view.module.css](src/components/ui/recovery-view.module.css)
- [src/components/ui/status-badge.module.css](src/components/ui/status-badge.module.css)
- [src/components/workspace/workspace.module.css](src/components/workspace/workspace.module.css)
