# Deploy

比赛原型的部署和服务管理配置。

```text
systemd/   用户级 systemd service 模板
proxy/     可选的反向代理配置
```

当前默认部署是算力平台 Python 虚拟环境加前端静态产物。Docker 配置不是比赛 MVP 的前置条件。

## 比赛演示配置

- `107-native.env.example`：107 Native 演示环境模板。复制到未跟踪的 `data/107dashboard.env`，替换 `USERNAME`，不要提交真实路径或账号配置。
- `107-native-interactive.env.example`：真实提交、日志、取消和克隆全部开放的产品配置；Fixture 回退固定关闭，模拟作业不会进入正常产品视图。
- `systemd/107dashboard.service.example`：用户级 systemd 模板；若平台未启用 linger，开发和比赛现场可暂用 tmux。
- `scripts/107-dashboard-service.sh`：用户目录下的 tmux 服务管理入口，提供 `configure/start/stop/restart/status/logs`。启动前会检查有效 Unix owner、Slurm 命令、最新前端产物、四项能力和 Native-only 数据策略。
- `SERVE_FRONTEND=true` 时，后端会从 `FRONTEND_DIST_DIRECTORY` 提供静态页面；目录缺少 `index.html` 时启动会立即失败并提示先构建。
- `DEMO_FALLBACK_ENABLED=true` 只允许 Native 读取失败后切换到脱敏 Fixture。回退期间提交、取消、克隆全部强制关闭，不能作为绕过 Slurm 或权限门禁的路径。

107 没有系统级 Node.js；正式发布统一执行 `npm run build:107`，可在开发电脑构建后复制未跟踪的 `frontend/dist/`，也可使用服务器用户目录下已配置的 Node 执行。该命令和启动预检都会强制 `/107-dashboard/assets/`、`/107-dashboard/api` 前缀并拒绝 localhost API，避免独立端口构建覆盖子路径入口。仅执行后端集中验收时可设置 `SERVE_FRONTEND=false`，不依赖静态产物。

正式产品入口使用统一导航构建。在开发电脑执行 `npm run build:navigation` 并传输 `frontend/dist/` 后，在 107 执行：

```bash
bash scripts/107-dashboard-service.sh stop
bash scripts/107-dashboard-service.sh configure
bash scripts/107-dashboard-service.sh start
bash scripts/107-dashboard-service.sh status
```

`configure` 会以当前 Unix 用户和仓库绝对路径生成权限为 `0600` 的未跟踪配置；已有配置会先备份。`status` 只有在运行来源为 `native`、Fixture 影响为 `false`、四项交互能力全部开启、列表与摘要一致且前端构建标识为 `native-basic-v1` 时才成功。
