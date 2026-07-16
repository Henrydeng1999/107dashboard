from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class JobResources(BaseModel):
    """Observed Slurm resources, not a job submission request."""

    cpus: int | None = Field(default=None, ge=0)
    memory_mb: int | None = Field(default=None, ge=0)
    gpus: int | None = Field(default=None, ge=0)
    time_limit_minutes: int | None = Field(default=None, ge=0)


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slurm_job_id: str
    owner: str
    name: str | None = None
    state: JobState
    partition: str | None = None
    account: str | None = None
    qos: str | None = None
    command: str | None = None
    resources: JobResources
    node: str | None = None
    exit_code: str | None = None
    reason: str | None = None
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[Job]
    page: int
    page_size: int
    total: int
    updated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
