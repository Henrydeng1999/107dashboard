from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build-release.py"


def _load_script():
    spec = spec_from_file_location("build_release", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_release_file_normalizes_shell_line_endings(tmp_path: Path) -> None:
    script = _load_script()
    source = tmp_path / "service.sh"
    target = tmp_path / "release" / "service.sh"
    source.write_bytes(b"#!/usr/bin/env bash\r\nset -euo pipefail\r\n")
    target.parent.mkdir()

    script.copy_release_file(source, target)

    assert target.read_bytes() == b"#!/usr/bin/env bash\nset -euo pipefail\n"


def test_copy_release_file_preserves_non_shell_bytes(tmp_path: Path) -> None:
    script = _load_script()
    source = tmp_path / "config.txt"
    target = tmp_path / "release" / "config.txt"
    source_bytes = b"line one\r\nline two\x00\r"
    source.write_bytes(source_bytes)
    target.parent.mkdir()

    script.copy_release_file(source, target)

    assert target.read_bytes() == source_bytes


def test_validate_shell_line_endings_rejects_carriage_returns(tmp_path: Path) -> None:
    script = _load_script()
    shell_file = tmp_path / "nested" / "service.sh"
    shell_file.parent.mkdir()
    shell_file.write_bytes(b"#!/usr/bin/env bash\nset -euo pipefail\r\n")

    try:
        script.validate_shell_line_endings(tmp_path)
    except RuntimeError as error:
        assert "nested/service.sh" in str(error)
    else:
        raise AssertionError("expected CRLF shell script to be rejected")


def test_windows_client_only_sources_are_marked_for_exclusion() -> None:
    script = _load_script()

    assert Path("scripts/build-windows-client.py") in script.CLIENT_ONLY_PATHS
    assert Path("backend/tests/unit/test_build_windows_client.py") in script.CLIENT_ONLY_PATHS
