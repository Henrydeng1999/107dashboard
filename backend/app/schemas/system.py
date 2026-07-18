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
    read_only: bool
    capabilities: RuntimeCapabilities
