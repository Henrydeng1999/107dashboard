# Backend

FastAPI 后端目录。后端负责参数校验、作业管理、Slurm 调用、日志读取和元数据持久化。

主要结构：

```text
app/api/           HTTP 路由和请求入口
app/core/          配置、日志、错误和公共基础设施
app/models/        数据库模型
app/repositories/  数据访问
app/schemas/       API 请求与响应结构
app/services/      业务流程
app/slurm/         Slurm 命令适配和输出解析
migrations/        数据库迁移
tests/             后端单元与集成测试
```

路由层不直接拼接 shell 命令；所有 Slurm 操作统一经过 `app/slurm/` 和业务服务层。
