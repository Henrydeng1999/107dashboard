# 107 Dashboard

面向学生的算力平台作业管理与可视化 Dashboard。

在线项目文档：[https://henrydeng1999.github.io/107dashboard/](https://henrydeng1999.github.io/107dashboard/)

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
├── backend/              # FastAPI、数据模型和 Slurm 适配
├── frontend/             # React 前端
├── deploy/               # 用户级服务和可选反向代理配置
├── docs/
│   ├── 01-PLAN.md        # 分阶段开发计划
│   ├── 02-ARCHITECTURE.md # 架构与安全边界
│   ├── 03-ENVIRONMENT_CHECK.md # 算力平台环境检查
│   ├── 04-COLLABORATION.md # 四人团队协作方案
│   ├── 05-DIRECTORY-STRUCTURE.md # 项目目录规范
│   ├── 06-PLATFORM-DEPLOYMENT.md # 算力平台部署与更新
│   ├── 07-MVP-API-DESIGN.md # MVP 作业模型与 API 设计
│   └── 08-PROGRESS-CHECKLIST.md # 项目进度与功能检查表
├── examples/             # 可公开的示例作业
├── fixtures/             # 脱敏 mock 数据
├── scripts/              # 平台检查和维护脚本
├── tests/                # 端到端测试
├── .env.example          # 环境变量模板
└── README.md
```

## 项目入口

新成员或开发 Agent 进入项目后，从以下入口开始：

| 入口 | 用途 |
| --- | --- |
| `AGENTS.md` | Agent 工作约束、平台事实和验证要求 |
| `docs/01-PLAN.md` | 比赛 MVP 阶段、范围和验收标准 |
| `docs/02-ARCHITECTURE.md` | 产品架构、Slurm 集成和安全边界 |
| `docs/03-ENVIRONMENT_CHECK.md` | 已验证的服务器、QoS、GPU 和用户权限 |
| `docs/04-COLLABORATION.md` | 四人分工、Gitee 工作流和演示保障 |
| `docs/05-DIRECTORY-STRUCTURE.md` | 文件归属和目录扩展规则 |
| `docs/06-PLATFORM-DEPLOYMENT.md` | 算力平台只读部署、更新和安全操作 |
| `docs/07-MVP-API-DESIGN.md` | MVP 作业模型、状态与 API 契约 |
| `docs/08-PROGRESS-CHECKLIST.md` | 彩色项目进度与已完成功能检查表 |
| `backend/README.md` | FastAPI 后端目录说明 |
| `frontend/README.md` | React 前端目录说明 |
| `deploy/README.md` | 用户级服务和部署配置说明 |
| `fixtures/README.md` | 脱敏 mock 数据说明 |
| `examples/README.md` | 示例 Slurm 作业说明 |
| `tests/README.md` | 测试分层和端到端测试说明 |

在线文档站入口是 `docs/index.html`。GitHub Pages 可以直接选择 `master` 分支的 `/docs` 目录发布；页面会按导航选择动态读取同目录的 Markdown，每次仅展示一个章节，文档更新后不需要重新生成 HTML。

GitHub Pages 发布设置：

```text
Source: Deploy from a branch
Branch: master
Folder: /docs
```

本地预览不能直接双击 `index.html`，需要从仓库根目录启动静态服务器：

```bash
python3 -m http.server 8765 --directory docs
```

然后访问 `http://127.0.0.1:8765/`。

开发时先确认任务属于哪个目录，再创建文件。新增一级目录前必须同步更新 [05 目录规范](docs/05-DIRECTORY-STRUCTURE.md)。

## 本地开发依赖

- Git
- Node.js LTS 与 npm/pnpm
- Python 3.12
- 可选：本地 Slurm 环境，或者用于开发的 Slurm 命令 mock

依赖定义位于 `backend/pyproject.toml`、`backend/requirements.txt` 和
`frontend/package.json`；根目录 `environment.yml` 仅作为可选 Conda 导入入口。

### 初始化后端虚拟环境

```powershell
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install --upgrade pip
backend/.venv/Scripts/python -m pip install -r backend/requirements.txt
```

Linux/算力平台对应命令为 `python3.12 -m venv backend/.venv`，激活后执行
`python -m pip install -r backend/requirements.txt`。`.venv`、前端
`node_modules` 和构建产物均已加入 `.gitignore`。

前端依赖安装与构建：

```bash
cd frontend
npm install
npm run build
```

启动最小骨架：

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --reload
```

然后访问 `http://127.0.0.1:8000/docs` 查看 API 文档，或在 `frontend` 目录执行
`npm run dev` 打开前端页面。健康检查接口为 `GET /api/health`。

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

当前仓库已经完成前后端最小骨架、完整 Fixture MVP 故事，以及受有效 Unix UID、部署 owner 和 Slurm user 三层约束的 Native 只读链路。Native 模式开放列表、详情、用户摘要和资源统计；提交、取消、克隆和日志仍在服务端关闭，前端也会读取 `/api/runtime` 隐藏这些操作。SQLite 元数据按 Fixture/Native 来源隔离，并与 Slurm 实时状态去重合并。提交 `05a64a3` 已于 2026-07-18 在 107 使用账号 `pb24030760` 完成正式只读验收；提交安全底座随后在 `88a0147` 上完成唯一一次最小真实作业验收，Job `24011` 以 `1 CPU / 512 MiB / 0 GPU / 1 分钟` 正常完成并返回 `0:0`，元数据、回执和审计均已持久化。Native HTTP 写能力仍未开放。按章节顺序阅读：[01 开发计划](docs/01-PLAN.md)、[02 系统架构](docs/02-ARCHITECTURE.md)、[03 环境检查](docs/03-ENVIRONMENT_CHECK.md)、[04 团队协作](docs/04-COLLABORATION.md)、[05 目录规范](docs/05-DIRECTORY-STRUCTURE.md)、[06 平台部署](docs/06-PLATFORM-DEPLOYMENT.md)、[07 MVP API 设计](docs/07-MVP-API-DESIGN.md)。

算力平台的实际环境检查结果见 [03 环境检查](docs/03-ENVIRONMENT_CHECK.md)。

当前目标是完成可演示的比赛 MVP，优先打通“填写作业参数 -> 提交 Slurm -> 查看状态与日志 -> 克隆作业 -> 查看资源统计”的完整闭环。生产级多用户委托、统一认证和容器化部署放入赛后演进路线。

比赛鼓励使用 AI 辅助项目开发。本项目会使用 AI 协助需求整理、代码编写、文档维护、测试和问题排查，但 AI 不属于 Dashboard 的产品功能。

## 协作约定

- 功能开发前先在 `docs/01-PLAN.md` 中记录目标和验收标准。
- 一个提交尽量只解决一个明确问题。
- 不提交密码、Token、SSH 私钥、生产环境配置或真实用户数据。
- 所有来自用户的作业参数都必须经过后端校验，禁止直接拼接 shell 命令。
