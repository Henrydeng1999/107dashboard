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
    cpus: int = Field(ge=1, le=4)
    memory_mb: int = Field(ge=512, le=16384)
    gpus: int = Field(ge=0, le=1)
    time_limit_minutes: int = Field(ge=1, le=240)


class Job(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slurm_job_id: str
    owner: str
    name: str
    state: JobState
    partition: str
    account: str
    qos: str
    command: str
    resources: JobResources
    node: str | None = None
    exit_code: str | None = None
    reason: str | None = None
    submitted_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime


class JobListResponse(BaseModel):
    items: list[Job]
    page: int
    page_size: int
    total: int
    updated_at: datetime
