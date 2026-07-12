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
