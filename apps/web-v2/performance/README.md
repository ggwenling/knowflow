# Web v2 性能验证与门禁

所有命令在 `apps/web-v2` 运行。使用 Node 24 和 `npm ci`；本轮未增加运行时依赖。保留同源代理、0.2.0 SSE 校验、账户隔离、原生链接、PDF Range 和现有 WebGL 效果。

## 常规门禁

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm run perf:budget
```

- `npm test` 使用 Node 自带测试器和类型擦除，覆盖 SSE 分块/状态机、取消/并发、正文限额、Unicode 定位、上传规则及指标脱敏。未更改应用 package 的模块类型；Node 在直接读取 TS 时可能给出 MODULE_TYPELESS_PACKAGE_JSON 提示，该提示属于测试加载，不是生产 bundle 的运行开销。
- `perf:budget` 读取当前固定 Next 版本的 `.next/diagnostics/route-bundle-stats.json`，逐路由累计唯一首载 JS 的 gzip level 9 大小。后续动态块、RSC、字体和图片不混入这个口径。
- `budgets.json` 保存审查前基线，门禁为基线 +5%。新增功能若需要超预算，应提交清晰的包体归因与评审；脚本不会自动抬高基线，报告结构缺失也不会静默跳过。
- CI 在 typecheck/lint 后运行单元测试，构建后运行包体门禁，并上传 `bundle.json`。浏览器新增用例包含在已有隔离全栈步骤中。

## 浏览器样本、Trace 与截图

先在独立终端启动生产服务：

```sh
npm run build
npm run start -- --hostname 127.0.0.1 --port 3300
```

再运行：

```sh
npm run perf:sample
```

- 默认目标 `http://127.0.0.1:3300`，可用 `KNOWFLOW_E2E_BASE_URL` 指定目标。
- **脚本会模拟 API，请只对开发/隔离验收服务运行。** 不登录真实账户，不写入真实资料。
- 默认 1440×1000、每路由 3 个新浏览器上下文、无网络/CPU节流；记录 Chromium/Node 版本和条件。设置 `PERF_CPU_RATE=4` 可以做 4× CPU 样本，`PERF_REPEATS` 可配置 1–10 次。
- 输出 `browser.json`、Chrome Performance 可导入的 `home-trace.json`、桌面截图及 390px 首页截图。另输出 `retention.json`：2 次预热后进行 60 次首页/工作流 SPA 往返，每 20 次采样，每次等待 WebGL 挂载和卸载，GC 后比较 JS 堆、DOM 和事件监听器；不把这些值当成 GPU 内存。结果目录 `performance-results/` 已被 Git 和 Docker 忽略。
- 记录资源解压/传输大小、布局偏移、LCP、长任务、JSHeapUsedSize 和 API 数量。资源记录可能包含合法的导航预取，不能和构建首载 gzip 混为一谈。
- CLS 按会话窗口计算；INP 需要真实交互与足够样本，脚本的加载样本不能证明线上 P75/INP 达标。
- 若比较前后加载时延，应保持相同数据、缓存、视口、节流、浏览器、CPU负载和等待条件；不要在 Docker 构建或其他重负载期间采样。

## 堆保留增长归因

在独立 localhost 生产实例中运行（只使用脚本内合成数据）：

```sh
npm run perf:retention
# 输出目录见命令最后的 Report 行；替换以下 <label>
npm run perf:heap -- performance-results/retention/<label>/0.heapsnapshot performance-results/retention/<label>/60.heapsnapshot performance-results/retention/<label>/180.heapsnapshot
```

- 默认 2 次预热、180 次首页/工作流往返，每 20 次显式 GC 后采样；保存 0/60/180 的 heap snapshots。等待条件沿用原 `perf:sample`：首页 canvas 可见，离开后 canvas 移除。快照会改变 GC/JIT 时机，不把该组当成无探针环境。
- `PERF_RETENTION_LABEL` 指定独立输出目录；`PERF_RETENTION_ROUNDS` 可设 60–1000 的 20 倍数（60 次时快照为 0/20/60）；不同组必须使用不同标签。
- `PERF_RETENTION_MODE=metrics` 不拍快照，保留 CDP Performance 指标；`minimal` 关闭该域并用 Runtime.getHeapUsage。两组仍使用 Playwright/CDP，不能等同真实用户无探针。
- 固定 Chromium/Node 版本、1440×1000、CPU rate 1、本机无节流、相同 fixture；Playwright 路由拦截会禁用 HTTP 缓存。报告包含系统、构建 ID、branch/HEAD、src 与配置/锁文件内容清单和哈希；该应用哈希不包括 public、构建输出或所有 Node 依赖，不能替代完整发行制品校验。采样期间不要修改源码或并行运行构建/压测。
- `perf:heap` 用 V8 node/edge 元数据计算对象数量、同会话存活 ID、强引用最短保留路径与 immediate dominator。算法排除 weak edge，包含 internal/shortcut edge；结果为诊断图，不能冒充 Chrome 的 ephemeron/native retained-size 口径，也不能与 JSHeapUsedSize 直接相加。算法有循环/菱形/弱引用及独立可达性 oracle 回归。
- 结果保留在已忽略的 `performance-results/`。快照包含合成页面的整个堆；禁止用于真实账号，禁止把快照/Trace 或其中内容复制到交接或提交中。持久报告只保留统计、必要对象类型和脱敏保留链结论。

## 内存与交付对比

```sh
npm run perf:memory
npm run perf:containers
```

- `perf:memory` 对旧/新上传缓冲和文本摘录算法各运行 3 个独立进程。上传为 8 MiB、64 KiB 分块；文本为 750000 码点，比较相同摘录。记录采样 RSS、堆内存、ArrayBuffer 峰值。
- 这是带显式 GC 的压力实验，不是线上延迟基准。RSS 受分配器和平台影响，resizable buffer 的统计也有平台差异。必须分别报告各指标，不能把 ArrayBuffer 下降等同于 RSS 下降。
- `perf:containers` 需要 Docker，构建同一工作树源代码的两种交付：`scripts/performance/Dockerfile.baseline` 使用原全量 production node_modules 打包，生产 `Dockerfile` 使用 standalone。基线仅移除 standalone 构建选项，不回退业务代码。
- 脚本创建独立、仅绑定 localhost 随机端口的容器；20 次登录页面 GET 预热后采集实际 next-server 进程的 `/proc` VmRSS，取 3 次中位数，同时比较 image size。没有后端，不会连接或修改现有 KnowFlow 栈。
- 容器总是在 finally 中清理；两张本地 benchmark 镜像保留以方便复查。已构建相同源代码时可运行 `npm run perf:containers -- --skip-build`。

## 全栈与缺陷回归

```sh
npm run e2e
```

该命令使用根目录 `scripts/e2e-web.mjs --v2`，创建随机 Compose 项目、端口和临时卷，执行当前 E2E、SSE 捕获校验和旧版 Web 回退，结束后清理。它与本地 mock 浏览器样本是两个不同的证据层。

核心新增断言：

- 上传入口可用键盘；不支持格式不发 POST；上传接受即释放控件，索引终态错误可见。
- 菜单方向键/Esc/回焦；历史搜索能继续分页；侧栏加载更多确实扩大可见范围。
- 输入 10 字符不刷新外壳、历史和资料；流式 delta 仅更新答案域。探针排除复用 fiber 遗留 flags，不把标记次数冒充 CPU 节省。
- 慢历史不阻塞设置；首批知识库无需等待后续页；已加载文档在终态刷新后保持完整。
- 轮询请求并发 ≤4，退出后无新旧作用域轮询；隐藏页不启动队列中的 HTTP；仍保留代次保护。
- PDF 已知版本直接进入原生 iframe，应用不额外 fetch 文件做探测；原生查看器自身的多次 Range 读取是允许的。
- 500 个知识库、1000 个文档仍能分页、聚焦末尾控件；动态列表链接不引发投机详情预取。
- URL 外部变化不会被旧 debounce 覆盖；指标不携带用户、资料、问题正文或查询参数。

## 性能事件与可选远程接收

`PerformanceReporter` 使用 Next 的 `useReportWebVitals`，通过 `knowflow-performance` 自定义事件提供数值型观测；请求、问答和索引也通过同一通道报告。事件结构：

```json
{"name":"question_duration_ms","value":1234,"unit":"ms","route":"/conversations/[questionId]","outcome":"ok"}
```

- 支持 CWV（CLS/FCP/INP/LCP/TTFB）、api_request、api_headers_ms、question_first_delta_ms、question_duration_ms、upload_accept_ms、index_wait_ms。
- `api_headers_ms` 只表示收到响应头的时间，不代表下载全文的时间；`index_wait_ms` 只用于本视图中刚接受的上传任务，不冒充后端完整索引耗时。
- route 为固定路由模板，移除 ID 和 query；不记录邮箱、问题、答案、来源文本、Cookie 或凭据。
- 默认只在本机事件通道采集，不外发。对接已有同源指标接收服务时，在 **构建时** 配置 `NEXT_PUBLIC_PERFORMANCE_ENDPOINT=/你的同源指标端点`。Docker 对应 `--build-arg NEXT_PUBLIC_PERFORMANCE_ENDPOINT=/你的同源指标端点`。本次没有新增后端存储/可视化平台。
- 可选远程通道只发送白名单字段，按 20 条或页面隐藏/pagehide 批量上报。上线前需由部署侧确认接收端、留存与采样策略；不能在未配置接收端时宣称已经取得线上 RUM 数据。

## 可复查记录

实施记录与本轮数值见仓库根 `docs/reviews/2026-11-08-web-v2-optimization-progress.md`；原始问题见相邻审查报告。本地 `performance-results/` 为可再生证据，不作为已实现线上收益的证明。
