# Web 前端（M 所有）

Next.js / React / TypeScript 用户体验，包括登录、知识库、上传状态、问答与来源核验。
本目录为 KF2-008 预研交付：页面路由、统一 API 客户端与契约样例 Mock。

## 状态：预研，不是完整 KF2-008 验收

- KF2-004 未冻结：契约当前为 DRAFT 0.2.0-draft.5 候选（见 `contracts/api-draft.md`，
  其中明确写明“不表示 KF2-004 冻结或生产 API”）。本骨架的字段形状为候选推断，
  冻结后以生成客户端替换，不得把候选字段当作已冻结契约引用。
- Mock 只能用于开发，必须可见地区分（页面顶部横幅），不能代替真实端到端验收。
- 文档重建入口在 KF2-004 冻结代次与幂等键前不可公开，本骨架不提供重建入口。
- 完整 KF2-008 验收（字段来自冻结契约、真实与 Mock 模式可区分、后续任务可直接接 API）
  需等 KF2-004 冻结后补齐；历史页面、流式页面、PDF 页码预览属后续任务，不在骨架范围。

## 路由

- `/`：首页与模式说明。
- `/login`：登录与注册（邮箱 + 密码；密码长度候选 12–128 字符；成功返回一次性 Bearer 凭证，8 小时有效，无刷新令牌）。
- `/libraries`：知识库列表与新建（创建请求不接受 owner 字段；列表只含当前所有者且 ACTIVE 的知识库）。
- `/libraries/[kbId]`：文档列表、上传（TXT/MD/文本 PDF；8 MiB、PDF 200 页、200,000 码点开发上限）、文档状态与删除。
- `/ask`：单轮问答与来源核验（每次提问独立检索，历史不作为多轮上下文；有答案必须有至少一个来源，无证据返回无答案）。

## 配置

浏览器只访问 Java API，不直接携带模型 API Key 调用供应商；密钥不得放进 `NEXT_PUBLIC` 环境变量。
`NEXT_PUBLIC_API_BASE_URL` 默认 `http://localhost:8080`（与 java 分支的 `apps/web/.env.example` 一致）。
`NEXT_PUBLIC_USE_MOCK=true` 开启 Mock 模式（开发预研默认）；生产必须设为 `false` 并以真实接口验收。

```sh
cp .env.example .env.local
npm install
npm run dev     # 开发
npm run build   # 构建
npm start       # 启动生产构建
```

## 技术选择说明

本预研只引入 Next.js + React + TypeScript 与少量手写样式，未引入 Tailwind、shadcn/ui 与 TanStack Query。
计划书第 4.1 节以 Tailwind、shadcn/ui、TanStack Query 为前端基线；完整 KF2-008（冻结后）将锁定并接入它们。
预研阶段不引入，是为了让路由、客户端与 Mock 先行可验证，不以样式与数据层选型阻塞骨架。
