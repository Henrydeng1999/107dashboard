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

仓库已提供提交安全底座，但尚未接入 Native HTTP API。更新代码后，先运行以下预检：

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
