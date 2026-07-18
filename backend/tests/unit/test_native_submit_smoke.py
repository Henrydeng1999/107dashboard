from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.core.config import Settings
from app.slurm.runner import CommandResult

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "submit-native-smoke-test.py"


def load_smoke_module():
    spec = spec_from_file_location("native_submit_smoke", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_minimal_request_is_fixed() -> None:
    request = load_smoke_module().build_minimal_request()
    assert request.command == "python3 --version"
    assert request.resources.model_dump() == {
        "cpus": 1,
        "memory_mb": 512,
        "gpus": 0,
        "time_limit_minutes": 1,
    }


def test_exact_confirmation_is_required() -> None:
    module = load_smoke_module()
    with pytest.raises(PermissionError):
        module.require_confirmation("yes")
    module.require_confirmation(module.CONFIRMATION)


def test_prior_receipt_prevents_repeat_submission(tmp_path: Path) -> None:
    module = load_smoke_module()
    receipt = tmp_path / ("submission-" + "1" * 32) / "slurm-job-id"
    receipt.parent.mkdir()
    receipt.write_text("21484\n", encoding="ascii")
    with pytest.raises(RuntimeError, match="refusing a repeat"):
        module.ensure_no_prior_receipt(tmp_path)


def test_execution_uses_exact_sbatch_plan_and_persists_evidence(tmp_path: Path) -> None:
    module = load_smoke_module()

    class FakeRunner:
        arguments: tuple[str, ...] | None = None

        def run(self, arguments: tuple[str, ...]) -> CommandResult:
            self.arguments = tuple(arguments)
            return CommandResult(stdout="21484;training\n", stderr="")

    runner = FakeRunner()
    settings = Settings(
        slurm_data_source="native",
        dashboard_owner="pb24030760",
        database_url=f"sqlite:///{tmp_path / 'dashboard.sqlite3'}",
        job_workspace_directory=tmp_path / "jobs",
    )
    evidence = module.execute_minimal_submission(
        settings,
        owner="pb24030760",
        runner=runner,
    )
    assert runner.arguments is not None
    assert runner.arguments[:2] == ("sbatch", "--parsable")
    assert "--cpus-per-task=1" in runner.arguments
    assert "--mem=512M" in runner.arguments
    assert "--time=1" in runner.arguments
    assert not any(argument.startswith("--gres=") for argument in runner.arguments)
    assert evidence["slurm_job_id"] == "21484"
    assert evidence["audit_statuses"] == ["PREPARED", "SUCCEEDED"]
    assert evidence["http_submission_enabled"] is False
