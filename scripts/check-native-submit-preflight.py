#!/usr/bin/env python3
"""Read-only Native submission preflight; this script never invokes sbatch."""

import json
import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.schemas.jobs import JobSubmitRequest  # noqa: E402
from app.slurm.submission import build_submission_plan  # noqa: E402


def nearest_existing_parent(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def main() -> int:
    settings = Settings()
    effective_owner = resolve_effective_unix_username()
    owner = assert_deployment_owner(settings.dashboard_owner, effective_owner)
    request = JobSubmitRequest.model_validate(
        {
            "name": "dashboard-preflight",
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
    plan = build_submission_plan(
        request,
        owner=owner,
        workspace_root=settings.job_workspace_directory,
        submission_id="submission-00000000000000000000000000000000",
    )
    workspace_parent = nearest_existing_parent(settings.job_workspace_directory)
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    database_parent = nearest_existing_parent(database_path.parent)
    result = {
        "mode": "native-submit-read-only-preflight",
        "passed": all(
            [
                shutil.which("sbatch") is not None,
                os.access(workspace_parent, os.W_OK | os.X_OK),
                os.access(database_parent, os.W_OK | os.X_OK),
            ]
        ),
        "owner": owner,
        "sbatch_available": shutil.which("sbatch") is not None,
        "workspace_parent_accessible": os.access(workspace_parent, os.W_OK | os.X_OK),
        "database_parent_accessible": os.access(database_parent, os.W_OK | os.X_OK),
        "sample_command": list(plan.arguments),
        "resource_limits": {"cpus": 4, "memory_mb": 16384, "gpus": 1, "minutes": 240},
        "would_invoke_sbatch": False,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
