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
  "command": "python train.py",
  "resources": {"cpus": 2, "memory_mb": 4096, "gpus": 1, "time_limit_minutes": 60},
  "node": "anode05",
  "exit_code": null,
  "reason": null,
  "submitted_at": "2026-07-15T10:00:00Z",
  "started_at": "2026-07-15T10:01:00Z",
  "finished_at": null,
  "updated_at": "2026-07-15T10:02:00Z"
}
```

`id` 是 Dashboard 内部标识，`slurm_job_id` 是 Slurm 事实来源。克隆时必须生成新的两个标识。

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

列表、详情、日志和控制操作只允许访问当前用户自己的作业。不存在或不属于当前用户时统一返回 `404`，避免暴露其他用户的作业是否存在。

提交请求至少包含 `name`、`command`、`partition`、`account`、`qos` 和资源对象。服务端校验通过后才生成受控脚本并调用 `sbatch`；禁止拼接未经校验的 shell 字符串。

日志的 `stream` 只允许 `stdout` 或 `stderr`，`tail` 必须有上限，并拒绝路径穿越。取消只允许 `PENDING` 或 `RUNNING` 作业。克隆必须重新校验并重新提交，不能复用旧 Job ID。

## 统一错误格式

```json
{"error": {"code": "JOB_NOT_FOUND", "message": "Job was not found", "request_id": "request-id"}}
```

前端依赖稳定的 `code`，不依赖 Slurm 原始输出文本。

## 实现顺序

1. Pydantic schema 固化请求和响应；
2. fixture 驱动的 Mock Slurm adapter；
3. 作业列表和详情只读 API；
4. SQLite repository；
5. 提交、日志、取消和克隆；
6. 最小资源真实 Slurm 验证。
