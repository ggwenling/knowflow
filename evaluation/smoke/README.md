# KF2-003 模型与依赖冒烟

本目录提供仅用 Python 3.12 标准库的可复现模型客户端检查，不安装生产 AI 服务依赖或启动产品接口。真实运行记录见下方。时间均为 Asia/Hong_Kong。

## 当前证据（2026-10-30）

- [python 分支双模型真实调用](evidence/model-live-20261030-python.json)：硅基流动两条 1024 维向量及 DeepSeek 中文合成事实检查均通过；使用合成输入。
- [鉴权检查](evidence/provider-auth-20261030.json)：两个 GET /v1/models 均 HTTP 200；记录不含凭证值。
- [前次完整句测试](evidence/model-live-20261030-full-sentence.json)通过；[首轮中文输出检查失败](evidence/model-live-20261030.json)作为失败样本保留。
- [历史网络失败](evidence/siliconflow-deepseek-live-attempt.json)及[旧代理诊断](evidence/provider-connectivity.json)保留为历史记录，不代表目前网络状态。
- [15 项客户端离线回归](test_model_smoke.py)只验证客户端逻辑，不等同真实模型证据。
- [解析候选许可证检查](evidence/parser-licenses.json)只核对两个 wheel，不是已安装服务依赖的完整许可清单。
- [模型、费用与供应商政策](provider-profile.md)记录当前核查结果和未决项；[运行基线](../../docs/architecture/runtime-profile.md)记录容量边界。

## 真实运行

已选择硅基流动 BAAI/bge-m3（1024 维）及 DeepSeek deepseek-flash。环境凭证变量名为 EMBEDING_KEY 和 DEEPSEEK_API_KEY。公开参数可参考 [.env.example](.env.example)，此文件只提供变量名及模型设置，脚本不会读取或加载其中内容。凭证值由托管环境注入，不可保存到本地文件。

```sh
KNOWFLOW_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1 \
KNOWFLOW_EMBEDDING_MODEL=BAAI/bge-m3 \
KNOWFLOW_EMBEDDING_DIMENSIONS=1024 \
KNOWFLOW_EMBEDDING_KEY_ENV=EMBEDING_KEY \
KNOWFLOW_LLM_BASE_URL=https://api.deepseek.com \
KNOWFLOW_LLM_MODEL=deepseek-flash \
KNOWFLOW_LLM_KEY_ENV=DEEPSEEK_API_KEY \
KNOWFLOW_LLM_THINKING=disabled \
python evaluation/smoke/model_smoke.py --output /workspace/scratch/knowflow-live-smoke.json --timeout 30
```

使用一个新的输出路径。脚本缺少配置时以 WAITING_INPUT 退出且不发请求；完整成功以 LIVE_SMOKE_PASSED 退出 0；其他失败退出 1。每轮每端点最多一次请求，无自动重试或模型回退；Embedding 失败时不发 LLM 请求。传输超时默认 20 秒、本次显式 30 秒，响应体上限 1 MiB，拒绝重定向并保留 TLS 验证和环境代理。

外部调用把 fixture.json 两个短句发给硅基流动，把原创合成片段和问题发给 DeepSeek。不会读取用户文档、知识库或私有文件。记录只含模型标识、fixture/runner 哈希、环境、有限用量、耗时和回答哈希，不含密钥、回答正文、向量、私有文本或供应商原始错误正文。

## 本地检查

```sh
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
python evaluation/smoke/audit_dependencies.py --output /workspace/scratch/knowflow-parser-licenses.json
git diff --check
```

许可证脚本下载指定 wheel 作哈希及许可证文件检查，不安装依赖。PyMuPDF 2.0 的 Linux wheel 为 68,938,796 字节；审计下载上限为 80 MiB。完整服务依赖锁和传递依赖许可审核属于 KF2-007。
