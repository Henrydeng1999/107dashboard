# 03 算力平台环境检查结果

## 检查范围

检查时间：2026-07-13。检查对象为中国科学技术大学本科生算力平台登录节点 `tradmin-02`，使用账号 `pb24030760`。本章记录已经获得的实际结果，不要求团队成员重复执行检查命令。

## 系统与资源

```text
操作系统：Ubuntu 24.04.3 LTS
内核：Linux 6.8.0-53-generic
架构：x86_64
CPU：Intel Xeon Silver 4510
逻辑 CPU：48
物理配置：2 sockets, 12 cores/socket, 2 threads/core
内存：125 GiB total, 22 GiB available
Swap：8 GiB
```

存储结果：

```text
/home：983 TB total, 950 TB available, 4% used
/：437 GB total, 96 GB available, 78% used
```

比赛原型的数据、日志和 SQLite 文件可以放在用户 Home 目录。大型计算仍由 Slurm 调度，Dashboard 本身只运行轻量 Web 服务。

## Python 与前端运行时

```text
Python：3.12.3
pip：24.0
venv：可用
ensurepip：可用
SQLite library：3.45.1
OpenSSL：3.0.13
Git：2.43.0
gcc：可用
make：可用
Conda：未安装
Node.js：未安装
npm/pnpm/yarn：未安装
uv：未安装
```

系统 Python 中未预装以下项目依赖：

```text
FastAPI、Uvicorn、SQLAlchemy
NumPy、Pandas、SciPy、scikit-learn
PyTorch、TorchVision、TorchAudio、Transformers
```

这不会阻塞原型。后端可以创建项目独立的 `.venv` 并安装少量 Web 依赖；前端在开发电脑构建后，把静态产物部署到服务器，不要求服务器安装 Node.js。

## Slurm

平台已经安装 Slurm `25.11.2`，当前账号可以直接使用：

```text
/usr/bin/sbatch
/usr/bin/squeue
/usr/bin/sacct
/usr/bin/scancel
/usr/bin/sinfo
/usr/bin/srun
```

Slurm 配置文件 `/etc/slurm/slurm.conf` 可读，集群名称为 `training`，控制节点为 `tradmin-01`。

当前可见资源：

```text
分区             GPU             CPU/node   Memory/node
CPU-6530         RTX5090 x8      128        512000 MB
CPU-8358P        A100 x8         128        1024000 MB
GPU-RTX5090      RTX5090 x8      128        512000 MB
GPU-A100         A100 x8         128        1024000 MB
P107-RTX5090     RTX5090 x8      128        512000 MB
P107-A100        A100 x8         128        1024000 MB
Students         A100/RTX5090 x8 128        512000-1024000 MB
```

检查时账号没有正在运行的作业。Dashboard 可以直接围绕 `sbatch`、`squeue`、`sacct` 和 `scancel` 实现提交、状态、历史、取消和资源统计。

### 当前账号与 QoS 权限

```text
Linux user: pb24030760
uid/gid: 68311
Slurm cluster: training
Default account: stu
Slurm admin level: None
```

当前账号在 `Students` 分区的 association：

```text
Account: stu
Allowed QoS: qos_stu_default, qos_stu_medium_2gpu
Default QoS: qos_stu_medium_2gpu
```

与比赛原型最相关的 QoS 限制：

```text
qos_stu_default:
  MaxWall: 04:00:00
  MaxJobsPerUser: 4
  MaxSubmitPerUser: 10
  MaxTRESPerUser: cpu=4, gpu=1, mem=16G
  Flags: DenyOnLimit

qos_stu_medium_2gpu:
  MaxWall: 1-00:00:00
  MaxTRESPerUser: cpu=24, gpu=2, mem=128G
  Flags: DenyOnLimit
```

账号在多个其他分区存在 association 记录，但分区本身还配置了 `AllowAccounts` 和 `AllowQos`。Dashboard 不能只根据 association 判断可提交范围；比赛原型优先使用已经通过真实作业验证的 `Students + stu + qos_stu_default` 组合。

### 节点状态快照

检查时 `Students` 分区覆盖 `anode05` 至 `anode17`：

```text
anode05: mix, RTX 5090 x8
anode06-anode15: idle, RTX 5090 x8
anode16: mix-, A100 x8
anode17: down*, A100 x8
```

节点状态会实时变化，Dashboard 应通过 `sinfo` 和 `squeue` 动态查询，不能把这份快照写死为产品配置。

### 实际 GPU 作业验证

项目中的 `scripts/check-platform-gpu.sh` 已通过 `sbatch` 提交验证：

```text
Job ID: 21482
Job name: dashboard-env-check
Partition: Students
Account: stu
QoS: qos_stu_default
State: COMPLETED
Exit code: 0:0
Queue wait: 30 seconds
Elapsed: less than 1 second
Allocated node: anode05
Allocated resources: cpu=2, mem=4G, gpu=1, node=1
```

计算节点实际环境：

```text
Node: anode05
Kernel: Linux 6.8.0-53-generic
CPU: Intel Xeon Gold 6530
Logical CPUs: 128
Memory: 503 GiB total, 407 GiB available

GPU: NVIDIA GeForce RTX 5090
GPU memory: 32607 MiB total, 32109 MiB free
Compute capability: 12.0
Driver: 580.159.03
Driver-supported CUDA: 13.0
nvcc toolkit: CUDA 12.0, V12.0.140
CUDA_VISIBLE_DEVICES: 0
Physical Slurm GPU allocation: GPU index 3 mapped to visible device 0
```

计算节点系统 Python 为 `3.12.3`，没有预装 PyTorch：

```text
torch_import=failed: No module named 'torch'
```

这不影响 Dashboard 本身，因为 Dashboard 不在计算节点运行模型。若学生作业需要 PyTorch，应由作业自己的虚拟环境、模块环境或项目依赖提供。

这次验证说明 Dashboard 可以从 Slurm 获取并可视化：排队原因、Job ID、账户、QoS、分区、节点、申请资源、实际分配、运行状态、退出码和耗时。GPU 型号、驱动和显存信息可以通过受控检查作业或用户作业日志补充。

### Native 只读 API 正式验收

2026-07-18，服务器仓库快进到提交 `05a64a3` 后执行 `scripts/check-native-readonly.py`，结果如下：

```text
Unix user: pb24030760
Effective UID: 68311
Mode: native-read-only
Owner check: passed
Visible jobs: 1
Sample Slurm Job ID: 21482
State: COMPLETED
Exit code: 0:0
elapsed_seconds: present
max_rss_kb: present
total_cpu_seconds: present
Script exit code: 0
```

验收期间只执行列表、详情和资源统计查询，没有提交或取消作业，也没有读取作业日志。该证据确认当前提交的有效 UID、部署 owner、Slurm user 校验及 Native 只读 API 在 107 可用；不代表 Native 写操作或真实日志已经开放。

## GPU

登录节点存在 `/usr/bin/nvidia-smi`，但不能连接 NVIDIA 驱动。这个结果符合登录节点不直接提供 GPU 的平台模式；实际 Slurm 作业已经确认计算节点 GPU 正常可用。

Dashboard 不在登录节点执行 GPU 任务。GPU 类型来自 Slurm 分区信息，实际 GPU 使用数据从 Slurm 记录或计算节点作业日志获取。

## 用户级服务

```text
systemd --user：可用并处于 running 状态
XDG_RUNTIME_DIR：/run/user/68311
Linger：no
绑定本地随机端口：成功
文件描述符上限：10240
进程数上限：unlimited
```

服务器没有预装 Nginx、Caddy、Apache 或 Lighttpd。比赛演示阶段可以让 FastAPI/Uvicorn 同时提供 API 和前端静态文件，并通过 SSH 端口转发访问。

`Linger=no` 表示用户退出后 systemd 用户服务不保证长期运行。比赛演示阶段可以使用现有 SSH ControlMaster 和 tmux 保持开发服务；tmux 只是开发运维工具，不属于 Dashboard 产品功能。

## Docker

```text
Docker CLI：29.1.5
Docker Compose：5.0.1
系统 Docker socket：存在
当前用户访问系统 Docker daemon：Permission denied
RootlessKit：已安装
slirp4netns：已安装
Podman/Buildah/nerdctl：未安装
当前账号 subuid/subgid：未配置
user namespace：Operation not permitted
Rootless Docker 用户服务：未配置
```

因此比赛原型不采用 Docker 作为前置条件。容器化可以作为产品后续部署能力写入演进路线，但当前直接使用 Python 虚拟环境更快、更贴合平台。

## 网络

```text
Gitee DNS：正常
GitHub DNS：正常
Gitee HTTPS：HTTP 200
GitHub HTTPS：可访问
```

平台可以访问公开代码仓库，适合通过 Git 拉取原型代码。

## 比赛原型结论

当前环境足以支持比赛 MVP：

```text
开发电脑构建 React 静态前端
        -> 上传或 Git 拉取到平台
        -> Python venv 运行 FastAPI/Uvicorn
        -> FastAPI 提供静态页面和 API
        -> 原生调用 Slurm 命令
        -> SQLite 保存演示所需元数据
```

比赛阶段重点展示完整故事闭环：学生填写作业参数并提交 Slurm，Dashboard 展示作业状态、日志、克隆入口和资源统计，降低命令行使用门槛。

多用户真实身份委托、统一认证、生产级 HTTPS、长期服务托管、PostgreSQL 和容器化部署属于赛后演进，不阻塞当前原型。
