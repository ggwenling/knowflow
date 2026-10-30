# Python AI 服务（Codex-B 所有）

Python 3.12 / FastAPI 内部服务，当前使用共享契约 `0.2.0-draft.6`（Schema SHA-256：`d64f9521b2d1b753f918d74906ea162337a4938490976cf4223a824ef107ccb1`）。契约仍是候选版本；Q 独立审阅、M 页面消费确认和正式冻结未完成。

## 当前能力

- `GET /health/live`：无凭证存活探针；`GET /internal/v1/health`：内部 Bearer 认证后的版本与 request ID。
- `POST /internal/v1/index-executions`：接收 Java 创建的 lease-fenced 派发，排入单进程有界队列；按 task/lease/fencing 去重，后台每 10 秒 heartbeat。
- IndexWorker 只经 Java 内部接口读取原文件、续租、写入最多 16 条的批次和提交 completion。Java 是唯一业务状态及向量写入者；Python 不连接 Java 写库凭据。Java 完成数据库事实验收后才发布 READY。
- `POST /internal/v1/index-executions/{task_id}/cancel`：按 task、lease、fencing 精确取消当前执行。
- `POST /internal/v1/answers`：只接受 Java 提供的可信快照范围；使用只读 PostgreSQL 账号和 READY 索引检索证据，并在调用 DeepSeek 前再核对每条检索记录的 document/content/index 三元组属于该快照。生成后校验来源 ID 与实际检索证据。空检索或越界检索都不会调用生成模型。浏览器不能调用此内部入口或自行指定 owner。
- 模型凭证/数据库配置缺失时，业务入口明确返回受控不可用错误，不伪造索引或回答。默认使用 SiliconFlow `BAAI/bge-m3`（1024 维）与 DeepSeek `deepseek-flash`；请求超时、有界响应、模型 ID/维度校验和错误脱敏均由适配器执行。

## Windows 本地开发

在仓库根目录使用 Python 3.12：

```powershell
uv sync --project services/ai --frozen --python 3.12
$env:KNOWFLOW_INTERNAL_SHARED_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:KNOWFLOW_JAVA_BASE_URL = "http://127.0.0.1:8080"
uv run --project services/ai --frozen uvicorn knowflow_ai.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Java 与 Python 必须注入同一个 `KNOWFLOW_INTERNAL_SHARED_SECRET`（32–256 个允许字符），但不要将密钥写入命令行历史、日志或仓库。服务不会自动读取 `.env`。问答还需注入 `KNOWFLOW_AI_DATABASE_URL`（`knowflow_ai` 只读数据库身份）及 `EMBEDING_KEY`、`DEEPSEEK_API_KEY`；凭证名可由 `KNOWFLOW_EMBEDDING_KEY_ENV` / `KNOWFLOW_LLM_KEY_ENV` 选择。Embedding 与 LLM base URL 默认分别为 `https://api.siliconflow.cn/v1` 和 `https://api.deepseek.com`，代码校验固定受支持的主机。

若本地 Schema 以只读挂载提供，设置 `KNOWFLOW_CONTRACT_PATH`。默认路径为仓库共享 Schema；启动时会校验精确 SHA-256，不能通过关闭校验来绕过版本不匹配。

## 校验

```powershell
uv run --project services/ai --frozen pytest services/ai/tests -q
uv run --project services/ai --frozen python contracts/validate.py
python -m unittest discover -s evaluation/smoke -p 'test_*.py' -v
uv run --project services/ai --frozen python services/ai/tools/process_smoke.py
```

当前 Python 单测、Schema、离线模型回归及真实 Python HTTP process smoke 分别验证不同边界，不替代 Java↔Python 双进程联调、真实数据库权限测试或真实模型质量/费用验收。`java_python_smoke.py` 验证真实 Java WebClient 与 Python HTTP health；Java `DocumentApiIntegrationTest` 另以本地 HTTP fixture 验证上游 AI 返回 503 时公开问答接口映射为可重试 502，并将问题状态记为失败。索引/问答真实模型闭环仍使用本地合成 adapter 验收；真实模型质量需有凭证后单独验证。

2026-10-30 的本机合成 E2E 使用真实 Java/Python 进程、PostgreSQL/pgvector 和 MinIO，验证上传、索引 READY、只读检索、问答来源校验与持久化；新增 Python 快照范围 guard 后再次通过。另在活动合成 embedding 阻塞期间删除文档，真实验证 Java cancellation outbox 到 Python HTTP cancel、worker 子任务中断、adapter 收尾、清理队列排空及无迟到 Chunk/向量写入。修复记录与报告见 `docs/evidence/cancellation-e2e-local-draft6-verified.json`。Embedding/LLM 使用本地替身，外部模型调用为 0。问答证据见 `docs/evidence/local-backend-e2e-draft6-verified.json`；当前 Compose 权限见 `docs/evidence/local-db-role-audit-draft6.json`；12 道开发题与 3 道留出题的来源证据 Chunk 覆盖见 `docs/evidence/seed-chunk-coverage-local-draft6.json`。这些不代表真实模型质量或向量排名通过。Windows 默认 Proactor 事件循环不支持 psycopg 异步连接，因此只读 SQL 通过 `asyncio.to_thread` 调用同步 psycopg；连接与语句均有 5 秒上限，事务保持只读。

可从仓库根运行 `uv run --project services/ai --frozen python services/ai/tools/local_backend_e2e.py` 重放该合成闭环。需要先按 API README 启动健康的本地 Compose PostgreSQL/MinIO，并准备本机 `services/api/.env`；8000/8080 必须空闲，数据库不能有未完成的索引任务或待处理清理队列。脚本会创建合成账户及知识库，删除知识库、等待相应存储/索引/取消清理完成并退出会话；合成账户记录保留在本地开发数据库中。测试使用合成 adapter，不发起外部模型调用；结果见 `docs/evidence/local-backend-e2e-draft6-replay.json`。

报告中的源码 SHA-256 按运行时工作区的原始字节计算；Git 行尾转换可能使其他检出或 Git blob 的字节哈希不同。需要复核时，应对运行时工作区文件计算哈希，或在目标检出中重跑验证。契约 Schema 的 LF 字节由 `.gitattributes` 固定。

依赖使用 `uv.lock` 精确锁定；`requirements.lock` 是无开发依赖、带哈希的 pip 导出。PDF 解析使用 pypdf，TXT/MD 严格按 UTF-8 读取；解析、分段、定位说明分别见 `docs/parsing.md` 和 `docs/chunking.md`。模型和数据政策见仓库 `evaluation/smoke/provider-profile.md`。
