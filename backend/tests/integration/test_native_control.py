from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.repositories.job_metadata import JobMetadataRecord, JobMetadataRepository
from app.repositories.submission import SubmissionRepository
from app.slurm.models import SlurmJob
from app.slurm.runner import CommandResult


class NativeControlAdapter:
    def list_queue(self, user: str) -> list[SlurmJob]:
        return [
            SlurmJob(
                job_id="24011",
                user=user,
                name="dashboard-control-source",
                state="RUNNING",
                partition="Students",
                account="stu",
                qos="qos_stu_default",
            )
        ]

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return []

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[object]:
        return []


def source_metadata(workspace: Path, *, owner: str = "demo-user") -> JobMetadataRecord:
    directory = workspace / ("submission-" + "1" * 32)
    return JobMetadataRecord(
        id="slurm-24011",
        slurm_job_id="24011",
        owner=owner,
        source="native",
        name="dashboard-control-source",
        command="python3 --version",
        partition="Students",
        account="stu",
        qos="qos_stu_default",
        cpus=1,
        memory_mb=512,
        gpus=0,
        time_limit_minutes=1,
        stdout_path=str(directory / "stdout.log"),
        stderr_path=str(directory / "stderr.log"),
        state="RUNNING",
        submitted_at=datetime.now(timezone.utc),
    )


def build_native_control_client(
    tmp_path: Path,
    monkeypatch,
) -> tuple[TestClient, list[tuple[str, ...]]]:
    database_url = f"sqlite:///{tmp_path / 'dashboard.sqlite3'}"
    workspace = tmp_path / "jobs"
    metadata_repository = JobMetadataRepository(database_url)
    metadata_repository.initialize()
    metadata_repository.upsert(source_metadata(workspace))
    calls: list[tuple[str, ...]] = []

    def fake_run(self: object, arguments: list[str] | tuple[str, ...]) -> CommandResult:
        del self
        command = tuple(arguments)
        calls.append(command)
        if command[0] == "sbatch":
            return CommandResult(stdout="24012;training\n", stderr="")
        if command[0] == "scancel":
            return CommandResult(stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command[0]}")

    monkeypatch.setattr(
        "app.services.job_catalog.resolve_effective_unix_username",
        lambda: "demo-user",
    )
    monkeypatch.setattr(
        "app.services.job_catalog.build_slurm_adapter",
        lambda settings: NativeControlAdapter(),
    )
    monkeypatch.setattr("app.slurm.runner.SubprocessCommandRunner.run", fake_run)
    settings = Settings(
        _env_file=None,
        slurm_data_source="native",
        dashboard_owner="demo-user",
        native_submission_enabled=False,
        native_cancel_enabled=True,
        native_clone_enabled=True,
        native_max_active_jobs=2,
        database_url=database_url,
        job_workspace_directory=workspace,
    )
    return TestClient(create_app(settings)), calls


def test_native_cancel_and_clone_are_owner_scoped_idempotent_and_audited(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, calls = build_native_control_client(tmp_path, monkeypatch)

    runtime = client.get("/api/runtime").json()
    cancel_missing = client.post("/api/jobs/slurm-24011/cancel")
    cancelled = client.post(
        "/api/jobs/slurm-24011/cancel",
        headers={"Idempotency-Key": "cancel-source-safe-0001"},
    )
    cancel_replay = client.post(
        "/api/jobs/slurm-24011/cancel",
        headers={"Idempotency-Key": "cancel-source-safe-0001"},
    )
    clone_missing = client.post("/api/jobs/slurm-24011/clone")
    cloned = client.post(
        "/api/jobs/slurm-24011/clone",
        headers={"Idempotency-Key": "clone-source-safe-0001"},
    )
    clone_replay = client.post(
        "/api/jobs/slurm-24011/clone",
        headers={"Idempotency-Key": "clone-source-safe-0001"},
    )
    clone_cancelled = client.post(
        "/api/jobs/slurm-24012/cancel",
        headers={"Idempotency-Key": "cancel-clone-safe-0001"},
    )

    assert runtime["read_only"] is False
    assert runtime["capabilities"]["submit"] is False
    assert runtime["capabilities"]["cancel"] is True
    assert runtime["capabilities"]["clone"] is True
    assert cancel_missing.status_code == 400
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"
    assert cancel_replay.json() == cancelled.json()
    assert clone_missing.status_code == 400
    assert cloned.status_code == 201
    assert cloned.json()["slurm_job_id"] == "24012"
    assert clone_replay.json() == cloned.json()
    assert clone_cancelled.status_code == 200
    assert clone_cancelled.json()["state"] == "CANCELLED"
    assert [call[0] for call in calls].count("sbatch") == 1
    assert [call[0] for call in calls].count("scancel") == 2
    assert ("scancel", "24011") in calls
    assert ("scancel", "24012") in calls

    events = SubmissionRepository(
        f"sqlite:///{tmp_path / 'dashboard.sqlite3'}"
    ).list_events(owner="demo-user")
    result_codes = [event.result_code for event in events]
    assert result_codes.count("SCANCEL_ACCEPTED") == 2
    assert "SBATCH_ACCEPTED" in result_codes


def test_native_control_hides_jobs_without_owner_metadata(tmp_path: Path, monkeypatch) -> None:
    client, calls = build_native_control_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/jobs/slurm-99999/cancel",
        headers={"Idempotency-Key": "cancel-foreign-safe-0001"},
    )

    assert response.status_code == 404
    assert calls == []
