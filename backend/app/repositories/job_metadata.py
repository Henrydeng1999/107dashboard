from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.job_metadata import Base, JobMetadata


@dataclass(frozen=True, slots=True)
class JobMetadataRecord:
    id: str
    slurm_job_id: str
    owner: str
    name: str
    command: str
    partition: str
    account: str
    qos: str
    cpus: int
    memory_mb: int
    gpus: int
    time_limit_minutes: int
    stdout_path: str | None = None
    stderr_path: str | None = None
    state: str = "PENDING"
    submitted_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobMetadataRepository:
    """SQLite-backed metadata access whose reads always require an owner."""

    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        if engine is not None:
            self._engine = engine
        elif database_url == "sqlite://":
            self._engine = create_engine(
                database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            self._engine = create_engine(database_url)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self) -> None:
        if self._engine.dialect.name == "sqlite":
            database_path = self._engine.url.database
            if database_path not in {None, "", ":memory:"}:
                Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)

    def upsert(self, record: JobMetadataRecord) -> JobMetadataRecord:
        with self._session_factory.begin() as session:
            model = session.get(JobMetadata, record.id)
            if model is None:
                model = JobMetadata(**self._write_values(record))
                session.add(model)
            else:
                if model.owner != record.owner:
                    raise ValueError("job metadata owner cannot be changed")
                for field, value in self._write_values(record).items():
                    if field not in {"id", "owner"}:
                        setattr(model, field, value)
            session.flush()
            return self._to_record(model)

    def get_by_id(self, job_id: str, *, owner: str) -> JobMetadataRecord | None:
        statement = select(JobMetadata).where(
            JobMetadata.id == job_id, JobMetadata.owner == owner
        )
        return self._fetch_one(statement)

    def get_by_slurm_job_id(
        self, slurm_job_id: str, *, owner: str
    ) -> JobMetadataRecord | None:
        statement = select(JobMetadata).where(
            JobMetadata.slurm_job_id == slurm_job_id, JobMetadata.owner == owner
        )
        return self._fetch_one(statement)

    def list_by_owner(self, owner: str) -> list[JobMetadataRecord]:
        statement = (
            select(JobMetadata)
            .where(JobMetadata.owner == owner)
            .order_by(JobMetadata.created_at.desc(), JobMetadata.id.desc())
        )
        with self._session_factory() as session:
            return [self._to_record(model) for model in session.scalars(statement)]

    def _fetch_one(self, statement: object) -> JobMetadataRecord | None:
        with self._session_factory() as session:
            model = session.scalars(statement).one_or_none()
            return None if model is None else self._to_record(model)

    @staticmethod
    def _write_values(record: JobMetadataRecord) -> dict[str, object]:
        return {
            "id": record.id,
            "slurm_job_id": record.slurm_job_id,
            "owner": record.owner,
            "name": record.name,
            "command": record.command,
            "partition": record.partition,
            "account": record.account,
            "qos": record.qos,
            "cpus": record.cpus,
            "memory_mb": record.memory_mb,
            "gpus": record.gpus,
            "time_limit_minutes": record.time_limit_minutes,
            "stdout_path": record.stdout_path,
            "stderr_path": record.stderr_path,
            "state": record.state,
            "submitted_at": record.submitted_at,
            "finished_at": record.finished_at,
        }

    @staticmethod
    def _to_record(model: JobMetadata) -> JobMetadataRecord:
        return JobMetadataRecord(
            id=model.id,
            slurm_job_id=model.slurm_job_id,
            owner=model.owner,
            name=model.name,
            command=model.command,
            partition=model.partition,
            account=model.account,
            qos=model.qos,
            cpus=model.cpus,
            memory_mb=model.memory_mb,
            gpus=model.gpus,
            time_limit_minutes=model.time_limit_minutes,
            stdout_path=model.stdout_path,
            stderr_path=model.stderr_path,
            state=model.state,
            submitted_at=(
                JobMetadataRepository._as_utc(model.submitted_at)
                if model.submitted_at is not None
                else None
            ),
            finished_at=(
                JobMetadataRepository._as_utc(model.finished_at)
                if model.finished_at is not None
                else None
            ),
            created_at=JobMetadataRepository._as_utc(model.created_at),
            updated_at=JobMetadataRepository._as_utc(model.updated_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        # SQLite drops timezone metadata even when SQLAlchemy receives aware values.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
