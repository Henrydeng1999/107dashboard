# Fixtures

离线开发和比赛演示使用的固定输入数据。

```text
slurm/       脱敏后的 squeue、sacct、sinfo 等输出样例
job-output/  成功、失败、排队等作业日志样例
```

Fixtures 必须脱敏，不能包含密码、Token、私钥、真实用户目录或未授权的其他用户信息。

`job-output/` 使用 `<slurm_job_id>.stdout.log` 和 `<slurm_job_id>.stderr.log` 命名。文件名只对应脱敏 Fixture Job ID，不使用用户输入路径。
