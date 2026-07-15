from fastapi import APIRouter, HTTPException, Query

from app.schemas.jobs import Job, JobListResponse, JobState
from app.services.job_catalog import get_job, list_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def jobs(
    state: JobState | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> JobListResponse:
    return list_jobs(owner="demo-user", state=state, page=page, page_size=page_size)


@router.get("/{job_id}", response_model=Job)
def job_detail(job_id: str) -> Job:
    job = get_job(owner="demo-user", job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job was not found")
    return job
