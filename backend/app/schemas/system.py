from typing import Literal

from pydantic import BaseModel


class RuntimeCapabilities(BaseModel):
    list_jobs: bool = True
    job_details: bool = True
    usage: bool = True
    submit: bool
    cancel: bool
    clone: bool
    logs: bool


class RuntimeInfo(BaseModel):
    data_source: Literal["fixture", "native"]
    serving_source: Literal["fixture", "native", "fixture_fallback"]
    read_only: bool
    degraded: bool = False
    demo_fallback_enabled: bool = False
    fallback_reason: Literal["slurm_unavailable"] | None = None
    capabilities: RuntimeCapabilities
