# Java API 服务（A 所有）

职责：外部认证与 API、资源所有者隔离、文档/任务业务状态、活动索引发布、问答结果权限复核。Java 是用户、文档和任务状态的唯一写入方。

KF2-006 最小服务骨架已建立。当前只公开 `GET /actuator/health`；其余路由默认关闭，登录与业务 API 尚未实现。A 维护 Java、Flyway 与唯一正式契约；Python 服务不写业务状态。

要求 Java 21。服务运行需要 Java 21 JRE；当前编译器插件固定使用 Eclipse Compiler，因而在本开发环境不必另装 `javac`。构建前先设置 `KNOWFLOW_INTERNAL_SHARED_SECRET`（32–256 字符的 Bearer token：ASCII 字母、数字及 `-._~+/`，末尾可有 `=` 填充）；缺失、过短或含空白/控制字符时服务启动失败。`KNOWFLOW_AI_BASE_URL` 默认 `http://localhost:8000`，只校验配置结构，不会在启动时连接 AI 服务。

KF2-011 使用 Flyway、PostgreSQL 16 和 pgvector 0.8.1。先由数据库管理员创建数据库并执行 `src/main/resources/db/bootstrap-roles.sql`；该脚本安装 `vector` 扩展、建立隔离 Schema 和 `knowflow_migrator`、`knowflow_app`、`knowflow_ai` 登录角色，但不设置密码。通过本地 secret manager 或数据库管理流程分别配置这些角色的密码，不把密码写进 SQL 或仓库。

仅在启用 `db-migrate` Spring profile 时，Flyway 才会用独立迁移角色执行版本迁移。Java 服务可通过 `database` Spring profile 启用 Hikari 应用 DataSource，使用单独的 `KNOWFLOW_DATABASE_*` 凭据连接 `knowflow_app`；默认不连接数据库。当前还没有业务 Repository/API。`knowflow_ai` 只有读取检索所需表的权限，不能改写文档/任务状态或直接写入 Chunk/向量。Java 侧提出在 KF2-018 通过带 fencing 的受控批量网关接收索引写入，仍待 B/Q 确认。

从仓库根启动：

```sh
cd services/api
export KNOWFLOW_INTERNAL_SHARED_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
./mvnw verify
./mvnw spring-boot:run
```

首次数据库准备由管理员执行 `psql -X -v ON_ERROR_STOP=1 -h localhost -U <admin> -d knowflow -f services/api/src/main/resources/db/bootstrap-roles.sql`，然后通过安全凭据管理分别设置迁移、应用和 AI 角色密码。在 `services/api` 目录执行迁移：设置 `KNOWFLOW_MIGRATION_DATABASE_URL`、`KNOWFLOW_MIGRATION_DATABASE_USERNAME`、`KNOWFLOW_MIGRATION_DATABASE_PASSWORD`，再运行 `java -jar target/knowflow-api-0.2.0-SNAPSHOT.jar --migrate-only`（开发时可用 `./mvnw spring-boot:run -Dspring-boot.run.main-class=com.knowflow.api.db.DatabaseMigrationApplication`）。迁移历史位于独立 `knowflow_flyway` Schema；迁移不自动清库。

应用进程连接数据库前，设置 `KNOWFLOW_DATABASE_URL`、`KNOWFLOW_DATABASE_USERNAME=knowflow_app`、`KNOWFLOW_DATABASE_PASSWORD`，并启用 profile：`SPRING_PROFILES_ACTIVE=database ./mvnw spring-boot:run`。不要将迁移角色凭据用于应用连接。

`./mvnw verify` 会启动真实的 `pgvector/pgvector:0.8.1-pg16` 测试容器（镜像摘要 `sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337`），因此构建环境需要可用的 Docker daemon。

PowerShell 可先用 `$env:KNOWFLOW_INTERNAL_SHARED_SECRET = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))` 生成进程内值，再运行 `./mvnw.cmd verify` 和 `./mvnw.cmd spring-boot:run`。健康地址为 `http://localhost:8080/actuator/health`；只返回状态，不显示配置或组件详情。当前骨架不调用模型，也不提供用户登录或业务 API；启用 database profile 后 DataSource 可连接，尚无业务读写实现。

受限开发环境需要通过自己的 Maven `settings.xml` 配置 HTTPS 出站代理；settings 属于本机环境配置，不提交仓库。本会话用 `/tmp/knowflow-maven-settings.xml` 指向执行环境的 Maven 代理完成依赖下载。TLS 验证保持开启。
