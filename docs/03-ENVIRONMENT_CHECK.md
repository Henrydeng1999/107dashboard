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

## GPU

登录节点存在 `/usr/bin/nvidia-smi`，但不能连接 NVIDIA 驱动。这个结果符合登录节点不直接提供 GPU 的平台模式，不代表计算节点没有 GPU。

Dashboard 不在登录节点执行 GPU 任务。GPU 类型来自 Slurm 分区信息，实际 GPU 使用数据后续从 Slurm 记录或计算节点作业日志获取。

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
