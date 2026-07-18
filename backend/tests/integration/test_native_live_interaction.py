from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.slurm import SlurmJob, SlurmResources, SlurmUsageRecord
from app.slurm.runner import CommandResult

PROJECT_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run-native-live-interaction.py"


def load_script():
    spec = spec_from_file_location("run_native_live_interaction", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InteractiveNativeAdapter:
    def __init__(self) -> None:
        self.jobs: dict[str, SlurmJob] = {}

    def list_queue(self, user: str) -> list[SlurmJob]:
        return [
            job
            for job in self.jobs.values()
            if job.user == user and job.state in {"PENDING", "RUNNING"}
        ]

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return [
            job
            for job in self.jobs.values()
            if job.user == user and job.state not in {"PENDING", "RUNNING"}
        ]

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[SlurmUsageRecord]:
        if job_id != "25001":
            return []
        resources = SlurmResources(cpus=1, memory_mb=512, gpus=0)
        return [
            SlurmUsageRecord(
                job_id=job_id,
                requested=resources,
                allocated=resources,
                elapsed_seconds=0,
                time_limit_seconds=60,
                total_cpu_seconds=0.02,
            ),
            SlurmUsageRecord(job_id=f"{job_id}.batch", max_rss_kb=300),
        ]


def test_full_native_http_interaction_is_owner_scoped_persisted_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = load_script()
    adapter = InteractiveNativeAdapter()
    calls: list[tuple[str, ...]] = []
    next_job_id = iter(("25001", "25002", "25003"))

    def fake_run(self: object, arguments: list[str] | tuple[str, ...]) -> CommandResult:
        del self
        command = tuple(arguments)
        calls.append(command)
        if command[0] == "sbatch":
            job_id = next(next_job_id)
            name = next(value.removeprefix("--job-name=") for value in command if value.startswith("--job-name="))
            is_completion = name == "dashboard-live-completion"
            resources = SlurmResources(cpus=1, memory_mb=512, gpus=0)
            adapter.jobs[job_id] = SlurmJob(
                job_id=job_id,
                user="demo-user",
                name=name,
                state="COMPLETED" if is_completion else "RUNNING",
                partition="Students",
                account="stu",
                qos="qos_stu_default",
                exit_code="0:0" if is_completion else None,
                requested=resources,
                allocated=resources,
                time_limit="00:01:00" if is_completion else "00:02:00",
                elapsed="00:00:00",
            )
            if is_completion:
                stdout_path = Path(
                    next(value.removeprefix("--output=") for value in command if value.startswith("--output="))
                )
                stderr_path = Path(
                    next(value.removeprefix("--error=") for value in command if value.startswith("--error="))
                )
                stdout_path.write_text("Python 3.12.3\n", encoding="utf-8")
                stderr_path.write_text("", encoding="utf-8")
            return CommandResult(stdout=f"{job_id};training\n", stderr="")
        if command[0] == "scancel":
            job_id = command[1]
            current = adapter.jobs[job_id]
            adapter.jobs[job_id] = SlurmJob(
                job_id=current.job_id,
                user=current.user,
                name=current.name,
                state="CANCELLED",
                partition=current.partition,
                account=current.account,
                qos=current.qos,
                exit_code="0:0",
                requested=current.requested,
                allocated=current.allocated,
                time_limit=current.time_limit,
                elapsed="00:00:00",
            )
            return CommandResult(stdout="", stderr="")
        raise AssertionError(f"unexpected command: {command[0]}")

    monkeypatch.setattr(
        "app.services.job_catalog.resolve_effective_unix_username",
        lambda: "demo-user",
    )
    monkeypatch.setattr(
        "app.services.job_catalog.build_slurm_adapter",
        lambda settings: adapter,
    )
    monkeypatch.setattr("app.slurm.runner.SubprocessCommandRunner.run", fake_run)
    settings = Settings(
        _env_file=None,
        slurm_data_source="native",
        dashboard_owner="demo-user",
        database_url=f"sqlite:///{tmp_path / 'dashboard.sqlite3'}",
        job_workspace_directory=tmp_path / "jobs",
        native_submission_enabled=True,
        native_logs_enabled=True,
        native_cancel_enabled=True,
        native_clone_enabled=True,
        native_max_active_jobs=2,
        slurm_query_cache_ttl_seconds=0.1,
    )

    with TestClient(create_app(settings)) as client:
        evidence = script.execute_interaction(
            client,
            owner="demo-user",
            timeout_seconds=10,
            pause=lambda seconds: None,
        )
    persistence = script._audit_evidence(settings, "demo-user", evidence)

    assert evidence["passed"] is True
    assert evidence["completion_job"]["state"] == "COMPLETED"
    assert evidence["completion_job"]["stdout_bytes"] == 14
    assert evidence["completion_job"]["logs_content_redacted"] is True
    assert evidence["control_job"]["cancelled"] is True
    assert evidence["clone_job"]["cancelled"] is True
    assert evidence["raw_log_content_emitted"] is False
    assert persistence["idempotency_records_succeeded"] == 5
    assert persistence["audit_chain_present"] is True
    assert [call[0] for call in calls].count("sbatch") == 3
    assert [call[0] for call in calls].count("scancel") == 2


def test_live_interaction_requires_all_gates_and_one_time_receipt(tmp_path: Path) -> None:
    script = load_script()
    with pytest.raises(PermissionError):
        script.require_confirmation("yes")
    script.require_confirmation(script.CONFIRMATION)

    with pytest.raises(RuntimeError, match="submit, logs, cancel, and clone"):
        script.validate_settings(
            Settings(
                _env_file=None,
                slurm_data_source="native",
                native_submission_enabled=True,
                native_logs_enabled=False,
                native_cancel_enabled=True,
                native_clone_enabled=True,
                native_max_active_jobs=2,
            )
        )

    receipt = tmp_path / script.RECEIPT_NAME
    script.ensure_first_run(receipt)
    receipt.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already"):
        script.ensure_first_run(receipt)
