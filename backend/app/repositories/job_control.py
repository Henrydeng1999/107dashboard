from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models.job_metadata import Base, JobOperationIdempotency


@dataclass(frozen=True, slots=True)
class JobOperationRecord:
    owner: str
    operation: str
    key_digest: str
    target_job_id: str
    status: str


class JobControlRepository:
    """Persist idempotency state for owner-scoped Native control operations."""

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(database_url)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self) -> None:
        if self._engine.dialect.name == "sqlite":
            database_path = self._engine.url.database
            if database_path not in {None, "", ":memory:"}:
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)

    def get(
        self,
        *,
        owner: str,
        operation: str,
        key_digest: str,
    ) -> JobOperationRecord | None:
        statement = select(JobOperationIdempotency).where(
            JobOperationIdempotency.owner == owner,
            JobOperationIdempotency.operation == operation,
            JobOperationIdempotency.key_digest == key_digest,
        )
        with self._session_factory() as session:
            model = session.scalars(statement).one_or_none()
            return None if model is None else self._to_record(model)

    def reserve(self, record: JobOperationRecord) -> None:
        if record.status != "PREPARED":
            raise ValueError("job operation reservation must start prepared")
        with self._session_factory.begin() as session:
            session.add(
                JobOperationIdempotency(
                    owner=record.owner,
                    operation=record.operation,
                    key_digest=record.key_digest,
                    target_job_id=record.target_job_id,
                    status=record.status,
                )
            )

    def mark_status(
        self,
        *,
        owner: str,
        operation: str,
        key_digest: str,
        expected_status: str,
        status: str,
    ) -> None:
        with self._session_factory.begin() as session:
            model = session.scalars(
                select(JobOperationIdempotency).where(
                    JobOperationIdempotency.owner == owner,
                    JobOperationIdempotency.operation == operation,
                    JobOperationIdempotency.key_digest == key_digest,
                )
            ).one_or_none()
            if model is None or model.status != expected_status:
                raise ValueError("job operation reservation state changed")
            model.status = status

    @staticmethod
    def _to_record(model: JobOperationIdempotency) -> JobOperationRecord:
        return JobOperationRecord(
            owner=model.owner,
            operation=model.operation,
            key_digest=model.key_digest,
            target_job_id=model.target_job_id,
            status=model.status,
        )
