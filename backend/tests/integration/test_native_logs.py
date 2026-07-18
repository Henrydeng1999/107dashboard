from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.schemas.jobs import JobLogStream
from app.services.job_catalog import (
    JobCatalog,
    JobLogOffsetOutOfRange,
    JobLogsUnavailable,
)
from app.slurm.models import SlurmJob


class NativeLogAdapter:
    def list_queue(self, user: str) -> list[SlurmJob]:
        return []

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return [
            SlurmJob(
                job_id="24011",
                user=user,
                name="dashboard-native-smoke",
                state="COMPLETED",
                partition="Students",
                account="stu",
                qos="qos_stu_default",
                exit_code="0:0",
            )
        ]

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[object]:
        return []


def metadata_record(
    workspace: Path,
    *,
    owner: str = "pb24030760",
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> JobMetadataRecord:
    directory = workspace / ("submission-" + "1" * 32)
    return JobMetadataRecord(
        id="submission-legacy-native",
        slurm_job_id="24011",
        owner=owner,
        source="native",
        name="dashboard-native-smoke",
        command="python3 --version",
        partition="Students",
        account="stu",
        qos="qos_stu_default",
        cpus=1,
        memory_mb=512,
        gpus=0,
        time_limit_minutes=1,
        stdout_path=str(stdout_path or directory / "stdout.log"),
        stderr_path=str(stderr_path or directory / "stderr.log"),
        state="PENDING",
    )


def build_catalog(
    tmp_path: Path,
    *,
    record: JobMetadataRecord | None = None,
) -> tuple[JobCatalog, Path]:
    workspace = tmp_path / "jobs"
    repository = JobMetadataRepository(f"sqlite:///{tmp_path / 'dashboard.sqlite3'}")
    repository.initialize()
    repository.upsert(record or metadata_record(workspace))
    catalog = JobCatalog(
        adapter=NativeLogAdapter(),
        owner="pb24030760",
        metadata_repository=repository,
        metadata_source="native",
        native_log_workspace=workspace,
    )
    return catalog, workspace


def test_native_log_reads_incrementally_from_trusted_metadata(tmp_path: Path) -> None:
    catalog, workspace = build_catalog(tmp_path)
    log_path = workspace / ("submission-" + "1" * 32) / "stdout.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_bytes(b"Python 3.12.3\n")

    first = catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 0, 7)
    second = catalog.read_job_log(
        "slurm-24011", JobLogStream.STDOUT, first.next_offset, 65536
    )

    assert first.content == "Python "
    assert first.eof is False
    assert second.content == "3.12.3\n"
    assert second.eof is True


def test_native_missing_log_is_explicitly_unavailable(tmp_path: Path) -> None:
    catalog, _ = build_catalog(tmp_path)

    response = catalog.read_job_log("slurm-24011", JobLogStream.STDERR, 0, 100)

    assert response.available is False
    assert response.content == ""


def test_native_log_rejects_metadata_owned_by_another_user(tmp_path: Path) -> None:
    workspace = tmp_path / "jobs"
    catalog, _ = build_catalog(
        tmp_path, record=metadata_record(workspace, owner="another-user")
    )

    with pytest.raises(JobLogsUnavailable):
        catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 0, 100)


@pytest.mark.parametrize(
    "unsafe_kind", ["outside", "wrong_name", "nested", "parent_traversal"]
)
def test_native_log_rejects_paths_outside_exact_submission_layout(
    tmp_path: Path, unsafe_kind: str
) -> None:
    workspace = tmp_path / "jobs"
    directory = workspace / ("submission-" + "1" * 32)
    paths = {
        "outside": tmp_path / "outside" / "stdout.log",
        "wrong_name": directory / "other.log",
        "nested": directory / "nested" / "stdout.log",
        "parent_traversal": directory / ".." / directory.name / "stdout.log",
    }
    catalog, _ = build_catalog(
        tmp_path,
        record=metadata_record(workspace, stdout_path=paths[unsafe_kind]),
    )

    with pytest.raises(JobLogsUnavailable):
        catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 0, 100)


def test_native_log_rejects_offset_beyond_snapshot(tmp_path: Path) -> None:
    catalog, workspace = build_catalog(tmp_path)
    log_path = workspace / ("submission-" + "1" * 32) / "stdout.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("short", encoding="utf-8")

    with pytest.raises(JobLogOffsetOutOfRange):
        catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 6, 100)


def test_native_log_rejects_non_regular_file(tmp_path: Path) -> None:
    catalog, workspace = build_catalog(tmp_path)
    log_path = workspace / ("submission-" + "1" * 32) / "stdout.log"
    log_path.mkdir(parents=True)

    with pytest.raises(JobLogsUnavailable):
        catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 0, 100)


def test_native_log_rejects_symlink_that_changes_directory(tmp_path: Path) -> None:
    catalog, workspace = build_catalog(tmp_path)
    log_path = workspace / ("submission-" + "1" * 32) / "stdout.log"
    outside_path = tmp_path / "outside" / "stdout.log"
    log_path.parent.mkdir(parents=True)
    outside_path.parent.mkdir()
    outside_path.write_text("must not leak", encoding="utf-8")
    try:
        log_path.symlink_to(outside_path)
    except OSError:
        pytest.skip("symlink creation is unavailable on this test host")

    with pytest.raises(JobLogsUnavailable):
        catalog.read_job_log("slurm-24011", JobLogStream.STDOUT, 0, 100)


def test_native_log_api_reads_controlled_file(tmp_path: Path) -> None:
    catalog, workspace = build_catalog(tmp_path)
    log_path = workspace / ("submission-" + "1" * 32) / "stdout.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_bytes(b"Python 3.12.3\n")
    client = TestClient(
        create_app(
            Settings(
                _env_file=None,
                slurm_data_source="native",
                dashboard_owner="pb24030760",
                native_logs_enabled=True,
            ),
            job_catalog=catalog,
        )
    )

    response = client.get("/api/jobs/slurm-24011/logs", params={"limit": 7})

    assert response.status_code == 200
    assert response.json()["content"] == "Python "
    assert response.json()["next_offset"] == 7


def test_native_log_api_capability_and_sanitized_path_failure(tmp_path: Path) -> None:
    workspace = tmp_path / "jobs"
    secret_path = tmp_path / "private" / "stdout.log"
    secret_path.parent.mkdir()
    secret_path.write_text("must not leak", encoding="utf-8")
    catalog, _ = build_catalog(
        tmp_path,
        record=metadata_record(workspace, stdout_path=secret_path),
    )
    client = TestClient(
        create_app(
            Settings(
                _env_file=None,
                slurm_data_source="native",
                dashboard_owner="pb24030760",
                native_logs_enabled=True,
            ),
            job_catalog=catalog,
        )
    )

    runtime = client.get("/api/runtime").json()
    response = client.get("/api/jobs/slurm-24011/logs")

    assert runtime["read_only"] is True
    assert runtime["capabilities"]["logs"] is True
    assert runtime["capabilities"]["submit"] is False
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "JOB_LOGS_UNAVAILABLE"
    assert "must not leak" not in response.text
    assert str(secret_path) not in response.text
