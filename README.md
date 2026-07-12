# 107 Dashboard

面向学生的算力平台作业管理与可视化 Dashboard。

项目目标是通过一个简单清晰的 Web 服务降低 Slurm 算力平台的使用门槛，让学生可以完成作业提交、状态查看、日志查看、作业克隆和资源使用统计。

## 目标功能

- 学生身份识别与基础权限控制
- 作业提交与参数校验
- 作业列表、状态和详情查看
- 实时或近实时日志查看
- 作业取消与作业克隆
- GPU、CPU、内存和运行时长统计
- 对接 Slurm 作业系统

## 初步技术方案

| 部分 | 方案 |
| --- | --- |
| 前端 | React + Vite + TypeScript |
| 后端 | FastAPI + Python |
| 作业调度 | Slurm (`sbatch`、`squeue`、`sacct`、`scancel`) |
| 数据库 | SQLite 起步，生产环境预留 PostgreSQL |
| 实时日志 | HTTP 轮询起步，后续可升级 WebSocket |
| 默认部署 | 算力平台用户级 Python 虚拟环境 + 静态前端 |
| 服务管理 | 用户级 systemd；生产环境需管理员启用持久运行 |
| 容器化 | 保留为可选部署方案，不作为当前前置条件 |

## 目录规划

```text
107dashboard/
├── backend/              # FastAPI 服务，后续创建
├── frontend/             # React 前端，后续创建
├── docs/
│   ├── 01-PLAN.md        # 分阶段开发计划
│   ├── 02-ARCHITECTURE.md # 架构与安全边界
│   ├── 03-ENVIRONMENT_CHECK.md # 算力平台环境检查
│   └── 04-COLLABORATION.md # 四人团队协作方案
├── deploy/               # 用户级服务和可选容器配置，后续创建
├── .env.example          # 环境变量模板，后续创建
└── README.md
```

## 本地开发依赖

- Git
- Node.js LTS 与 npm/pnpm
- Python 3.11 或更新版本
- 可选：本地 Slurm 环境，或者用于开发的 Slurm 命令 mock

正式开发时，前端和后端依赖分别维护在：

- `frontend/package.json`
- `backend/pyproject.toml`

前端在开发电脑或 CI 中构建为静态文件；后端在算力平台使用项目独立的 Python 虚拟环境。依赖文件应固定主要版本，避免不同开发者环境产生不可重复的问题。

## 部署原则

当前默认部署使用算力平台用户级 Python 虚拟环境，直接复用平台已有的 Slurm 客户端。Web 服务不在登录节点执行学生计算任务；后端只负责接收请求、校验参数、生成受控的 Slurm 作业描述并提交，实际训练或计算任务由 Slurm 调度到计算节点执行。

推荐的服务关系：

```text
浏览器 -> 反向代理 -> Dashboard API -> Slurm
                             └-------> 数据库
```

## 当前状态

当前仓库处于初始化阶段，暂不包含具体业务代码。按章节顺序阅读：[01 开发计划](docs/01-PLAN.md)、[02 系统架构](docs/02-ARCHITECTURE.md)、[03 环境检查](docs/03-ENVIRONMENT_CHECK.md)、[04 团队协作](docs/04-COLLABORATION.md)。

算力平台的实际环境检查结果见 [03 环境检查](docs/03-ENVIRONMENT_CHECK.md)。

当前目标是完成可演示的比赛 MVP，优先打通“填写作业参数 -> 提交 Slurm -> 查看状态与日志 -> 克隆作业 -> 查看资源统计”的完整闭环。生产级多用户委托、统一认证和容器化部署放入赛后演进路线。

比赛鼓励使用 AI 辅助项目开发。本项目会使用 AI 协助需求整理、代码编写、文档维护、测试和问题排查，但 AI 不属于 Dashboard 的产品功能。

## 协作约定

- 功能开发前先在 `docs/01-PLAN.md` 中记录目标和验收标准。
- 一个提交尽量只解决一个明确问题。
- 不提交密码、Token、SSH 私钥、生产环境配置或真实用户数据。
- 所有来自用户的作业参数都必须经过后端校验，禁止直接拼接 shell 命令。
