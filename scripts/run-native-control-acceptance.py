#!/usr/bin/env python3
"""Run one bounded Native submit, cancel, clone, and cleanup acceptance flow."""

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.main import create_app  # noqa: E402

CONFIRMATION = "RUN-ONE-NATIVE-CONTROL-ACCEPTANCE"
SOURCE_KEY = "native-control-acceptance-source-v1"
CANCEL_SOURCE_KEY = "native-control-acceptance-cancel-source-v1"
CLONE_KEY = "native-control-acceptance-clone-v1"
CANCEL_CLONE_KEY = "native-control-acceptance-cancel-clone-v1"


def require_confirmation(value: str) -> None:
    if value != CONFIRMATION:
        raise PermissionError(f"confirmation must exactly equal {CONFIRMATION}")


def validate_settings(settings: Settings) -> None:
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native")
    if not (
        settings.native_submission_enabled
        and settings.native_cancel_enabled
        and settings.native_clone_enabled
    ):
        raise RuntimeError("Native submit, cancel, and clone must be explicitly enabled")
    if settings.native_max_active_jobs < 2:
        raise RuntimeError("NATIVE_MAX_ACTIVE_JOBS must be at least 2 for cleanup overlap")


def _request(client: TestClient, method: str, path: str, **kwargs: object) -> dict[str, object]:
    response = client.request(method, path, **kwargs)
    expected_status = 201 if method == "POST" and path.endswith(("/clone", "/jobs")) else 200
    if response.status_code != expected_status:
        raise RuntimeError(f"acceptance API step failed safely at {path}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("acceptance API returned an invalid response")
    return payload


def _numeric_job_id(payload: dict[str, object]) -> str:
    value = payload.get("slurm_job_id")
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise RuntimeError("acceptance API returned an invalid Slurm Job ID")
    return value


def execute_acceptance(client: TestClient, *, owner: str) -> dict[str, object]:
    runtime = _request(client, "GET", "/api/runtime")
    capabilities = runtime.get("capabilities")
    if not isinstance(capabilities, dict) or not all(
        capabilities.get(capability) is True for capability in ("submit", "cancel", "clone")
    ):
        raise RuntimeError("runtime write capabilities are not fully enabled")

    pending_cleanup: dict[str, str] = {}
    try:
        source = _request(
            client,
            "POST",
            "/api/jobs",
            headers={"Idempotency-Key": SOURCE_KEY},
            json={
                "name": "dashboard-control-acceptance",
                "command": "python3 -m timeit -n 100000000 pass",
                "partition": "Students",
                "account": "stu",
                "qos": "qos_stu_default",
                "resources": {
                    "cpus": 1,
                    "memory_mb": 512,
                    "gpus": 0,
                    "time_limit_minutes": 2,
                },
            },
        )
        source_job_id = _numeric_job_id(source)
        source_dashboard_id = str(source.get("id"))
        pending_cleanup[source_dashboard_id] = source_job_id
        cancelled_source = _request(
            client,
            "POST",
            f"/api/jobs/{source_dashboard_id}/cancel",
            headers={"Idempotency-Key": CANCEL_SOURCE_KEY},
        )
        if cancelled_source.get("state") != "CANCELLED":
            raise RuntimeError("source acceptance job was not cancelled")
        pending_cleanup.pop(source_dashboard_id)

        clone = _request(
            client,
            "POST",
            f"/api/jobs/{source_dashboard_id}/clone",
            headers={"Idempotency-Key": CLONE_KEY},
        )
        clone_job_id = _numeric_job_id(clone)
        if clone_job_id == source_job_id:
            raise RuntimeError("clone did not create a distinct Slurm job")
        clone_dashboard_id = str(clone.get("id"))
        pending_cleanup[clone_dashboard_id] = clone_job_id
        cancelled_clone = _request(
            client,
            "POST",
            f"/api/jobs/{clone_dashboard_id}/cancel",
            headers={"Idempotency-Key": CANCEL_CLONE_KEY},
        )
        if cancelled_clone.get("state") != "CANCELLED":
            raise RuntimeError("cloned acceptance job was not cancelled")
        pending_cleanup.pop(clone_dashboard_id)
    finally:
        for dashboard_id, slurm_job_id in pending_cleanup.items():
            client.post(
                f"/api/jobs/{dashboard_id}/cancel",
                headers={
                    "Idempotency-Key": f"native-control-cleanup-{slurm_job_id}-v1"
                },
            )

    return {
        "mode": "native-control-end-to-end-acceptance",
        "passed": True,
        "owner": owner,
        "source_slurm_job_id": source_job_id,
        "source_cancelled": True,
        "clone_slurm_job_id": clone_job_id,
        "clone_cancelled": True,
        "resources_per_job": {
            "cpus": 1,
            "memory_mb": 512,
            "gpus": 0,
            "time_limit_minutes": 2,
        },
        "submitted_jobs": 2,
        "cancelled_jobs": 2,
        "raw_log_content_read": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    arguments = parser.parse_args(argv)
    require_confirmation(arguments.confirm)

    settings = Settings()
    validate_settings(settings)
    owner = assert_deployment_owner(
        settings.dashboard_owner,
        resolve_effective_unix_username(),
    )
    with TestClient(create_app(settings)) as client:
        evidence = execute_acceptance(client, owner=owner)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
