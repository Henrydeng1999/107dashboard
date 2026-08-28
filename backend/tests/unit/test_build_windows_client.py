import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build-windows-client.py"


def _load_script():
    spec = spec_from_file_location("build_windows_client", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_portable_bundle_contains_executable_data_and_metadata(tmp_path: Path) -> None:
    script = _load_script()
    executable = tmp_path / "107Dashboard.exe"
    output_path = tmp_path / "107Dashboard-Windows-x64-0.1.0-abcdef12.zip"
    executable.write_bytes(b"portable-test-executable")

    script.build_portable_bundle(executable, output_path, "0.1.0", "abcdef1234567890")

    with ZipFile(output_path) as archive:
        assert archive.namelist() == [
            "107Dashboard-Windows-x64-0.1.0-abcdef12/107Dashboard.exe",
            "107Dashboard-Windows-x64-0.1.0-abcdef12/data/",
            "107Dashboard-Windows-x64-0.1.0-abcdef12/version.json",
            "107Dashboard-Windows-x64-0.1.0-abcdef12/README.txt",
        ]
        assert archive.read(
            "107Dashboard-Windows-x64-0.1.0-abcdef12/107Dashboard.exe"
        ) == b"portable-test-executable"
        metadata = json.loads(
            archive.read("107Dashboard-Windows-x64-0.1.0-abcdef12/version.json")
        )

    assert metadata == {
        "product": "107 Dashboard",
        "version": "0.1.0",
        "commit": "abcdef1234567890",
        "architecture": "win-x64",
        "portable_data_directory": "data",
    }


def test_build_script_disables_and_cleans_persistent_dotnet_servers() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert '"--disable-build-servers"' in source
    assert '"build-server", "shutdown"' in source


def test_frontend_release_entry_uses_native_shell_per_platform() -> None:
    package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    powershell_script = (PROJECT_ROOT / "scripts" / "build-107-frontend.ps1").read_text(encoding="utf-8")
    bash_script = (PROJECT_ROOT / "scripts" / "build-107-frontend.sh").read_text(encoding="utf-8")

    assert package["scripts"]["build:107"] == "node ../scripts/build-107-frontend.mjs"
    assert package["scripts"]["build:107:windows"].startswith("pwsh ")
    assert package["scripts"]["build:107:linux"] == "bash ../scripts/build-107-frontend.sh"
    assert "Remove-Item" in powershell_script
    assert "Move-Item" in powershell_script
    assert "bash" not in powershell_script.lower()
    assert "rm -rf" in bash_script
