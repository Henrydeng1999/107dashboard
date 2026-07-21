# 09 AI 赋能实施计划

## 1. 文档目的

本文定义 107 Dashboard 从“学生 Slurm 作业管理面板”演进为“AI Native HPC Research Platform”的可实施路线。目标不是用大模型替代 Slurm、权限校验或科研判断，而是在现有真实作业闭环之上增加日志诊断、指标可视化和实验报告能力，让学生更容易理解作业结果、定位失败并沉淀实验记录。

本文是增量演进方案，不改变当前比赛 MVP 的事实来源和安全边界。现有作业管理功能必须继续独立可用；AI 服务不可用时，提交、查询、日志、取消、克隆和资源统计仍应正常工作。

当前范围已经确定为单 Unix 账号比赛版本。分析、报告和项目评价只能处理后端进程所属账号的 owner 可见数据；多用户登录、跨账号比较、共享项目和校园 SSO 不进入本计划的比赛验收。

## 2. 可行性结论

总体可行，但原提案中的能力不能视为同等成本，也不应一次性实现。

| 方向 | 可行性 | 当前基础 | 判断 |
| --- | --- | --- | --- |
| 科研工作台式首页 | 高 | 已有 React/Vite 页面、作业摘要和状态 | 可直接迭代信息架构与视觉系统 |
| 页面动画与高级交互 | 高 | 当前仅依赖 React/React DOM | 可引入 Router、图标和轻量动画，但应服务于操作反馈 |
| 作业指标曲线 | 高 | 已有 usage、日志和受控项目 | 先定义结构化 metrics 契约，再接图表库 |
| 规则化失败诊断 | 高 | 已有状态、退出码、reason、stdout/stderr | 成本低、结果稳定，适合作为第一阶段 |
| LLM 日志总结 | 中高 | 已有受控日志读取与 owner 校验 | 需先做脱敏、截断、提示注入隔离和超时降级 |
| 自动实验报告 | 中高 | 已有作业元数据、usage 和日志 | 适合模板生成，LLM 只补充解释性文字 |
| 学校私有模型接入 | 中 | FastAPI 易于接入兼容 API | 取决于网络、认证、限流、模型 SLA 和数据政策 |
| 任意 checkpoint 自动分析 | 低 | 当前没有统一产物协议 | 文件格式、体积和不可信反序列化风险较高，暂不纳入 MVP |
| Three.js 集群数字孪生 | 中 | 当前无 3D 依赖和实时节点遥测 | 展示价值有限、成本较高，不作为关键路径 |

结论：比赛阶段可以做出有说服力的“AI+HPC”闭环，但应聚焦一个纵向切片：**作业结束或失败后，自动整理可信事实、绘制指标、生成带证据的诊断与报告**。单纯增加动态背景不会提升产品壁垒。

## 3. 产品定位与原则

建议产品名称暂定为：

> 107 AI HPC Research Copilot

一句话定位：

> 面向高校科研计算场景，将 Slurm 作业、运行指标、日志诊断和实验报告整合为一个可信的科研工作台。

实施原则：

1. **Slurm 是事实来源**：作业状态、退出码和资源数据以 `squeue`、`sacct` 和受控日志为准。
2. **确定性处理优先**：结构化解析、规则诊断和图表数据先于 LLM；可计算的指标不交给模型猜测。
3. **AI 只读、可解释**：AI 不直接提交、取消、克隆作业，不修改脚本，不执行建议命令。
4. **证据与推断分离**：报告明确区分“系统事实”“规则命中”“AI 推断”和“建议”。
5. **失败可降级**：模型超时、限流或不可用时，页面仍展示结构化数据与规则诊断。
6. **隐私最小化**：只发送完成分析所需的最少日志片段和指标，不发送密钥、路径、环境变量或完整源码。
7. **不假报能力**：缺失 GPU 遥测、准确率或曲线数据时显示“未采集”，不得补零或由模型虚构。

## 4. 目标用户与核心场景

### 4.1 初学者提交作业

学生从受控项目或模板选择任务，填写 CPU、GPU、内存和时限后提交。系统解释资源配置并保留当前后端校验，不让 AI 绕过白名单与 QoS 上限。

### 4.2 失败作业诊断

系统采集 owner 范围内的状态、退出码、Slurm reason 和限量日志，先匹配 CUDA OOM、超时、文件缺失、模块缺失、权限错误等规则，再由 AI 将证据组织成易读说明。

### 4.3 计算过程理解

项目按约定输出通用长格式 `metrics.jsonl` 或 `metrics.csv`，后端进行受限解析。CPU 数值计算可以展示 residual、iteration 和 throughput，测试作业可以展示 pass/fail，机器学习任务可以展示 loss、accuracy 和 learning rate；没有专项指标时仍生成基础 Slurm 报告。AI 只能解释已解析的数据，不解析图像像素猜测数值。

### 4.4 实验归档与汇报

作业完成后，系统以模板生成 Markdown 报告，包含配置、状态、关键指标、资源使用、异常、图表和建议。用户确认后再导出；报告不自动成为论文结论。

## 5. 比赛 MVP 范围

### 5.1 必须完成

- 四个一级模块形成统一导航：作业提交管理、作业诊断自动报告、项目结果评价、AI 工作台；
- 作业提交管理继续覆盖真实列表、结构化提交、状态、日志、usage、取消和克隆；
- 基于状态、退出码、reason 和日志特征的确定性规则诊断；
- 支持通用长格式结构化指标，CPU 与 GPU 项目均可使用；
- 前端在指标存在时展示 residual、throughput、loss、accuracy 或测试通过率等项目专项指标，不存在时明确显示缺失；
- 对终态作业手动触发 AI 分析，返回摘要、证据、风险提示和建议；
- 一键生成 Markdown 实验报告预览；
- 项目页可以比较同一登记项目下的多次真实实验，展示结果质量、稳定性、资源效率、可复现性和证据覆盖率；
- 模型不可用时展示规则诊断和模板报告；
- Fixture 中准备成功、OOM、超时或受控失败等脱敏演示样例。

### 5.2 比赛阶段不做

- 不允许 AI 自动执行修复或重新提交；
- 不允许未经校验的任意模型 Endpoint，也不允许通过查询接口读取或回显 API Key；
- 不读取任意服务器路径或其他用户产物；
- 不加载 PyTorch pickle checkpoint；
- 不做任意格式科研数据理解；
- 不以 Three.js 动态背景作为阻塞项；
- 不实现生产级多用户、校园 SSO、跨账号 Slurm 委托或跨用户项目评价。

## 6. 目标架构

```text
浏览器
  |
  v
FastAPI API
  |
  +--> JobCatalog / Slurm Adapter ----> squeue / sacct / sbatch / scancel
  |
  +--> Analysis Service
         |
         +--> Evidence Collector
         |      状态、退出码、reason、限量日志、usage、metrics
         |
         +--> Redaction & Budget Guard
         |      脱敏、截断、字段白名单、大小限制
         |
         +--> Rule Engine
         |      确定性错误分类和建议
         |
         +--> LLM Provider Adapter
         |      学校私有模型或 OpenAI-compatible API
         |
         +--> Report Builder
                结构化结果 + Markdown 报告
  |
  +--> SQLite
         作业元数据、分析版本、状态、结果、审计；不保存原始 API Key
```

AI 分析不直接调用 Slurm 写操作。它只消费现有 service 已完成 owner 校验后返回的受控证据，不能自行接受 `job_id` 后绕过 `JobCatalog` 读取日志路径。

## 7. 后端设计

建议在现有边界内增量增加：

```text
backend/app/
├── ai/
│   ├── provider.py          # LLM Provider Protocol 与兼容客户端
│   ├── prompts.py           # 版本化系统提示和输出契约
│   ├── redaction.py         # 密钥、路径、Token、环境变量脱敏
│   ├── rules.py             # 确定性错误诊断
│   └── models.py            # 内部分析模型
├── services/
│   ├── job_analysis.py      # owner 校验后的分析编排
│   ├── metrics_parser.py    # 受限 CSV/JSONL 解析
│   └── report_builder.py    # 报告模板
├── schemas/
│   └── analysis.py          # API 请求与响应
└── api/routes/
    └── analyses.py          # HTTP 边界
```

`ai/` 只负责模型调用和纯处理；owner 校验、证据收集、幂等与审计留在 service。若新增该目录，应同步更新 `docs/05-DIRECTORY-STRUCTURE.md`。

### 7.1 建议 API

```text
POST /api/jobs/{job_id}/analyses
GET  /api/jobs/{job_id}/analyses/latest
GET  /api/jobs/{job_id}/metrics
GET  /api/jobs/{job_id}/reports/latest
```

创建分析请求不接受日志、路径、owner、模型 Endpoint 或提示词，只接受有限选项：

```json
{
  "analysis_type": "completion",
  "language": "zh-CN"
}
```

建议响应：

```json
{
  "id": "analysis-...",
  "job_id": "slurm-24159",
  "status": "completed",
  "evidence": {
    "job_state": "COMPLETED",
    "exit_code": "0:0",
    "log_bytes_analyzed": 4096,
    "metrics_available": true
  },
  "rule_findings": [],
  "ai_summary": "作业正常完成，Loss 持续下降。",
  "recommendations": ["检查验证集指标后再决定是否继续训练"],
  "model": "school-qwen",
  "prompt_version": "job-analysis-v1",
  "generated_at": "..."
}
```

### 7.2 指标文件契约

不要扫描任意 checkpoint。第一版只允许服务端登记项目在其 submission 目录内输出固定文件：

- `metrics.jsonl`，每行一个 JSON 对象；或
- `metrics.csv`，首行为固定字段名。

建议字段：`step`、`epoch`、`loss`、`val_loss`、`accuracy`、`val_accuracy`、`learning_rate`、`timestamp`。限制文件为普通文件、禁止符号链接、限定 owner、规范化路径、最大文件大小、最大行数和数值范围。未知字段忽略，非法行计数并报告，不执行文件中的任何内容。

### 7.3 分析状态与幂等

- 分析只允许对当前 owner 可见作业执行；
- 默认只分析终态作业，运行中分析可作为后续能力；
- 同一 Job、证据摘要、分析类型和 prompt 版本生成稳定请求摘要；
- 重复请求返回已有结果，避免重复消耗模型额度；
- 记录 `queued/running/completed/failed` 状态、耗时和脱敏错误码；
- 不将模型原始异常、请求体或密钥返回浏览器。

比赛版可先在单进程内执行短任务，但必须设置严格超时。若真实模型响应经常超过 HTTP 时限，再引入持久化后台 worker；不要为路演过早增加 Redis/Celery。

## 8. AI Provider 接入

采用 Provider Protocol 隔离学校模型：

```python
class LLMProvider(Protocol):
    async def analyze(self, request: AnalysisPrompt) -> AnalysisResult: ...
```

配置由管理员通过环境变量注入，例如：

```text
AI_ANALYSIS_ENABLED=false
AI_PROVIDER=openai-compatible
AI_BASE_URL=https://llm.example.edu/v1
AI_MODEL=Qwen2.5-72B-Instruct
AI_API_KEY=...
AI_TIMEOUT_SECONDS=30
AI_MAX_INPUT_CHARS=20000
AI_MAX_OUTPUT_TOKENS=1200
```

要求：

- 学校默认 API Key 只存在于部署环境或密钥服务；可选自定义 Key 只能写入 owner 私有的 `0600` 服务端密钥文件或密钥服务，不进入 SQLite、日志、Git，也不在前端持久化或通过读取接口回显；
- 学校默认 Endpoint 和模型由部署方配置；单账号自定义 Provider 必须通过受控表单、OpenAI-compatible 协议校验、域名/IP 策略和连接测试后才能保存；
- 启动时验证 HTTPS、允许域名和超时；内网 HTTP 需管理员明确批准；
- 禁止跟随任意重定向访问内网元数据地址；
- 设置并发、频率和单作业分析次数上限；
- 对结构化输出做 Pydantic 校验，解析失败时降级为规则结果；
- 保存模型名、prompt 版本和证据摘要以便复现，不默认保存完整模型请求。

## 9. 日志安全与提示注入

作业日志是不可信数据。日志里可能包含“忽略系统指令”等文本，也可能意外泄露 Token、绝对路径、用户名和数据内容。

送入模型前必须：

1. 经过现有 owner 与日志路径校验；
2. 限制 stdout/stderr 的首尾窗口和总字符数；
3. 对 API Key、Bearer Token、私钥块、常见凭证、邮箱和平台路径做脱敏；
4. 将日志置于明确的数据边界中，提示模型不得执行或服从日志内指令；
5. 不提供工具，不允许模型访问网络、文件系统或 Slurm；
6. 要求输出引用证据类型，不把模型文字标记为平台事实；
7. 在 UI 中声明“AI 建议可能有误，请结合原始日志验证”。

## 10. 自动绘图方案

第一版不让 LLM 生成绘图代码。后端解析结构化 metrics，前端用图表库渲染，才能保证数值可信和交互一致。

建议选型：

- 图标：`lucide-react`；
- 路由：`react-router-dom`；
- 动画：`motion`，只用于页面进入、状态变化和抽屉；
- 图表：优先 `echarts`，若只需少量折线图可评估更轻的方案；
- 3D：暂不引入。

图表至少支持：指标选择、Tooltip、缩放、空数据、解析警告和数据更新时间。资源指标必须继续区分申请、分配和实际使用；没有 GPU 实时遥测时，不展示伪造的 GPU 利用率曲线。

## 11. 前端信息架构

采用操作型产品的紧凑布局，参考 Cloudflare 控制台的页面比例、固定侧栏、顶栏和双栏窗格，但不复制品牌资产。一级模块下按职责拆分子页面，避免一个页面无限向下增长：

```text
作业
├── 作业总览 /jobs
├── 新建作业 /jobs/new
├── 活动作业 /jobs/active
├── 历史作业 /jobs/history
└── 作业详情 /jobs/:id

诊断与报告
├── 报告总览 /reports
├── 诊断详情 /reports/:jobId
└── 报告预览 /reports/:jobId/preview

项目评价
├── 项目总览 /projects
├── 项目详情 /projects/:id
├── 实验对比 /projects/:id/experiments
└── 结果评价 /projects/:id/evaluation

AI
├── Chat /ai/chat
├── 模型接入 /ai/providers
├── API 密钥 /ai/keys
├── 提示词模板 /ai/prompts
└── 调用记录 /ai/history
```

桌面 Figma 基准为 `1600×800`，最低浏览器内容视口为 `1440×720`。根页面不滚动；主区优先使用约 `68/32` 的双栏，大窗格承载表格、表单、日志、指标和对话，小窗格承载摘要、状态、操作、诊断和建议。超量内容放入窗格内部滚动，或拆分成上述子页面。移动端可以单栏滚动。视觉升级重点应是层级、密度、状态反馈、排版和一致组件，而不是堆叠发光卡片。

AI Chat 默认使用学校 Provider，并允许选择经过 owner 校验的作业、报告或项目作为上下文；模型不得自动读取未选择的数据。模型接入页展示 Provider 名称、兼容协议、Endpoint、模型名、连接状态和最后验证时间。API 密钥页只提供写入、替换、连接测试和删除，保存后仅显示掩码与更新时间。原始密钥不得进入前端存储、SQLite、Git、普通日志或可下载报告。提示词模板区分系统内置模板和当前账号自定义模板；调用记录保存模型、用途、时间、耗时、状态和预算信息，不默认保存完整敏感 Prompt。

## 12. 实施阶段

### Phase A：可信诊断底座

目标：不依赖 LLM 也能给出稳定价值。

- 定义 analysis schema 和状态模型；
- 建立 owner 范围内的 Evidence Collector；
- 实现日志脱敏、截断和证据摘要；
- 实现 OOM、超时、退出码、模块/文件/权限错误规则；
- 增加 Fixture 与单元测试；
- 前端新增诊断区域并展示证据来源。

验收：关闭 AI 配置时，受控失败样例仍能返回正确错误类型和保守建议；不读取其他 owner 或任意路径。

### Phase B：指标与报告

目标：完成可视化实验闭环。

- 定义 `metrics.jsonl/csv` 契约；
- 增加一个可快速完成的 CPU 数值计算示例，并在条件允许时增加一个最小 GPU 示例；
- 实现安全解析、降采样和 Metrics API；
- 增加按指标名渲染的通用曲线和空状态；
- 用确定性模板生成 Markdown 报告。

验收：成功作业可展示真实指标曲线并导出报告；损坏或超限文件被安全拒绝，页面不假报数据。

### Phase C：私有 LLM 增强

目标：把规则和指标组织成自然语言分析。

- 实现 Provider Protocol 和 OpenAI-compatible 客户端；
- 接入管理员配置的学校私有模型；
- 设计版本化提示与结构化输出；
- 增加超时、限流、幂等、缓存和降级；
- 展示模型、生成时间、证据与免责声明。

验收：模型可用时生成结构化总结；断网、超时、非 JSON 或幻觉字段时仍返回规则结果，不影响主业务。

### Phase D：体验升级与比赛包装

目标：形成清晰、有节奏的演示。

- 按已确认设计实现作业、诊断与报告、项目评价、AI 四个一级模块及必要子页面；
- 建立颜色、排版、间距、按钮、状态和图表规范；
- 加入克制的页面与状态动画；
- 准备真实路径和脱敏 Fixture 两套演示数据；
- 完成桌面和移动端截图回归、可访问性与性能检查。

验收：核心演示在模型不可用时仍能完成；页面不重排、不重叠，动效关闭后功能完整。

## 13. 建议开发拆分

| 分支 | 内容 | 依赖 |
| --- | --- | --- |
| `feature/analysis-contract` | schema、状态、API 契约与迁移 | 当前 Job API |
| `feature/diagnostic-rules` | Evidence Collector、脱敏和规则诊断 | analysis contract |
| `feature/metrics-ingestion` | metrics 契约、安全解析和 API | 受控项目快照 |
| `feature/metrics-charts` | Job Detail 图表与空状态 | metrics API |
| `feature/report-builder` | 模板报告与预览 | analysis、metrics |
| `feature/llm-provider` | Provider、超时、结构化输出和降级 | 脱敏与规则诊断 |
| `feature/research-workspace-ui` | Overview、导航和设计系统 | 稳定 API |
| `feature/ai-demo-flow` | Fixture、演示脚本和端到端验收 | 全部纵向切片 |

每个分支都应同步更新 API 文档和 `docs/08-PROGRESS-CHECKLIST.md`。AI 功能未通过测试前保持 `AI_ANALYSIS_ENABLED=false`。

## 14. 测试与验收矩阵

### 后端

- owner 不匹配、未知 Job、Fixture/Native source 混淆；
- 日志路径穿越、符号链接、非普通文件和超限内容；
- Token、私钥、绝对路径和环境变量脱敏；
- metrics 空文件、非法列、NaN/Infinity、超长行、超大文件；
- LLM 超时、429、5xx、非法 JSON、缺字段和超长输出；
- 同证据重复分析不重复调用模型；
- AI 关闭或失败不影响现有 Job API。

### 前端

- loading、empty、partial、failed、degraded 和 stale 状态；
- 长作业名、长诊断文本、窄屏与移动端无重叠；
- 图表空数据、单点、万级点降采样和 Tooltip；
- `prefers-reduced-motion`；
- AI 推断与系统事实视觉区分；
- 现有提交、日志、取消、克隆流程无回归。

### 平台验收

真实平台只使用最小、受控且由验收流程创建的作业。报告 Job ID、资源、终态、退出码和采集证据；不得为测试 AI 而扩大 Slurm 资源。学校 LLM 接入验收不得在日志中输出 API Key 或原始敏感请求。

## 15. 比赛演示脚本

建议控制在四分钟：

1. **工作台**：展示真实服务状态、最近实验和活动作业；
2. **提交**：选择受控 CPU 或 GPU 示例，配置最小资源并提交；
3. **运行**：展示实时状态和增量日志，不等待长计算；
4. **结果**：打开预置完成作业，展示真实专项指标或明确的指标缺失状态，以及 Slurm 资源统计；
5. **诊断**：打开受控失败作业，规则识别错误，AI 用证据解释原因；
6. **报告**：生成 Markdown 实验报告，展示事实、图表、分析和建议；
7. **降级证明**：说明 AI 失败不会影响 Slurm 主流程，Fixture 数据有明确标识。

比赛演示应预先准备完成作业和失败作业，现场提交只用于证明链路，不能把节奏押在排队时间或模型响应速度上。

## 16. 成功指标

- 常见受控错误的规则分类准确率达到预设样例 100%；
- AI 不可用时主作业流程成功率不下降；
- 分析结果中的所有事实字段都能追溯到 Slurm、日志、usage 或 metrics；
- 单次分析输入和输出有明确预算，响应超时可控；
- 演示路径四分钟内稳定完成；
- 不出现跨 owner 数据、密钥、原始服务器路径或未脱敏日志泄露；
- 新增前端在目标桌面和移动视口无重叠，生产构建通过。

## 17. 开工前待确认

1. 学校私有模型的兼容协议、Endpoint、模型名、认证方式和网络可达性；
2. 学校是否允许将学生作业日志发送给该模型，日志保留与审计政策是什么；
3. 首个真实指标样例优先选择 CPU 数值计算、GPU 训练，还是两者同时覆盖；
4. 报告只需 Markdown 预览与下载，还是必须生成 PDF；
5. 比赛评分更偏技术创新、视觉展示，还是平台安全与工程完整度。

已确定答案：单 Unix 账号、四个一级模块、`2:1` 浏览器内容视口、页面级无滚动、Slurm 事实优先、规则诊断先行、AI 只读且手动触发。其余推荐默认采用学校 OpenAI-compatible Provider、通用长格式 `metrics.jsonl`、Markdown 报告和 Three.js 延后；首批验收尽量同时包含一个 CPU 项目和一个 GPU 项目。
