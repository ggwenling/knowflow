# infra（M 所有）

本地编排与部署配置。基础版本暂不引入 Redis。

## 当前状态：KF2-009 草案，未验收

- `docker-compose.yml` 为草案：编排 PostgreSQL/pgvector、MinIO 与三端服务，含持久卷、健康检查与依赖启动。
- 草案不等于完成：`services/api`、`services/ai` 尚不在 next 分支（只在 java/python 分支有骨架），
  真实三端启动需等 006/007/008 落地与集成；本机无 Docker，`docker compose config` 与启动/停止/重启验证尚未执行。
- 安全边界：AI、数据库、对象存储不作为公开浏览器入口（Compose 只发布 web:3000 与 api:8080）；
  模型凭证通过运行配置注入，不得写入编排文件；文件中的默认值仅为本地开发占位，生产必须替换。

## 未来运行（条件齐备后）

```sh
docker compose up --build
docker compose ps
docker compose down
```

完整验收以 KF2-009 任务卡为准；验收前不得把草案说成已打通。
