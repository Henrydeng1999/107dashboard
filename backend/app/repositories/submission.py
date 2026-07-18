from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.job_metadata import Base, JobMetadata, SubmissionAudit
from app.repositories.job_metadata import JobMetadataRecord


@dataclass(frozen=True, slots=True)
class SubmissionAuditRecord:
    submission_id: str
    owner: str
    status: str
    result_code: str
    slurm_job_id: str | None = None
    created_at: datetime | None = None


class SubmissionRepository:
    """Persists sanitized submission events and Native job metadata."""

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(database_url)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self) -> None:
        if self._engine.dialect.name == "sqlite":
            database_path = self._engine.url.database
            if database_path not in {None, "", ":memory:"}:
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)

    def record_event(self, record: SubmissionAuditRecord) -> None:
        with self._session_factory.begin() as session:
            session.add(SubmissionAudit(**self._audit_values(record)))

    def record_success(
        self, metadata: JobMetadataRecord, audit: SubmissionAuditRecord
    ) -> None:
        """Commit the final metadata and success audit as one database transaction."""
        if metadata.source != "native" or metadata.owner != audit.owner:
            raise ValueError("Native submission metadata owner/source mismatch")
        if metadata.id != audit.submission_id or metadata.slurm_job_id != audit.slurm_job_id:
            raise ValueError("Native submission metadata/audit mismatch")
        with self._session_factory.begin() as session:
            session.add(
                JobMetadata(
                    id=metadata.id,
                    slurm_job_id=metadata.slurm_job_id,
                    owner=metadata.owner,
                    source=metadata.source,
                    name=metadata.name,
                    command=metadata.command,
                    partition=metadata.partition,
                    account=metadata.account,
                    qos=metadata.qos,
                    cpus=metadata.cpus,
                    memory_mb=metadata.memory_mb,
                    gpus=metadata.gpus,
                    time_limit_minutes=metadata.time_limit_minutes,
                    stdout_path=metadata.stdout_path,
                    stderr_path=metadata.stderr_path,
                    state=metadata.state,
                    submitted_at=metadata.submitted_at,
                    finished_at=metadata.finished_at,
                )
            )
            session.add(SubmissionAudit(**self._audit_values(audit)))

    def list_events(self, *, owner: str) -> list[SubmissionAuditRecord]:
        statement = (
            select(SubmissionAudit)
            .where(SubmissionAudit.owner == owner)
            .order_by(SubmissionAudit.id)
        )
        with self._session_factory() as session:
            return [self._to_record(model) for model in session.scalars(statement)]

    @staticmethod
    def _audit_values(record: SubmissionAuditRecord) -> dict[str, object]:
        return {
            "submission_id": record.submission_id,
            "owner": record.owner,
            "status": record.status,
            "result_code": record.result_code,
            "slurm_job_id": record.slurm_job_id,
        }

    @staticmethod
    def _to_record(model: SubmissionAudit) -> SubmissionAuditRecord:
        created_at = model.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return SubmissionAuditRecord(
            submission_id=model.submission_id,
            owner=model.owner,
            status=model.status,
            result_code=model.result_code,
            slurm_job_id=model.slurm_job_id,
            created_at=created_at,
        )
