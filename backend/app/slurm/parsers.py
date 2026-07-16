import re
from collections.abc import Iterator

from app.slurm.models import SlurmJob, SlurmPartition, SlurmResources

_SQUEUE_FIELDS = 13
_SACCT_FIELDS = 14
_SINFO_FIELDS = 7
_NULL_VALUES = {"", "(null)", "n/a", "none", "unknown"}

_STATE_MAP = {
    "BOOT_FAIL": "FAILED",
    "CANCELLED": "CANCELLED",
    "COMPLETED": "COMPLETED",
    "COMPLETING": "RUNNING",
    "CONFIGURING": "PENDING",
    "DEADLINE": "TIMEOUT",
    "FAILED": "FAILED",
    "NODE_FAIL": "FAILED",
    "OUT_OF_MEMORY": "FAILED",
    "PENDING": "PENDING",
    "PREEMPTED": "FAILED",
    "REQUEUED": "PENDING",
    "REQUEUE_FED": "PENDING",
    "REQUEUE_HOLD": "PENDING",
    "RESIZING": "PENDING",
    "REVOKED": "CANCELLED",
    "RUNNING": "RUNNING",
    "SIGNALING": "RUNNING",
    "SPECIAL_EXIT": "FAILED",
    "STAGE_OUT": "RUNNING",
    "SUSPENDED": "RUNNING",
    "TIMEOUT": "TIMEOUT",
}


class SlurmParseError(ValueError):
    def __init__(self, source: str, line_number: int, detail: str) -> None:
        super().__init__(f"Malformed {source} output on line {line_number}: {detail}")
        self.source = source
        self.line_number = line_number


def _records(output: str, field_count: int, source: str) -> Iterator[tuple[int, list[str]]]:
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) > field_count:
            raise SlurmParseError(
                source,
                line_number,
                f"expected at most {field_count} fields, got {len(fields)}",
            )
        fields.extend([""] * (field_count - len(fields)))
        yield line_number, fields


def _optional(value: str) -> str | None:
    return None if value.strip().lower() in _NULL_VALUES else value.strip()


def _integer(value: str, source: str, line_number: int, field: str) -> int | None:
    normalized = _optional(value)
    if normalized is None:
        return None
    if re.fullmatch(r"\d+", normalized) is None:
        raise SlurmParseError(source, line_number, f"invalid {field} integer {value!r}")
    return int(normalized)


def _memory_mb(value: str, source: str, line_number: int, field: str) -> int | None:
    normalized = _optional(value)
    if normalized is None:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmgt]?)(?:[cn])?", normalized, re.I)
    if match is None:
        raise SlurmParseError(source, line_number, f"invalid {field} memory {value!r}")
    amount = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"": 1, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024**2}
    return round(amount * multiplier[unit])


def _gpu_count(value: str, source: str, line_number: int, field: str) -> int | None:
    normalized = _optional(value)
    if normalized is None:
        return None

    generic_counts: list[int] = []
    typed_counts: list[int] = []
    for token in normalized.split(","):
        token = token.strip()
        if not token.lower().startswith(("gpu", "gres/gpu")):
            continue
        match = re.fullmatch(
            r"(?:gres/)?gpu(?::(?P<model>[^,:=]+))?(?::|=)(?P<count>\d+)",
            token,
            re.I,
        )
        if match is None:
            raise SlurmParseError(source, line_number, f"invalid {field} GPU count {token!r}")
        counts = generic_counts if match.group("model") is None else typed_counts
        counts.append(int(match.group("count")))

    if generic_counts:
        return max(generic_counts)
    return sum(typed_counts) if typed_counts else None


def _tres_value(value: str, key: str) -> str | None:
    normalized = _optional(value)
    if normalized is None:
        return None
    prefix = f"{key}=".lower()
    for token in normalized.split(","):
        token = token.strip()
        if token.lower().startswith(prefix):
            return token[len(prefix) :]
    return None


def _tres_resources(value: str, source: str, line_number: int, field: str) -> SlurmResources:
    return SlurmResources(
        cpus=_integer(_tres_value(value, "cpu") or "", source, line_number, f"{field}.cpu"),
        memory_mb=_memory_mb(_tres_value(value, "mem") or "", source, line_number, f"{field}.mem"),
        gpus=_gpu_count(value, source, line_number, f"{field}.gpu"),
    )


def _state(value: str) -> str | None:
    normalized = value.strip()
    if not normalized or normalized.lower() in {"(null)", "n/a", "none"}:
        return None
    base_state = normalized.upper().split(maxsplit=1)[0].rstrip("+")
    return _STATE_MAP.get(base_state, "UNKNOWN")


def parse_squeue(output: str) -> list[SlurmJob]:
    jobs: list[SlurmJob] = []
    for line_number, fields in _records(output, _SQUEUE_FIELDS, "squeue"):
        job_id = _optional(fields[0])
        if job_id is None:
            continue
        state = _state(fields[2])
        cpus = _integer(fields[9], "squeue", line_number, "CPUs")
        jobs.append(
            SlurmJob(
                job_id=job_id,
                name=_optional(fields[1]),
                state=state,
                user=_optional(fields[3]),
                partition=_optional(fields[4]),
                account=_optional(fields[5]),
                qos=_optional(fields[6]),
                nodes=_optional(fields[7]),
                reason=_optional(fields[8]),
                requested=SlurmResources(
                    cpus=cpus if state == "PENDING" else None,
                    memory_mb=_memory_mb(fields[10], "squeue", line_number, "requested memory"),
                    gpus=_gpu_count(fields[11], "squeue", line_number, "requested GRES"),
                ),
                allocated=SlurmResources(cpus=cpus if state == "RUNNING" else None),
                time_limit=_optional(fields[12]),
            )
        )
    return jobs


def parse_sacct(output: str) -> list[SlurmJob]:
    jobs: list[SlurmJob] = []
    for line_number, fields in _records(output, _SACCT_FIELDS, "sacct"):
        job_id = _optional(fields[0])
        if job_id is None:
            continue
        jobs.append(
            SlurmJob(
                job_id=job_id,
                name=_optional(fields[1]),
                state=_state(fields[2]),
                user=_optional(fields[3]),
                partition=_optional(fields[4]),
                account=_optional(fields[5]),
                qos=_optional(fields[6]),
                nodes=_optional(fields[7]),
                exit_code=_optional(fields[8]),
                requested=_tres_resources(fields[9], "sacct", line_number, "ReqTRES"),
                allocated=_tres_resources(fields[10], "sacct", line_number, "AllocTRES"),
                time_limit=_optional(fields[11]),
                elapsed=_optional(fields[12]),
                reason=_optional(fields[13]),
            )
        )
    return jobs


def parse_sinfo(output: str) -> list[SlurmPartition]:
    partitions: list[SlurmPartition] = []
    for line_number, fields in _records(output, _SINFO_FIELDS, "sinfo"):
        name = _optional(fields[0])
        if name is None:
            continue
        partitions.append(
            SlurmPartition(
                name=name.rstrip("*"),
                availability=_optional(fields[1]),
                state=_optional(fields[2]),
                node_count=_integer(fields[3], "sinfo", line_number, "node count"),
                cpu_summary=_optional(fields[4]),
                memory_mb=_integer(fields[5], "sinfo", line_number, "memory MB"),
                gres=_optional(fields[6]),
            )
        )
    return partitions
