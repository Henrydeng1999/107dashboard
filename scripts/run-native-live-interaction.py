#!/usr/bin/env python3
"""Run one bounded Native HTTP submit, observe, log, usage, cancel, and clone flow."""

import argparse
from collections.abc import Callable, Sequence
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from time import monotonic, sleep

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.main import create_app  # noqa: E402
from app.repositories.job_control import JobControlRepository  # noqa: E402
from app.repositories.submission import SubmissionRepository  # noqa: E402

CONFIRMATION = "RUN-NATIVE-LIVE-INTERACTION-V1"
RECEIPT_NAME = ".native-live-interaction-v1.json"
COMPLETION_KEY = "native-live-completion-v1"
CONTROL_KEY = "native-live-control-v1"
CANCEL_CONTROL_KEY = "native-live-cancel-control-v1"
CLONE_KEY = "native-live-clone-v1"
CANCEL_CLONE_KEY = "native-live-cancel-clone-v1"
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}
ACTIVE_STATES = {"PENDING", "RUNNING"}


def require_confirmation(value: str) -> None:
    if value != CONFIRMATION:
        raise PermissionError(f"confirmation must exactly equal {CONFIRMATION}")


def validate_settings(settings: Settings) -> None:
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native")
    capabilities = (
        settings.native_submission_enabled,
        settings.native_logs_enabled,
        settings.native_cancel_enabled,
        settings.native_clone_enabled,
    )
    if not all(capabilities):
        raise RuntimeError("Native submit, logs, cancel, and clone must be explicitly enabled")
    if settings.native_max_active_jobs < 2:
        raise RuntimeError("NATIVE_MAX_ACTIVE_JOBS must be at least 2")


def ensure_first_run(receipt_path: Path) -> None:
    if receipt_path.exists():
        raise RuntimeError("Native live interaction V1 already has a completion receipt")


def _request(
    client: TestClient,
    method: str,
    path: str,
    *,
    expected_status: int = 200,
    **kwargs: object,
) -> dict[str, object]:
    response = client.request(method, path, **kwargs)
    if response.status_code != expected_status:
        raise RuntimeError(f"Native live interaction failed safely at {path}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Native live interaction API returned an invalid response")
    return payload


def _job_identity(payload: dict[str, object], owner: str) -> tuple[str, str]:
    dashboard_id = payload.get("id")
    slurm_job_id = payload.get("slurm_job_id")
    if (
        not isinstance(dashboard_id, str)
        or not isinstance(slurm_job_id, str)
        or dashboard_id != f"slurm-{slurm_job_id}"
        or re.fullmatch(r"[1-9][0-9]*", slurm_job_id) is None
        or payload.get("owner") != owner
    ):
        raise RuntimeError("Native live interaction returned an invalid owner-scoped Job ID")
    return dashboard_id, slurm_job_id


def _wait_for_state(
    client: TestClient,
    dashboard_id: str,
    accepted_states: set[str],
    *,
    timeout_seconds: float,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> dict[str, object]:
    deadline = clock() + timeout_seconds
    while True:
        job = _request(client, "GET", f"/api/jobs/{dashboard_id}")
        if job.get("state") in accepted_states:
            return job
        if clock() >= deadline:
            raise RuntimeError("Native job did not reach the expected state before timeout")
        pause(1.0)


def _wait_for_log(
    client: TestClient,
    dashboard_id: str,
    stream: str,
    *,
    require_content: bool,
    timeout_seconds: float,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> dict[str, object]:
    deadline = clock() + timeout_seconds
    while True:
        log = _request(
            client,
            "GET",
            f"/api/jobs/{dashboard_id}/logs",
            params={"stream": stream, "offset": 0, "limit": 4096},
        )
        content = log.get("content")
        available = log.get("available") is True
        if available and isinstance(content, str) and (content or not require_content):
            return log
        if clock() >= deadline:
            raise RuntimeError("Native job log did not become available before timeout")
        pause(1.0)


def _wait_for_usage(
    client: TestClient,
    dashboard_id: str,
    *,
    timeout_seconds: float,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> dict[str, object]:
    deadline = clock() + timeout_seconds
    while True:
        usage = _request(client, "GET", f"/api/jobs/{dashboard_id}/usage")
        requested = usage.get("requested")
        if (
            isinstance(requested, dict)
            and requested.get("cpus") == 1
            and requested.get("memory_mb") == 512
        ):
            return usage
        if clock() >= deadline:
            raise RuntimeError("Native usage did not become available before timeout")
        pause(1.0)


def _submission(name: str, command: str, minutes: int) -> dict[str, object]:
    return {
        "name": name,
        "command": command,
        "partition": "Students",
        "account": "stu",
        "qos": "qos_stu_default",
        "resources": {
            "cpus": 1,
            "memory_mb": 512,
            "gpus": 0,
            "time_limit_minutes": minutes,
        },
    }


def execute_interaction(
    client: TestClient,
    *,
    owner: str,
    timeout_seconds: float = 90.0,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> dict[str, object]:
    runtime = _request(client, "GET", "/api/runtime")
    capabilities = runtime.get("capabilities")
    if (
        runtime.get("data_source") != "native"
        or runtime.get("serving_source") != "native"
        or runtime.get("degraded") is not False
        or not isinstance(capabilities, dict)
        or not all(
            capabilities.get(capability) is True
            for capability in ("submit", "logs", "cancel", "clone")
        )
    ):
        raise RuntimeError("Native live interaction runtime capabilities are unsafe")

    initial_jobs = _request(client, "GET", "/api/jobs", params={"page_size": 100})
    initial_summary = _request(client, "GET", "/api/jobs/summary")
    if initial_jobs.get("total") != initial_summary.get("total_jobs"):
        raise RuntimeError("Native list and summary disagree before interaction")

    pending_cleanup: dict[str, tuple[str, str]] = {}
    try:
        completed = _request(
            client,
            "POST",
            "/api/jobs",
            expected_status=201,
            headers={"Idempotency-Key": COMPLETION_KEY},
            json=_submission("dashboard-live-completion", "python3 --version", 1),
        )
        completed_id, completed_slurm_id = _job_identity(completed, owner)
        pending_cleanup[completed_id] = (completed_slurm_id, "native-live-cleanup-completion-v1")
        completed = _wait_for_state(
            client,
            completed_id,
            TERMINAL_STATES,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )
        if completed.get("state") != "COMPLETED" or completed.get("exit_code") != "0:0":
            raise RuntimeError("Native completion job did not finish successfully")
        pending_cleanup.pop(completed_id)

        stdout = _wait_for_log(
            client,
            completed_id,
            "stdout",
            require_content=True,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )
        stderr = _wait_for_log(
            client,
            completed_id,
            "stderr",
            require_content=False,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )
        usage = _wait_for_usage(
            client,
            completed_id,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )

        control = _request(
            client,
            "POST",
            "/api/jobs",
            expected_status=201,
            headers={"Idempotency-Key": CONTROL_KEY},
            json=_submission(
                "dashboard-live-control",
                "python3 -m timeit -n 1000000000 pass",
                2,
            ),
        )
        control_id, control_slurm_id = _job_identity(control, owner)
        pending_cleanup[control_id] = (control_slurm_id, CANCEL_CONTROL_KEY)
        _wait_for_state(
            client,
            control_id,
            ACTIVE_STATES,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )
        cancelled_control = _request(
            client,
            "POST",
            f"/api/jobs/{control_id}/cancel",
            headers={"Idempotency-Key": CANCEL_CONTROL_KEY},
        )
        if cancelled_control.get("state") != "CANCELLED":
            raise RuntimeError("Native control job was not cancelled")
        pending_cleanup.pop(control_id)

        clone = _request(
            client,
            "POST",
            f"/api/jobs/{control_id}/clone",
            expected_status=201,
            headers={"Idempotency-Key": CLONE_KEY},
        )
        clone_id, clone_slurm_id = _job_identity(clone, owner)
        if clone_slurm_id in {completed_slurm_id, control_slurm_id}:
            raise RuntimeError("Native clone did not create a distinct Slurm job")
        pending_cleanup[clone_id] = (clone_slurm_id, CANCEL_CLONE_KEY)
        _wait_for_state(
            client,
            clone_id,
            ACTIVE_STATES,
            timeout_seconds=timeout_seconds,
            clock=clock,
            pause=pause,
        )
        cancelled_clone = _request(
            client,
            "POST",
            f"/api/jobs/{clone_id}/cancel",
            headers={"Idempotency-Key": CANCEL_CLONE_KEY},
        )
        if cancelled_clone.get("state") != "CANCELLED":
            raise RuntimeError("Native cloned job was not cancelled")
        pending_cleanup.pop(clone_id)
    finally:
        for dashboard_id, (_, cleanup_key) in pending_cleanup.items():
            client.post(
                f"/api/jobs/{dashboard_id}/cancel",
                headers={"Idempotency-Key": cleanup_key},
            )

    final_jobs = _request(client, "GET", "/api/jobs", params={"page_size": 100})
    final_summary = _request(client, "GET", "/api/jobs/summary")
    if final_jobs.get("total") != final_summary.get("total_jobs"):
        raise RuntimeError("Native list and summary disagree after interaction")

    stdout_content = stdout.get("content")
    stderr_content = stderr.get("content")
    requested_usage = usage.get("requested")
    allocated_usage = usage.get("allocated")
    return {
        "mode": "native-live-http-full-interaction",
        "passed": True,
        "owner": owner,
        "runtime_capabilities": {
            capability: capabilities.get(capability)
            for capability in ("submit", "logs", "cancel", "clone")
        },
        "initial_visible_jobs": initial_jobs.get("total"),
        "final_visible_jobs": final_jobs.get("total"),
        "completion_job": {
            "dashboard_job_id": completed_id,
            "slurm_job_id": completed_slurm_id,
            "state": completed.get("state"),
            "exit_code": completed.get("exit_code"),
            "stdout_bytes": len(stdout_content.encode("utf-8"))
            if isinstance(stdout_content, str)
            else None,
            "stderr_bytes": len(stderr_content.encode("utf-8"))
            if isinstance(stderr_content, str)
            else None,
            "logs_content_redacted": True,
            "requested": requested_usage,
            "allocated": allocated_usage,
            "elapsed_seconds": usage.get("elapsed_seconds"),
            "max_rss_kb": usage.get("max_rss_kb"),
            "total_cpu_seconds": usage.get("total_cpu_seconds"),
        },
        "control_job": {
            "dashboard_job_id": control_id,
            "slurm_job_id": control_slurm_id,
            "cancelled": True,
        },
        "clone_job": {
            "dashboard_job_id": clone_id,
            "slurm_job_id": clone_slurm_id,
            "cancelled": True,
        },
        "submitted_jobs": 3,
        "cancelled_jobs": 2,
        "raw_log_content_emitted": False,
    }


def _key_digest(value: str) -> str:
    return sha256(value.encode("ascii")).hexdigest()


def _audit_evidence(
    settings: Settings,
    owner: str,
    interaction: dict[str, object],
) -> dict[str, object]:
    completion = interaction["completion_job"]
    control = interaction["control_job"]
    clone = interaction["clone_job"]
    if not all(isinstance(item, dict) for item in (completion, control, clone)):
        raise RuntimeError("Native live interaction evidence is invalid")
    completion_id = str(completion["slurm_job_id"])
    control_id = str(control["slurm_job_id"])
    clone_id = str(clone["slurm_job_id"])
    control_dashboard_id = str(control["dashboard_job_id"])
    clone_dashboard_id = str(clone["dashboard_job_id"])

    submission_repository = SubmissionRepository(settings.database_url)
    events = submission_repository.list_events(owner=owner)
    submission_records = (
        submission_repository.get_idempotency(
            owner=owner,
            key_digest=_key_digest(COMPLETION_KEY),
        ),
        submission_repository.get_idempotency(
            owner=owner,
            key_digest=_key_digest(CONTROL_KEY),
        ),
        submission_repository.get_idempotency(
            owner=owner,
            key_digest=_key_digest(f"clone:{control_dashboard_id}:{CLONE_KEY}"),
        ),
    )
    control_repository = JobControlRepository(settings.database_url)
    cancellation_records = (
        control_repository.get(
            owner=owner,
            operation="cancel",
            key_digest=_key_digest(CANCEL_CONTROL_KEY),
        ),
        control_repository.get(
            owner=owner,
            operation="cancel",
            key_digest=_key_digest(CANCEL_CLONE_KEY),
        ),
    )
    accepted_submission_ids = {
        event.slurm_job_id
        for event in events
        if event.result_code == "SBATCH_ACCEPTED"
    }
    accepted_cancellation_ids = {
        event.slurm_job_id
        for event in events
        if event.result_code == "SCANCEL_ACCEPTED"
    }
    idempotency_records_succeeded = sum(
        record is not None and record.status == "SUCCEEDED"
        for record in (*submission_records, *cancellation_records)
    )
    audit_chain_present = (
        {completion_id, control_id, clone_id} <= accepted_submission_ids
        and {control_id, clone_id} <= accepted_cancellation_ids
        and idempotency_records_succeeded == 5
        and cancellation_records[0] is not None
        and cancellation_records[0].target_job_id == control_dashboard_id
        and cancellation_records[1] is not None
        and cancellation_records[1].target_job_id == clone_dashboard_id
    )
    return {
        "submission_idempotency_records": 3,
        "cancellation_idempotency_records": 2,
        "idempotency_records_succeeded": idempotency_records_succeeded,
        "audit_chain_present": audit_chain_present,
    }


def write_receipt(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    arguments = parser.parse_args(argv)
    require_confirmation(arguments.confirm)
    if not 10 <= arguments.timeout_seconds <= 300:
        raise ValueError("timeout must be between 10 and 300 seconds")

    settings = Settings()
    validate_settings(settings)
    owner = assert_deployment_owner(
        settings.dashboard_owner,
        resolve_effective_unix_username(),
    )
    receipt_path = settings.job_workspace_directory / RECEIPT_NAME
    ensure_first_run(receipt_path)
    with TestClient(create_app(settings)) as client:
        evidence = execute_interaction(
            client,
            owner=owner,
            timeout_seconds=arguments.timeout_seconds,
        )
    persistence = _audit_evidence(settings, owner, evidence)
    if not persistence["audit_chain_present"]:
        raise RuntimeError("Native live interaction audit chain is incomplete")
    evidence["persistence"] = persistence
    write_receipt(receipt_path, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
