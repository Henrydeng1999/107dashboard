# 06 算力平台部署与更新

## 用途

算力平台上的项目副本用于运行和演示 Dashboard，并通过 Gitee 部署公钥以只读方式获取代码。服务器不使用个人 Gitee 私钥，也不能向仓库推送代码。

## 已完成配置

```text
平台账号：pb24030760
项目目录：/home/scc/pb24030760/107dashboard
远程仓库：git@gitee-107dashboard:tuilichaoshi/107dashboard.git
部署权限：clone、fetch、pull
写入权限：无
```

部署公钥文件：

```text
私钥：~/.ssh/id_ed25519_107dashboard_deploy
公钥：~/.ssh/id_ed25519_107dashboard_deploy.pub
指纹：SHA256:wkBSydGFIE0c0n9R2KDnmB24LsKHHErT1inYSYmrN4U
```

私钥只保存在算力平台，不能进入 Git、文档、Issue、群聊或其他机器。

## SSH 配置

算力平台的 `~/.ssh/config` 使用项目专用别名：

```sshconfig
Host gitee-107dashboard
    HostName gitee.com
    User git
    IdentityFile ~/.ssh/id_ed25519_107dashboard_deploy
    IdentitiesOnly yes
```

测试部署公钥认证：

```bash
ssh -T gitee-107dashboard
```

正常结果会显示 `Anonymous (DeployKey)`，并说明部署公钥只支持 `pull/fetch`。Gitee 不提供交互式 SSH shell，这不是错误。

## 首次克隆

服务器首次部署使用：

```bash
git -c protocol.version=0 clone \
  git@gitee-107dashboard:tuilichaoshi/107dashboard.git \
  ~/107dashboard

git -C ~/107dashboard config protocol.version 0
git -C ~/107dashboard config pull.ff only
```

Gitee 部署公钥与 Git protocol v2 曾出现 `expected flush after ref listing` 兼容问题，因此该部署副本固定使用 protocol v0。

## 日常更新

从任意目录执行：

```bash
git -C ~/107dashboard pull --ff-only
```

或者：

```bash
cd ~/107dashboard
git pull --ff-only
```

`--ff-only` 确保服务器部署副本只向前更新，不创建本地合并提交。

## 更新前检查

```bash
git -C ~/107dashboard status --short --branch
git -C ~/107dashboard remote -v
```

正常状态应类似：

```text
## master...origin/master
origin git@gitee-107dashboard:tuilichaoshi/107dashboard.git
```

如果服务器目录出现本地修改，不要直接覆盖或重置。先确认修改来源，并将需要保留的内容转移到正确的开发分支或运行时目录。

## 文档站

项目在线文档由 GitHub Pages 发布：

```text
https://henrydeng1999.github.io/107dashboard/
```

对应源码位于：

```text
~/107dashboard/docs/index.html
~/107dashboard/docs/site.css
~/107dashboard/docs/site.js
~/107dashboard/docs/*.md
```

网页会动态读取 Markdown。修改手册并推送后，不需要重新生成 HTML。

## 原型服务运行原则

- Dashboard 使用项目独立 Python 虚拟环境；
- 前端静态文件在开发电脑构建后随仓库部署；
- FastAPI 可以同时提供 API 和静态文件；
- Dashboard 只在登录节点运行轻量 Web 服务；
- 学生计算任务必须通过 `sbatch` 提交到计算节点；
- 比赛演示阶段可以用 tmux 保持 Web 服务，tmux 不属于产品功能；
- SQLite、日志、临时作业脚本和虚拟环境不提交到 Git。

默认 `DATABASE_URL=sqlite:///./data/dashboard.sqlite3` 会由后端解析为仓库根目录下的 `data/dashboard.sqlite3`，首次应用装配时自动创建父目录和表。测试固定使用线程安全的内存 SQLite，不会复用部署数据库；服务器上的 `data/` 必须保留为运行时目录，不能提交到 Git。

## Native 只读验收

当前 Native 模式只开放作业列表、详情、用户摘要和资源统计。验收脚本不会提交或取消作业，也不会读取日志；它只通过 API 执行 `squeue`、`sacct` 对应的只读查询，并检查返回记录均属于后端进程的有效 Unix 用户。

更新服务器副本并执行：

```bash
cd ~/107dashboard
git pull --ff-only

export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"

backend/.venv/bin/python scripts/check-native-readonly.py
```

通过时脚本输出 JSON 证据，包括模式、owner 检查、可见作业数、抽样 Job ID、状态、退出码和资源字段是否存在。空队列也是合法结果，此时 `total_jobs=0`、`sample=null`。若有效 UID 与 `DASHBOARD_OWNER` 不一致、Slurm 命令缺失/超时/失败、响应混入其他 owner，脚本会以非零状态退出。

验收后启动 Web 服务时使用同一组环境变量。`GET /api/runtime` 应返回 `data_source=native`、`read_only=true`；Native 前端会隐藏新建、取消、克隆和日志入口。不要为了测试按钮而开启写操作。

2026-07-18 已在 107 对提交 `05a64a3` 完成本流程：有效用户 `pb24030760`（UID `68311`），owner 检查通过，读取到真实作业 `21482`，状态 `COMPLETED`、退出码 `0:0`，`elapsed_seconds`、`max_rss_kb`、`total_cpu_seconds` 均存在，脚本退出码为 0。验收没有执行任何写操作或日志读取。

## Native 提交无写入预检

底层提交安全底座可独立于 HTTP 路由执行无写入预检。更新代码后运行：

```bash
cd ~/107dashboard
git pull --ff-only

export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"

backend/.venv/bin/python scripts/check-native-submit-preflight.py
```

预检只检查有效 Unix 身份、`sbatch` 是否可发现、数据库与作业目录父级访问权限，以及最小请求能否生成安全参数计划。脚本不会创建目录、写数据库或调用 `sbatch`，输出中的 `would_invoke_sbatch` 必须为 `false`。

预检通过后也不能直接开放网页提交。下一步必须由项目管理员重新明确授权，再通过未接入 HTTP 的受控 service 提交一次 `1 CPU / 512 MiB / 0 GPU / 1 分钟`、命令为 `python3 --version` 的最小作业，并记录 Job ID、资源、状态和退出码。没有该次授权时，只停留在预检阶段。

获得明确授权后，使用固定的一次性验收入口：

```bash
backend/.venv/bin/python scripts/submit-native-smoke-test.py \
  --confirm SUBMIT-ONE-MINIMAL-NATIVE-JOB
```

该脚本不接受命令或资源覆盖参数，并在作业目录中发现已有真实提交回执时拒绝重复运行。它只提交作业并保存 Job ID、元数据和审计，不读取 stdout/stderr、不取消作业，也不会开放 HTTP 提交。随后使用输出的 Job ID 执行只读 `sacct` 验证最终状态与退出码。

2026-07-18 已在 107 对提交 `88a0147` 完成唯一一次真实最小作业验收：Dashboard ID `submission-e095de46b95e441cbeef29c96a0bc6b9`，Slurm Job ID `24011`，owner `pb24030760`，命令 `python3 --version`，请求 `1 CPU / 512 MiB / 0 GPU / 1 分钟`。作业状态为 `COMPLETED`、退出码为 `0:0`；元数据、Job ID 回执和 `PREPARED -> SUCCEEDED` 审计均已持久化。验收未读取日志、未取消作业、未进行第二次提交，HTTP 提交能力保持关闭。

## Native HTTP 提交门禁检查

受控路由默认关闭。拉取包含该功能的提交后，可在临时 shell 中显式启用并运行无 `sbatch` 检查：

```bash
export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"
export NATIVE_SUBMISSION_ENABLED=true
export NATIVE_MAX_ACTIVE_JOBS=1

backend/.venv/bin/python scripts/check-native-submit-api-gate.py
```

脚本会初始化必要的 SQLite 表，读取 `/api/runtime`，并验证缺少幂等键返回 `400`、含 shell 语法的命令返回 `422`。两次请求都在活跃作业查询和 `sbatch` 之前失败，因此不会创建 Slurm 作业；输出中的 `would_invoke_sbatch` 必须为 `false`。平台检查完成前不要把开关写入长期服务配置。比赛原型启用后只运行单个 Uvicorn worker。

2026-07-18 已在 107 对提交 `0f88ede` 完成本检查：有效用户 `pb24030760`（UID `68311`），`runtime_submit=true`，缺少幂等键返回 `400`，Shell 语法命令返回 `422`，取消、克隆和日志能力均为 `false`，`would_invoke_sbatch=false`。临时开关只存在于验收 shell，没有写入长期服务配置；运行时 `data/` 证据保持未跟踪且未被修改或删除。

## Native 日志路径无读取预检

日志能力默认关闭。代码更新后，可先只验证 Job `24011` 的持久化路径，不打开或读取日志文件：

```bash
export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"
export NATIVE_LOGS_ENABLED=true

backend/.venv/bin/python scripts/check-native-log-path-preflight.py --job-id 24011
```

通过时 `stdout_path_safe`、`stderr_path_safe` 为 `true`，且 `would_open_log=false`、`would_read_log=false`。该检查只读取 SQLite 元数据并规范化路径，不读取 stdout/stderr 内容；完成前不要把日志开关写入长期服务配置。

2026-07-18 已在 107 对提交 `beb39f7` 和 Job `24011` 完成本检查：owner `pb24030760` 校验通过，stdout 与 stderr 路径均位于受控作业目录，`stdout_path_safe=true`、`stderr_path_safe=true`、`would_open_log=false`、`would_read_log=false`。临时日志开关仅存在于本次验收 shell，没有写入长期配置；运行时 `data/` 证据未删除、未修改、保持未跟踪。该结果只批准路径映射，真实日志读取仍需项目管理员单独授权。

## Native 日志与控制集中验收

真实日志读取只对已验收的 Job `24011` 执行一次，每个流最多读取 4096 字节，输出只包含字节数、偏移、EOF 和可用状态，不回显正文：

```bash
export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"
export NATIVE_SUBMISSION_ENABLED=false
export NATIVE_CANCEL_ENABLED=false
export NATIVE_CLONE_ENABLED=false
export NATIVE_LOGS_ENABLED=true

backend/.venv/bin/python scripts/read-native-log-acceptance.py \
  --confirm READ-ONE-NATIVE-JOB-LOG-SAMPLE
```

控制闭环会创建两个 `1 CPU / 512 MiB / 0 GPU / 2 分钟` 的 CPU 测试作业：第一个提交后取消，再从其可信元数据克隆并取消克隆。脚本只操作自身返回并持久化的 Job ID，固定幂等键防止重复提交：

```bash
export NATIVE_LOGS_ENABLED=false
export NATIVE_SUBMISSION_ENABLED=true
export NATIVE_CANCEL_ENABLED=true
export NATIVE_CLONE_ENABLED=true
export NATIVE_MAX_ACTIVE_JOBS=2

backend/.venv/bin/python scripts/run-native-control-acceptance.py \
  --confirm RUN-ONE-NATIVE-CONTROL-ACCEPTANCE
```

运行后还应使用 `sacct` 核对脚本输出的两个 Job ID 均进入终态，并确认没有遗留的活动验收作业。以上开关仅用于本次 shell，不写入 `.env` 或长期服务配置。

2026-07-18 已在 107 对提交 `11cd3b4` 完成集中验收。Job `24011` 的 stdout 限量读取 14 字节、stderr 读取 0 字节，两个流均到达 EOF，正文没有回显。控制脚本创建 Job `24063` 与 `24064`，每个申请 `1 CPU / 512 MiB / 0 GPU / 2 分钟`，两个作业均由 UID `68311` 取消；`sacct` 状态为 `CANCELLED by 68311`，`squeue` 无遗留活动验收作业。Owner、两条取消幂等记录和 `SBATCH_ACCEPTED -> SCANCEL_VALIDATED -> SCANCEL_ACCEPTED` 审计证据均通过；所有开关只存在于验收 shell，`data/` 证据保持未跟踪。

## Native 全交互集中验收

该验收一次覆盖真实 HTTP 提交、状态查询、限量日志、资源统计、取消和克隆。它会创建三个最小 CPU 作业：一个正常完成，另外两个由脚本取消。只在 107 登录节点执行，计算内容均通过 `sbatch` 调度；脚本不会回显日志正文，也不会操作自己未创建的作业。

```bash
cd ~/107dashboard
git pull --ff-only

export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"
export NATIVE_SUBMISSION_ENABLED=true
export NATIVE_LOGS_ENABLED=true
export NATIVE_CANCEL_ENABLED=true
export NATIVE_CLONE_ENABLED=true
export NATIVE_MAX_ACTIVE_JOBS=2
export DEMO_FALLBACK_ENABLED=true
export SERVE_FRONTEND=false

backend/.venv/bin/python scripts/run-native-live-interaction.py \
  --confirm RUN-NATIVE-LIVE-INTERACTION-V1 \
  --timeout-seconds 120
```

通过输出必须包含 `mode=native-live-http-full-interaction`、`passed=true`、三个不同 Slurm Job ID、完成作业 `COMPLETED/0:0`、`submitted_jobs=3`、`cancelled_jobs=2`、`raw_log_content_emitted=false` 和 `audit_chain_present=true`。随后用 `squeue -u "$USER"` 确认没有遗留活动验收作业，并用 `sacct` 核对三个 Job 的终态。一次性回执位于未跟踪的作业工作目录；不要为了重跑而删除回执，失败时应先保留现场并检查脚本输出和 `squeue`。

平台集中验收通过后，可将 `deploy/107-native-interactive.env.example` 复制到未跟踪的运行配置并替换 `USERNAME`。全交互配置仍应只监听回环地址或受控反向代理，使用单 Uvicorn worker；任何 Native 故障触发 Fixture 回退时写能力必须保持关闭。

2026-07-19 已在 107 对提交 `85c9646` 完成本验收。完成作业 Job `24159` 使用 `1 CPU / 512 MiB / 0 GPU / 1 分钟`，状态为 `COMPLETED`、退出码 `0:0`，stdout/stderr 限量读取 14/0 字节且正文未输出；usage 返回 `elapsed_seconds=0.0`、`max_rss_kb=24`、`total_cpu_seconds=0.004`。控制 Job `24160` 与克隆 Job `24161` 均由 UID `68311` 取消。三个提交、两个取消的幂等记录全部为 `SUCCEEDED`，审计链完整，`squeue` 无活动作业，一次性回执权限为 `0600`，运行时证据保留在未跟踪的 `data/` 中。

## 用户目录基础产品服务

2026-07-22，提交 `6ba4939` 已在 107 从干净 `master` 完成部署。目标 Python 3.12 环境执行后端 `268 passed`、Ruff 和 `pip check`；用户目录 Node 24.18/npm 11.16 执行 `npm ci`、TypeScript 检查、`build:navigation` 与 npm 官方审计，0 漏洞。服务器构建与开发机统一导航构建逐文件 SHA-256 一致。服务重启后 Native-only 产品检查通过，9 个作业的列表/摘要一致，四项交互能力开启，四模块 API、SQLite 完整性、AI 密钥权限和 Slurm 控制器状态正常，队列无活动作业。该检查没有提交、取消或克隆 Slurm 作业，浏览器视口与交互验收仍单独执行。

单账号验收项目部署在源码仓库之外：

```bash
rsync -az --delete examples/test-projects/ 107:~/dashboard-test-projects/
ssh 107 'chmod -R go-rwx ~/dashboard-test-projects'
```

正式环境配置使用 `TEST_PROJECT_DIRECTORY=~/dashboard-test-projects` 的绝对展开路径。产品启动检查会加载 CPU 完成、增量日志、受控失败、取消与克隆四个项目；目录缺失、owner 不匹配、文件可被组/其他用户写入、符号链接、非法 manifest 或项目集合不完整都会阻止服务启动。该检查不执行项目源码，也不调用 `sbatch`。

正式产品配置不启用 Fixture 回退。开发电脑先生成带 `native-basic-v1` 标识的统一导航前端并传输到 107：

```bash
cd frontend
npm run build:navigation
rsync -az --delete dist/ 107:~/107dashboard/frontend/dist/
```

然后在 107 用户目录拉取代码并启动：

```bash
cd ~/107dashboard
git pull --ff-only
bash scripts/107-dashboard-service.sh stop
bash scripts/107-dashboard-service.sh configure
bash scripts/107-dashboard-service.sh start
bash scripts/107-dashboard-service.sh status
```

服务由名为 `107dashboard` 的 tmux session 承载，只监听 `127.0.0.1:8000`，单 worker 运行。`configure` 根据当前用户和仓库路径生成未跟踪的 `data/107dashboard.env`，权限为 `0600`，并在覆盖前备份已有配置。`start` 先执行无 Slurm 写入的产品检查；若前端构建过期、owner 不一致、`sbatch/scancel/squeue/sacct` 缺失、Fixture 回退开启、四项能力未全部开放或真实列表/摘要不一致，服务不会进入健康状态。失败的启动 session 会被清理，日志保留在 `data/107dashboard.log`。

浏览器打开统一入口 `/107-dashboard/` 后，页首必须显示“Native 真实交互”和“当前只展示真实 Slurm 作业”。基础回归依次执行：

1. 使用“CPU 快速检查”提交并等待完成，查看 stdout/stderr 和 usage；
2. 使用“可取消 CPU 任务”提交，在排队或运行状态取消；
3. 从该作业详情克隆为新 Job，再取消克隆；
4. 确认页面 Job ID 均为真实 Slurm 数字 ID，`status` 输出 `fixture_influence=false`；
5. 最后使用 `squeue -u "$USER"` 确认没有测试作业遗留。

常用管理命令：

```bash
bash scripts/107-dashboard-service.sh status
bash scripts/107-dashboard-service.sh logs
bash scripts/107-dashboard-service.sh restart
bash scripts/107-dashboard-service.sh stop
```

## 演示发布集中验收

本阶段不再创建或取消 Slurm 作业。它集中验证真实 Native 查询仍健康、作业与摘要数量一致、自动回退能在模拟故障下展示脱敏 Fixture，并证明回退期间 HTTP 写能力返回 503 且不会调用 `sbatch`。

```bash
cd ~/107dashboard
git pull --ff-only

export SLURM_DATA_SOURCE=native
export DASHBOARD_OWNER="$(id -un)"
export DATABASE_URL="sqlite:////home/scc/$(id -un)/107dashboard/data/dashboard.sqlite3"
export JOB_WORKSPACE_DIRECTORY="/home/scc/$(id -un)/107dashboard/data/jobs"
export DEMO_FALLBACK_ENABLED=true
export DEMO_FALLBACK_COOLDOWN_SECONDS=30
export NATIVE_SUBMISSION_ENABLED=false
export NATIVE_LOGS_ENABLED=false
export NATIVE_CANCEL_ENABLED=false
export NATIVE_CLONE_ENABLED=false
export SERVE_FRONTEND=false

backend/.venv/bin/python scripts/check-demo-release.py
```

通过输出必须包含 `mode=demo-release-readiness-no-write`、`passed=true`、Native `serving_source=native`、回退 `serving_source=fixture_fallback`、`write_status=503` 和 `would_invoke_sbatch=false`。如果真实查询已进入回退，脚本会主动失败，不能把 Fixture 成功误记为 Native 平台通过。

完整网页演示前，在开发电脑执行 `npm run build`，把未跟踪的 `frontend/dist/` 复制到 107 的仓库同一路径，再参考 `deploy/107-native.env.example` 设置 `SERVE_FRONTEND=true`。后端找不到 `index.html` 时会拒绝启动，防止出现 API 正常但网页空白的假部署。

通过本机统一导航页部署时，使用固定字符路径构建，避免静态资源和 API 请求退回站点根路径：

```bash
cd frontend
npm run build:navigation
rsync -az --delete dist/ 107:~/107dashboard/frontend/dist/
```

统一入口为 `/107-dashboard/`，构建产物使用 `/107-dashboard/assets/`，API 使用 `/107-dashboard/api`。本机 Nginx 剥离该前缀后转发到 SSH 隧道；独立端口入口仅作为兼容和诊断路径。

2026-07-18 已在 107 对提交 `b253ac0` 完成本验收。真实 Native 路径的 `visible_jobs=4`、`summary_jobs=4`，样例 Job ID 为 `24064`；模拟故障路径返回 `serving_source=fixture_fallback` 和 5 个脱敏作业，写请求状态为 503，`would_invoke_sbatch=false`。提交、取消、克隆和日志能力均保持关闭，没有调用 `sbatch` 或 `scancel`、没有读取真实日志，`squeue` 无活动作业，未跟踪的 `data/` 验收证据未修改或删除。

2026-07-19 已完成整页演示排练：最新静态产物部署到 107，由 FastAPI 同源托管；本机 SSH ControlMaster 将远端 `127.0.0.1:8000` 转发至 `10780`，统一导航 Nginx 以 `/107-dashboard/` 提供页面与 API。桌面 `1440x1000`、移动端 `390x844` 以及 Tailscale 入口均加载成功，真实 Native 4 个作业、摘要和详情一致，无资源 404、控制台错误、横向溢出或元素重叠。移动端刷新按钮已提高到至少 44px 触控高度。演示长期配置继续保持提交、日志、取消和克隆关闭。

## 安全边界

- 部署公钥保持只读，不改用个人写入密钥；
- 不在服务器保存 Gitee Personal Access Token；
- 不把部署私钥挂载到 Dashboard 应用；
- 不允许 Web API 直接执行任意 shell 字符串；
- 所有 Slurm 参数必须结构化校验；
- 不在登录节点直接运行训练或 GPU 作业；
- 服务器更新失败时保留现场，不使用 `git reset --hard` 清理未知修改。

## 常用诊断

检查远程认证：

```bash
ssh -T gitee-107dashboard
```

检查远程提交：

```bash
git -C ~/107dashboard ls-remote origin HEAD
```

查看当前部署版本：

```bash
git -C ~/107dashboard log -1 --oneline
```

查看项目状态：

```bash
git -C ~/107dashboard status --short --branch
```

查看 Dashboard 自己的 Slurm 作业：

```bash
squeue -u "$USER"
```
