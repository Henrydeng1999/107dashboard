from datetime import UTC, datetime, timedelta

from app.schemas.jobs import Job, JobListResponse, JobResources, JobState


def _demo_jobs() -> list[Job]:
    now = datetime.now(UTC)
    return [
        Job(
            id="local-job-001",
            slurm_job_id="21482",
            owner="demo-user",
            name="mnist-training",
            state=JobState.RUNNING,
            partition="Students",
            account="stu",
            qos="qos_stu_default",
            command="python train.py",
            resources=JobResources(cpus=2, memory_mb=4096, gpus=1, time_limit_minutes=60),
            node="anode05",
            submitted_at=now - timedelta(minutes=12),
            started_at=now - timedelta(minutes=11),
            updated_at=now,
        ),
        Job(
            id="local-job-002",
            slurm_job_id="21481",
            owner="demo-user",
            name="data-preprocess",
            state=JobState.COMPLETED,
            partition="Students",
            account="stu",
            qos="qos_stu_default",
            command="python preprocess.py",
            resources=JobResources(cpus=1, memory_mb=2048, gpus=0, time_limit_minutes=30),
            node="anode06",
            exit_code="0:0",
            submitted_at=now - timedelta(hours=1),
            started_at=now - timedelta(minutes=59),
            finished_at=now - timedelta(minutes=45),
            updated_at=now,
        ),
    ]


def list_jobs(owner: str, state: JobState | None, page: int, page_size: int) -> JobListResponse:
    jobs = [job for job in _demo_jobs() if job.owner == owner and (state is None or job.state == state)]
    start = (page - 1) * page_size
    return JobListResponse(
        items=jobs[start : start + page_size],
        page=page,
        page_size=page_size,
        total=len(jobs),
        updated_at=datetime.now(UTC),
    )


def get_job(owner: str, job_id: str) -> Job | None:
    return next((job for job in _demo_jobs() if job.owner == owner and job.id == job_id), None)
