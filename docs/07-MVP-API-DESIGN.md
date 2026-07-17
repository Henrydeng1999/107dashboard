# MVP 作业模型与 API 设计

本文定义第一版前后端联调契约。字段优先保持简单、可由 Mock 和 Slurm 两种数据源共同提供。

## 核心对象

```json
{
  "id": "local-job-001",
  "slurm_job_id": "21482",
  "owner": "demo-user",
  "name": "mnist-training",
  "state": "RUNNING",
  "partition": "Students",
  "account": "stu",
  "qos": "qos_stu_default",
  "command": null,
  "resources": {"cpus": 2, "memory_mb": 4096, "gpus": 1, "time_limit_minutes": 60},
  "node": "anode05",
  "exit_code": null,
  "reason": null,
  "submitted_at": null,
  "started_at": null,
  "finished_at": null,
  "updated_at": "2026-07-15T10:02:00Z"
}
```

`id` 是 Dashboard 内部标识，`slurm_job_id` 是 Slurm 事实来源。克隆时必须生成新的两个标识。

只读 Slurm 查询不会伪造 Slurm 未提供的数据。`name`、`partition`、`account`、`qos`、
`command`、`node`、`exit_code`、`reason`、`submitted_at`、`started_at`、`finished_at`，
以及 `resources` 内各字段均允许为 `null`。当前 `squeue`/`sacct` 查询没有作业命令和提交、
开始、结束时间的可靠来源，因此这些字段保持 `null`；后续只能由受信任的 Dashboard 元数据
或新增的结构化 Slurm 字段补齐。当前前端仅消费列表的 `total`，尚未依赖这些 nullable 字段。

## 状态和资源边界

状态统一为：`PENDING`、`RUNNING`、`COMPLETED`、`FAILED`、`CANCELLED`、`TIMEOUT`、`UNKNOWN`。

默认使用已验证的 `Students + stu + qos_stu_default`：CPU 1-4、GPU 0-1、内存 512-16384 MB、时长 1-240 分钟。提交和克隆时必须后端重新校验，前端校验不能替代后端校验。

## API 契约

```text
GET  /api/health
GET  /api/jobs?state=RUNNING&page=1&page_size=20
GET  /api/jobs/summary
GET  /api/jobs/{job_id}
POST /api/jobs
GET  /api/jobs/{job_id}/logs?stream=stdout&offset=0&limit=16384
GET  /api/jobs/{job_id}/usage
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/clone
```

Fixture 模式下，`POST /api/jobs` 仅模拟生成排队作业，不执行 `sbatch`。第一版提交请求固定使用已验证组合 `Students + stu + qos_stu_default`，资源范围为 CPU 1-4、GPU 0-1、内存 512-16384 MiB、时长 1-240 分钟；作业名称和命令均拒绝换行及超长输入。

Fixture 模式支持取消可见的 `PENDING`、`RUNNING` 作业，并保留取消后的历史记录。克隆会读取原作业的提交参数，重新通过同一个 `JobSubmitRequest` 校验后生成新 Job ID；只读样例缺少命令或完整资源参数时返回 `409 JOB_OPERATION_CONFLICT`。不存在的作业统一返回 `404 JOB_NOT_FOUND`，Native 控制功能仍返回脱敏的 `503`。

列表、详情、日志和控制操作只允许访问当前用户自己的作业。不存在或不属于当前用户时统一返回 `404`，避免暴露其他用户的作业是否存在。

列表先合并同一 Slurm Job ID：`squeue` 的实时状态、节点、原因和当前资源优先，
`sacct` 仅逐字段填补空值。随后按 Slurm Job ID 的数字前缀降序、完整 ID 降序稳定排序，
最后才筛选和分页，因此轮询时在数据未变化的情况下分页边界保持稳定。单次快照最多保留
`SLURM_MAX_JOBS` 个作业（默认 1000），查询结果使用 `SLURM_QUERY_CACHE_TTL_SECONDS`
秒的短缓存（默认 2 秒），同一刷新窗口内的并发请求合并为一次 `squeue` + `sacct` 查询。

提交请求至少包含 `name`、`command`、`partition`、`account`、`qos` 和资源对象。服务端校验通过后才生成受控脚本并调用 `sbatch`；禁止拼接未经校验的 shell 字符串。

日志的 `stream` 只允许 `stdout` 或 `stderr`，`offset` 使用从 0 开始的字节偏移，`limit` 范围为 1-65536 字节。响应返回 `content`、`next_offset`、`eof` 和 `available`；尚未产生日志时返回空内容且 `available=false`，偏移超过文件末尾返回 `416 JOB_LOG_OFFSET_OUT_OF_RANGE`。Fixture 文件路径只能由服务端根据已校验的 Slurm Job ID 和流类型生成，客户端不能提交路径。取消只允许 `PENDING` 或 `RUNNING` 作业。克隆必须重新校验并重新提交，不能复用旧 Job ID。

资源统计接口分别返回 `requested`、`allocated`、`elapsed_seconds`、`time_limit_seconds`、`max_rss_kb` 和 `total_cpu_seconds`。顶层作业记录提供申请、分配和时长，`.batch` 步骤提供峰值内存等实际指标；峰值内存以 KiB 保存，避免 `260K` 被错误舍入为 0 MiB。`0` 与 `null` 必须区分：零表示平台明确报告为零，`null` 表示平台未提供。当前平台没有 `gpuutil` 或 `gpumem`，因此 GPU 实际利用率和显存使用保持 `null`，不能根据分配数量推断。

用户摘要接口仅汇总服务端可信身份对应的可见作业，返回作业总数、活跃/成功/异常数量、完整状态分布，以及资源字段合计和每项覆盖作业数。资源口径固定为 `requested_or_allocated_snapshot`，表示当前作业记录中的申请或分配值，不代表实际利用率；缺失字段不作为 0 参与合计。

## 统一错误格式

```json
{"error": {"code": "JOB_NOT_FOUND", "message": "Job was not found", "request_id": "request-id"}}
```

前端依赖稳定的 `code`，不依赖 Slurm 原始输出文本。
`404`、`503` 和参数校验 `422` 均使用该格式；`request_id` 由服务端生成，不接受请求方覆盖，
并同时写入 `X-Request-ID` 响应头。底层 Slurm 命令、用户、路径和 stderr 不进入 API 响应。

## Native Slurm 安全门禁

默认和 `.env.example` 均使用 fixture。即使误将 `SLURM_DATA_SOURCE` 改为 `native`，
应用也会在创建 native adapter 和 subprocess runner 之前无条件 fail closed。当前项目尚无
可信认证和逐请求身份映射，因此不存在可启用真实 Native jobs API 的环境开关。未来只有在
可信认证、所有权映射和部署审查完成并修改应用实现后，才能开放 native 访问；请求参数、
客户端 header 或环境布尔值均不能开启。

比赛原型选用单 Unix 账号身份边界：未来 Native 实现必须从 FastAPI 进程的有效 UID 解析用户名，并将 `DASHBOARD_OWNER` 作为启动一致性断言；任何 HTTP 输入都不能选择用户。每个作业操作还需以 Slurm 返回的 user 或持久化 owner 复核所有权。该设计已经确定，但代码门禁不会因为文档确定而自动开放。

## Fixture 与 Native 验证策略

Fixture 和 Native 采用并行验证，不互相替代：

- Fixture 用于自动化回归、边界条件和故障场景，稳定覆盖 `PENDING`、`RUNNING`、终态、空队列、异常字段、超时和命令失败；
- Native 用于每个 Slurm 功能完成后的真实平台验收，避免仅凭脱敏样例判断平台兼容性；
- 只读查询可以在 107 登录节点使用当前 Linux 用户和最小暴露范围验证；提交、取消等写操作必须使用最小资源、最短时长，并保留 Job ID、资源、状态和退出码证据；
- Native 验证通过不代表可以绕过认证门禁。正式 API 仍需可信身份映射和逐请求所有权校验。

2026-07-17 已在 107 登录节点进行一次只读验证：在不修改源码和 `.env` 的临时测试实例中，向
`JobCatalog` 注入 `NativeSlurmAdapter`，`GET /api/jobs` 返回 HTTP 200，并读取到当前用户最近
7 天内的真实作业 `21482`。API 返回的状态、分区、账户、QoS、节点、CPU、内存、GPU、时限和
退出码与同一时刻的 `squeue`/`sacct` 原始查询一致。测试结束后临时进程和回环端口均已关闭。
该证据只证明 Native 只读链路可用，不代表生产 Native API、真实提交、日志、取消或克隆已经开放。

## 实现顺序

1. Pydantic schema 固化请求和响应；
2. fixture 驱动的 Mock Slurm adapter；
3. 作业列表和详情只读 API；
4. SQLite repository；
5. 提交、日志、取消和克隆；
6. 最小资源真实 Slurm 验证。
