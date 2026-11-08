# Web v2 另会话改动独立审阅

日期：2026-11-08。结论：**REQUEST CHANGES：1 项 P1、1 项 P2，均已用当前生产构建的浏览器场景复现。**

本轮主要核查接收会话新增的知识库分页修复、采样/堆分析脚本、对应测试与收口报告，没有将此前整个六阶段工作树误当作该会话新增。未修改业务代码、测试或交接状态；只新增本审阅记录。复现使用合成 API，不连接真实知识库，不对真实数据执行删除或上传。

## 审阅目标与验证

- 分支/HEAD：`local@e216fe3f4ce3f24973b7654bb723db667a3b74ae`；实际改动仍未提交。
- 使用现有构建 `8VNj8mM7O53LxWKdePB0B`，没有重新 build 覆盖对方的构建标识。
- 独立重算当前 88 个 src/配置/锁文件清单 SHA：`33ef8ffc96b330ed01fd04109a5bbb8b86d4c4dd3c809e9df0dc3349295d83c7`，与接收会话报告一致。
- 独立 `127.0.0.1:3311` 生产服务，Playwright Chromium，受控可变 API 数据；两个业务反例均成功复现。
- 本轮实际执行：typecheck、lint、28 项单元测试、新增的 `base-pagination-mutations.spec.ts` 均通过；这没有覆盖下面两个反例。
- Docker Linux daemon 当前仍不可达，未启动 Docker Desktop、未重跑真实隔离全栈/SSE/回退，未沿用历史结果作为本轮通过。

## P1：末页选择兜底覆盖合法深链，详情页展示及上传落到其他库

位置：`apps/web-v2/src/hooks/use-knowledge-bases.ts:86–87`。

关联：`src/components/workspace/workspace-provider.tsx:40` 使用全局 selectedBase 创建文档作用域；`src/components/knowledge/base-detail-view.tsx:53、72、74–76` 只在路由变化时设置选择，但标题可以继续使用已成功取得的远端详情。

### 可复现顺序

1. 知识库第一页查询获得旧列表中的 50 项，后续分页挂起。
2. 新库 B 在第一页查询之后创建（例如另一个标签页），当前页面通过合法深链 `/knowledge-bases/fresh-base` 打开 B。B 的详情 GET 成功，并显示 B 的文档。
3. 后续 OFFSET 分页在新插入后的列表上查询，只返回旧列表尾部，并不包含排在最前的新库 B。这不是 B 不存在或无权限的证明。
4. 新增兜底只检查 `visible.some(id === selectedRef.current)`，未找到 B 就把全局 selectedBase 改为旧库 A。
5. 路由与标题依然为 B，文档作用域却切到 A。详情组件的 effect 依赖未改变，不会重新纠正选择。

### 实测

```text
URL: /knowledge-bases/fresh-base
h1: NEW BASE DETAIL
文档请求: fresh-base → old-1
页面文档: WRONG-BASE-DOC.txt（旧库 A 的资料）
B 原有文档: 不再显示
在该页面选择新文件后，POST: /api/v1/knowledge-bases/old-1/documents
```

这不仅是标题显示不一致：用户在 B 页面上传的文件会发往 A，更新/删除也存在操作错库的风险。这里只证明同一账户内的库作用域错配，没有证据表明跨账户越权。

### 建议修复与验收

- 不要仅用一次非一致性 OFFSET 分页的缺席判断显式选择已失效；对合法深链应保留经详情 GET 验证的库选择，或通过单独资源请求确认失效后再兜底。
- 详情页文档读取与修改应绑定路由 baseId；即使全局选择发生异步变化，也不能把另一库的数据和操作渲染到当前库标题下。至少在作用域不一致时阻止错误展示和写操作。
- 新增回归：第一页后新建库、合法深链详情成功、后续页不含该库，验证标题/文档请求/上传 POST 始终属于同一个 baseId。

## P2：删除过滤没有处理 OFFSET 左移，仍会漏掉未删除的库

位置：`apps/web-v2/src/hooks/use-knowledge-bases.ts:79–90、152`。

后端依据：`services/api/src/main/java/com/knowflow/api/knowledgebase/KnowledgeBaseService.java:51–64`，真实服务针对当前 ACTIVE 集合执行 `ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`，没有跨页快照或稳定游标。

### 可复现顺序

1. 准备 51 个库，第一页返回第 1–50 项；`offset=50` 的下一次查询在执行前挂起。
2. 删除第一页的第 1 项，服务端现在剩 50 项。
3. 让下一页在删除后的集合上执行 `OFFSET 50`，正确结果是空页。
4. 前端 removed 集合仅过滤已删除项，仍按旧偏移续读，没有重新获取已经左移到前一页位置的第 51 项。

### 实测

```text
服务端剩余数量: 50
页面知识库卡片数量: 49
Knowledge 51: 未显示
第二页 API 返回: []
```

被漏掉的库仍存在，但列表/搜索里不可达，直到重新加载。当前修复解决的是旧响应中已删除项复活，未完整解决可变 OFFSET 分页与删除的竞争。

### 建议修复与验收

- 在本地删除成功后，使正在读取的列表代次失效并从第一页重新建立列表，或采用经过契约设计的一致分页方案；单纯过滤或去重不能补回已跳过的资源。
- 保留现有账户隔离、取消和短期 busy 保护，不通过永久禁用删除来绕开。
- 新增真实分页模型回归：51 项、首批 50 项、删除改变服务端数组、后续页在释放时按当前数组执行 slice(offset, offset + limit)，最后确认全部 50 个未删除项均存在。
- 当前 `e2e/base-pagination-mutations.spec.ts:16–23` 的第一页只有一项，第二页固定返回预先构造的 second；它可检测复活，却无法检测真实 OFFSET 位移。因此该用例通过不代表上述竞争已闭环。

## 采样与堆分析代码的审阅边界

已阅读 `scripts/performance/retention.mjs`、`heap-summary.mjs`、`tests/heap-summary.test.mjs` 与收口说明。现有 dominator 环/菱形/弱边、随机图独立 oracle 和同会话 ID 单元均通过，本轮没有确认与上述业务问题同等级的确定性分析器算法错误。

诊断图与 Chrome ephemeron/native retained-size 不同、观测会影响 GC/JIT、对象计数不能单独证明无泄漏等限制，对方报告已明确列出，不作为重复缺陷。此结论不表示本轮独立重跑了三组 180 次快照，或已确认所有内存/浏览器场景没有问题。

## 证据与后续顺序

临时复现材料：`C:/Users/31180/AppData/Local/Temp/web-v2-postreview.ckLCRA/` 中的 `reproduce.cjs`、`results.json`、两张截图与现有分页测试输出。永久记录只保留上述必要逻辑和结果；没有将堆快照、缓存或真实用户数据写入本报告。

建议先修复 P1 错库作用域，再补齐 OFFSET 删除竞争及两种回归；通过静态检查与 mock 后，恢复 Docker 并验证该修复的隔离全栈/SSE/回退。当前不建议仅凭原 41 项 mock 或旧全栈结果合入/上线。
