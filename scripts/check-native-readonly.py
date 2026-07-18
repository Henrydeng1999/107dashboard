#!/usr/bin/env python3
"""Read-only 107 acceptance check; never submits, cancels, or reads logs."""

import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def require_success(response: object, label: str) -> dict[str, object]:
    status_code = getattr(response, "status_code", None)
    if status_code != 200:
        raise RuntimeError(f"{label} failed with HTTP {status_code}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned an unexpected payload")
    return payload


def main() -> int:
    settings = get_settings()
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native for this acceptance check")

    client = TestClient(app)
    runtime = require_success(client.get("/api/runtime"), "runtime check")
    if runtime.get("data_source") != "native" or runtime.get("read_only") is not True:
        raise RuntimeError("backend did not start in Native read-only mode")

    jobs = require_success(client.get("/api/jobs", params={"page_size": 100}), "job list")
    items = jobs.get("items")
    if not isinstance(items, list):
        raise RuntimeError("job list did not contain an items array")
    if any(job.get("owner") != settings.dashboard_owner for job in items):
        raise RuntimeError("job list contained a record outside the trusted owner")

    evidence: dict[str, object] = {
        "mode": "native-read-only",
        "owner_check": "passed",
        "total_jobs": jobs.get("total", 0),
        "sample": None,
    }
    if items:
        sample = items[0]
        job_id = sample.get("id")
        if not isinstance(job_id, str):
            raise RuntimeError("sample job did not contain a dashboard ID")
        detail = require_success(client.get(f"/api/jobs/{job_id}"), "job detail")
        usage = require_success(client.get(f"/api/jobs/{job_id}/usage"), "job usage")
        evidence["sample"] = {
            "dashboard_job_id": job_id,
            "slurm_job_id": detail.get("slurm_job_id"),
            "state": detail.get("state"),
            "exit_code": detail.get("exit_code"),
            "usage_fields_present": {
                "elapsed_seconds": usage.get("elapsed_seconds") is not None,
                "max_rss_kb": usage.get("max_rss_kb") is not None,
                "total_cpu_seconds": usage.get("total_cpu_seconds") is not None,
            },
        }

    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
