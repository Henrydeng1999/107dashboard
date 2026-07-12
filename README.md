# 107 Dashboard

面向学生的算力平台作业管理与可视化 Dashboard。

项目目标是通过一个简单的 Web 服务，降低 Slurm 算力平台的使用门槛，让学生可以在网页中完成作业提交、状态查看、日志查看、作业克隆和基础资源统计。

## 目标功能

- 学生身份识别与基础权限控制
- 作业提交与参数校验
- 作业列表、状态和详情查看
- 实时或近实时日志查看
- 作业取消与作业克隆
- GPU、CPU、内存和运行时长统计
- Docker 化部署
- 对接 Slurm 作业系统

## 初步技术方案

| 部分 | 方案 |
| --- | --- |
| 前端 | React + Vite + TypeScript |
| 后端 | FastAPI + Python |
| 作业调度 | Slurm (`sbatch`、`squeue`、`sacct`、`scancel`) |
| 数据库 | SQLite 起步，生产环境预留 PostgreSQL |
| 实时日志 | HTTP 轮询起步，后续可升级 WebSocket |
| 部署 | Docker Compose |
| 反向代理 | Nginx 或 Traefik，按部署环境决定 |

## 目录规划

```text
107dashboard/
├── backend/              # FastAPI 服务，后续创建
├── frontend/             # React 前端，后续创建
├── docs/
│   ├── PLAN.md           # 分阶段开发计划
│   └── ARCHITECTURE.md   # 架构与安全边界
├── deploy/               # Docker、反向代理和部署配置，后续创建
├── .env.example          # 环境变量模板，后续创建
└── README.md
```

## 本地开发依赖

- Git
- Docker Engine
- Docker Compose Plugin
- Node.js LTS 与 npm/pnpm
- Python 3.11 或更新版本
- 可选：本地 Slurm 环境，或者用于开发的 Slurm 命令 mock

正式开发时，前端和后端依赖分别维护在：

- `frontend/package.json`
- `backend/pyproject.toml`

依赖文件和 Docker 镜像应固定主要版本，避免不同开发者环境产生不可重复的问题。

## 部署原则

生产部署使用 Docker 容器，但 Web 服务不直接在登录节点执行用户命令。后端只负责校验参数、生成受控的 Slurm 作业描述并提交作业；实际训练或计算任务由 Slurm 调度到计算节点执行。

推荐的服务关系：

```text
浏览器 -> 反向代理 -> Dashboard API -> Slurm
                             └-------> 数据库
```

## 当前状态

当前仓库处于初始化阶段，暂不包含具体业务代码。开发计划见 [docs/PLAN.md](docs/PLAN.md)，架构和安全边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

算力平台环境检查命令见 [docs/ENVIRONMENT_CHECK.md](docs/ENVIRONMENT_CHECK.md)。

## 协作约定

- 功能开发前先在 `docs/PLAN.md` 中记录目标和验收标准。
- 一个提交尽量只解决一个明确问题。
- 不提交密码、Token、SSH 私钥、生产环境配置或真实用户数据。
- 所有来自用户的作业参数都必须经过后端校验，禁止直接拼接 shell 命令。
