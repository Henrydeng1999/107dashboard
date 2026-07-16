from datetime import UTC, datetime
import re
from threading import Condition
from time import monotonic
from typing import Callable

from app.core.config import Settings
from app.schemas.jobs import Job, JobListResponse, JobResources, JobState
from app.slurm import (
    FixtureSlurmAdapter,
    SlurmAdapter,
    SlurmCommandError,
    SlurmJob,
    SlurmParseError,
    SlurmResources,
)

_DASHBOARD_ID_PREFIX = "slurm-"
_TIME_LIMIT_PATTERN = re.compile(
    r"(?:(?P<days>\d+)-)?(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)"
)


class JobCatalogUnavailable(RuntimeError):
    """The configured Slurm data source could not provide a safe response."""


class NativeSlurmApiDisabled(RuntimeError):
    """Native Slurm API access is unavailable without trusted request identity."""


def build_slurm_adapter(settings: Settings) -> SlurmAdapter:
    if settings.slurm_data_source == "fixture":
        return FixtureSlurmAdapter(settings.slurm_fixture_directory)
    if settings.slurm_data_source == "native":
        raise NativeSlurmApiDisabled(
            "Native Slurm API access is disabled until trusted authentication is configured"
        )
    raise ValueError(f"Unsupported Slurm data source: {settings.slurm_data_source!r}")


def build_job_catalog(settings: Settings) -> "JobCatalog":
    return JobCatalog(
        adapter=build_slurm_adapter(settings),
        owner=settings.dashboard_owner,
        cache_ttl_seconds=settings.slurm_query_cache_ttl_seconds,
        max_jobs=settings.slurm_max_jobs,
    )


def _time_limit_minutes(value: str | None) -> int | None:
    if value is None:
        return None
    match = _TIME_LIMIT_PATTERN.fullmatch(value)
    if match is None:
        return None
    return (
        int(match.group("days") or 0) * 24 * 60
        + int(match.group("hours")) * 60
        + int(match.group("minutes"))
        + (1 if int(match.group("seconds")) > 0 else 0)
    )


def _resource_value(job: SlurmJob, field: str) -> int | None:
    requested = getattr(job.requested, field) if job.requested is not None else None
    allocated = getattr(job.allocated, field) if job.allocated is not None else None
    return requested if requested is not None else allocated


def _merge_resources(
    primary: SlurmResources | None, fallback: SlurmResources | None
) -> SlurmResources | None:
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    return SlurmResources(
        cpus=primary.cpus if primary.cpus is not None else fallback.cpus,
        memory_mb=(primary.memory_mb if primary.memory_mb is not None else fallback.memory_mb),
        gpus=primary.gpus if primary.gpus is not None else fallback.gpus,
    )


def _prefer(primary: str | None, fallback: str | None) -> str | None:
    return primary if primary is not None else fallback


def _merge_slurm_job(queue_job: SlurmJob, accounting_job: SlurmJob) -> SlurmJob:
    """Keep live queue values and fill only missing fields from accounting."""
    return SlurmJob(
        job_id=queue_job.job_id,
        name=_prefer(queue_job.name, accounting_job.name),
        state=_prefer(queue_job.state, accounting_job.state),
        user=_prefer(queue_job.user, accounting_job.user),
        partition=_prefer(queue_job.partition, accounting_job.partition),
        account=_prefer(queue_job.account, accounting_job.account),
        qos=_prefer(queue_job.qos, accounting_job.qos),
        nodes=_prefer(queue_job.nodes, accounting_job.nodes),
        reason=_prefer(queue_job.reason, accounting_job.reason),
        exit_code=_prefer(queue_job.exit_code, accounting_job.exit_code),
        requested=_merge_resources(queue_job.requested, accounting_job.requested),
        allocated=_merge_resources(queue_job.allocated, accounting_job.allocated),
        time_limit=_prefer(queue_job.time_limit, accounting_job.time_limit),
        elapsed=_prefer(queue_job.elapsed, accounting_job.elapsed),
    )


def _job_sort_key(job: SlurmJob) -> tuple[int, int, str]:
    numeric_prefix = re.match(r"\d+", job.job_id)
    if numeric_prefix is None:
        return (0, 0, job.job_id)
    return (1, int(numeric_prefix.group()), job.job_id)


def _to_job(job: SlurmJob, owner: str, observed_at: datetime) -> Job:
    try:
        state = JobState(job.state or JobState.UNKNOWN)
    except ValueError:
        state = JobState.UNKNOWN
    return Job(
        id=f"{_DASHBOARD_ID_PREFIX}{job.job_id}",
        slurm_job_id=job.job_id,
        owner=owner,
        name=job.name,
        state=state,
        partition=job.partition,
        account=job.account,
        qos=job.qos,
        command=None,
        resources=JobResources(
            cpus=_resource_value(job, "cpus"),
            memory_mb=_resource_value(job, "memory_mb"),
            gpus=_resource_value(job, "gpus"),
            time_limit_minutes=_time_limit_minutes(job.time_limit),
        ),
        node=job.nodes,
        exit_code=job.exit_code,
        reason=job.reason,
        submitted_at=None,
        started_at=None,
        finished_at=None,
        updated_at=observed_at,
    )


class JobCatalog:
    def __init__(
        self,
        adapter: SlurmAdapter,
        owner: str,
        cache_ttl_seconds: float = 2.0,
        max_jobs: int = 1000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 0.1 <= cache_ttl_seconds <= 60:
            raise ValueError("cache_ttl_seconds must be between 0.1 and 60")
        if not 1 <= max_jobs <= 10000:
            raise ValueError("max_jobs must be between 1 and 10000")
        self.adapter = adapter
        self.owner = owner
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_jobs = max_jobs
        self._clock = clock
        self._cache_condition = Condition()
        self._cached_jobs: tuple[Job, ...] | None = None
        self._cached_observed_at: datetime | None = None
        self._cache_expires_at = 0.0
        self._refreshing = False

    def _query_jobs(self, observed_at: datetime) -> tuple[Job, ...]:
        try:
            queue_jobs = self.adapter.list_queue(self.owner)
            accounting_jobs = self.adapter.list_accounting(self.owner)
        except (SlurmCommandError, SlurmParseError, OSError, UnicodeError) as exc:
            raise JobCatalogUnavailable("Job data source is unavailable") from exc

        merged: dict[str, SlurmJob] = {}
        for job in queue_jobs:
            if job.user == self.owner:
                merged[job.job_id] = job
        for job in accounting_jobs:
            if job.user != self.owner:
                continue
            queue_job = merged.get(job.job_id)
            merged[job.job_id] = _merge_slurm_job(queue_job, job) if queue_job is not None else job
        ordered = sorted(merged.values(), key=_job_sort_key, reverse=True)[: self.max_jobs]
        return tuple(_to_job(job, self.owner, observed_at) for job in ordered)

    def _observed_jobs(self) -> tuple[tuple[Job, ...], datetime]:
        with self._cache_condition:
            while True:
                now = self._clock()
                if (
                    self._cached_jobs is not None
                    and self._cached_observed_at is not None
                    and now < self._cache_expires_at
                ):
                    return self._cached_jobs, self._cached_observed_at
                if not self._refreshing:
                    self._refreshing = True
                    break
                self._cache_condition.wait()

        observed_at = datetime.now(UTC)
        try:
            jobs = self._query_jobs(observed_at)
        except Exception:
            with self._cache_condition:
                self._refreshing = False
                self._cache_condition.notify_all()
            raise

        with self._cache_condition:
            self._cached_jobs = jobs
            self._cached_observed_at = observed_at
            self._cache_expires_at = self._clock() + self.cache_ttl_seconds
            self._refreshing = False
            self._cache_condition.notify_all()
            return jobs, observed_at

    def list_jobs(self, state: JobState | None, page: int, page_size: int) -> JobListResponse:
        cached_jobs, observed_at = self._observed_jobs()
        jobs = list(cached_jobs)
        if state is not None:
            jobs = [job for job in jobs if job.state == state]
        start = (page - 1) * page_size
        return JobListResponse(
            items=jobs[start : start + page_size],
            page=page,
            page_size=page_size,
            total=len(jobs),
            updated_at=observed_at,
        )

    def get_job(self, dashboard_job_id: str) -> Job | None:
        if not dashboard_job_id.startswith(_DASHBOARD_ID_PREFIX):
            return None
        jobs, _ = self._observed_jobs()
        return next(
            (job for job in jobs if job.id == dashboard_job_id),
            None,
        )
