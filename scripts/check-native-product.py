#!/usr/bin/env python3
"""Verify that the deployed product is real Native, interactive, and free of Fixture data."""

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import shutil
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.main import create_app  # noqa: E402

REQUIRED_COMMANDS = ("sbatch", "scancel", "squeue", "sacct")
REQUIRED_CAPABILITIES = ("submit", "logs", "cancel", "clone")
PRODUCT_BUILD = "native-basic-v1"


def validate_product_settings(settings: Settings) -> dict[str, object]:
    if settings.slurm_data_source != "native":
        raise RuntimeError("product must use the Native Slurm data source")
    if settings.demo_fallback_enabled:
        raise RuntimeError("Fixture fallback must be disabled for the real product")
    if not settings.serve_frontend:
        raise RuntimeError("product must serve the built frontend")
    if not all(
        (
            settings.native_submission_enabled,
            settings.native_logs_enabled,
            settings.native_cancel_enabled,
            settings.native_clone_enabled,
        )
    ):
        raise RuntimeError("submit, logs, cancel, and clone must all be enabled")
    if settings.app_host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("product must listen on a loopback address")

    frontend_index = settings.frontend_dist_directory / "index.html"
    frontend_assets = settings.frontend_dist_directory / "assets"
    frontend_manifest = settings.frontend_dist_directory / "product-manifest.json"
    if not frontend_index.is_file() or not frontend_assets.is_dir():
        raise RuntimeError("built frontend index and assets are required")
    if not any(path.suffix == ".js" for path in frontend_assets.iterdir()):
        raise RuntimeError("built frontend JavaScript asset is missing")
    try:
        manifest = json.loads(frontend_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("built frontend product manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("product_build") != PRODUCT_BUILD:
        raise RuntimeError("built frontend is not the current Native basic product")

    missing_commands = [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]
    if missing_commands:
        raise RuntimeError("required Slurm commands are unavailable")
    owner = assert_deployment_owner(
        settings.dashboard_owner,
        resolve_effective_unix_username(),
    )
    return {
        "owner": owner,
        "frontend_index": True,
        "frontend_assets": True,
        "product_build": PRODUCT_BUILD,
        "slurm_commands": list(REQUIRED_COMMANDS),
    }


def validate_product_payloads(
    health: dict[str, Any],
    runtime: dict[str, Any],
    jobs: dict[str, Any],
    summary: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, object]:
    capabilities = runtime.get("capabilities")
    if health.get("status") != "ok":
        raise RuntimeError("product health check failed")
    if (
        runtime.get("data_source") != "native"
        or runtime.get("serving_source") != "native"
        or runtime.get("degraded") is not False
        or runtime.get("demo_fallback_enabled") is not False
        or not isinstance(capabilities, dict)
        or not all(capabilities.get(name) is True for name in REQUIRED_CAPABILITIES)
    ):
        raise RuntimeError("product runtime is not a full real Native service")
    if jobs.get("total") != summary.get("total_jobs"):
        raise RuntimeError("job list and summary disagree")
    if manifest.get("product_build") != PRODUCT_BUILD:
        raise RuntimeError("deployed frontend is not the current Native basic product")
    items = jobs.get("items")
    if not isinstance(items, list):
        raise RuntimeError("product jobs response is invalid")
    if any(not isinstance(item, dict) or not str(item.get("id", "")).startswith("slurm-") for item in items):
        raise RuntimeError("non-Native job appeared in the product list")
    return {
        "serving_source": "native",
        "fixture_influence": False,
        "visible_jobs": jobs.get("total"),
        "summary_jobs": summary.get("total_jobs"),
        "capabilities": {name: True for name in REQUIRED_CAPABILITIES},
        "product_build": PRODUCT_BUILD,
    }


def _get_json(base_url: str, path: str) -> dict[str, Any]:
    try:
        with urlopen(f"{base_url.rstrip('/')}{path}", timeout=10) as response:  # noqa: S310
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("deployed product HTTP check failed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("deployed product returned an invalid response")
    return payload


def check_with_client(client: TestClient) -> dict[str, object]:
    health = client.get("/api/health").json()
    runtime = client.get("/api/runtime").json()
    jobs = client.get("/api/jobs", params={"page": 1, "page_size": 100}).json()
    summary = client.get("/api/jobs/summary").json()
    manifest = client.get("/product-manifest.json").json()
    return validate_product_payloads(health, runtime, jobs, summary, manifest)


def check_live_service(base_url: str) -> dict[str, object]:
    return validate_product_payloads(
        _get_json(base_url, "/api/health"),
        _get_json(base_url, "/api/runtime"),
        _get_json(base_url, "/api/jobs?page=1&page_size=100"),
        _get_json(base_url, "/api/jobs/summary"),
        _get_json(base_url, "/product-manifest.json"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Check an already running service instead of in-process API")
    arguments = parser.parse_args(argv)
    settings = Settings()
    configuration = validate_product_settings(settings)
    if arguments.base_url:
        product = check_live_service(arguments.base_url)
    else:
        with TestClient(create_app(settings)) as client:
            product = check_with_client(client)
    print(
        json.dumps(
            {
                "mode": "native-product-readiness",
                "passed": True,
                "configuration": configuration,
                "product": product,
                "would_invoke_sbatch": False,
                "would_invoke_scancel": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
