from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.schemas.jobs import JobState, JobSubmitRequest
from app.services.job_catalog import JobCatalog
from app.slurm import SlurmJob, SlurmResources, SlurmUsageRecord


class EmptyAdapter:
    def __init__(self, accounting: list[SlurmJob] | None = None) -> None:
        self.accounting = accounting or []

    def list_queue(self, user: str) -> list[SlurmJob]:
        return []

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return self.accounting

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[SlurmUsageRecord]:
        return []


def build_record(**overrides: object) -> JobMetadataRecord:
    values: dict[str, object] = {
        "id": "job-local-1",
        "slurm_job_id": "21482",
        "owner": "student_user",
        "name": "training",
        "command": "python train.py",
        "partition": "Students",
        "account": "stu",
        "qos": "qos_stu_default",
        "cpus": 2,
        "memory_mb": 4096,
        "gpus": 1,
        "time_limit_minutes": 30,
        "stdout_path": "/safe/jobs/21482.out",
        "stderr_path": "/safe/jobs/21482.err",
    }
    values.update(overrides)
    return JobMetadataRecord(**values)  # type: ignore[arg-type]


@pytest.fixture
def repository(tmp_path: Path) -> JobMetadataRepository:
    database_path = (tmp_path / "dashboard.sqlite3").as_posix()
    result = JobMetadataRepository(f"sqlite:///{database_path}")
    result.initialize()
    return result


def test_repository_round_trip_and_owner_isolation(repository: JobMetadataRepository) -> None:
    created = repository.upsert(build_record())

    assert created.created_at is not None
    assert repository.get_by_id("job-local-1", owner="student_user") == created
    assert repository.get_by_slurm_job_id("21482", owner="student_user") == created
    assert repository.get_by_id("job-local-1", owner="another_user") is None
    assert repository.get_by_slurm_job_id("21482", owner="another_user") is None


def test_repository_updates_mutable_metadata_without_changing_owner(
    repository: JobMetadataRepository,
) -> None:
    repository.upsert(build_record())

    updated = repository.upsert(build_record(name="training-v2", memory_mb=8192))

    assert updated.name == "training-v2"
    assert updated.memory_mb == 8192
    assert repository.list_by_owner("student_user") == [updated]


def test_repository_rejects_owner_change(repository: JobMetadataRepository) -> None:
    repository.upsert(build_record())

    with pytest.raises(ValueError, match="owner cannot be changed"):
        repository.upsert(build_record(owner="another_user"))


def test_repository_rejects_metadata_source_change(repository: JobMetadataRepository) -> None:
    repository.upsert(build_record())

    with pytest.raises(ValueError, match="source cannot be changed"):
        repository.upsert(build_record(source="native"))


def test_repository_enforces_unique_slurm_job_id(repository: JobMetadataRepository) -> None:
    repository.upsert(build_record())

    with pytest.raises(IntegrityError):
        repository.upsert(build_record(id="job-local-2", owner="another_user"))


def test_catalog_restores_submitted_and_cancelled_jobs_after_rebuild(
    repository: JobMetadataRepository,
) -> None:
    submission = JobSubmitRequest.model_validate(
        {
            "name": "training",
            "command": "python train.py",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 2,
                "memory_mb": 4096,
                "gpus": 1,
                "time_limit_minutes": 30,
            },
        }
    )
    first_catalog = JobCatalog(
        adapter=EmptyAdapter(),
        owner="student_user",
        allow_fixture_submissions=True,
        metadata_repository=repository,
    )

    submitted = first_catalog.submit_job(submission)
    restored_catalog = JobCatalog(
        adapter=EmptyAdapter(),
        owner="student_user",
        allow_fixture_submissions=True,
        metadata_repository=repository,
    )
    restored = restored_catalog.get_job(submitted.id)

    assert restored is not None
    assert restored.command == "python train.py"
    assert restored.state == JobState.PENDING

    restored_catalog.cancel_job(submitted.id)
    cancelled_catalog = JobCatalog(
        adapter=EmptyAdapter(),
        owner="student_user",
        allow_fixture_submissions=True,
        metadata_repository=repository,
    )

    cancelled = cancelled_catalog.get_job(submitted.id)
    assert cancelled is not None
    assert cancelled.state == JobState.CANCELLED


def test_catalog_does_not_restore_another_owners_metadata(
    repository: JobMetadataRepository,
) -> None:
    repository.upsert(build_record(id="slurm-21482"))

    catalog = JobCatalog(
        adapter=EmptyAdapter(),
        owner="another_user",
        allow_fixture_submissions=True,
        metadata_repository=repository,
    )

    assert catalog.get_job("slurm-21482") is None
    assert catalog.list_jobs(None, 1, 20).total == 0


def test_repository_filters_fixture_and_native_metadata_sources(
    repository: JobMetadataRepository,
) -> None:
    fixture_record = repository.upsert(build_record())
    native_record = repository.upsert(
        build_record(id="job-local-2", slurm_job_id="21483", source="native")
    )

    assert repository.list_by_owner("student_user", source="fixture") == [fixture_record]
    assert repository.list_by_owner("student_user", source="native") == [native_record]


def test_native_catalog_merges_metadata_without_duplicating_slurm_job(
    repository: JobMetadataRepository,
) -> None:
    repository.upsert(
        build_record(id="submission-legacy-native", source="native", memory_mb=4096)
    )
    adapter = EmptyAdapter(
        accounting=[
            SlurmJob(
                job_id="21482",
                user="student_user",
                name="scheduler-name",
                state="COMPLETED",
                partition="Students",
                allocated=SlurmResources(cpus=2, gpus=1),
                exit_code="0:0",
            )
        ]
    )

    catalog = JobCatalog(
        adapter=adapter,
        owner="student_user",
        metadata_repository=repository,
        metadata_source="native",
    )
    response = catalog.list_jobs(None, 1, 20)

    assert response.total == 1
    merged = response.items[0]
    assert merged.id == "slurm-21482"
    assert merged.state == JobState.COMPLETED
    assert merged.name == "scheduler-name"
    assert merged.command == "python train.py"
    assert merged.resources.cpus == 2
    assert merged.resources.memory_mb == 4096
    assert merged.exit_code == "0:0"


def test_repository_upgrades_initial_sqlite_schema_without_deleting_data(tmp_path: Path) -> None:
    database_path = (tmp_path / "legacy.sqlite3").as_posix()
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE job_metadata (
                    id VARCHAR(64) PRIMARY KEY,
                    slurm_job_id VARCHAR(64) NOT NULL UNIQUE,
                    owner VARCHAR(32) NOT NULL,
                    name VARCHAR(64) NOT NULL,
                    command VARCHAR(500) NOT NULL,
                    partition VARCHAR(64) NOT NULL,
                    account VARCHAR(64) NOT NULL,
                    qos VARCHAR(64) NOT NULL,
                    cpus INTEGER NOT NULL,
                    memory_mb INTEGER NOT NULL,
                    gpus INTEGER NOT NULL,
                    time_limit_minutes INTEGER NOT NULL,
                    stdout_path VARCHAR(1024),
                    stderr_path VARCHAR(1024),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )

    repository = JobMetadataRepository(f"sqlite:///{database_path}", engine=engine)
    repository.initialize()
    columns = {column["name"] for column in inspect(engine).get_columns("job_metadata")}
    created = repository.upsert(build_record())

    assert {"source", "state", "submitted_at", "finished_at"} <= columns
    assert created.source == "fixture"
    assert created.state == "PENDING"
