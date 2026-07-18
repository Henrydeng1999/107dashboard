from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "check-native-product.py"


def load_script():
    spec = spec_from_file_location("check_native_product", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def product_settings(tmp_path: Path, **overrides: object) -> Settings:
    frontend = tmp_path / "dist"
    assets = frontend / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (frontend / "index.html").write_text("<script src='/assets/app.js'></script>", encoding="utf-8")
    (assets / "app.js").write_text("", encoding="utf-8")
    (frontend / "product-manifest.json").write_text(
        '{"product_build":"native-basic-v1","data_policy":"native-only"}',
        encoding="utf-8",
    )
    values = {
        "_env_file": None,
        "slurm_data_source": "native",
        "dashboard_owner": "demo-user",
        "serve_frontend": True,
        "frontend_dist_directory": frontend,
        "native_submission_enabled": True,
        "native_logs_enabled": True,
        "native_cancel_enabled": True,
        "native_clone_enabled": True,
        "demo_fallback_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def test_product_settings_require_real_native_without_fixture_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = load_script()
    monkeypatch.setattr(script, "resolve_effective_unix_username", lambda: "demo-user")
    monkeypatch.setattr(script.shutil, "which", lambda command: f"/usr/bin/{command}")

    result = script.validate_product_settings(product_settings(tmp_path))

    assert result["owner"] == "demo-user"
    with pytest.raises(RuntimeError, match="Fixture fallback"):
        script.validate_product_settings(product_settings(tmp_path, demo_fallback_enabled=True))
    stale_settings = product_settings(tmp_path)
    (tmp_path / "dist" / "product-manifest.json").write_text(
        '{"product_build":"stale-build"}', encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="current Native basic product"):
        script.validate_product_settings(stale_settings)


def test_product_payloads_reject_fixture_or_non_native_jobs() -> None:
    script = load_script()
    health = {"status": "ok"}
    runtime = {
        "data_source": "native",
        "serving_source": "native",
        "degraded": False,
        "demo_fallback_enabled": False,
        "capabilities": {"submit": True, "logs": True, "cancel": True, "clone": True},
    }
    summary = {"total_jobs": 1}
    manifest = {"product_build": "native-basic-v1", "data_policy": "native-only"}

    result = script.validate_product_payloads(
        health,
        runtime,
        {"total": 1, "items": [{"id": "slurm-123"}]},
        summary,
        manifest,
    )
    assert result["fixture_influence"] is False

    with pytest.raises(RuntimeError, match="non-Native"):
        script.validate_product_payloads(
            health,
            runtime,
            {"total": 1, "items": [{"id": "fixture-123"}]},
            summary,
            manifest,
        )
