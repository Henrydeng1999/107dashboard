from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class JobState(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


class JobLogStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


class JobResources(BaseModel):
    """Observed Slurm resources, not a job submission request."""

    cpus: int | None = Field(default=None, ge=0)
    memory_mb: int | None = Field(default=None, ge=0)
    gpus: int | None = Field(default=None, ge=0)
    time_limit_minutes: int | None = Field(default=None, ge=0)


class JobSubmitResources(BaseModel):
    """Validated resource request for the verified student QoS."""

    cpus: int = Field(ge=1, le=4)
    memory_mb: int = Field(ge=512, le=16384)
    gpus: int = Field(ge=0, le=1)
    time_limit_minutes: int = Field(ge=1, le=240)


class JobSubmitRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    command: str = Field(min_length=1, max_length=500, pattern=r"^[^\r\n\x00]+$")
    partition: Literal["Students"]
    account: Literal["stu"]
    qos: Literal["qos_stu_default"]
    resources: JobSubmitResources


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


class JobLogResponse(BaseModel):
    job_id: str
    stream: JobLogStream
    content: str
    offset: int = Field(ge=0)
    next_offset: int = Field(ge=0)
    eof: bool
    available: bool


class JobUsageResponse(BaseModel):
    job_id: str
    requested: JobResources
    allocated: JobResources
    elapsed_seconds: float | None = Field(default=None, ge=0)
    time_limit_seconds: float | None = Field(default=None, ge=0)
    max_rss_kb: int | None = Field(default=None, ge=0)
    total_cpu_seconds: float | None = Field(default=None, ge=0)
    gpu_utilization_percent: float | None = Field(default=None, ge=0, le=100)
    gpu_memory_mb: int | None = Field(default=None, ge=0)


class JobResourceSummary(BaseModel):
    cpus: int = Field(ge=0)
    memory_mb: int = Field(ge=0)
    gpus: int = Field(ge=0)
    time_limit_minutes: int = Field(ge=0)
    cpus_jobs: int = Field(ge=0)
    memory_jobs: int = Field(ge=0)
    gpus_jobs: int = Field(ge=0)
    time_limit_jobs: int = Field(ge=0)


class UserJobSummary(BaseModel):
    total_jobs: int = Field(ge=0)
    active_jobs: int = Field(ge=0)
    successful_jobs: int = Field(ge=0)
    unsuccessful_jobs: int = Field(ge=0)
    state_counts: dict[JobState, int]
    resources: JobResourceSummary
    resource_basis: Literal["requested_or_allocated_snapshot"]
    updated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
