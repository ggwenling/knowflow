# KF2-018：Embedding 适配器 B03

状态：硅基流动适配器和定向回归已实现。它可以供 B06 索引执行器调用，但目前没有处理路由、任务执行器或 Java 写入客户端。真正索引写入须等 A 的 draft.5 与有 fencing 的 Java 批次网关。

## 行为约定

- 配置固定为 `BAAI/bge-m3`、1024 维及 `https://api.siliconflow.cn/v1/embeddings`。只接受 HTTPS 的硅基流动 API 主机，拒绝 HTTP、自带凭证的 URL、查询串、重定向及未知模型配置。
- 默认从 `EMBEDING_KEY` 读取凭证；`KNOWFLOW_EMBEDDING_KEY_ENV` 可选择其他环境变量名。只读取选中的变量，不回退到 LLM/API 通用密钥。凭证隐藏在配置对象 repr 中，错误只返回固定代码。
- 每批 1–32 条，每条最多 800 个 Unicode 码点；响应最多 2 MiB；超时最多 30 秒。大小、超时限制用于控制本开发接口的输入，不是目标硬件性能承诺。
- 一次调用只发一个请求，无自动重试。超时/429/服务器暂时失败会带重试属性交回上层；重试策略属于 Java 任务队列，以免 Python 重试造成模型重复计费。
- 对返回模型 ID、响应条数、每个唯一索引、1024 维和有限非零向量执行严格检查。内部结果排序为输入顺序，带当前调用的 request_id、模型、维数及可核验 token 用量。第三方响应正文、输入、向量与凭证不写入日志或证据。
- HTTP 客户端保留云环境代理、系统 CA 和 TLS 校验；禁用重定向。可注入 httpx transport 做离线协议/故障验证。

## 验证

```sh
uv run --project services/ai --frozen pytest services/ai/tests/test_embedding.py -q
uv run --project services/ai --frozen python services/ai/tools/embedding_smoke.py --output services/ai/docs/evidence/embedding-live-YYYYMMDD.json
```

Live smoke 只发送一条内置原创合成句子，生成新证据文件且拒绝覆盖旧文件。证据只保存请求和响应模型名、向量条数/维度、有限值结论、token 用量、耗时以及输入/代码哈希，不保存句子原文、响应向量、响应正文或凭证。运行前确认输出文件名不存在。

离线回归覆盖配置拒绝、凭证选择器隔离、模型/顺序/维数/非有限值/空结果、超时、429、不重试、重定向拒绝、响应体上限和调用输入上限。真实 API 冒烟只能证明该合成请求当时通过，不能证明业务索引质量、并发容量、部署后端版本或实际账单。
