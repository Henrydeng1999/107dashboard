# Deploy

比赛原型的部署和服务管理配置。

```text
systemd/   用户级 systemd service 模板
proxy/     可选的反向代理配置
```

当前默认部署是算力平台 Python 虚拟环境加前端静态产物。Docker 配置不是比赛 MVP 的前置条件。

## 比赛演示配置

- `107-native.env.example`：107 Native 演示环境模板。复制到未跟踪的 `data/107dashboard.env`，替换 `USERNAME`，不要提交真实路径或账号配置。
- `systemd/107dashboard.service.example`：用户级 systemd 模板；若平台未启用 linger，开发和比赛现场可暂用 tmux。
- `SERVE_FRONTEND=true` 时，后端会从 `FRONTEND_DIST_DIRECTORY` 提供静态页面；目录缺少 `index.html` 时启动会立即失败并提示先构建。
- `DEMO_FALLBACK_ENABLED=true` 只允许 Native 读取失败后切换到脱敏 Fixture。回退期间提交、取消、克隆全部强制关闭，不能作为绕过 Slurm 或权限门禁的路径。

107 没有 Node.js，因此先在开发电脑执行 `npm run build`，再把未跟踪的 `frontend/dist/` 复制到服务器同一路径。仅执行后端集中验收时可设置 `SERVE_FRONTEND=false`，不依赖静态产物。
