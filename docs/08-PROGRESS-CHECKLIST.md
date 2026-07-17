# 项目完成情况检查表

<div class="progress-meta">
  <span class="status-badge status-done">● 最近本地验证通过</span>
  <span>更新时间：2026-07-17</span>
  <span>基线提交：<code>07a7898</code></span>
</div>

<div class="progress-summary" aria-label="当前项目摘要">
  <div class="progress-stat progress-stat-done"><strong>可用</strong><span>前后端最小骨架</span></div>
  <div class="progress-stat progress-stat-done"><strong>100 / 100</strong><span>后端测试通过</span></div>
  <div class="progress-stat progress-stat-done"><strong>通过</strong><span>前端类型检查与构建</span></div>
  <div class="progress-stat progress-stat-next"><strong>下一步</strong><span>基础资源统计</span></div>
</div>

> **状态说明：** <span class="status-badge status-done">✓ 已完成</span> 已实现并通过对应测试、构建、fixture 或平台证据验证；<span class="status-badge status-active">→ 进行中</span> 已有部分成果；<span class="status-badge status-pending">○ 待开始</span> 尚未实现；<span class="status-badge status-later">◇ 赛后</span> 不阻塞比赛 MVP。

## 分阶段完成情况

<div class="phase-list">
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 0 · 项目初始化</strong><span class="status-badge status-active">3 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="项目初始化完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="60"><span class="progress-fill progress-60"></span></div>
    <p>项目文档、技术版本和平台部署方向已确定；配置边界与认证方式待确认。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 1 · 最小可用骨架</strong><span class="status-badge status-active">3 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="最小可用骨架完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="60"><span class="progress-fill progress-60"></span></div>
    <p>FastAPI、React、环境配置和基础测试可用；统一错误响应与日志仍需补齐，云 CI 暂不启用。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 2 · 作业只读视图</strong><span class="status-badge status-active">4 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="作业只读视图完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="80"><span class="progress-fill progress-80"></span></div>
    <p>作业模型、Fixture jobs API 和基础前端列表/详情已完成；Native 只读查询链路已在 107 临时测试实例验证。可信身份所有权机制待实现，正式 Native API 在认证完成前仍无条件关闭，视觉美化留到核心功能闭环后统一进行。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 3 · 作业提交与控制</strong><span class="status-badge status-active">4 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="作业提交与控制完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="80"><span class="progress-fill progress-80"></span></div>
    <p>结构化参数、资源校验、Fixture 模拟提交、取消和克隆已完成；真实 sbatch 与持久化尚未实现。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 4 · 日志和资源可视化</strong><span class="status-badge status-active">2 / 4</span></div>
    <div class="progress-track" role="progressbar" aria-label="日志和资源可视化完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50"><span class="progress-fill progress-50"></span></div>
    <p>Fixture stdout/stderr 展示与字节偏移增量读取已完成；CPU/GPU/内存和运行时长统计尚未实现。</p>
  </div>
  <div class="phase-row phase-later">
    <div class="phase-heading"><strong>阶段 5 · 生产化部署</strong><span class="status-badge status-later">赛后</span></div>
    <div class="progress-track" role="progressbar" aria-label="生产化部署完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0"><span class="progress-fill progress-0"></span></div>
    <p>HTTPS、长期服务、备份、审计和生产数据库不阻塞比赛 MVP。</p>
  </div>
</div>

## 已完成功能检查表

| 状态 | 类别 | 已完成内容 | 验证证据 |
| --- | --- | --- | --- |
| <span class="status-badge status-done">✓</span> | 环境 | Python 3.12 虚拟环境、固定后端依赖、可选 Conda YAML | `pip check` 通过 |
| <span class="status-badge status-done">✓</span> | 前端环境 | React、Vite、TypeScript 与 lockfile | `npm ci` 通过 |
| <span class="status-badge status-done">✓</span> | 后端骨架 | FastAPI 应用、配置加载、CORS、健康检查 | `GET /api/health` 测试通过 |
| <span class="status-badge status-done">✓</span> | 作业模型 | 状态枚举、资源边界、列表与详情响应模型 | Pydantic 校验生效 |
| <span class="status-badge status-done">✓</span> | Fixture jobs API | Fixture adapter 已接入作业列表与详情 API，支持状态筛选、稳定分页、详情和 404 | 集成与单元测试通过 |
| <span class="status-badge status-done">✓</span> | Slurm fixtures | 脱敏 squeue、sacct、sinfo 和空队列输出样例 | 解析器与 Fixture adapter 测试通过 |
| <span class="status-badge status-done">✓</span> | Slurm adapter | SlurmAdapter Protocol、参数数组 runner、Fixture/Native adapter、超时与命令错误映射 | adapter 单元测试通过；107 临时只读实例已执行真实 `squeue`/`sacct` |
| <span class="status-badge status-done">✓</span> | Slurm 解析 | squeue、sacct、sinfo 的作业状态、节点、退出码和资源字段解析 | fixture、异常输入和状态映射测试通过 |
| <span class="status-badge status-done">✓</span> | API 安全边界 | Native jobs API 无条件 fail-closed；404/422/503 使用脱敏错误 envelope 与服务端 request ID | 外部 native 环境下完整 pytest 通过；未调用 subprocess |
| <span class="status-badge status-done">✓</span> | 前端骨架 | React 页面入口、基础布局与 API 状态 | TypeScript 检查、Vite 构建通过 |
| <span class="status-badge status-done">✓</span> | 前端作业视图 | Fixture 作业列表、状态筛选、分页、详情、加载、空数据和错误重试 | TypeScript 检查、Vite 生产构建通过 |
| <span class="status-badge status-done">✓</span> | Fixture 作业提交 | 结构化提交 API、固定分区/账户/QoS、资源上限校验、模拟排队 Job ID 和基础提交表单 | 合法提交、非法参数测试及前端构建通过；未执行 sbatch |
| <span class="status-badge status-done">✓</span> | Fixture 作业控制 | 排队/运行作业取消、终态冲突保护、重新校验后克隆新 Job ID，以及前端确认和反馈 | 取消、克隆、404、409 集成测试及前端构建通过；未执行 scancel/sbatch |
| <span class="status-badge status-done">✓</span> | Fixture 作业日志 | stdout/stderr 流切换、字节偏移增量读取、缺失日志提示、刷新和继续加载 | 正常、缺失、404、416、非法参数集成测试及前端构建通过；未读取真实用户日志 |
| <span class="status-badge status-done">✓</span> | 代码质量 | Ruff、pytest、npm audit | 后端 100 个 pytest 通过，目标 Ruff 通过；0 个生产依赖漏洞 |
| <span class="status-badge status-done">✓</span> | 文档 | 架构、环境、协作、部署、API 契约 | 文档站可直接访问 |
| <span class="status-badge status-done">✓</span> | 文档体验 | 单章节按需加载、模糊过渡、URL 定位、前进后退和章节筛选 | 浏览器交互检查通过 |

## 当前待办与提示

<div class="notice-grid">
  <div class="notice notice-next"><strong>下一开发项</strong><span>基于现有 sacct 字段实现 CPU、GPU、内存和运行时长基础统计，先区分申请值与平台未提供的实际值。</span></div>
  <div class="notice notice-warning"><strong>暂时限制</strong><span>当前提交、取消和克隆均为内存模拟，日志来自脱敏 Fixture；Native 只读链路虽已在 107 验证，但正式 API 仍等待可信身份映射，写操作和真实日志尚未进行平台验收。</span></div>
  <div class="notice notice-safe"><strong>安全边界</strong><span>真实测试只能通过 Slurm 提交，禁止在登录节点直接运行学生计算任务。</span></div>
  <div class="notice notice-info"><strong>验证方式</strong><span>Fixture 用于稳定回归和边界覆盖，Native 用于阶段性真实验收：后端 pytest 100 passed、目标 Ruff、前端类型检查和生产构建通过；107 临时只读实例的 jobs API 与 `squeue`/`sacct` 对照一致。</span></div>
</div>

## MVP 必须功能

- [x] 前后端最小骨架与健康检查
- [x] 作业数据模型与 Fixture 只读 API
- [x] squeue、sacct、sinfo 受控查询参数与 fixture 输出解析
- [x] Fixture adapter 接入 jobs service/API
- [ ] 真实 Slurm 查询与 jobs service/API 正式接入（读取链路已验证，等待可信身份方案）
- [ ] 作业所有权校验
- [x] 基础作业列表与详情页面
- [x] Fixture 作业提交与资源校验
- [ ] 真实 sbatch 提交与 Job ID 持久化
- [x] Fixture stdout/stderr 日志查看与增量读取
- [ ] 真实日志路径映射、所有权校验与平台验收
- [x] Fixture 作业取消与克隆
- [ ] 真实 scancel 与基于持久化元数据的克隆
- [ ] CPU、GPU、内存和运行时长统计
- [ ] Mock、预提交作业、真实平台三路演示

## 可选创新功能

- [ ] 自动演示模式与 Slurm 故障回退
- [ ] 状态变化提示和智能轮询
- [ ] 资源趋势图与申请/实际使用对比
- [ ] 常用作业模板
- [ ] 基于退出码和日志特征的失败排查提示

## 维护规则

每次 PR 准备合入 `master` 前，负责开发或评审的 Agent 必须检查本页。若 PR 改变功能状态、验证证据、阶段进度、限制或下一任务，应在同一 PR 中同步更新本页；管理员直接提交阶段成果时执行相同规则。

只有相关测试、构建、fixture 或真实平台证据通过后，功能才能标记为“已完成”。不影响项目进度的 PR 应在评审摘要中注明“无需更新进度表”，避免无意义改动。
