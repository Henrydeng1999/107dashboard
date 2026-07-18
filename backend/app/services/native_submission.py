from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
from typing import Callable, Protocol

from app.repositories.job_metadata import JobMetadataRecord
from app.repositories.submission import (
    SubmissionAuditRecord,
    SubmissionIdempotencyRecord,
    SubmissionRepository,
)
from app.schemas.jobs import JobSubmitRequest
from app.slurm.submission import (
    SubmissionPlan,
    build_submission_plan,
    materialize_submission,
    parse_allowed_command,
    write_submission_receipt,
)


class SlurmSubmitter(Protocol):
    def submit(self, plan: SubmissionPlan) -> str: ...


@dataclass(frozen=True, slots=True)
class ExplicitSubmissionAuthorization:
    confirmed: bool = False


class NativeIdempotencyRequiredError(RuntimeError):
    """The idempotency key is absent or invalid."""


class NativeIdempotencyConflictError(RuntimeError):
    """The idempotency key conflicts with an existing attempt."""


class NativeActiveJobLimitError(RuntimeError):
    """The trusted owner already has the configured number of active jobs."""


_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", re.ASCII)


class NativeSubmissionService:
    """Native write workflow kept separate from the HTTP catalog until enabled explicitly."""

    def __init__(
        self,
        *,
        owner: str,
        workspace_root: Path,
        submitter: SlurmSubmitter,
        repository: SubmissionRepository,
    ) -> None:
        self._owner = owner
        self._workspace_root = workspace_root
        self._submitter = submitter
        self._repository = repository
        self._submission_lock = Lock()

    def submit(
        self,
        request: JobSubmitRequest,
        *,
        authorization: ExplicitSubmissionAuthorization,
    ) -> JobMetadataRecord:
        if not authorization.confirmed:
            raise PermissionError("explicit Native submission authorization is required")

        return self._submit_new(request)

    def submit_idempotent(
        self,
        request: JobSubmitRequest,
        *,
        authorization: ExplicitSubmissionAuthorization,
        idempotency_key: str | None,
        active_job_count: Callable[[], int],
        max_active_jobs: int,
        idempotency_namespace: str = "",
    ) -> JobMetadataRecord:
        if not authorization.confirmed:
            raise PermissionError("explicit Native submission authorization is required")
        if idempotency_key is None or _IDEMPOTENCY_KEY.fullmatch(idempotency_key) is None:
            raise NativeIdempotencyRequiredError("a valid Idempotency-Key is required")
        if not 1 <= max_active_jobs <= 100:
            raise ValueError("max_active_jobs must be between 1 and 100")
        parse_allowed_command(request.command)

        key_digest = sha256(
            f"{idempotency_namespace}{idempotency_key}".encode("ascii")
        ).hexdigest()
        request_digest = sha256(
            json.dumps(
                request.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with self._submission_lock:
            existing = self._repository.get_idempotency(
                owner=self._owner, key_digest=key_digest
            )
            if existing is not None:
                return self._resolve_existing(existing, request_digest)
            if active_job_count() >= max_active_jobs:
                raise NativeActiveJobLimitError("active Native job limit reached")
            self._repository.reserve_idempotency(
                SubmissionIdempotencyRecord(
                    owner=self._owner,
                    key_digest=key_digest,
                    request_digest=request_digest,
                    status="PREPARED",
                )
            )
            try:
                return self._submit_new(
                    request,
                    key_digest=key_digest,
                    request_digest=request_digest,
                )
            except Exception:
                try:
                    self._repository.mark_idempotency_failed(
                        owner=self._owner, key_digest=key_digest
                    )
                except Exception:
                    pass
                raise

    def _resolve_existing(
        self,
        existing: SubmissionIdempotencyRecord,
        request_digest: str,
    ) -> JobMetadataRecord:
        if existing.request_digest != request_digest:
            raise NativeIdempotencyConflictError("Idempotency-Key was used for another request")
        if existing.status != "SUCCEEDED" or existing.submission_id is None:
            raise NativeIdempotencyConflictError(
                "Idempotency-Key has no replayable successful result"
            )
        metadata = self._repository.get_successful_metadata(
            owner=self._owner,
            submission_id=existing.submission_id,
        )
        if metadata is None:
            raise NativeIdempotencyConflictError("idempotent submission metadata is unavailable")
        return metadata

    def _submit_new(
        self,
        request: JobSubmitRequest,
        *,
        key_digest: str | None = None,
        request_digest: str | None = None,
    ) -> JobMetadataRecord:
        plan = build_submission_plan(
            request,
            owner=self._owner,
            workspace_root=self._workspace_root,
        )
        self._repository.record_event(self._audit(plan, "PREPARED", "VALIDATED"))
        try:
            materialize_submission(plan)
            slurm_job_id = self._submitter.submit(plan)
            write_submission_receipt(plan, slurm_job_id)
            now = datetime.now(timezone.utc)
            metadata = JobMetadataRecord(
                id=f"slurm-{slurm_job_id}",
                slurm_job_id=slurm_job_id,
                owner=self._owner,
                source="native",
                name=request.name,
                command=request.command,
                partition=request.partition,
                account=request.account,
                qos=request.qos,
                cpus=request.resources.cpus,
                memory_mb=request.resources.memory_mb,
                gpus=request.resources.gpus,
                time_limit_minutes=request.resources.time_limit_minutes,
                stdout_path=str(plan.stdout_path),
                stderr_path=str(plan.stderr_path),
                state="PENDING",
                submitted_at=now,
            )
            metadata = self._repository.record_success(
                metadata,
                self._audit(plan, "SUCCEEDED", "SBATCH_ACCEPTED", slurm_job_id),
                key_digest=key_digest,
                request_digest=request_digest,
            )
            return metadata
        except Exception as exc:
            try:
                self._repository.record_event(
                    self._audit(plan, "FAILED", self._safe_failure_code(exc))
                )
            except Exception:
                pass
            raise

    @staticmethod
    def _audit(
        plan: SubmissionPlan,
        status: str,
        result_code: str,
        slurm_job_id: str | None = None,
    ) -> SubmissionAuditRecord:
        return SubmissionAuditRecord(
            submission_id=plan.submission_id,
            owner=plan.owner,
            status=status,
            result_code=result_code,
            slurm_job_id=slurm_job_id,
        )

    @staticmethod
    def _safe_failure_code(exc: Exception) -> str:
        name = exc.__class__.__name__.upper()
        return name[:64] if name.isascii() and name.replace("_", "").isalnum() else "ERROR"
