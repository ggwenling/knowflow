# Java API 服务（A 所有）

职责：外部认证与 API、资源所有者隔离、文档/任务业务状态、活动索引发布、问答结果权限复核。Java 是用户、文档和任务状态的唯一写入方。

KF2-006 最小服务骨架已建立。当前只公开 `GET /actuator/health`；其余路由默认关闭，登录与业务 API 尚未实现。A 维护 Java、Flyway 与唯一正式契约；Python 服务不写业务状态。

要求 Java 21。服务运行需要 Java 21 JRE；当前编译器插件固定使用 Eclipse Compiler，因而在本开发环境不必另装 `javac`。构建前先设置 `KNOWFLOW_INTERNAL_SHARED_SECRET`（32–256 字符的 Bearer token：ASCII 字母、数字及 `-._~+/`，末尾可有 `=` 填充）；缺失、过短或含空白/控制字符时服务启动失败。`KNOWFLOW_AI_BASE_URL` 默认 `http://localhost:8000`，只校验配置结构，不会在启动时连接 AI 服务。数据库配置仅供后续 KF2-011 使用，当前不读取。真实密钥只能经本地忽略文件或运行环境提供。

从仓库根启动：

```sh
cd services/api
export KNOWFLOW_INTERNAL_SHARED_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
./mvnw verify
./mvnw spring-boot:run
```

PowerShell 可先用 `$env:KNOWFLOW_INTERNAL_SHARED_SECRET = [Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(48))` 生成进程内值，再运行 `./mvnw.cmd verify` 和 `./mvnw.cmd spring-boot:run`。健康地址为 `http://localhost:8080/actuator/health`；只返回状态，不显示配置或组件详情。该骨架不接数据库、不调用模型，也不提供用户登录能力。

受限开发环境需要通过自己的 Maven `settings.xml` 配置 HTTPS 出站代理；settings 属于本机环境配置，不提交仓库。本会话用 `/tmp/knowflow-maven-settings.xml` 指向执行环境的 Maven 代理完成依赖下载。TLS 验证保持开启。
