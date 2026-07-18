from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check-native-submit-preflight.py"


def load_preflight_module():
    spec = spec_from_file_location("native_submit_preflight", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_database_uses_its_parent_directory(tmp_path: Path) -> None:
    module = load_preflight_module()
    database_path = tmp_path / "dashboard.sqlite3"
    database_path.touch()

    database_parent = module.nearest_existing_parent(database_path.parent)

    assert database_parent == tmp_path.resolve()
