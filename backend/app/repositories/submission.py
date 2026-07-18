from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.job_metadata import Base, JobMetadata, SubmissionAudit, SubmissionIdempotency
from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository


@dataclass(frozen=True, slots=True)
class SubmissionAuditRecord:
    submission_id: str
    owner: str
    status: str
    result_code: str
    slurm_job_id: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SubmissionIdempotencyRecord:
    owner: str
    key_digest: str
    request_digest: str
    status: str
    submission_id: str | None = None
    slurm_job_id: str | None = None


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

    def get_idempotency(
        self, *, owner: str, key_digest: str
    ) -> SubmissionIdempotencyRecord | None:
        statement = select(SubmissionIdempotency).where(
            SubmissionIdempotency.owner == owner,
            SubmissionIdempotency.key_digest == key_digest,
        )
        with self._session_factory() as session:
            model = session.scalars(statement).one_or_none()
            return None if model is None else self._to_idempotency_record(model)

    def reserve_idempotency(self, record: SubmissionIdempotencyRecord) -> None:
        if record.status != "PREPARED" or record.submission_id is not None:
            raise ValueError("idempotency reservation must start prepared and unassigned")
        with self._session_factory.begin() as session:
            session.add(
                SubmissionIdempotency(
                    owner=record.owner,
                    key_digest=record.key_digest,
                    request_digest=record.request_digest,
                    status=record.status,
                )
            )

    def mark_idempotency_failed(self, *, owner: str, key_digest: str) -> None:
        with self._session_factory.begin() as session:
            model = session.scalars(
                select(SubmissionIdempotency).where(
                    SubmissionIdempotency.owner == owner,
                    SubmissionIdempotency.key_digest == key_digest,
                )
            ).one_or_none()
            if model is not None and model.status == "PREPARED":
                model.status = "FAILED"

    def record_success(
        self,
        metadata: JobMetadataRecord,
        audit: SubmissionAuditRecord,
        *,
        key_digest: str | None = None,
        request_digest: str | None = None,
    ) -> JobMetadataRecord:
        """Commit the final metadata and success audit as one database transaction."""
        if metadata.source != "native" or metadata.owner != audit.owner:
            raise ValueError("Native submission metadata owner/source mismatch")
        if metadata.slurm_job_id != audit.slurm_job_id:
            raise ValueError("Native submission metadata/audit mismatch")
        with self._session_factory.begin() as session:
            metadata_model = JobMetadata(
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
            session.add(metadata_model)
            session.add(SubmissionAudit(**self._audit_values(audit)))
            if key_digest is not None:
                if request_digest is None:
                    raise ValueError("request digest is required with idempotency key digest")
                idempotency = session.scalars(
                    select(SubmissionIdempotency).where(
                        SubmissionIdempotency.owner == metadata.owner,
                        SubmissionIdempotency.key_digest == key_digest,
                    )
                ).one_or_none()
                if (
                    idempotency is None
                    or idempotency.status != "PREPARED"
                    or idempotency.request_digest != request_digest
                ):
                    raise ValueError("idempotency reservation does not match submission")
                idempotency.status = "SUCCEEDED"
                idempotency.submission_id = metadata.id
                idempotency.slurm_job_id = metadata.slurm_job_id
            session.flush()
            return JobMetadataRepository._to_record(metadata_model)

    def get_successful_metadata(
        self, *, owner: str, submission_id: str
    ) -> JobMetadataRecord | None:
        statement = select(JobMetadata).where(
            JobMetadata.owner == owner,
            JobMetadata.id == submission_id,
            JobMetadata.source == "native",
        )
        with self._session_factory() as session:
            model = session.scalars(statement).one_or_none()
            return None if model is None else JobMetadataRepository._to_record(model)

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

    @staticmethod
    def _to_idempotency_record(
        model: SubmissionIdempotency,
    ) -> SubmissionIdempotencyRecord:
        return SubmissionIdempotencyRecord(
            owner=model.owner,
            key_digest=model.key_digest,
            request_digest=model.request_digest,
            status=model.status,
            submission_id=model.submission_id,
            slurm_job_id=model.slurm_job_id,
        )
