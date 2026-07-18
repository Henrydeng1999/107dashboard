#!/usr/bin/env python3
from pathlib import Path
import json
import sys
from typing import Any

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.demo_fallback import DemoFallbackJobCatalog  # noqa: E402
from app.services.job_catalog import JobCatalog  # noqa: E402
from app.slurm import FixtureSlurmAdapter, SlurmCommandFailed, SlurmJob  # noqa: E402


class UnavailableNativeAdapter:
    def list_queue(self, user: str) -> list[SlurmJob]:
        raise SlurmCommandFailed(("squeue", f"--user={user}"), 1, "simulated failure")

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return []

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[object]:
        return []


def _payload(response: Any, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise RuntimeError(f"{label} returned HTTP {response.status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} did not return an object")
    return payload


def _check_native(settings: Settings) -> dict[str, Any]:
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native")
    if not settings.demo_fallback_enabled:
        raise RuntimeError("DEMO_FALLBACK_ENABLED must be true")
    if any(
        (
            settings.native_submission_enabled,
            settings.native_cancel_enabled,
            settings.native_clone_enabled,
            settings.native_logs_enabled,
        )
    ):
        raise RuntimeError("all Native write and log switches must remain false")

    client = TestClient(create_app(settings))
    jobs = _payload(client.get("/api/jobs", params={"page": 1, "page_size": 5}), "jobs")
    summary = _payload(client.get("/api/jobs/summary"), "summary")
    runtime = _payload(client.get("/api/runtime"), "runtime")
    if runtime.get("serving_source") != "native" or runtime.get("degraded") is not False:
        raise RuntimeError("Native read path is degraded; inspect Slurm before release")
    return {
        "serving_source": runtime.get("serving_source"),
        "visible_jobs": jobs.get("total"),
        "summary_jobs": summary.get("total_jobs"),
        "sample_job_id": (
            jobs["items"][0].get("slurm_job_id") if jobs.get("items") else None
        ),
    }


def _check_fallback(settings: Settings) -> dict[str, Any]:
    primary = JobCatalog(UnavailableNativeAdapter(), settings.dashboard_owner)
    fallback = JobCatalog(
        FixtureSlurmAdapter(settings.slurm_fixture_directory),
        settings.demo_fallback_owner,
        allow_fixture_submissions=False,
        fixture_job_output_directory=settings.fixture_job_output_directory,
    )
    catalog = DemoFallbackJobCatalog(primary, fallback, cooldown_seconds=30)
    safe_settings = settings.model_copy(
        update={
            "native_submission_enabled": True,
            "native_cancel_enabled": True,
            "native_clone_enabled": True,
        }
    )
    client = TestClient(create_app(safe_settings, job_catalog=catalog))
    jobs = _payload(client.get("/api/jobs"), "fallback jobs")
    runtime = _payload(client.get("/api/runtime"), "fallback runtime")
    write = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "release-fallback-no-write"},
        json={
            "name": "must-not-submit",
            "command": "python3 --version",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {"cpus": 1, "memory_mb": 512, "gpus": 0, "time_limit_minutes": 1},
        },
    )
    capabilities = runtime.get("capabilities", {})
    passed = (
        runtime.get("serving_source") == "fixture_fallback"
        and runtime.get("degraded") is True
        and jobs.get("total", 0) > 0
        and capabilities.get("submit") is False
        and capabilities.get("cancel") is False
        and capabilities.get("clone") is False
        and write.status_code == 503
    )
    if not passed:
        raise RuntimeError("simulated fallback did not fail closed")
    return {
        "serving_source": runtime.get("serving_source"),
        "fixture_jobs": jobs.get("total"),
        "write_status": write.status_code,
        "would_invoke_sbatch": False,
    }


def main() -> int:
    settings = Settings()
    native = _check_native(settings)
    fallback = _check_fallback(settings)
    print(
        json.dumps(
            {
                "mode": "demo-release-readiness-no-write",
                "passed": True,
                "owner": settings.dashboard_owner,
                "native": native,
                "fallback": fallback,
                "http_submission_enabled": settings.native_submission_enabled,
                "http_cancel_enabled": settings.native_cancel_enabled,
                "http_clone_enabled": settings.native_clone_enabled,
                "http_logs_enabled": settings.native_logs_enabled,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
