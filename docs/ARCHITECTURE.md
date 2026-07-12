# 架构与安全边界

## 服务关系

```text
浏览器
  |
  v
反向代理 / HTTPS
  |
  v
Dashboard API
  |              \
  |               +--> 数据库：用户、作业元数据、状态快照
  v
Slurm 接口
  |
  +--> sbatch：提交作业
  +--> squeue：查询排队和运行状态
  +--> sacct：查询历史状态和资源统计
  +--> scancel：取消作业
```

## SSH ControlMaster 与 tmux

Dashboard 后端部署在算力平台服务器上时，可以复用现有的 SSH/命令包装模式：

```text
API 请求
  -> 连接管理器：检查或建立 SSH ControlMaster
  -> 复用 ControlPath 执行远程命令
  -> tmux：保持需要长期运行的交互会话
  -> Slurm：提交、调度和记录真正的作业
```

这四层职责不同：

- `ControlMaster` 负责复用认证后的 SSH 连接，避免每次命令重新登录；
- `tmux` 负责在 SSH 断开后保持交互式 shell 或辅助进程；
- `sbatch`/`srun` 负责把计算任务交给 Slurm，而不是在登录节点直接运行；
- `squeue`、`sacct` 和作业日志是 Dashboard 展示作业状态的主要来源。

现有 `gpu-*` 命令可以作为连接层和会话层的参考，核心模式包括：

1. 检查 ControlMaster 是否存在，不存在时建立后台连接；
2. 检查 tmux session 是否存在，不存在时创建；
3. 使用 `tmux send-keys` 发送受控命令；
4. 使用 `tmux capture-pane` 或日志文件读取输出；
5. 使用 Slurm 命令确认作业状态，而不是只依赖 tmux 是否存在。

Dashboard 中不建议所有用户共用一个 tmux session。推荐使用可追踪的会话名，例如：

```text
dashboard-u<user_id>-j<job_id>
```

作业提交后，应保存 `job_id`、tmux session 名称、工作目录和日志路径之间的映射。对于普通批处理作业，优先直接生成受控 `sbatch` 脚本并提交；只有需要交互式调试、保持 `srun` 分配或运行长期辅助进程时才使用 tmux。

后端需要对 tmux 和 SSH 命令增加超时、退出码检查、并发锁和清理逻辑，避免两个 API 请求同时创建同一个 session 或向同一个窗口发送相互覆盖的命令。

## 容器部署

初步计划使用 Docker Compose 管理：

- `frontend`：构建后的前端静态资源，或由反向代理直接托管；
- `api`：FastAPI 后端；
- `db`：开发阶段可使用 SQLite，生产环境优先 PostgreSQL；
- `proxy`：处理 HTTPS、静态资源和 API 转发。

Slurm 命令、日志目录和用户目录通过明确的只读或受限挂载提供给后端。不能把整台服务器的根目录或任意用户目录挂进容器。

## 作业提交流程

```text
用户填写结构化参数
  -> API 校验身份和资源限制
  -> 生成临时 sbatch 描述
  -> 提交 sbatch
  -> 保存 Slurm Job ID 和作业元数据
  -> 后台同步 squeue/sacct 状态
  -> 前端查询状态和日志
```

后端不应把用户输入直接拼接成一条 shell 命令。命令、参数、环境变量和资源申请应分别经过白名单、类型检查和长度限制。

## 权限边界

- 学生只能查看自己的作业、日志和资源统计。
- 学生不能通过 API 读取其他用户的路径或作业日志。
- 取消作业前必须校验作业归属。
- 管理员权限和学生权限分开设计。
- 数据库只保存必要的作业元数据，不默认保存密码、Token 或私钥。
- 生产环境密钥通过部署环境注入，不提交到 Git。

## 可靠性要求

- Slurm 是作业状态的事实来源，数据库中的状态是缓存和展示数据。
- API 重启后应能通过 Job ID 恢复作业状态。
- `sacct` 可能存在延迟，前端要显示同步时间和未知状态。
- 日志读取应支持文件不存在、权限不足、作业尚未开始和日志轮转等情况。
- 所有 Slurm 调用都需要超时、错误记录和可诊断的错误响应。
