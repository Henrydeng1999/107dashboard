from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class JobMetadata(Base):
    __tablename__ = "job_metadata"
    __table_args__ = (UniqueConstraint("slurm_job_id", name="uq_job_metadata_slurm_job_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slurm_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="fixture")
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    command: Mapped[str] = mapped_column(String(500), nullable=False)
    partition: Mapped[str] = mapped_column(String(64), nullable=False)
    account: Mapped[str] = mapped_column(String(64), nullable=False)
    qos: Mapped[str] = mapped_column(String(64), nullable=False)
    cpus: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    gpus: Mapped[int] = mapped_column(Integer, nullable=False)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    stdout_path: Mapped[str | None] = mapped_column(String(1024))
    stderr_path: Mapped[str | None] = mapped_column(String(1024))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SubmissionAudit(Base):
    __tablename__ = "submission_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    result_code: Mapped[str] = mapped_column(String(64), nullable=False)
    slurm_job_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SubmissionIdempotency(Base):
    __tablename__ = "submission_idempotency"
    __table_args__ = (
        UniqueConstraint("owner", "key_digest", name="uq_submission_idempotency_owner_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    submission_id: Mapped[str | None] = mapped_column(String(64))
    slurm_job_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class JobOperationIdempotency(Base):
    __tablename__ = "job_operation_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "owner",
            "operation",
            "key_digest",
            name="uq_job_operation_owner_operation_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    key_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    target_job_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
