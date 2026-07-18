from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.schemas.jobs import JobState, JobSubmitRequest
from app.services.job_catalog import JobCatalog
from app.slurm import SlurmJob, SlurmUsageRecord


class EmptyAdapter:
    def list_queue(self, user: str) -> list[SlurmJob]:
        return []

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return []

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
