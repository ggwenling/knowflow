# Python AI 服务（B 所有）

KF2-007 开发交付：Python 3.12 / FastAPI 最小内部服务，可独立启动。当前启用 GET /health/live（仅状态）及受 Bearer 认证的 GET /internal/v1/health（状态、契约版本、request_id）。索引、检索、生成业务路由未启用，未知路径在鉴权后返回 404；不伪造任务接收或回答。不是完整 RAG 产品。

从仓库根执行（uv 0.12.23 或兼容 lock revision 5 的版本；所有安装使用公开 PyPI）：

```sh
uv sync --project services/ai --frozen
export KNOWFLOW_INTERNAL_SHARED_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uv run --project services/ai --frozen uvicorn knowflow_ai.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Java 进程使用相同 KNOWFLOW_INTERNAL_SHARED_SECRET。密钥必须为 32–256 字符的 Bearer token，允许 ASCII 字母、数字及 -._~+/，末尾可有 =；不符合时启动失败，错误不回显值。禁止把密钥放进命令行参数、日志或仓库。服务不加载 .env；配置从进程环境注入。

默认读取仓库 contracts/schemas/protocol.schema.json，并检查精确哈希。非 editable 安装/部署时设置 KNOWFLOW_CONTRACT_PATH 为挂载的同一只读文件。缺失/哈希变化会启动失败；A 发布新候选后须按消费清单升级，不能绕过哈希校验。当前消费 0.2.0-draft.4，详见 [契约消费与提案](docs/contract-consumption.md)。内部 health 已纳入 A 的 draft.4 候选 Schema；候选尚未正式冻结。

运行依赖与传递哈希锁定于 uv.lock；requirements.lock 是无开发依赖的 hash export，可用 pip --require-hashes 安装后再安装本项目。uv.lock 同时记录测试依赖；构建后端精确固定。元数据及许可证文件哈希见 [依赖许可证记录](docs/evidence/dependency-licenses.json)，仅记录当前 Linux 环境，条件平台依赖未安装项保留未知；不是法律许可批准。外部模型凭证沿用 .env.example 的变量选择器；本骨架不会读取/调用模型，健康不保证模型或数据库可用。

从仓库根验证：

```sh
uv run --project services/ai --frozen pytest services/ai/tests -q
uv run --project services/ai --frozen python services/ai/tools/process_smoke.py
uv run --project services/ai --frozen python services/ai/tools/audit_licenses.py
uv run --project services/ai --frozen python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
```

进程冒烟会启动真实 Uvicorn、生成临时测试密钥并在退出时清理进程，证据只保存断言、哈希和版本，不保存密钥/正文。开发测试使用合成数据及离线 Provider 报文，不冒充实际模型调用。当前 Starlette TestClient 对 httpx 给出上游弃用提示，测试仍有效；运行时没有使用 TestClient。

职责：解析/分段/Embedding/受控检索/生成/来源映射；Java 独占业务状态和发布。本服务不持有业务数据库写权限。KF2-016 已交付内部纯解析组件（pypdf 6.21.4、UTF-8 TXT/MD），见[解析说明](docs/parsing.md)；KF2-017 已增加可复现分段和原文定位，见[分段说明](docs/chunking.md)。当前均是内部组件，未公开业务处理路由；实现与开发回归仍待 draft.5 消费、独立 Q 审阅和真实 A 网关集成后正式验收。

Java/Python 真实进程联调（需要 Java 21、可用 Maven 网络配置）：

```sh
uv run --project services/ai --frozen python services/ai/tools/java_python_smoke.py
# 需要代理时在本机增加 --maven-settings /path/to/local-settings.xml
```

该 B 线脚本只复制 Java 的源码/构建输入到临时目录，启动原 Spring 服务和 Python 服务，并使用原 AiHttpClientConfiguration；不修改 Java 源码或公共契约。慢响应场景使用单独本地测试夹具验证实际 30 秒 responseTimeout，不是假造 Python 业务接口。证据见 docs/evidence/java-python-smoke.json。Java 对外网关的统一超时/上游错误映射尚无业务调用入口，仍由 A 实现和验收；本测试只证明真实服务/传输及 Python 错误体兼容。
