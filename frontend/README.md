# Frontend

React、Vite 和 TypeScript 前端目录。

主要结构：

```text
public/            不经过构建处理的静态资源
src/api/           API 客户端
src/components/    通用界面组件
src/features/      按业务领域组织的功能
src/layouts/       页面布局
src/pages/         路由页面
src/routes/        路由配置
src/styles/        全局样式和设计变量
src/types/         跨功能共享的 TypeScript 类型
```

作业相关组件、状态和接口适配优先放在 `src/features/jobs/`，只有真正跨功能复用的内容才进入通用目录。

## 本地产品设计原型

四模块深色工作台放在 `src/prototype/`，并作为当前默认前端入口。启动前端后访问：

```text
http://127.0.0.1:5173/
```

新版作业管理页已直接接入现有 jobs、runtime、projects、summary、logs 和 usage API，并复用提交、取消、克隆的幂等与能力门禁逻辑。旧版页面入口已经移除，不再维护第二套界面。

诊断报告、项目评价和 AI 工作台已接入产品 API：诊断报告使用 Slurm、usage 和持久化元数据生成确定性结论；项目评价可以关联多个当前账号可见作业；AI 工作台支持 OpenAI 兼容 Provider、写入式 API Key 配置、作业证据选择、对话、提示词和调用记录。

API Key 只写入后端配置的用户私有目录，浏览器和 SQLite 都不能回读原文。默认学校 Provider 地址只是待替换模板，必须填写真实 HTTPS 地址和有效密钥后才能调用；AI 只接收用户明确勾选作业的结构化报告，不具备任何 Slurm 控制能力。

桌面验收视口为 `1600×800`，最低为 `1440×720`；增长型页面允许主内容区纵向滚动，但页面和面板不得产生横向滚动或裁剪资源行。窄屏允许改为纵向布局。

107 的唯一正式发布命令是 `npm run build:107`。它先在临时目录生成 `/107-dashboard/` 子路径构建，校验静态资源使用 `/107-dashboard/assets/`、API 使用 `/107-dashboard/api` 且不含开发地址，全部通过后才替换当前 `dist/`。`build` 和 `build:navigation` 仅用于普通开发或定向检查，不应直接覆盖 107 正式产物。
