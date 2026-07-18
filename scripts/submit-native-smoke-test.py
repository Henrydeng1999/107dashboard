#!/usr/bin/env python3
"""Submit exactly one minimal Native acceptance job after explicit confirmation."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.repositories.submission import SubmissionRepository  # noqa: E402
from app.schemas.jobs import JobSubmitRequest  # noqa: E402
from app.services.native_submission import (  # noqa: E402
    ExplicitSubmissionAuthorization,
    NativeSubmissionService,
)
from app.slurm.runner import SubprocessCommandRunner  # noqa: E402
from app.slurm.submission import NativeSlurmSubmitter  # noqa: E402

CONFIRMATION = "SUBMIT-ONE-MINIMAL-NATIVE-JOB"


def build_minimal_request() -> JobSubmitRequest:
    return JobSubmitRequest.model_validate(
        {
            "name": "dashboard-native-smoke",
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
        }
    )


def require_confirmation(value: str) -> None:
    if value != CONFIRMATION:
        raise PermissionError(f"confirmation must exactly equal {CONFIRMATION}")


def ensure_no_prior_receipt(workspace: Path) -> None:
    if any(workspace.glob("submission-*/slurm-job-id")):
        raise RuntimeError("a Native submission receipt already exists; refusing a repeat smoke job")


def execute_minimal_submission(
    settings: Settings,
    *,
    owner: str,
    runner: SubprocessCommandRunner,
) -> dict[str, object]:
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native")
    ensure_no_prior_receipt(settings.job_workspace_directory)

    repository = SubmissionRepository(settings.database_url)
    repository.initialize()
    service = NativeSubmissionService(
        owner=owner,
        workspace_root=settings.job_workspace_directory,
        submitter=NativeSlurmSubmitter(runner),
        repository=repository,
    )
    metadata = service.submit(
        build_minimal_request(),
        authorization=ExplicitSubmissionAuthorization(confirmed=True),
    )
    events = repository.list_events(owner=owner)
    success_event = next(
        (
            event
            for event in reversed(events)
            if event.status == "SUCCEEDED" and event.slurm_job_id == metadata.slurm_job_id
        ),
        None,
    )
    audit_statuses = (
        [event.status for event in events if event.submission_id == success_event.submission_id]
        if success_event is not None
        else []
    )
    return {
        "mode": "native-submit-minimal-acceptance",
        "submitted": True,
        "dashboard_job_id": metadata.id,
        "slurm_job_id": metadata.slurm_job_id,
        "owner": metadata.owner,
        "request": {
            "command": metadata.command,
            "partition": metadata.partition,
            "account": metadata.account,
            "qos": metadata.qos,
            "cpus": metadata.cpus,
            "memory_mb": metadata.memory_mb,
            "gpus": metadata.gpus,
            "time_limit_minutes": metadata.time_limit_minutes,
        },
        "metadata_persisted": True,
        "receipt_persisted": True,
        "audit_statuses": audit_statuses,
        "http_submission_enabled": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    arguments = parser.parse_args(argv)
    require_confirmation(arguments.confirm)

    settings = Settings()
    effective_owner = resolve_effective_unix_username()
    owner = assert_deployment_owner(settings.dashboard_owner, effective_owner)
    evidence = execute_minimal_submission(
        settings,
        owner=owner,
        runner=SubprocessCommandRunner(settings.slurm_command_timeout_seconds),
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
