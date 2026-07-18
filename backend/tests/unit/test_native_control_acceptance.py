from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run-native-control-acceptance.py"


def load_acceptance_module():
    spec = spec_from_file_location("native_control_acceptance", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_control_acceptance_requires_exact_confirmation() -> None:
    module = load_acceptance_module()
    with pytest.raises(PermissionError):
        module.require_confirmation("yes")
    module.require_confirmation(module.CONFIRMATION)


def test_control_acceptance_requires_all_temporary_write_gates() -> None:
    module = load_acceptance_module()
    module.validate_settings(
        Settings(
            _env_file=None,
            slurm_data_source="native",
            native_submission_enabled=True,
            native_cancel_enabled=True,
            native_clone_enabled=True,
            native_max_active_jobs=2,
        )
    )
    with pytest.raises(RuntimeError, match="submit, cancel, and clone"):
        module.validate_settings(
            Settings(
                _env_file=None,
                slurm_data_source="native",
                native_submission_enabled=True,
                native_cancel_enabled=True,
                native_clone_enabled=False,
                native_max_active_jobs=2,
            )
        )
