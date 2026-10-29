# KF2-003 模型与依赖冒烟

此目录服务于 Agent B 的第一个任务。模型脚本仅使用 Python 3.12 标准库，不安装 AI 服务依赖，不启动产品接口。所有时间为 `Asia/Hong_Kong`。

## 当前证据

- [真实环境预检](evidence/model-preflight.json)：`WAITING_INPUT`，未发出模型请求，没有模型通过结论。
- `test_model_smoke.py`：10 项离线客户端回归，模拟响应只验证脚本，不验证模型可用性。
- [许可核对](evidence/parser-licenses.json)：从 PyPI 下载指定版本 wheel，核对 SHA-256 并检查许可文件；未安装解析器，未验证解析质量。
- [运行基线及阻断](../../docs/architecture/runtime-profile.md)。

## 运行真实模型验证

由环境配置注入以下非秘密选择项，以及 `KNOWFLOW_MODEL_KEY_ENV` 指定的秘密变量：

| 环境变量 | 要求 |
|---|---|
| `KNOWFLOW_MODEL_BASE_URL` | 支持 OpenAI 风格 `/embeddings`、`/chat/completions` 的 HTTPS 基址，包含需要的 `/v1`；不能带用户信息、查询串或片段 |
| `KNOWFLOW_EMBEDDING_MODEL` | 供应商提供的 Embedding 模型/固定版本 ID |
| `KNOWFLOW_EMBEDDING_DIMENSIONS` | 该模型实际使用的向量维度，必须显式指定；不自动改模型输出维度 |
| `KNOWFLOW_LLM_MODEL` | 供应商提供的 LLM 模型/固定版本 ID，支持 `max_tokens` |
| `KNOWFLOW_MODEL_KEY_ENV` | 秘密变量名，默认 `OPENAI_API_KEY`；值是变量名，不是密钥 |

`.env.example` 仅展示变量名，脚本不会自动加载 `.env`。模型地址需通过云环境的正式网络配置开放；当前只确认包仓库和 GitHub 可访问，不能据此推断模型服务可访问。

在仓库根目录执行，使用一个尚不存在的输出路径：

```sh
python evaluation/smoke/model_smoke.py --output /workspace/scratch/knowflow-live-smoke.json --timeout 20
```

脚本先检查配置，缺项则退出 `2`，状态 `WAITING_INPUT`，不发请求。成功退出 `0`，状态 `LIVE_SMOKE_PASSED`；其他失败退出 `1`。已有证据文件不会覆盖。真实结果经人工检查后可将脱敏 JSON 保存到本目录 `evidence/`，不要提交秘密配置。

每次执行最多两个请求：一次包含两条原创中文短句的 Embedding，一次基于原创合成规范的中文问答；Embedding 失败时不继续调用 LLM。没有重试或模型回退。每个网络操作超时默认 20 秒，最多设置 30 秒；这是传输超时，不是整个任务的硬墙钟限制。响应体上限 1 MiB，重定向拒绝，TLS 验证及环境代理保留。

校验包括：数量、索引序号、向量维度、有限非零数值、LLM 正常结束、中文回答包含合成规范的 `8 MiB`。这只是冒烟条件，不是语义正确性评测。使用模型别名、供应商未返回同名 ID，或后台模型升级时，仍需人工确认真实版本，不能据单次通过宣布版本已冻结。

记录只包含配置中的模型 ID、夹具哈希、运行环境、用量整数、耗时、布尔校验及回答哈希；不保存密钥、完整地址、请求头、原始错误正文、回答正文或向量。401/403、429、超时及其他 HTTP/网络错误使用固定错误码。响应解析/维度/中文校验失败同样是失败，不能认定模型可用。模型费用可能已发生，即使回答校验失败；没有供应商价格和账单时，费用保持 `null`。

外部调用会发送 `fixture.json` 中的两条中文句子、合成规范和问题，执行前可直接检查该文件。脚本不会读取用户文件、知识库或原始私有文档。供应商的保留和训练政策待供应商确定后核对。

## 复现本地检查与许可核对

```sh
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
python evaluation/smoke/audit_dependencies.py --output /workspace/scratch/knowflow-parser-licenses.json
git diff --check
```

许可脚本固定核对 PyMuPDF `2.0` 的 Linux x86_64 wheel 与 pypdf `6.21.4` 的通用 wheel；不安装它们。单 wheel 上限 80 MiB。PyMuPDF Linux wheel 实际为 68,938,796 字节，初次 64 MiB 上限拒绝了它，调整核对工具的下载上限后重新核验；这不是解析器运行性能证据。完整的服务依赖锁与传递依赖许可清单属于 KF2-007。
