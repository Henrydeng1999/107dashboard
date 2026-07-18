from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check-demo-release.py"


def _load_script():
    spec = spec_from_file_location("check_demo_release", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simulated_release_fallback_never_invokes_native_write() -> None:
    script = _load_script()
    settings = Settings(
        _env_file=None,
        slurm_data_source="native",
        dashboard_owner="demo-user",
        demo_fallback_enabled=True,
    )

    result = script._check_fallback(settings)

    assert result == {
        "serving_source": "fixture_fallback",
        "fixture_jobs": 5,
        "write_status": 503,
        "would_invoke_sbatch": False,
    }
