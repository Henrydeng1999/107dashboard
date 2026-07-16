from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SlurmResources:
    cpus: int | None = None
    memory_mb: int | None = None
    gpus: int | None = None


@dataclass(frozen=True, slots=True)
class SlurmJob:
    job_id: str
    name: str | None = None
    state: str | None = None
    user: str | None = None
    partition: str | None = None
    account: str | None = None
    qos: str | None = None
    nodes: str | None = None
    reason: str | None = None
    exit_code: str | None = None
    requested: SlurmResources | None = None
    allocated: SlurmResources | None = None
    time_limit: str | None = None
    elapsed: str | None = None


@dataclass(frozen=True, slots=True)
class SlurmPartition:
    name: str
    availability: str | None = None
    state: str | None = None
    node_count: int | None = None
    cpu_summary: str | None = None
    memory_mb: int | None = None
    gres: str | None = None
