# KF2-003：模型、隐私和费用记录

状态：IN_REVIEW。核对时间：2026-10-30（Asia/Hong_Kong）。配置记录不包含凭证值。

## 配置和真实执行

| 能力 | 供应商和端点 | 请求 ID | 实测 |
|---|---|---|---|
| Embedding | 硅基流动，api.siliconflow.cn/v1/embeddings | BAAI/bge-m3 | 返回两条有效非零向量，1024 维；本轮 33 tokens，1.49 秒 |
| LLM | DeepSeek，api.deepseek.com/chat/completions | deepseek-flash，thinking disabled | 合成中文事实检查通过；本轮输入 76、输出 14 tokens，1.16 秒 |
| Rerank | 本轮未调用 | 无 | 首轮不需要；BAAI/bge-reranker-v2-m3 是重排器，不代替 Embedding |

当前运行环境变量名为 EMBEDING_KEY 和 DEEPSEEK_API_KEY。此前鉴权检查的 GET /v1/models 均 HTTP 200；[本 python 分支双模型证据](evidence/model-live-20261030-python.json)重新验证两个真实端点。新证据只含模型别名、哈希、向量校验结果、用量及耗时，不记录密钥、响应正文或向量。

DeepSeek 官方价格页在核对时将 deepseek-flash 映射到 DeepSeek-V4.1-Flash-1017。实时响应只回报请求别名，不足以锁定某个不可变后端部署版本。硅基流动 API 响应回报 BAAI/bge-m3 别名，本次真实向量长度为 1024。

## 费用依据和估算

[DeepSeek 官方价目](https://api-docs.deepseek.com/quick_start/pricing/)以每百万 tokens 计价：峰时 cache-miss 输入 USD 0.30、cache-hit 输入 USD 0.006、输出 USD 1.20；非峰时分别为 USD 0.15、USD 0.003 和 USD 0.60。当前价目所述工作日峰时为 UTC 01:00–04:00、06:00–10:00（中国法定节假日除外）。本轮记录时间为 2026-10-30 10:39 HKT，即约 02:39 UTC 的工作日峰时。保守按输入均为 cache miss 估算：76×0.30/1,000,000 + 14×1.20/1,000,000 = USD 0.0000396。此为公布价格下的估算，不是实际扣费；缓存分类、账户折扣和账单未核验。

[硅基流动价格页](https://siliconflow.cn/pricing)核对时将标准 BAAI/bge-m3 列为免费；Pro/BAAI/bge-m3 是另一个型号。价格及免费政策会变化，控制台用量/账单是实际费用依据，本记录不把总账单写成零。

## 数据去向、隐私和未决项

本轮只把 smoke/fixture.json 的两句原创短文本发送给硅基流动，将合成规范及问题发送给 DeepSeek。不读取或发送用户文档、真实知识库、原始私有内容或个人资料。实际产品若采用外部 API，将把文档分段文本发送给 Embedding，将问题和检索片段发送给 LLM。

[硅基流动隐私政策](https://docs.siliconflow.cn/docs/legals/privacy-policy)披露其 API 服务会收集 IP、调用模型、token 数、请求时间及状态码等日志；平台安全风控可能处理输入提示词及输出。政策以实现服务所需期间等表述存储期限，未给出可据以承诺固定 API 内容保留时长或不训练的具体期限/保证。

[DeepSeek 通用隐私政策](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html)披露输入、提示词和输出的处理、服务改进/训练目的、按目的及法律需求决定的保留期限，并指出数据可能储存在中国大陆。该页面适用范围描述 app、网站和相关服务；开发者下游应用有自己的披露责任。当前没有取得针对本账户 Open Platform API 的专门 DPA、保留/删除时限或训练条款确认，因此不把通用隐私页面推断为该 API 账户的确定合同，也不宣称 API 输入一定用于或一定不会用于训练。

未决事项：供应商对本账户 API 的具体条款适用范围、提示词/输出精确保留期、训练选择/退出机制、区域、账号控制台配置、实际扣费明细。确认前，上传实测限制为获准合成或非敏感资料；产品应在上传前披露文本出站及供应商，不能宣称零保留或不会用于训练。

## 环境、依赖和资源边界

[真实冒烟证据](evidence/model-live-20261030-python.json)绑定 runner SHA 0ab056334e164e551f59b33144a83a3cc961c9556808e19cd99e90b542175a79 和本轮 fixture SHA。环境为 Python 3.12.14、Linux x86_64、逻辑 CPU 3、cgroup CPU 等效 2 核、内存上限 8 GiB；没有证明 GPU 可用。开发容器不代表生产目标硬件。

许可范围仅是两个直接候选，不是完整服务依赖锁：[PyMuPDF 2.0 的 Linux wheel](evidence/parser-licenses.json)元数据/COPYING 声明 AGPL-3.0 或 Artifex 商业许可；pypdf 6.21.4 是 BSD-3-Clause 替代候选。wheel SHA-256 与 PyPI 摘要匹配，均未安装，未做解析质量比较；不在本任务最终选用解析器。完整传递依赖和服务依赖锁留在 KF2-007。

| 边界 | 记录值 | 证据状态 |
|---|---|---|
| 输入文件 | UTF-8 TXT/MD、文本型 PDF；不含 OCR/DOCX | 计划范围，尚未跑解析回归 |
| 单文件 | 8 MiB | 提议，待样本/目标机器验证 |
| PDF 页数 | 200 页 | 提议，待验证扫描、加密和异常文件 |
| 提取文本 | 200,000 字符/文档 | 提议，待目标机器压测 |
| 知识库文档数 | 100 | 提议，待索引/检索验证 |
| 并发索引 | 1 | 保守提议，未实测 |
| 产品上下文 | 候选最多 8,192 tokens | 待切块/提示词预算验证；供应商宣称上下文更大不等于产品验收 |
| 冒烟网络 | 每个端点单次、无重试，20 秒默认传输超时，本次命令显式 30 秒 | 脚本及本轮记录 |
| 产品超时/重试 | 30 秒、最多两次为早期候选 | 待幂等、费用与限速测试 |

上述值仅为供 A/M 评估的建议，不能冒充接口限制、部署承诺或真实解析性能。KF2-035 和 KF2-038 应分别验证解析资源与生产负载。

## 历史验证

[首次旧会话调用](evidence/siliconflow-deepseek-live-attempt.json)和[旧网络诊断](evidence/provider-connectivity.json)记录当时的代理 403，保留为历史失败。随后新会话已解除限制；[前次通过证据](evidence/model-live-20261030-full-sentence.json)与本分支证据均通过真实模型验证。最早一次 DeepSeek 输出未含汉字的失败也保存在 model-live-20261030.json，没有通过放松中文校验掩盖。
