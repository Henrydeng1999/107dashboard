from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable

from app.schemas.jobs import (
    Job,
    JobListResponse,
    JobLogResponse,
    JobLogStream,
    JobState,
    JobSubmitRequest,
    JobUsageResponse,
    UserJobSummary,
)
from app.services.job_catalog import (
    JobCatalog,
    JobCatalogUnavailable,
    JobSubmissionUnavailable,
)


@dataclass(frozen=True, slots=True)
class DemoFallbackStatus:
    active: bool
    reason: str | None


class DemoFallbackJobCatalog:
    """Fail closed to sanitized read-only fixtures when Native reads are unavailable."""

    def __init__(
        self,
        primary: JobCatalog,
        fallback: JobCatalog,
        *,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        self.primary = primary
        self.fallback = fallback
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = Lock()
        self._active = False
        self._retry_at = 0.0

    def status(self) -> DemoFallbackStatus:
        with self._lock:
            return DemoFallbackStatus(
                active=self._active,
                reason="slurm_unavailable" if self._active else None,
            )

    def _activate(self) -> None:
        with self._lock:
            self._active = True
            self._retry_at = self._clock() + self.cooldown_seconds

    def _deactivate(self) -> None:
        with self._lock:
            self._active = False
            self._retry_at = 0.0

    def _should_retry_primary(self) -> bool:
        with self._lock:
            return not self._active or self._clock() >= self._retry_at

    def list_jobs(self, state: JobState | None, page: int, page_size: int) -> JobListResponse:
        if not self._should_retry_primary():
            return self.fallback.list_jobs(state, page, page_size)
        try:
            result = self.primary.list_jobs(state, page, page_size)
        except JobCatalogUnavailable:
            self._activate()
            return self.fallback.list_jobs(state, page, page_size)
        self._deactivate()
        return result

    def summarize_jobs(self) -> UserJobSummary:
        if self.status().active:
            return self.fallback.summarize_jobs()
        try:
            return self.primary.summarize_jobs()
        except JobCatalogUnavailable:
            self._activate()
            return self.fallback.summarize_jobs()

    def get_job(self, dashboard_job_id: str) -> Job | None:
        if self.status().active:
            return self.fallback.get_job(dashboard_job_id)
        try:
            return self.primary.get_job(dashboard_job_id)
        except JobCatalogUnavailable:
            self._activate()
            raise

    def get_job_usage(self, dashboard_job_id: str) -> JobUsageResponse:
        if self.status().active:
            return self.fallback.get_job_usage(dashboard_job_id)
        try:
            return self.primary.get_job_usage(dashboard_job_id)
        except JobCatalogUnavailable:
            self._activate()
            raise

    def read_job_log(
        self,
        dashboard_job_id: str,
        stream: JobLogStream,
        offset: int,
        limit: int,
    ) -> JobLogResponse:
        if self.status().active:
            return self.fallback.read_job_log(dashboard_job_id, stream, offset, limit)
        try:
            return self.primary.read_job_log(dashboard_job_id, stream, offset, limit)
        except JobCatalogUnavailable:
            self._activate()
            raise

    def submit_job(
        self, request: JobSubmitRequest, *, idempotency_key: str | None = None
    ) -> Job:
        if self.status().active:
            raise JobSubmissionUnavailable("Writes are disabled during demo fallback")
        return self.primary.submit_job(request, idempotency_key=idempotency_key)

    def cancel_job(self, dashboard_job_id: str, *, idempotency_key: str | None = None) -> Job:
        if self.status().active:
            raise JobSubmissionUnavailable("Writes are disabled during demo fallback")
        return self.primary.cancel_job(dashboard_job_id, idempotency_key=idempotency_key)

    def clone_job(self, dashboard_job_id: str, *, idempotency_key: str | None = None) -> Job:
        if self.status().active:
            raise JobSubmissionUnavailable("Writes are disabled during demo fallback")
        return self.primary.clone_job(dashboard_job_id, idempotency_key=idempotency_key)
