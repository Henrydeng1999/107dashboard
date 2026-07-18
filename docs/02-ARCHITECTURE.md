# 02 系统架构与安全边界

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

## 部署集成边界

Dashboard 是独立的作业管理和可视化产品。现有 `gpu-*` 命令、SSH ControlMaster 和 tmux 只用于开发阶段验证算力平台行为，以及作为平台运维脚本的参考，不属于 Dashboard 的产品功能，也不应暴露给学生。

Dashboard 后端部署在算力平台服务器上时，最终应通过受控的 Slurm 集成层访问作业系统：

```text
API 请求
  -> 作业服务：校验请求并生成受控作业描述
  -> Slurm 适配器：调用 sbatch/squeue/sacct/scancel
  -> Slurm：提交、调度和记录真正的作业
```

开发和平台运维阶段可以用以下工具验证链路：

- SSH ControlMaster 负责复用认证后的连接；
- tmux 负责在开发调试中保持交互式 shell 或辅助进程；
- `sbatch`/`srun` 负责把计算任务交给 Slurm，而不是在登录节点直接运行；
- `squeue`、`sacct` 和作业日志是 Dashboard 展示作业状态的主要来源。

现有 `gpu-*` 命令可以作为开发和运维验证工具参考，核心模式包括：

1. 检查 ControlMaster 是否存在，不存在时建立后台连接；
2. 检查 tmux session 是否存在，不存在时创建；
3. 使用 `tmux send-keys` 发送受控命令；
4. 使用 `tmux capture-pane` 或日志文件读取输出；
5. 使用 Slurm 命令确认作业状态，而不是只依赖 tmux 是否存在。

Dashboard 的核心数据模型应围绕用户、作业、Slurm Job ID、资源申请、状态和日志建立，不依赖 tmux session。对于普通批处理作业，直接生成受控 `sbatch` 脚本并提交；只有平台管理员明确要求交互式调试时，才在产品外部使用 tmux。

如果部署环境不能让容器直接调用 Slurm，优先设计受控的宿主机代理或作业提交服务，而不是把 SSH 私钥、ControlMaster socket 或 tmux 作为产品运行时依赖挂载进容器。

## 默认部署方式

当前默认采用算力平台用户级环境部署：

- 前端在开发电脑或 CI 中构建为静态文件；
- FastAPI 后端运行在项目独立的 Python 虚拟环境中；
- SQLite 起步，后续按规模评估 PostgreSQL；
- 后端通过受控适配器直接调用宿主机已有的 Slurm 客户端；
- 用户级 systemd 管理服务进程，生产部署需管理员启用 linger 或提供系统级 service；
- 反向代理、HTTPS 和访问域名由平台管理员确认。

容器化保留为可选部署方式，用于未来获得 Rootless Docker 或专用服务节点后的环境封装。Dashboard 不负责运行学生的 Docker 容器，学生计算任务始终由 Slurm 调度到计算节点。

## 产品交互边界

Dashboard 使用结构化表单和明确操作按钮完成作业提交、取消、克隆和日志查看。所有操作都经过参数校验和权限检查，Slurm 状态和数据库记录是事实来源。

AI 仅用于比赛期间辅助团队开发，不进入产品运行时架构，也不参与学生作业的自动决策或执行。

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

当前 Native 提交安全底座采用更窄的比赛原型边界：只接受 `python` 或 `python3` 可执行名和受限参数字符，拒绝 shell 元字符、绝对路径与 `..` 穿越；分区、账户、QoS 和资源通过独立 `sbatch` 参数数组传递。服务端在 `JOB_WORKSPACE_DIRECTORY` 下生成不可覆盖的作业目录与脚本，`sbatch --parsable` 的 Job ID 通过严格格式解析，并先写入本地回执，再将 owner 元数据与成功审计事务化保存。审计只记录状态码和 Job ID，不保存 stderr 或敏感内容。

底层 service 与 HTTP 能力声明保持分离：底层代码存在或平台烟雾测试通过都不会自动开放网页提交，部署开关关闭时 `/api/runtime` 的 Native `submit` 仍为 `false`。

Native HTTP 提交现采用显式部署门：默认 `NATIVE_SUBMISSION_ENABLED=false`，只有有效 UID/owner 启动校验通过且部署方明确开启时，`/api/runtime` 才声明 `submit=true`。每次请求必须带 8–128 位 `Idempotency-Key`；服务端只保存其 SHA-256 摘要和请求摘要，相同键与相同请求返回原 Job，不再次调用 `sbatch`，键复用于不同请求则返回冲突。提交检查与占位在单进程锁内串行执行，活跃作业数来自 Slurm 状态与本地待同步元数据的合并结果，默认上限为 1。

比赛原型部署必须保持单 Uvicorn worker；进程锁不声称提供跨进程并发控制。未来启用多 worker 前，应将“活跃数检查 + 幂等占位”迁移到具备行锁或等价原子语义的共享数据库事务。

## 权限边界

- 学生只能查看自己的作业、日志和资源统计。
- 学生不能通过 API 读取其他用户的路径或作业日志。
- 取消作业前必须校验作业归属。
- 管理员权限和学生权限分开设计。
- 数据库只保存必要的作业元数据，不默认保存密码、Token 或私钥。
- 生产环境密钥通过部署环境注入，不提交到 Git。

### 比赛原型身份方案

107 单账号演示采用“单 Unix 账号模式”。可信身份来自运行 FastAPI 进程的有效操作系统用户，部署配置中的 `DASHBOARD_OWNER` 只用于启动时断言二者一致，不能替代系统身份。浏览器请求参数、Header、Cookie 和前端状态均不得指定或覆盖 Slurm 用户。

正式开放 Native API 前必须同时满足：

1. 启动时读取有效 UID 对应的用户名，并与唯一允许的部署账号一致，不一致则拒绝启动；
2. 所有 `squeue`、`sacct`、`sbatch` 和 `scancel` 都以该进程账号执行，不接受请求方传入用户名；
3. 提交成功后持久化 Dashboard ID、Slurm Job ID、owner、结构化参数和受控日志路径；
4. 详情、日志、统计、取消和克隆前，必须确认 Slurm 记录或受信任元数据中的 owner 与进程账号一致；
5. 日志只能位于服务端生成并规范化后的作业目录，API 不接受文件路径；
6. 服务只监听回环地址或位于受控反向代理之后，不能让客户端绕过认证入口直连。

该方案只用于比赛时单平台账号演示，不等同于多学生认证。未来接入校园 SSO 或平台网关身份时，只有在后端端口不可绕过且代理身份头经过清洗和信任校验后，才能将可信代理身份映射到不同 Slurm 用户。

当前已将有效 UID 用户名解析、部署 owner 精确匹配断言和 SQLite 作业元数据仓库接入应用装配与作业 service。Native 模式只有在有效 UID 与 `DASHBOARD_OWNER` 完全一致时才能创建，默认仅开放列表、详情、用户摘要和资源统计；提交、日志、取消与克隆分别由 `NATIVE_SUBMISSION_ENABLED`、`NATIVE_LOGS_ENABLED`、`NATIVE_CANCEL_ENABLED`、`NATIVE_CLONE_ENABLED` 四个默认关闭门禁独立开放。`squeue`/`sacct` 查询固定传入可信 owner，解析后再次丢弃 Slurm `user` 不一致的记录，详情、usage、日志和控制操作还必须先命中当前 owner 的可见作业。

SQLite 元数据增加 `source=fixture|native` 隔离，避免模拟作业混入真实列表。Slurm 实时状态优先，数据库只补充可信命令、资源申请和时间字段；相同 Slurm Job ID 去重后只返回一条。旧原型数据库会以固定列定义补充 `source`、状态和时间字段，不删除已有记录。

Native 取消只接受纯数字 allocation ID，并仅在当前 owner 的 Slurm 可见状态为 `PENDING` 或 `RUNNING`、持久化元数据也属于同一 owner/source/Job ID 时执行参数数组 `scancel <job_id>`。原始幂等键只计算 SHA-256 摘要，成功重放不会再次取消；审计只保存状态和脱敏结果码。Native 克隆不复用客户端参数，而是从 owner 元数据构造新的 `JobSubmitRequest`，使用来源 Job namespaced idempotency，再走与普通提交相同的校验、并发和审计链。

前端轮询按当前页是否存在 `PENDING`/`RUNNING` 作业在活跃与空闲频率间切换，并在页面隐藏时暂停；状态变化只比较同一 Dashboard Job ID 的前后快照。资源可视化严格区分“分配/申请”“峰值/申请”和“运行时长/时限”，缺失指标显示未知而不是补零。模板只预填现有结构化提交字段，最终仍由后端重新校验；排障提示只基于状态、退出码和 Slurm reason，不能替代日志与平台事实。

Native 全交互部署仍使用同一个 FastAPI 进程、有效 Unix owner 和 SQLite 元数据链。四项能力开关必须同时由部署方启用，回退状态出现时写能力继续自动关闭。前端对活动作业每 3 秒按字节偏移增量跟踪当前日志，并在作业更新时间变化时刷新 usage；命令输入框明确展示窄 `python`/`python3` 策略。集中验收只通过 HTTP 路由操作脚本自己创建的 Job，输出不包含日志正文，完成回执以 `0600` 权限写入未跟踪作业目录并阻止 V1 意外重复执行。

比赛演示可显式启用 `DEMO_FALLBACK_ENABLED`。该模式不在启动时伪装 Native 成功：正常状态继续读取真实 Slurm；只有受控查询抛出已脱敏的数据源不可用错误时，目录层才在冷却期内切换到脱敏 Fixture。`GET /api/runtime` 动态返回 `serving_source=fixture_fallback`、`degraded=true`，前端显示醒目标记。回退目录不允许 Fixture 提交，包装层同时拒绝提交、取消和克隆；恢复探测仅由列表刷新触发，成功后整体切回 Native，避免单次页面中混合真实和演示数据。

真实基础产品部署与演示回退配置严格分离。`deploy/107-native-interactive.env.example` 固定 `SLURM_DATA_SOURCE=native` 与 `DEMO_FALLBACK_ENABLED=false`，启动检查要求所有可见 Job ID 使用 `slurm-` 前缀；Slurm 查询失败时产品显示 API 错误，不用模拟结果掩盖故障。Fixture 仅保留给本地自动化和单独的演示回退验收，不参与用户判断真实作业状态。

## 可靠性要求

- Slurm 是作业状态的事实来源，数据库中的状态是缓存和展示数据。
- API 重启后应能通过 Job ID 恢复作业状态。
- `sacct` 可能存在延迟，前端要显示同步时间和未知状态。
- 日志读取应支持文件不存在、权限不足、作业尚未开始和日志轮转等情况。
- 所有 Slurm 调用都需要超时、错误记录和可诊断的错误响应。

### Native 日志路径

Native 日志 API 不接受客户端路径。后端先确认作业在可信 owner 的 Slurm 可见范围内，再按 owner + Slurm Job ID 查询 `source=native` 元数据。持久化路径必须是绝对路径，且严格匹配 `JOB_WORKSPACE_DIRECTORY/submission-<32位hex>/stdout.log|stderr.log`；拒绝 `..`、工作区外路径、错误文件名、额外嵌套、跨 owner 元数据和改变目录的符号链接。读取使用固定字节上限、同一文件描述符的 `fstat/seek/read`，并要求普通文件；路径和底层系统错误不进入 API 响应。
