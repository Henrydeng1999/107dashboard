# 05 项目目录规范

## 完整目录

```text
107dashboard/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   ├── core/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── slurm/
│   ├── migrations/
│   └── tests/
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── public/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── features/
│       │   └── jobs/
│       ├── layouts/
│       ├── pages/
│       ├── routes/
│       ├── styles/
│       └── types/
├── deploy/
│   ├── systemd/
│   └── proxy/
├── docs/
│   ├── index.html
│   ├── .nojekyll
│   ├── site.css
│   ├── site.js
│   └── 01-06 Markdown 手册
├── examples/
│   └── job-scripts/
├── fixtures/
│   ├── slurm/
│   └── job-output/
├── scripts/
├── tests/
│   └── e2e/
├── README.md
└── .gitignore
```

## 后端边界

- `api/routes/` 只处理 HTTP 输入输出，不直接访问数据库或拼接 Slurm 命令；
- `schemas/` 定义经过校验的请求和响应；
- `services/` 编排提交、取消、克隆和日志读取流程；
- `slurm/` 只负责执行受控命令、解析输出和映射状态；
- `repositories/` 负责 SQLite 数据读写；
- `models/` 保存数据库模型；
- `core/` 保存配置、日志、异常和应用级公共能力。

## 前端边界

- `features/jobs/` 保存作业领域的组件、hooks、状态和类型；
- `components/` 只保存跨页面复用的通用组件；
- `pages/` 负责页面组合，不在页面中散落 API 请求；
- `api/` 统一处理后端地址、错误和响应；
- `types/` 只保存真正跨功能共享的类型。

## 测试与演示数据

- `backend/tests/unit/` 测试解析器、校验器和业务函数；
- `backend/tests/integration/` 测试数据库和 Slurm 适配器；
- `tests/e2e/` 测试提交到查看日志的完整流程；
- `fixtures/` 保存脱敏后的 Slurm 输出和作业日志；
- `examples/` 保存可以公开展示的示例作业脚本。

## 运行时文件

以下内容由程序或部署过程生成，不提交到 Git：

```text
.venv/
frontend/node_modules/
frontend/dist/
data/*.sqlite3
logs/
tmp/
```

数据库、日志、上传文件和临时作业脚本不能混入源码目录。后续实现时通过配置指定它们的实际路径。

`docs/index.html` 是 GitHub Pages 文档入口，会在浏览器中动态读取同目录的六章 Markdown 并渲染。修改 Markdown 后不需要重新生成 HTML；GitHub Pages 从 `/docs` 发布时也不需要构建命令。

## 新增目录规则

新增一级目录前应满足至少一个条件：

- 对应明确的所有权边界；
- 保存一种独立的构建或部署产物；
- 当前结构无法清晰容纳该内容。

不要为单个文件创建抽象目录，也不要同时维护含义重复的 `utils/`、`helpers/`、`common/`。公共代码应放在最接近其使用领域的位置。
