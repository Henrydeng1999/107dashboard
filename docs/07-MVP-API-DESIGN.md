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
GET  /api/jobs/{job_id}
POST /api/jobs
GET  /api/jobs/{job_id}/logs?stream=stdout&tail=200
POST /api/jobs/{job_id}/cancel
POST /api/jobs/{job_id}/clone
```

Fixture 模式下，`POST /api/jobs` 仅模拟生成排队作业，不执行 `sbatch`。第一版提交请求固定使用已验证组合 `Students + stu + qos_stu_default`，资源范围为 CPU 1-4、GPU 0-1、内存 512-16384 MiB、时长 1-240 分钟；作业名称和命令均拒绝换行及超长输入。

列表、详情、日志和控制操作只允许访问当前用户自己的作业。不存在或不属于当前用户时统一返回 `404`，避免暴露其他用户的作业是否存在。

列表先合并同一 Slurm Job ID：`squeue` 的实时状态、节点、原因和当前资源优先，
`sacct` 仅逐字段填补空值。随后按 Slurm Job ID 的数字前缀降序、完整 ID 降序稳定排序，
最后才筛选和分页，因此轮询时在数据未变化的情况下分页边界保持稳定。单次快照最多保留
`SLURM_MAX_JOBS` 个作业（默认 1000），查询结果使用 `SLURM_QUERY_CACHE_TTL_SECONDS`
秒的短缓存（默认 2 秒），同一刷新窗口内的并发请求合并为一次 `squeue` + `sacct` 查询。

提交请求至少包含 `name`、`command`、`partition`、`account`、`qos` 和资源对象。服务端校验通过后才生成受控脚本并调用 `sbatch`；禁止拼接未经校验的 shell 字符串。

日志的 `stream` 只允许 `stdout` 或 `stderr`，`tail` 必须有上限，并拒绝路径穿越。取消只允许 `PENDING` 或 `RUNNING` 作业。克隆必须重新校验并重新提交，不能复用旧 Job ID。

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

## 实现顺序

1. Pydantic schema 固化请求和响应；
2. fixture 驱动的 Mock Slurm adapter；
3. 作业列表和详情只读 API；
4. SQLite repository；
5. 提交、日志、取消和克隆；
6. 最小资源真实 Slurm 验证。
