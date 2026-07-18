from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from app.repositories.job_metadata import JobMetadataRecord
from app.repositories.submission import SubmissionAuditRecord, SubmissionRepository
from app.schemas.jobs import JobSubmitRequest
from app.slurm.submission import (
    SubmissionPlan,
    build_submission_plan,
    materialize_submission,
    write_submission_receipt,
)


class SlurmSubmitter(Protocol):
    def submit(self, plan: SubmissionPlan) -> str: ...


@dataclass(frozen=True, slots=True)
class ExplicitSubmissionAuthorization:
    confirmed: bool = False


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

    def submit(
        self,
        request: JobSubmitRequest,
        *,
        authorization: ExplicitSubmissionAuthorization,
    ) -> JobMetadataRecord:
        if not authorization.confirmed:
            raise PermissionError("explicit Native submission authorization is required")

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
                id=plan.submission_id,
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
            self._repository.record_success(
                metadata,
                self._audit(plan, "SUCCEEDED", "SBATCH_ACCEPTED", slurm_job_id),
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
