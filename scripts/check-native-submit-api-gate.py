#!/usr/bin/env python3
"""Verify the Native HTTP submission gate without calling sbatch."""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402


def main() -> int:
    settings = get_settings()
    if settings.slurm_data_source != "native" or not settings.native_submission_enabled:
        raise RuntimeError("Native submission must be explicitly enabled for this gate check")

    client = TestClient(app)
    runtime = client.get("/api/runtime")
    missing_key = client.post(
        "/api/jobs",
        json={
            "name": "dashboard-gate-check",
            "command": "python3 --version",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 1,
                "memory_mb": 512,
                "gpus": 0,
                "time_limit_minutes": 1,
            },
        },
    )
    invalid_command = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "api-gate-invalid-command-0001"},
        json={
            "name": "dashboard-gate-check",
            "command": "python train.py;whoami",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 1,
                "memory_mb": 512,
                "gpus": 0,
                "time_limit_minutes": 1,
            },
        },
    )
    runtime_payload = runtime.json()
    passed = (
        runtime.status_code == 200
        and runtime_payload.get("data_source") == "native"
        and runtime_payload.get("read_only") is False
        and runtime_payload.get("capabilities", {}).get("submit") is True
        and missing_key.status_code == 400
        and missing_key.json().get("error", {}).get("code") == "IDEMPOTENCY_KEY_REQUIRED"
        and invalid_command.status_code == 422
        and invalid_command.json().get("error", {}).get("code") == "INVALID_REQUEST"
    )
    evidence = {
        "mode": "native-submit-api-gate-no-sbatch",
        "passed": passed,
        "runtime_submit": runtime_payload.get("capabilities", {}).get("submit"),
        "missing_key_status": missing_key.status_code,
        "invalid_command_status": invalid_command.status_code,
        "would_invoke_sbatch": False,
        "http_cancel_enabled": runtime_payload.get("capabilities", {}).get("cancel"),
        "http_clone_enabled": runtime_payload.get("capabilities", {}).get("clone"),
        "http_logs_enabled": runtime_payload.get("capabilities", {}).get("logs"),
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
