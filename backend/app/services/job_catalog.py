from datetime import UTC, datetime
import os
from pathlib import Path
import re
import stat
from threading import Condition
from time import monotonic
from typing import Callable, Literal

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username
from app.repositories.job_control import JobControlRepository
from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.repositories.submission import SubmissionRepository
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
    NativeSlurmAdapter,
    SlurmAdapter,
    SlurmCommandError,
    SlurmJob,
    SlurmParseError,
    SlurmResources,
)
from app.slurm.runner import SubprocessCommandRunner
from app.slurm.control import NativeSlurmCanceller
from app.slurm.submission import (
    NativeSlurmSubmitter,
    SubmissionValidationError,
)
from app.services.native_submission import (
    ExplicitSubmissionAuthorization,
    NativeActiveJobLimitError,
    NativeIdempotencyConflictError,
    NativeIdempotencyRequiredError,
    NativeSubmissionService,
)
from app.services.native_logs import NativeLogPathError, resolve_native_log_path
from app.services.native_control import (
    NativeControlIdempotencyConflict,
    NativeControlIdempotencyRequired,
    NativeControlStateConflict,
    NativeJobControlService,
)

_DASHBOARD_ID_PREFIX = "slurm-"
_TIME_LIMIT_PATTERN = re.compile(
    r"(?:(?P<days>\d+)-)?(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)"
)


class JobCatalogUnavailable(RuntimeError):
    """The configured Slurm data source could not provide a safe response."""


class JobSubmissionUnavailable(RuntimeError):
    """Submission is unavailable for the configured data source."""


class JobIdempotencyRequired(RuntimeError):
    """Native submission requires one valid idempotency key."""


class JobSubmissionInvalid(RuntimeError):
    """Native submission parameters fail the controlled command policy."""


class JobIdempotencyConflict(RuntimeError):
    """The idempotency key cannot safely replay this request."""


class JobActiveLimitReached(RuntimeError):
    """The trusted owner has reached the Native active job limit."""


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
        return NativeSlurmAdapter(
            SubprocessCommandRunner(settings.slurm_command_timeout_seconds)
        )
    raise ValueError(f"Unsupported Slurm data source: {settings.slurm_data_source!r}")


def build_job_catalog(settings: Settings) -> "JobCatalog":
    owner = settings.dashboard_owner
    if settings.slurm_data_source == "native":
        owner = assert_deployment_owner(owner, resolve_effective_unix_username())

    adapter = build_slurm_adapter(settings)
    metadata_repository = JobMetadataRepository(settings.database_url)
    metadata_repository.initialize()
    native_submission_service = None
    native_control_service = None
    native_write_support = settings.slurm_data_source == "native" and (
        settings.native_submission_enabled
        or settings.native_clone_enabled
        or settings.native_cancel_enabled
    )
    if native_write_support:
        submission_repository = SubmissionRepository(settings.database_url)
        submission_repository.initialize()
    if settings.slurm_data_source == "native" and (
        settings.native_submission_enabled or settings.native_clone_enabled
    ):
        native_submission_service = NativeSubmissionService(
            owner=owner,
            workspace_root=settings.job_workspace_directory,
            submitter=NativeSlurmSubmitter(
                SubprocessCommandRunner(settings.slurm_command_timeout_seconds)
            ),
            repository=submission_repository,
        )
    if settings.slurm_data_source == "native" and settings.native_cancel_enabled:
        operation_repository = JobControlRepository(settings.database_url)
        operation_repository.initialize()
        native_control_service = NativeJobControlService(
            owner=owner,
            metadata_repository=metadata_repository,
            operation_repository=operation_repository,
            audit_repository=submission_repository,
            canceller=NativeSlurmCanceller(
                SubprocessCommandRunner(settings.slurm_command_timeout_seconds)
            ),
        )
    return JobCatalog(
        adapter=adapter,
        owner=owner,
        cache_ttl_seconds=settings.slurm_query_cache_ttl_seconds,
        max_jobs=settings.slurm_max_jobs,
        allow_fixture_submissions=settings.slurm_data_source == "fixture",
        fixture_job_output_directory=(
            settings.fixture_job_output_directory
            if settings.slurm_data_source == "fixture"
            else None
        ),
        metadata_repository=metadata_repository,
        metadata_source=settings.slurm_data_source,
        native_submission_service=native_submission_service,
        allow_native_submission=settings.native_submission_enabled,
        allow_native_clone=settings.native_clone_enabled,
        native_control_service=native_control_service,
        native_max_active_jobs=settings.native_max_active_jobs,
        native_log_workspace=(
            settings.job_workspace_directory
            if settings.slurm_data_source == "native" and settings.native_logs_enabled
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


def _merge_job_metadata(observed: Job, metadata: Job) -> Job:
    """Keep Slurm state authoritative while filling trusted submission metadata."""
    if observed.id != metadata.id or observed.owner != metadata.owner:
        raise ValueError("job snapshots must have matching identity and owner")
    return observed.model_copy(
        update={
            "name": observed.name or metadata.name,
            "partition": observed.partition or metadata.partition,
            "account": observed.account or metadata.account,
            "qos": observed.qos or metadata.qos,
            "command": metadata.command,
            "resources": JobResources(
                cpus=(
                    observed.resources.cpus
                    if observed.resources.cpus is not None
                    else metadata.resources.cpus
                ),
                memory_mb=(
                    observed.resources.memory_mb
                    if observed.resources.memory_mb is not None
                    else metadata.resources.memory_mb
                ),
                gpus=(
                    observed.resources.gpus
                    if observed.resources.gpus is not None
                    else metadata.resources.gpus
                ),
                time_limit_minutes=(
                    observed.resources.time_limit_minutes
                    if observed.resources.time_limit_minutes is not None
                    else metadata.resources.time_limit_minutes
                ),
            ),
            "reason": observed.reason or metadata.reason,
            "submitted_at": observed.submitted_at or metadata.submitted_at,
            "started_at": observed.started_at or metadata.started_at,
            "finished_at": observed.finished_at or metadata.finished_at,
        }
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
        metadata_repository: JobMetadataRepository | None = None,
        metadata_source: Literal["fixture", "native"] = "fixture",
        native_submission_service: NativeSubmissionService | None = None,
        allow_native_submission: bool = False,
        allow_native_clone: bool = False,
        native_control_service: NativeJobControlService | None = None,
        native_max_active_jobs: int = 1,
        native_log_workspace: Path | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 0.1 <= cache_ttl_seconds <= 60:
            raise ValueError("cache_ttl_seconds must be between 0.1 and 60")
        if not 1 <= max_jobs <= 10000:
            raise ValueError("max_jobs must be between 1 and 10000")
        if not 1 <= native_max_active_jobs <= 100:
            raise ValueError("native_max_active_jobs must be between 1 and 100")
        self.adapter = adapter
        self.owner = owner
        self.cache_ttl_seconds = cache_ttl_seconds
        self.max_jobs = max_jobs
        self.allow_fixture_submissions = allow_fixture_submissions
        self.fixture_job_output_directory = fixture_job_output_directory
        self.metadata_repository = metadata_repository
        self.metadata_source = metadata_source
        self.native_submission_service = native_submission_service
        self.allow_native_submission = allow_native_submission
        self.allow_native_clone = allow_native_clone
        self.native_control_service = native_control_service
        self.native_max_active_jobs = native_max_active_jobs
        self.native_log_workspace = native_log_workspace
        self._clock = clock
        self._cache_condition = Condition()
        self._cached_jobs: tuple[Job, ...] | None = None
        self._cached_observed_at: datetime | None = None
        self._cache_expires_at = 0.0
        self._refreshing = False
        self._submitted_jobs: dict[str, Job] = {}
        self._fixture_state_overrides: dict[str, Job] = {}
        self._next_fixture_job_id = 910000
        self._restore_metadata()

    def _restore_metadata(self) -> None:
        if self.metadata_repository is None:
            return
        try:
            records = self.metadata_repository.list_by_owner(
                self.owner, source=self.metadata_source
            )
        except SQLAlchemyError as exc:
            raise JobCatalogUnavailable("Job metadata is unavailable") from exc
        for record in records:
            job = self._job_from_metadata(record)
            self._submitted_jobs[job.id] = job
            if record.slurm_job_id.isdigit():
                self._next_fixture_job_id = max(
                    self._next_fixture_job_id, int(record.slurm_job_id) + 1
                )

    @staticmethod
    def _job_from_metadata(record: JobMetadataRecord) -> Job:
        try:
            state = JobState(record.state)
        except ValueError:
            state = JobState.UNKNOWN
        updated_at = record.updated_at or record.created_at or datetime.now(UTC)
        return Job(
            id=(
                f"{_DASHBOARD_ID_PREFIX}{record.slurm_job_id}"
                if record.source == "native"
                else record.id
            ),
            slurm_job_id=record.slurm_job_id,
            owner=record.owner,
            name=record.name,
            state=state,
            partition=record.partition,
            account=record.account,
            qos=record.qos,
            command=record.command,
            resources=JobResources(
                cpus=record.cpus,
                memory_mb=record.memory_mb,
                gpus=record.gpus,
                time_limit_minutes=record.time_limit_minutes,
            ),
            reason="PersistedMetadata",
            submitted_at=record.submitted_at,
            finished_at=record.finished_at,
            updated_at=updated_at,
        )

    def _persist_job(self, job: Job) -> None:
        if self.metadata_repository is None:
            return
        resources = job.resources
        if (
            job.name is None
            or job.command is None
            or job.partition is None
            or job.account is None
            or job.qos is None
            or resources.cpus is None
            or resources.memory_mb is None
            or resources.gpus is None
            or resources.time_limit_minutes is None
        ):
            raise JobSubmissionUnavailable("Job metadata is incomplete")
        output_directory = self.fixture_job_output_directory
        stdout_path = (
            str((output_directory / f"{job.slurm_job_id}.stdout.log").resolve())
            if output_directory is not None
            else None
        )
        stderr_path = (
            str((output_directory / f"{job.slurm_job_id}.stderr.log").resolve())
            if output_directory is not None
            else None
        )
        try:
            self.metadata_repository.upsert(
                JobMetadataRecord(
                    id=job.id,
                    slurm_job_id=job.slurm_job_id,
                    owner=job.owner,
                    source=self.metadata_source,
                    name=job.name,
                    command=job.command,
                    partition=job.partition,
                    account=job.account,
                    qos=job.qos,
                    cpus=resources.cpus,
                    memory_mb=resources.memory_mb,
                    gpus=resources.gpus,
                    time_limit_minutes=resources.time_limit_minutes,
                    stdout_path=stdout_path,
                    stderr_path=stderr_path,
                    state=job.state.value,
                    submitted_at=job.submitted_at,
                    finished_at=job.finished_at,
                )
            )
        except (SQLAlchemyError, ValueError) as exc:
            raise JobSubmissionUnavailable("Job metadata could not be saved") from exc

    def _jobs_with_submissions(self, jobs: tuple[Job, ...]) -> list[Job]:
        with self._cache_condition:
            submitted = tuple(self._submitted_jobs.values())
            overrides = dict(self._fixture_state_overrides)
        visible_jobs = {
            job.id: overrides.get(job.id, job)
            for job in jobs
            if job.owner == self.owner
        }
        for metadata_job in submitted:
            if metadata_job.owner != self.owner:
                continue
            observed_job = visible_jobs.get(metadata_job.id)
            visible_jobs[metadata_job.id] = (
                _merge_job_metadata(observed_job, metadata_job)
                if observed_job is not None
                else metadata_job
            )
        return sorted(
            visible_jobs.values(),
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
        job = next(
            (job for job in self._jobs_with_submissions(jobs) if job.id == dashboard_job_id),
            None,
        )
        return job if job is not None and job.owner == self.owner else None

    def submit_job(
        self, request: JobSubmitRequest, *, idempotency_key: str | None = None
    ) -> Job:
        if self.native_submission_service is not None and self.allow_native_submission:
            return self._submit_native_job(request, idempotency_key)
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
        self._persist_job(job)
        with self._cache_condition:
            self._submitted_jobs[job.id] = job
        return job

    def _submit_native_job(
        self,
        request: JobSubmitRequest,
        idempotency_key: str | None,
        *,
        idempotency_namespace: str = "",
    ) -> Job:
        service = self.native_submission_service
        if service is None:
            raise JobSubmissionUnavailable("Native submission is unavailable")
        try:
            metadata = service.submit_idempotent(
                request,
                authorization=ExplicitSubmissionAuthorization(confirmed=True),
                idempotency_key=idempotency_key,
                active_job_count=self._native_active_job_count,
                max_active_jobs=self.native_max_active_jobs,
                idempotency_namespace=idempotency_namespace,
            )
        except NativeIdempotencyRequiredError as exc:
            raise JobIdempotencyRequired("A valid Idempotency-Key is required") from exc
        except NativeIdempotencyConflictError as exc:
            raise JobIdempotencyConflict("Idempotency-Key conflicts with prior request") from exc
        except NativeActiveJobLimitError as exc:
            raise JobActiveLimitReached("Native active job limit reached") from exc
        except SubmissionValidationError as exc:
            raise JobSubmissionInvalid("Native command policy rejected submission") from exc
        except JobCatalogUnavailable as exc:
            raise JobSubmissionUnavailable("Native active jobs are unavailable") from exc
        except (
            SlurmCommandError,
            SlurmParseError,
            SQLAlchemyError,
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise JobSubmissionUnavailable("Native submission failed safely") from exc

        job = self._job_from_metadata(metadata)
        with self._cache_condition:
            self._submitted_jobs[job.id] = job
            self._cached_jobs = None
            self._cache_expires_at = 0.0
        return job

    def _native_active_job_count(self) -> int:
        observed_jobs, _ = self._observed_jobs()
        visible_jobs = self._jobs_with_submissions(observed_jobs)
        return sum(
            1
            for job in visible_jobs
            if job.owner == self.owner and job.state in {JobState.PENDING, JobState.RUNNING}
        )

    def cancel_job(
        self,
        dashboard_job_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> Job:
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")

        if self.native_control_service is not None:
            if self.metadata_repository is None:
                raise JobSubmissionUnavailable("Native job metadata is unavailable")
            metadata = self.metadata_repository.get_by_slurm_job_id(
                job.slurm_job_id,
                owner=self.owner,
            )
            if metadata is None or metadata.source != "native":
                raise JobNotFound("Job was not found")
            try:
                cancelled_metadata = self.native_control_service.cancel(
                    metadata,
                    observed_state=job.state.value,
                    idempotency_key=idempotency_key,
                )
            except NativeControlIdempotencyRequired as exc:
                raise JobIdempotencyRequired("A valid Idempotency-Key is required") from exc
            except NativeControlIdempotencyConflict as exc:
                raise JobIdempotencyConflict("Idempotency-Key conflicts with prior request") from exc
            except NativeControlStateConflict as exc:
                raise JobOperationConflict("Job cannot be cancelled in its current state") from exc
            except (
                SlurmCommandError,
                SQLAlchemyError,
                OSError,
                PermissionError,
                ValueError,
            ) as exc:
                raise JobSubmissionUnavailable("Native cancellation failed safely") from exc
            cancelled = self._job_from_metadata(cancelled_metadata)
            with self._cache_condition:
                self._submitted_jobs[cancelled.id] = cancelled
                self._cached_jobs = None
                self._cache_expires_at = 0.0
            return cancelled

        if not self.allow_fixture_submissions:
            raise JobSubmissionUnavailable("Job control is unavailable")
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
            is_dashboard_submission = dashboard_job_id in self._submitted_jobs
        if is_dashboard_submission:
            self._persist_job(cancelled)
        with self._cache_condition:
            if is_dashboard_submission:
                self._submitted_jobs[dashboard_job_id] = cancelled
            else:
                self._fixture_state_overrides[dashboard_job_id] = cancelled
        return cancelled

    def clone_job(
        self,
        dashboard_job_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> Job:
        job = self.get_job(dashboard_job_id)
        if job is None:
            raise JobNotFound("Job was not found")

        if self.allow_native_clone and self.native_submission_service is not None:
            if self.metadata_repository is None:
                raise JobSubmissionUnavailable("Native job metadata is unavailable")
            metadata = self.metadata_repository.get_by_slurm_job_id(
                job.slurm_job_id,
                owner=self.owner,
            )
            if metadata is None or metadata.source != "native":
                raise JobOperationConflict("Trusted Native submission metadata is unavailable")
            try:
                submission = JobSubmitRequest.model_validate(
                    {
                        "name": metadata.name,
                        "command": metadata.command,
                        "partition": metadata.partition,
                        "account": metadata.account,
                        "qos": metadata.qos,
                        "resources": {
                            "cpus": metadata.cpus,
                            "memory_mb": metadata.memory_mb,
                            "gpus": metadata.gpus,
                            "time_limit_minutes": metadata.time_limit_minutes,
                        },
                    }
                )
            except ValidationError as exc:
                raise JobOperationConflict("Job metadata cannot be cloned safely") from exc
            return self._submit_native_job(
                submission,
                idempotency_key,
                idempotency_namespace=f"clone:{metadata.id}:",
            )

        if not self.allow_fixture_submissions:
            raise JobSubmissionUnavailable("Job cloning is unavailable")

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
        if re.fullmatch(r"[0-9]+(?:[._+][A-Za-z0-9_-]+)*", job.slurm_job_id) is None:
            raise JobLogsUnavailable("Job log identifier is unsafe")

        if self.native_log_workspace is not None:
            log_path = self._native_log_path(job.slurm_job_id, stream)
        elif self.fixture_job_output_directory is not None:
            output_directory = self.fixture_job_output_directory.resolve()
            log_path = (output_directory / f"{job.slurm_job_id}.{stream.value}.log").resolve()
            if log_path.parent != output_directory:
                raise JobLogsUnavailable("Job log path is unsafe")
        else:
            raise JobLogsUnavailable("Job logs are unavailable")

        return self._read_log_path(job.id, stream, log_path, offset, limit)

    def _native_log_path(self, slurm_job_id: str, stream: JobLogStream) -> Path:
        if self.metadata_repository is None or self.native_log_workspace is None:
            raise JobLogsUnavailable("Native job metadata is unavailable")
        try:
            metadata = self.metadata_repository.get_by_slurm_job_id(
                slurm_job_id, owner=self.owner
            )
        except SQLAlchemyError as exc:
            raise JobLogsUnavailable("Native job metadata is unavailable") from exc
        if metadata is None or metadata.source != "native":
            raise JobLogsUnavailable("Native job log metadata is unavailable")

        configured_value = (
            metadata.stdout_path if stream == JobLogStream.STDOUT else metadata.stderr_path
        )
        if configured_value is None:
            raise JobLogsUnavailable("Native job log path is unavailable")
        try:
            return resolve_native_log_path(
                configured_value,
                workspace=self.native_log_workspace,
                stream=stream.value,
            )
        except NativeLogPathError as exc:
            raise JobLogsUnavailable("Native job log path is unsafe") from exc

    @staticmethod
    def _read_log_path(
        job_id: str,
        stream: JobLogStream,
        log_path: Path,
        offset: int,
        limit: int,
    ) -> JobLogResponse:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(log_path, flags)
        except FileNotFoundError:
            return JobLogResponse(
                job_id=job_id,
                stream=stream,
                content="",
                offset=offset,
                next_offset=offset,
                eof=True,
                available=False,
            )
        except OSError as exc:
            raise JobLogsUnavailable("Job log could not be opened") from exc

        try:
            file_status = os.fstat(descriptor)
            if not stat.S_ISREG(file_status.st_mode):
                raise JobLogsUnavailable("Job log is not a regular file")
            size = file_status.st_size
            if offset > size:
                raise JobLogOffsetOutOfRange(
                    "Job log offset is beyond the current file size"
                )
            os.lseek(descriptor, offset, os.SEEK_SET)
            chunk = os.read(descriptor, limit)
        except (JobLogOffsetOutOfRange, JobLogsUnavailable):
            raise
        except OSError as exc:
            raise JobLogsUnavailable("Job log could not be read") from exc
        finally:
            os.close(descriptor)

        next_offset = offset + len(chunk)
        return JobLogResponse(
            job_id=job_id,
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
