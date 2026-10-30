# KF2-003：已选择的外部模型配置

更新：2026-10-30，Asia/Hong_Kong。用户确认以下模型。仅记录非秘密配置；凭证未写入本文件或仓库。

| 能力 | 供应商及请求地址 | 模型及状态 |
|---|---|---|
| Embedding | 硅基流动，`https://api.siliconflow.cn/v1/embeddings` | `BAAI/bge-m3`，真实输出两条有效 1024 维向量 |
| LLM | DeepSeek，`https://api.deepseek.com/chat/completions` | `deepseek-flash`，短问答显式 `thinking.type=disabled`，完整中文句子夹具通过 |
| Rerank | 本轮不调用 | 用户最初给出的 `BAAI/bge-reranker-v2-m3` 是重排器，不能替代 Embedding；保留到计划中的可选增强项 |

## 官方来源核对

- [硅基流动 Embeddings API](https://docs.siliconflow.cn/docs/api/embeddings-post)：支持 BGE-M3 文本输入；长度上限 8192 tokens。`dimensions` 请求参数只支持文档列出的 Qwen3 系列，本次不为 BGE-M3发送维度变更，只验证实际响应是否为 1024。
- [硅基流动 Rerank API](https://docs.siliconflow.cn/docs/api/rerank-post)：`BAAI/bge-reranker-v2-m3` 属于 `/rerank`，输出是候选相关性而非入库向量。
- [BGE 官方仓库的 BGE-M3 说明](https://github.com/FlagOpen/FlagEmbedding/tree/master/research/BGE_M3)：模型作者的结构与使用说明；模型维度还需由真实供应商响应验证。
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：`deepseek-flash`、`max_tokens` 和 `thinking.type` 均为公开接口；默认启用思考，128 token 的短问答采用非思考模式。
- [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)：核对时 `deepseek-flash` 指向 `DeepSeek-V4.1-Flash-1017`。这是供应商公开说明，不是此次请求已确认的部署版本，也不能将可变别名当成不可变模型锁。
- [硅基流动价格](https://siliconflow.cn/pricing)：核对时标准 `BAAI/bge-m3` 页面标为免费，`Pro/` 是另一型号；尚无真实用量或账单，不据此写入本次实际费用为零。

DeepSeek 前次核对时每百万 token 的美元价格：缓存命中输入 0.003/0.006，未命中输入 0.15/0.30，输出 0.60/1.20（分别为非高峰/高峰）。实际计算需请求时间、缓存命中/未命中 token、输出 token 和账单；新会话已有成功响应和用量，但未核对当前价格/账单，不计算金额。价格会变化，计费时复核官方页面。

产品上下文候选预算仍为 8192 tokens 内，不因供应商更大窗口而扩大产品承诺。未核对两家数据保留、训练使用及区域政策，不宣称“文本不出站”或“零保留”。

## 历史真实执行与网络阻断

已按用户要求直接使用提供的两家密钥，借助不回显输入读取到单个 Python 进程内存，不写入环境文件、仓库、日志或证据。两家密钥分别只绑定自身 endpoint，不会将硅基流动密钥发给 DeepSeek。进程结束后未创建可复用秘密文件。

[真实尝试证据](evidence/siliconflow-deepseek-live-attempt.json)：Embedding 尝试以 `NETWORK_FAILURE` 结束。按脚本规则没有继续发出 LLM 生成调用，所以它不能证明 DeepSeek 凭证/模型可用或不可用。证据中的 `runner_sha256` 绑定当时脚本字节；`git_head` 是执行时的父提交。

[无凭证连接诊断](evidence/provider-connectivity.json)：两个域名在 HTTPS 代理隧道建立时均得到 403，未收到供应商 HTTP 响应。云环境当前为 restricted/enforced，允许列表中没有这两个域名。不得将这个 403 解释成 API 密钥错误；更换模型或重复输入密钥不能修复网络放行。

上述网络阻断已在新会话解除。当前绑定变量为 `EMBEDING_KEY`、`DEEPSEEK_API_KEY`，无需再次发送密钥。

## 新会话验证结果

2026-10-30 10:27–10:28（Asia/Hong_Kong）：环境观察 current、网络 unrestricted/enforced，两个变量 ready；[鉴权检查](evidence/provider-auth-20261030.json)的两个 `GET /v1/models` 均 HTTP 200。

[首轮](evidence/model-live-20261030.json) Embedding 成功，LLM 已生成但回答不含汉字，未通过中文检查。保留失败，将问题明确为完整中文句子后，[第二轮](evidence/model-live-20261030-full-sentence.json)两项均 PASSED；验证规则未变。Embedding 1024 维、约 1.69 秒；LLM 合成事实与中文检查通过、约 1.55 秒，两者响应模型名均与请求一致。两轮合计 Embedding 66 tokens、LLM 157 tokens；未核对实际账单。别名一致不等于锁定不可变后端版本。

仅发送原创合成资料，未持久化密钥或回答正文。KF2-003 当前 IN_PROGRESS；数据保留/区域/训练使用政策、部署资源、Q 审阅与集成仍待验证，不据此直接解除下游依赖。
