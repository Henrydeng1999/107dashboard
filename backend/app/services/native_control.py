from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import re
from threading import Lock

from app.repositories.job_control import JobControlRepository, JobOperationRecord
from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.repositories.submission import SubmissionAuditRecord, SubmissionRepository
from app.slurm.control import SlurmCanceller

_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", re.ASCII)


class NativeControlIdempotencyRequired(RuntimeError):
    """A valid operation idempotency key was not supplied."""


class NativeControlIdempotencyConflict(RuntimeError):
    """An operation key cannot safely be replayed."""


class NativeControlStateConflict(RuntimeError):
    """The observed job state cannot be cancelled."""


class NativeJobControlService:
    def __init__(
        self,
        *,
        owner: str,
        metadata_repository: JobMetadataRepository,
        operation_repository: JobControlRepository,
        audit_repository: SubmissionRepository,
        canceller: SlurmCanceller,
    ) -> None:
        self._owner = owner
        self._metadata_repository = metadata_repository
        self._operation_repository = operation_repository
        self._audit_repository = audit_repository
        self._canceller = canceller
        self._lock = Lock()

    def cancel(
        self,
        metadata: JobMetadataRecord,
        *,
        observed_state: str,
        idempotency_key: str | None,
    ) -> JobMetadataRecord:
        if idempotency_key is None or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise NativeControlIdempotencyRequired("a valid Idempotency-Key is required")
        if (
            metadata.owner != self._owner
            or metadata.source != "native"
            or re.fullmatch(r"[1-9][0-9]*", metadata.slurm_job_id, re.ASCII) is None
        ):
            raise PermissionError("trusted owner-scoped Native metadata is required")
        key_digest = sha256(idempotency_key.encode("ascii")).hexdigest()
        operation = "cancel"
        with self._lock:
            existing = self._operation_repository.get(
                owner=self._owner,
                operation=operation,
                key_digest=key_digest,
            )
            if existing is not None:
                return self._resolve_existing(existing, metadata)
            if observed_state not in {"PENDING", "RUNNING"}:
                raise NativeControlStateConflict("only pending or running jobs can be cancelled")

            trusted = self._metadata_repository.get_by_slurm_job_id(
                metadata.slurm_job_id,
                owner=self._owner,
            )
            if trusted is None or trusted.source != "native" or trusted.id != metadata.id:
                raise PermissionError("trusted owner-scoped Native metadata is required")
            self._operation_repository.reserve(
                JobOperationRecord(
                    owner=self._owner,
                    operation=operation,
                    key_digest=key_digest,
                    target_job_id=metadata.id,
                    status="PREPARED",
                )
            )
            self._audit_repository.record_event(
                self._audit(metadata, "PREPARED", "SCANCEL_VALIDATED")
            )
            try:
                self._canceller.cancel(metadata.slurm_job_id)
                now = datetime.now(timezone.utc)
                cancelled = self._metadata_repository.upsert(
                    replace(trusted, state="CANCELLED", finished_at=now)
                )
                self._audit_repository.record_event(
                    self._audit(metadata, "SUCCEEDED", "SCANCEL_ACCEPTED")
                )
                self._operation_repository.mark_status(
                    owner=self._owner,
                    operation=operation,
                    key_digest=key_digest,
                    expected_status="PREPARED",
                    status="SUCCEEDED",
                )
                return cancelled
            except Exception as exc:
                try:
                    self._operation_repository.mark_status(
                        owner=self._owner,
                        operation=operation,
                        key_digest=key_digest,
                        expected_status="PREPARED",
                        status="FAILED",
                    )
                    self._audit_repository.record_event(
                        self._audit(metadata, "FAILED", self._safe_failure_code(exc))
                    )
                except Exception:
                    pass
                raise

    def _resolve_existing(
        self,
        existing: JobOperationRecord,
        metadata: JobMetadataRecord,
    ) -> JobMetadataRecord:
        if existing.target_job_id != metadata.id or existing.status != "SUCCEEDED":
            raise NativeControlIdempotencyConflict("operation key has no replayable result")
        restored = self._metadata_repository.get_by_id(metadata.id, owner=self._owner)
        if restored is None or restored.state != "CANCELLED":
            raise NativeControlIdempotencyConflict("cancelled metadata is unavailable")
        return restored

    def _audit(
        self,
        metadata: JobMetadataRecord,
        status: str,
        result_code: str,
    ) -> SubmissionAuditRecord:
        return SubmissionAuditRecord(
            submission_id=metadata.id,
            owner=self._owner,
            status=status,
            result_code=result_code,
            slurm_job_id=metadata.slurm_job_id,
        )

    @staticmethod
    def _safe_failure_code(exc: Exception) -> str:
        name = exc.__class__.__name__.upper()
        return name[:64] if name.isascii() and name.replace("_", "").isalnum() else "ERROR"
