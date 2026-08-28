# Deploy

比赛原型的部署和服务管理配置。

```text
systemd/   用户级 systemd service 模板
proxy/     可选的反向代理配置
release/   Linux 发布包安装与完整性校验
```

当前默认部署是算力平台 Python 虚拟环境加前端静态产物。Docker 配置不是比赛 MVP 的前置条件。

## 发布包

在开发电脑运行以下命令，可生成不包含运行数据和密钥的 Linux 部署包：

```powershell
backend/.venv/Scripts/python.exe scripts/build-release.py
```

输出位于未跟踪的 `data/releases/`。正式交付使用 `--require-clean`，本地试打包可省略。
包内已经包含 `/107-dashboard/` 前缀的前端静态产物，Linux 平台不需要安装 Node.js。
解压后执行 `bash deploy/release/install.sh`，详细限制和参数见 `deploy/release/README.md`。

Windows 一键交付使用 `scripts/build-windows-client.py`。该脚本先生成同一 Linux 发布包，
再运行客户端测试并把服务包嵌入自包含 `win-x64` EXE，同时生成包含 EXE、`data/` 和说明
文件的便携 ZIP；产物同样位于未跟踪的 `data/releases/`。客户端通过 SFTP 上传、SHA-256
校验和版本目录安装，不要求普通用户拥有 Gitee 凭据。Windows 客户端的连接配置写入
EXE 同级的 `data/client-settings.json`，更新时保留该目录。

远端更新使用 `$HOME/.local/share/107dashboard` 下的 `releases/<release-id>` 版本目录和
`current`/`previous` 软链接。更新锁保证同一账号不会并发切换版本；服务成功启动后只保留
当前版本和上一个版本，更旧的版本目录及服务包会被清理。数据库、日志和作业数据位于
`runtime/`，不参与版本清理。

Python 虚拟环境也不再随每个版本目录重复创建。发布安装脚本按
`backend/requirements.txt` 的 SHA-256 在 `runtime/python-venvs/` 中复用环境；前后端代码更新
但依赖不变时不会重新执行整套 `pip install`，只有依赖哈希变化或 `pip check` 失败时才安装。

`proxy/107-dashboard.nginx.conf.example` 是供平台管理员使用的共享入口模板。应用继续只监听
回环地址；Windows 客户端默认通过用户自己的 SSH 隧道访问，不要求共享反向代理。若平台改为
提供统一 URL，反向代理仍必须配置认证、VPN 或 IP 白名单。

## 比赛演示配置

- `107-native.env.example`：107 Native 演示环境模板。复制到未跟踪的 `data/107dashboard.env`，替换 `USERNAME`，不要提交真实路径或账号配置。
- `107-native-interactive.env.example`：真实提交、日志、取消和克隆全部开放的产品配置；Fixture 回退固定关闭，模拟作业不会进入正常产品视图。
- `systemd/107dashboard.service.example`：用户级 systemd 模板；若平台未启用 linger，开发和比赛现场可暂用 tmux。
- `scripts/107-dashboard-service.sh`：用户目录下的 tmux 服务管理入口，提供 `configure/start/stop/restart/status/logs`。启动前会检查有效 Unix owner、Slurm 命令、最新前端产物、四项能力和 Native-only 数据策略。
- `SERVE_FRONTEND=true` 时，后端会从 `FRONTEND_DIST_DIRECTORY` 提供静态页面；目录缺少 `index.html` 时启动会立即失败并提示先构建。
- `DEMO_FALLBACK_ENABLED=true` 只允许 Native 读取失败后切换到脱敏 Fixture。回退期间提交、取消、克隆全部强制关闭，不能作为绕过 Slurm 或权限门禁的路径。

107 没有系统级 Node.js；正式发布统一执行 `npm run build:107`，可在开发电脑构建后复制未跟踪的 `frontend/dist/`，也可使用服务器用户目录下已配置的 Node 执行。该入口按系统选择原生 shell：Windows 使用 PowerShell，Linux 使用 Bash；Windows 不依赖 Git Bash。该命令和启动预检都会强制 `/107-dashboard/assets/`、`/107-dashboard/api` 前缀并拒绝 localhost API，避免独立端口构建覆盖子路径入口。仅执行后端集中验收时可设置 `SERVE_FRONTEND=false`，不依赖静态产物。
后端同时保留 `/api/...` 作为反向代理剥离前缀后的兼容入口，并提供 `/107-dashboard/api/...` 作为直接访问带前缀静态页面时的 API 入口。

正式产品入口使用统一导航构建。在开发电脑执行 `npm run build:navigation` 并传输 `frontend/dist/` 后，在 107 执行：

```bash
bash scripts/107-dashboard-service.sh stop
bash scripts/107-dashboard-service.sh configure
bash scripts/107-dashboard-service.sh start
bash scripts/107-dashboard-service.sh status
```

`configure` 会以当前 Unix 用户和仓库绝对路径生成权限为 `0600` 的未跟踪配置；已有配置会先备份。`status` 只有在运行来源为 `native`、Fixture 影响为 `false`、四项交互能力全部开启、列表与摘要一致且前端构建标识为 `native-basic-v1` 时才成功。
