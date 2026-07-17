from datetime import UTC, datetime
from pathlib import Path
import re
from threading import Condition
from time import monotonic
from typing import Callable

from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.jobs import (
    Job,
    JobListResponse,
    JobLogResponse,
    JobLogStream,
    JobResources,
    JobResourceSummary,
    JobState,
    JobSubmitRequest,
    JobUsageResponse,
    UserJobSummary,
)
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


class JobSubmissionUnavailable(RuntimeError):
    """Submission is unavailable for the configured data source."""


class JobNotFound(RuntimeError):
    """The requested job is not visible to the configured owner."""


class JobOperationConflict(RuntimeError):
    """The requested operation is invalid for the current job state or metadata."""


class JobLogsUnavailable(RuntimeError):
    """Job logs are unavailable for the configured data source."""


class JobLogOffsetOutOfRange(RuntimeError):
    """The requested log offset is beyond the current file size."""


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
        allow_fixture_submissions=settings.slurm_data_source == "fixture",
        fixture_job_output_directory=(
            settings.fixture_job_output_directory
            if settings.slurm_data_source == "fixture"
            else None
        ),
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
        allow_fixture_submissions: bool = False,
        fixture_job_output_directory: Path | None = None,
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
        self.allow_fixture_submissions = allow_fixture_submissions
        self.fixture_job_output_directory = fixture_job_output_directory
        self._clock = clock
        self._cache_condition = Condition()
        self._cached_jobs: tuple[Job, ...] | None = None
        self._cached_observed_at: datetime | None = None
        self._cache_expires_at = 0.0
        self._refreshing = False
        self._submitted_jobs: dict[str, Job] = {}
        self._fixture_state_overrides: dict[str, Job] = {}
        self._next_fixture_job_id = 910000

    def _jobs_with_submissions(self, jobs: tuple[Job, ...]) -> list[Job]:
        with self._cache_condition:
            submitted = tuple(self._submitted_jobs.values())
            overrides = dict(self._fixture_state_overrides)
        observed = tuple(overrides.get(job.id, job) for job in jobs)
        return sorted(
            [*submitted, *observed],
            key=lambda job: _job_sort_key(SlurmJob(job_id=job.slurm_job_id)),
            reverse=True,
        )

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
        jobs = self._jobs_with_submissions(cached_jobs)
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

    def summarize_jobs(self) -> UserJobSummary:
        cached_jobs, observed_at = self._observed_jobs()
        jobs = self._jobs_with_submissions(cached_jobs)
        state_counts = {state: 0 for state in JobState}
        for job in jobs:
            state_counts[job.state] += 1

        def total(field: str) -> int:
            return sum(
                value
                for job in jobs
                if (value := getattr(job.resources, field)) is not None
            )

        def coverage(field: str) -> int:
            return sum(getattr(job.resources, field) is not None for job in jobs)

        return UserJobSummary(
            total_jobs=len(jobs),
            active_jobs=state_counts[JobState.PENDING] + state_counts[JobState.RUNNING],
            successful_jobs=state_counts[JobState.COMPLETED],
            unsuccessful_jobs=(
                state_counts[JobState.FAILED]
                + state_counts[JobState.CANCELLED]
                + state_counts[JobState.TIMEOUT]
            ),
            state_counts=state_counts,
            resources=JobResourceSummary(
                cpus=total("cpus"),
                memory_mb=total("memory_mb"),
                gpus=total("gpus"),
                time_limit_minutes=total("time_limit_minutes"),
                cpus_jobs=coverage("cpus"),
                memory_jobs=coverage("memory_mb"),
                gpus_jobs=coverage("gpus"),
                time_limit_jobs=coverage("time_limit_minutes"),
            ),
            resource_basis="requested_or_allocated_snapshot",
            updated_at=observed_at,
        )

    def get_job(self, dashboard_job_id: str) -> Job | None:
        if not dashboard_job_id.startswith(_DASHBOARD_ID_PREFIX):
            return None
        jobs, _ = self._observed_jobs()
        return next(
            (job for job in self._jobs_with_submissions(jobs) if job.id == dashboard_job_id),
            None,
        )

    def submit_job(self, request: JobSubmitRequest) -> Job:
        if not self.allow_fixture_submissions:
            raise JobSubmissionUnavailable("Job submission is unavailable")

        now = datetime.now(UTC)
        with self._cache_condition:
            slurm_job_id = str(self._next_fixture_job_id)
            self._next_fixture_job_id += 1
            job = Job(
                id=f"{_DASHBOARD_ID_PREFIX}{slurm_job_id}",
                slurm_job_id=slurm_job_id,
                owner=self.owner,
                name=request.name,
                state=JobState.PENDING,
                partition=request.partition,
                account=request.account,
                qos=request.qos,
                command=request.command,
                resources=JobResources(**request.resources.model_dump()),
                reason="FixtureSubmission",
                submitted_at=now,
                updated_at=now,
            )
            self._submitted_jobs[job.id] = job
        return job

    def cancel_job(self, dashboard_job_id: str) -> Job:
        if not self.allow_fixture_submissions:
            raise JobSubmissionUnavailable("Job control is unavailable")
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")
        if job.state not in {JobState.PENDING, JobState.RUNNING}:
            raise JobOperationConflict("Only pending or running jobs can be cancelled")

        cancelled = job.model_copy(
            update={
                "state": JobState.CANCELLED,
                "reason": "FixtureCancellation",
                "finished_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        with self._cache_condition:
            if dashboard_job_id in self._submitted_jobs:
                self._submitted_jobs[dashboard_job_id] = cancelled
            else:
                self._fixture_state_overrides[dashboard_job_id] = cancelled
        return cancelled

    def clone_job(self, dashboard_job_id: str) -> Job:
        if not self.allow_fixture_submissions:
            raise JobSubmissionUnavailable("Job cloning is unavailable")
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")

        try:
            submission = JobSubmitRequest.model_validate(
                {
                    "name": job.name,
                    "command": job.command,
                    "partition": job.partition,
                    "account": job.account,
                    "qos": job.qos,
                    "resources": job.resources.model_dump(),
                }
            )
        except ValidationError as exc:
            raise JobOperationConflict("Job does not have complete submission metadata") from exc
        return self.submit_job(submission)

    def read_job_log(
        self,
        dashboard_job_id: str,
        stream: JobLogStream,
        offset: int,
        limit: int,
    ) -> JobLogResponse:
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")
        if self.fixture_job_output_directory is None:
            raise JobLogsUnavailable("Job logs are unavailable")
        if re.fullmatch(r"[0-9]+(?:[._+][A-Za-z0-9_-]+)*", job.slurm_job_id) is None:
            raise JobLogsUnavailable("Job log identifier is unsafe")

        output_directory = self.fixture_job_output_directory.resolve()
        log_path = (output_directory / f"{job.slurm_job_id}.{stream.value}.log").resolve()
        if log_path.parent != output_directory:
            raise JobLogsUnavailable("Job log path is unsafe")
        try:
            size = log_path.stat().st_size
        except FileNotFoundError:
            return JobLogResponse(
                job_id=job.id,
                stream=stream,
                content="",
                offset=offset,
                next_offset=offset,
                eof=True,
                available=False,
            )
        except OSError as exc:
            raise JobLogsUnavailable("Job log could not be inspected") from exc
        if offset > size:
            raise JobLogOffsetOutOfRange("Job log offset is beyond the current file size")

        try:
            with log_path.open("rb") as log_file:
                log_file.seek(offset)
                chunk = log_file.read(limit)
        except OSError as exc:
            raise JobLogsUnavailable("Job log could not be read") from exc
        next_offset = offset + len(chunk)
        return JobLogResponse(
            job_id=job.id,
            stream=stream,
            content=chunk.decode("utf-8", errors="replace"),
            offset=offset,
            next_offset=next_offset,
            eof=next_offset >= size,
            available=True,
        )

    def get_job_usage(self, dashboard_job_id: str) -> JobUsageResponse:
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")
        try:
            records = self.adapter.get_usage(job.slurm_job_id)
        except (SlurmCommandError, SlurmParseError, OSError, UnicodeError, ValueError) as exc:
            raise JobCatalogUnavailable("Job usage data is unavailable") from exc

        allocation = next((record for record in records if record.job_id == job.slurm_job_id), None)
        steps = [record for record in records if record.job_id.startswith(f"{job.slurm_job_id}.")]
        max_rss_values = [record.max_rss_kb for record in steps if record.max_rss_kb is not None]
        total_cpu_values = [
            record.total_cpu_seconds for record in records if record.total_cpu_seconds is not None
        ]
        with self._cache_condition:
            is_fixture_submission = job.id in self._submitted_jobs
        requested = allocation.requested if allocation is not None else None
        if requested is None and is_fixture_submission:
            requested = SlurmResources(
                cpus=job.resources.cpus,
                memory_mb=job.resources.memory_mb,
                gpus=job.resources.gpus,
            )
        allocated = allocation.allocated if allocation is not None else None
        return JobUsageResponse(
            job_id=job.id,
            requested=JobResources(
                cpus=requested.cpus if requested else None,
                memory_mb=requested.memory_mb if requested else None,
                gpus=requested.gpus if requested else None,
                time_limit_minutes=(
                    round(allocation.time_limit_seconds / 60)
                    if allocation is not None and allocation.time_limit_seconds is not None
                    else None
                ),
            ),
            allocated=JobResources(
                cpus=allocated.cpus if allocated else None,
                memory_mb=allocated.memory_mb if allocated else None,
                gpus=allocated.gpus if allocated else None,
                time_limit_minutes=None,
            ),
            elapsed_seconds=allocation.elapsed_seconds if allocation else None,
            time_limit_seconds=allocation.time_limit_seconds if allocation else None,
            max_rss_kb=max(max_rss_values) if max_rss_values else None,
            total_cpu_seconds=max(total_cpu_values) if total_cpu_values else None,
            gpu_utilization_percent=None,
            gpu_memory_mb=None,
        )
