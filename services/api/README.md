# Java API 服务（A 所有）

职责：外部认证与 API、资源所有者隔离、文档/任务业务状态、活动索引发布、问答结果权限复核。Java 是用户、文档和任务状态的唯一写入方。

默认 profile 沿用 KF2-006 安全骨架，只公开 `GET /actuator/health`。迁移数据库并设置应用凭据后，`database` profile 提供 KF2-012 注册/登录/登出/当前用户及 KF2-013 个人知识库 API。A 维护 Java、Flyway 与唯一正式契约；Python 服务不写业务状态。

要求 Java 21。服务运行需要 Java 21 JRE；当前编译器插件固定使用 Eclipse Compiler，因而在本开发环境不必另装 `javac`。构建前先设置 `KNOWFLOW_INTERNAL_SHARED_SECRET`（32–256 字符的 Bearer token：ASCII 字母、数字及 `-._~+/`，末尾可有 `=` 填充）；缺失、过短或含空白/控制字符时服务启动失败。`KNOWFLOW_AI_BASE_URL` 默认 `http://localhost:8000`，只校验配置结构，不会在启动时连接 AI 服务。

KF2-011 使用 Flyway、PostgreSQL 16 和 pgvector 0.8.1。先由数据库管理员创建数据库并执行 `src/main/resources/db/bootstrap-roles.sql`；该脚本安装 `vector` 扩展、建立隔离 Schema 和 `knowflow_migrator`、`knowflow_app`、`knowflow_ai` 登录角色，但不设置密码。通过本地 secret manager 或数据库管理流程分别配置这些角色的密码，不把密码写进 SQL 或仓库。

仅在启用 `db-migrate` Spring profile 时，Flyway 才会用独立迁移角色执行版本迁移。Java 服务通过 `database` profile 以 Hikari/`knowflow_app` 连接数据库；文档上传和原文件代理还需 `storage` profile。默认不启用周期索引调度，显式设置 `KNOWFLOW_INDEXING_SCHEDULER_ENABLED=true` 后才会派发任务及处理删除 outbox。密码使用 PBKDF2；8 小时 opaque Bearer token 仅在注册/登录响应中返回，数据库存 SHA-256 摘要；注册冲突响应不回显邮箱或密码，但 409 仍可能暴露邮箱冲突，限速/验证邮箱策略待 M/Q 评估。`knowflow_ai` 只有检索所需表的 SELECT，不能改写状态或直接写 Chunk/向量。draft.5 候选已实现 Java 受控批量写入与原子发布；B 消费确认及 Q 审阅待完成。

从仓库根启动：

```sh
cd services/api
export KNOWFLOW_INTERNAL_SHARED_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
./mvnw verify
./mvnw spring-boot:run
```

首次数据库准备由管理员执行 `psql -X -v ON_ERROR_STOP=1 -h localhost -U <admin> -d knowflow -f services/api/src/main/resources/db/bootstrap-roles.sql`，然后通过安全凭据管理分别设置迁移、应用和 AI 角色密码。在 `services/api` 目录执行迁移：设置 `KNOWFLOW_MIGRATION_DATABASE_URL`、`KNOWFLOW_MIGRATION_DATABASE_USERNAME`、`KNOWFLOW_MIGRATION_DATABASE_PASSWORD`，再运行 `java -jar target/knowflow-api-0.2.0-SNAPSHOT.jar --migrate-only`（开发时可用 `./mvnw spring-boot:run -Dspring-boot.run.main-class=com.knowflow.api.db.DatabaseMigrationApplication`）。迁移历史位于独立 `knowflow_flyway` Schema；迁移不自动清库。

### 独立开发数据库与 MinIO

`compose.dev.yml` 只启动 Java 服务自己的 PostgreSQL/pgvector 与 MinIO，不依赖仓库级 Compose 或修改共享 `infra/`。容器镜像按摘要固定，服务端口仅绑定 `127.0.0.1`；独立 named volume 使用 `knowflow-api-dev-*` 名称。

```sh
cd services/api
cp .env.dev.example .env
# 编辑 .env：为所有本地占位符生成单独的随机值。
docker compose -f compose.dev.yml --env-file .env up -d
set -a
. ./.env
set +a
export KNOWFLOW_MIGRATION_DATABASE_URL=jdbc:postgresql://127.0.0.1:55432/knowflow
export KNOWFLOW_MIGRATION_DATABASE_USERNAME=knowflow_migrator
export KNOWFLOW_MIGRATION_DATABASE_PASSWORD="$KNOWFLOW_DEV_MIGRATOR_PASSWORD"
export KNOWFLOW_DATABASE_URL=jdbc:postgresql://127.0.0.1:55432/knowflow
export KNOWFLOW_DATABASE_USERNAME=knowflow_app
export KNOWFLOW_DATABASE_PASSWORD="$KNOWFLOW_DEV_APP_PASSWORD"
export KNOWFLOW_STORAGE_ENDPOINT=http://127.0.0.1:59000
export KNOWFLOW_STORAGE_BUCKET=knowflow-documents
export KNOWFLOW_STORAGE_ACCESS_KEY="$KNOWFLOW_DEV_MINIO_ROOT_USER"
export KNOWFLOW_STORAGE_SECRET_KEY="$KNOWFLOW_DEV_MINIO_ROOT_PASSWORD"
export KNOWFLOW_STORAGE_REQUEST_TIMEOUT=10s
SPRING_PROFILES_ACTIVE=db-migrate ./mvnw spring-boot:run \
  -Dspring-boot.run.main-class=com.knowflow.api.db.DatabaseMigrationApplication
```

迁移成功后以 `SPRING_PROFILES_ACTIVE=database,storage ./mvnw spring-boot:run` 启动应用。请勿把 `.env` 中的开发凭据用于其他环境。`docker compose ... down` 停止服务；只有要删除本地开发数据时才使用 `down -v`。

MinIO 使用锁定的 `bitnamilegacy/minio:2025.4.22` 镜像摘要 `sha256:50cec18ac4184af4671a78aedd5554942c8ae105d51a465fa82037949046da01`。S3 v4 签名、bucket 建立、对象 put/get/delete、错误凭证与读取上限由 Testcontainers 对真实 MinIO 测试。

对象存储每个请求（包括完整响应正文）的总时限由 `KNOWFLOW_STORAGE_REQUEST_TIMEOUT` 控制，默认 `10s`，允许范围为大于 0 且不超过 `2m`。请求超时后会取消未完成读取；源文件代理和内部索引源读取也不会在访问对象存储期间持有数据库事务。

应用进程连接数据库前，设置 `KNOWFLOW_DATABASE_URL`、`KNOWFLOW_DATABASE_USERNAME=knowflow_app`、`KNOWFLOW_DATABASE_PASSWORD`，并启用 profile：`SPRING_PROFILES_ACTIVE=database ./mvnw spring-boot:run`。当前外部路由包括注册/登录/登出、当前用户、个人知识库、上传/文档列表/文档与任务查询、文档删除、单轮提问、引用查询和原文件代理读取。内部路由包括任务派发所需的健康调用、受控源文件读取、heartbeat、索引批次和 completion；数据库租约与 `fencing` 是唯一写入授权依据。注册/登录 JSON 使用契约版本 `0.2.0-draft.5`。不要将迁移角色凭据用于应用连接。

启用 `database,storage` profile 后，上传只接受经签名/解析检查的 TXT、MD 与 PDF，最大 8 MiB；PDF 最多 200 页，文本最多 200,000 Unicode 码点。上传返回 202 并创建 `QUEUED` 任务。索引 Worker 必须通过 Java source/batch/heartbeat/completion 接口工作；Java 验证 1024 维向量、批次 SHA、租约及数据库事实后才切换 READY 活动索引。`POST /api/v1/knowledge-bases/{id}/questions` 只收 question 字段；Java 构建 READY 索引快照并复核 Python 返回引用，删除后来源和文件代理立即不可见。删除通过数据库 outbox 传播取消并重试物理清理。

`./mvnw verify` 会启动真实的 `pgvector/pgvector:0.8.1-pg16` 测试容器（镜像摘要 `sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337`），因此构建环境需要可用的 Docker daemon。

PowerShell 可先用 `$env:KNOWFLOW_INTERNAL_SHARED_SECRET = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))` 生成进程内值，再运行 `./mvnw.cmd verify` 和 `./mvnw.cmd spring-boot:run`。健康地址为 `http://localhost:8080/actuator/health`；只返回状态，不显示配置或组件详情。问答、索引派发和取消通过受认证的 Java WebClient 调用 AI 服务；部署必须在 Java 与 Python 进程中配置相同的内部共享密钥。

受限开发环境需要通过自己的 Maven `settings.xml` 配置 HTTPS 出站代理；settings 属于本机环境配置，不提交仓库。本会话用 `/tmp/knowflow-maven-settings.xml` 指向执行环境的 Maven 代理完成依赖下载。TLS 验证保持开启。
