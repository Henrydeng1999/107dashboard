# 项目完成情况检查表

<div class="progress-meta">
  <span class="status-badge status-done">● 最近本地与 107 验证通过</span>
  <span>更新时间：2026-07-18</span>
  <span>平台验收提交：<code>0f88ede</code></span>
</div>

<div class="progress-summary" aria-label="当前项目摘要">
  <div class="progress-stat progress-stat-done"><strong>可用</strong><span>前后端最小骨架</span></div>
  <div class="progress-stat progress-stat-done"><strong>203 / 203</strong><span>后端测试通过</span></div>
  <div class="progress-stat progress-stat-done"><strong>通过</strong><span>前端类型检查与构建</span></div>
  <div class="progress-stat progress-stat-next"><strong>下一步</strong><span>107 日志与控制集中验收</span></div>
</div>

> **状态说明：** <span class="status-badge status-done">✓ 已完成</span> 已实现并通过对应测试、构建、fixture 或平台证据验证；<span class="status-badge status-active">→ 进行中</span> 已有部分成果；<span class="status-badge status-pending">○ 待开始</span> 尚未实现；<span class="status-badge status-later">◇ 赛后</span> 不阻塞比赛 MVP。

## 分阶段完成情况

<div class="phase-list">
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 0 · 项目初始化</strong><span class="status-badge status-active">4 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="项目初始化完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="80"><span class="progress-fill progress-80"></span></div>
    <p>项目文档、技术版本、部署方向和比赛原型单 Unix 账号身份边界已确定；开发/测试/生产配置边界仍待固化。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 1 · 最小可用骨架</strong><span class="status-badge status-active">3 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="最小可用骨架完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="60"><span class="progress-fill progress-60"></span></div>
    <p>FastAPI、React、环境配置和基础测试可用；统一错误响应与日志仍需补齐，云 CI 暂不启用。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 2 · 作业只读视图</strong><span class="status-badge status-done">5 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="作业只读视图完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="100"><span class="progress-fill progress-100"></span></div>
    <p>Native 只读列表、详情、摘要和资源统计已在身份门禁后正式接入；Slurm 与 SQLite 去重合并、source 隔离和前端能力提示通过本地回归，并已在 107 对提交 <code>05a64a3</code> 正式验收。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 3 · 作业提交与控制</strong><span class="status-badge status-done">5 / 5</span></div>
    <div class="progress-track" role="progressbar" aria-label="作业提交与控制完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="100"><span class="progress-fill progress-100"></span></div>
    <p>Native 安全提交、取消与克隆均已完成默认关闭门禁、Owner 校验、持久化幂等、审计和注入式回归；107 真实控制闭环待集中验收。</p>
  </div>
  <div class="phase-row">
    <div class="phase-heading"><strong>阶段 4 · 日志和资源可视化</strong><span class="status-badge status-done">4 / 4</span></div>
    <div class="progress-track" role="progressbar" aria-label="日志和资源可视化完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="100"><span class="progress-fill progress-100"></span></div>
    <p>Fixture 日志、增量读取、作业级资源统计和当前用户摘要均已完成；真实作业 <code>21482</code> 的 elapsed、MaxRSS 和 TotalCPU 字段已通过平台验收。</p>
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
| <span class="status-badge status-done">✓</span> | API 安全边界 | Native 默认仅开放受 UID/owner 门禁保护的查询；提交、日志、取消和克隆均使用独立默认关闭开关 | 其他 owner 隐藏、身份失败、命令失败、路径越界、能力声明和错误脱敏测试通过 |
| <span class="status-badge status-done">✓</span> | 前端骨架 | React 页面入口、基础布局与 API 状态 | TypeScript 检查、Vite 构建通过 |
| <span class="status-badge status-done">✓</span> | 前端作业视图 | Fixture 作业列表、状态筛选、分页、详情、加载、空数据和错误重试 | TypeScript 检查、Vite 生产构建通过 |
| <span class="status-badge status-done">✓</span> | Fixture 作业提交 | 结构化提交 API、固定分区/账户/QoS、资源上限校验、模拟排队 Job ID 和基础提交表单 | 合法提交、非法参数测试及前端构建通过；未执行 sbatch |
| <span class="status-badge status-done">✓</span> | Fixture 作业控制 | 排队/运行作业取消、终态冲突保护、重新校验后克隆新 Job ID，以及前端确认和反馈 | 取消、克隆、404、409 集成测试及前端构建通过；未执行 scancel/sbatch |
| <span class="status-badge status-done">✓</span> | Fixture 作业日志 | stdout/stderr 流切换、字节偏移增量读取、缺失日志提示、刷新和继续加载 | 正常、缺失、404、416、非法参数集成测试及前端构建通过；未读取真实用户日志 |
| <span class="status-badge status-done">✓</span> | Fixture 资源统计 | 区分申请、分配和实际指标，聚合顶层与 `.batch` 数据，展示CPU、GPU、内存和时长 | 真实字段格式驱动的 parser、adapter、API 测试及前端构建通过；GPU实际使用保持未知 |
| <span class="status-badge status-done">✓</span> | 当前用户摘要 | 作业总数、活跃/成功/异常数量、完整状态分布和带字段覆盖率的资源快照合计 | 摘要初始值、提交后更新和前端构建通过；不声称为实际利用率 |
| <span class="status-badge status-done">✓</span> | Fixture MVP 回归 | 健康检查、列表/详情、日志、资源、提交、取消、克隆和摘要组成单一可重复故事 | `test_mvp_fixture_flow.py` 通过，不调用真实 Slurm |
| <span class="status-badge status-done">✓</span> | 身份设计 | 比赛原型采用后端进程有效 UID 对应的单 Unix 账号，HTTP 输入不能选择 Slurm 用户 | Native 创建前 UID/owner 精确匹配测试通过 |
| <span class="status-badge status-done">✓</span> | 身份与元数据链路 | SQLite source 隔离、旧表兼容升级、Slurm 状态优先去重合并和 owner 限定查询 | 恢复、跨 owner、来源隔离、旧表升级和合并测试通过 |
| <span class="status-badge status-done">✓</span> | Native 能力界面 | `/api/runtime` 分别声明提交、日志等能力，前端展示当前 Native 模式并隐藏未开放操作 | TypeScript 检查和 Vite 生产构建通过 |
| <span class="status-badge status-done">✓</span> | Native 平台验收 | 有效 UID、owner、真实列表、详情和 usage 在 107 运行通过 | 提交 `05a64a3`；用户 `pb24030760`；Job `21482`；`COMPLETED`；`0:0`；脚本退出 0 |
| <span class="status-badge status-done">✓</span> | Native 提交安全底座 | 窄命令白名单、资源上限、受控目录/脚本、参数数组、Job ID 解析、回执、owner 元数据和脱敏审计；未接入 HTTP | 注入式伪 `sbatch`、攻击字符串、文件边界、审计与授权门测试通过；未调用真实 `sbatch` |
| <span class="status-badge status-done">✓</span> | Native 最小提交验收 | 固定一次性入口提交 `python3 --version`，持久化 Job ID、owner 元数据、回执和审计；HTTP 保持关闭 | 提交 `88a0147`；用户 `pb24030760`；Job `24011`；`1 CPU / 512 MiB / 0 GPU / 1 分钟`；`COMPLETED`；`0:0` |
| <span class="status-badge status-done">✓</span> | Native 受控 HTTP 提交 | 默认关闭的部署门、持久化幂等摘要、同键安全重放、异请求冲突、活跃作业上限、稳定 Dashboard ID 和前端幂等重试 | 注入式 API 回归证明相同请求仅调用一次伪 `sbatch`；前端类型检查和生产构建通过；未调用真实 `sbatch` |
| <span class="status-badge status-done">✓</span> | Native HTTP 门禁验收 | 临时启用提交能力，验证缺少幂等键和非法命令在 `sbatch` 前稳定拒绝，其他写/日志能力继续关闭 | 提交 `0f88ede`；用户 `pb24030760`；`400/422`；`would_invoke_sbatch=false`；开关未持久化 |
| <span class="status-badge status-done">✓</span> | Native 受控日志 | owner/source 元数据限定、固定 submission 路径、普通文件与符号链接边界、字节偏移读取和默认关闭部署门 | 本地正常/缺失/跨 owner/穿越/文件类型/416/503 回归通过；未读取真实日志 |
| <span class="status-badge status-done">✓</span> | Native 日志路径预检 | 在不打开文件的前提下校验 Job `24011` 的 owner 元数据及 stdout/stderr 受控目录边界 | 提交 `beb39f7`；用户 `pb24030760`；两个路径均安全；`would_open_log=false`；`would_read_log=false`；开关未持久化 |
| <span class="status-badge status-done">✓</span> | Native 受控取消与克隆 | 独立门禁、Owner/元数据/状态二次校验、参数数组 scancel、持久化幂等和审计；克隆重新走提交校验与活跃上限 | 注入式闭环只调用一次伪 sbatch，并对来源/克隆各调用一次伪 scancel；未知 Job 不触发命令 |
| <span class="status-badge status-done">✓</span> | 代码质量 | Ruff、pytest、npm audit | 后端 203 个 pytest 通过（符号链接用例在 Windows 跳过），目标 Ruff 通过；0 个生产依赖漏洞 |
| <span class="status-badge status-done">✓</span> | 文档 | 架构、环境、协作、部署、API 契约 | 文档站可直接访问 |
| <span class="status-badge status-done">✓</span> | 文档体验 | 单章节按需加载、模糊过渡、URL 定位、前进后退和章节筛选 | 浏览器交互检查通过 |

## 当前待办与提示

<div class="notice-grid">
  <div class="notice notice-next"><strong>下一开发项</strong><span>在 107 集中执行 Job `24011` 的脱敏日志读取，以及脚本自建两个最小作业的提交、取消、克隆、再取消闭环。</span></div>
  <div class="notice notice-warning"><strong>暂时限制</strong><span>Native 提交、日志、取消和克隆长期部署开关均保持关闭；真实闭环验收通过前不要长期开放写能力。</span></div>
  <div class="notice notice-safe"><strong>安全边界</strong><span>真实测试只能通过 Slurm 提交，禁止在登录节点直接运行学生计算任务。</span></div>
  <div class="notice notice-info"><strong>验证方式</strong><span>Fixture 与注入式 Native 回归用于本地稳定验证，107 脚本用于平台门禁与真实验收：后端 pytest 203 passed、目标 Ruff、前端类型检查和生产构建通过。</span></div>
</div>

## MVP 必须功能

- [x] 前后端最小骨架与健康检查
- [x] 作业数据模型与 Fixture 只读 API
- [x] squeue、sacct、sinfo 受控查询参数与 fixture 输出解析
- [x] Fixture adapter 接入 jobs service/API
- [x] 真实 Slurm 查询与 jobs service/API 只读实现及 107 验收
- [x] Native 作业所有权校验实现、自动回归及 107 验收
- [x] 有效 UID 身份解析、部署 owner 断言和 SQLite 元数据仓库接入
- [x] 基础作业列表与详情页面
- [x] Fixture 作业提交与资源校验
- [x] 真实 sbatch 提交与 Job ID 持久化
- [x] Native HTTP 提交幂等、并发门禁和默认关闭的部署开关
- [x] Native HTTP 提交在 107 的无作业门禁检查
- [x] Fixture stdout/stderr 日志查看与增量读取
- [x] 真实日志路径映射、所有权校验与无读取平台预检
- [ ] 单次真实 stdout/stderr 读取验收
- [x] Fixture 作业取消与克隆
- [x] Native scancel 与基于持久化元数据的克隆受控实现
- [ ] 真实平台提交、取消、克隆、再取消闭环验收
- [x] Fixture 作业级 CPU、GPU、内存和运行时长统计
- [x] 当前用户作业与资源字段摘要
- [x] 真实统计平台验收
- [x] Mock/Fixture 完整故事自动回归
- [ ] 预提交作业与真实平台演示回归

## 可选创新功能

- [ ] 自动演示模式与 Slurm 故障回退
- [ ] 状态变化提示和智能轮询
- [ ] 资源趋势图与申请/实际使用对比
- [ ] 常用作业模板
- [ ] 基于退出码和日志特征的失败排查提示

## 维护规则

每次 PR 准备合入 `master` 前，负责开发或评审的 Agent 必须检查本页。若 PR 改变功能状态、验证证据、阶段进度、限制或下一任务，应在同一 PR 中同步更新本页；管理员直接提交阶段成果时执行相同规则。

只有相关测试、构建、fixture 或真实平台证据通过后，功能才能标记为“已完成”。不影响项目进度的 PR 应在评审摘要中注明“无需更新进度表”，避免无意义改动。
