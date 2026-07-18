#!/usr/bin/env python3
"""Validate persisted Native log paths without opening or reading log files."""

import argparse
import json
from pathlib import Path
import re
import sys

from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.repositories.job_metadata import JobMetadataRepository  # noqa: E402
from app.services.native_logs import resolve_native_log_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    arguments = parser.parse_args()
    if re.fullmatch(r"[1-9][0-9]*", arguments.job_id, re.ASCII) is None:
        raise ValueError("job ID must be one numeric Slurm allocation ID")

    settings = Settings()
    if settings.slurm_data_source != "native" or not settings.native_logs_enabled:
        raise RuntimeError("Native logs must be explicitly enabled for this preflight")
    owner = assert_deployment_owner(
        settings.dashboard_owner, resolve_effective_unix_username()
    )
    repository = JobMetadataRepository(settings.database_url)
    try:
        metadata = repository.get_by_slurm_job_id(arguments.job_id, owner=owner)
    except SQLAlchemyError as exc:
        raise RuntimeError("Native metadata database is unavailable") from exc
    if metadata is None or metadata.source != "native":
        raise RuntimeError("trusted Native metadata was not found for this owner and job")
    if metadata.stdout_path is None or metadata.stderr_path is None:
        raise RuntimeError("trusted Native metadata does not contain both log paths")

    resolve_native_log_path(
        metadata.stdout_path,
        workspace=settings.job_workspace_directory,
        stream="stdout",
    )
    resolve_native_log_path(
        metadata.stderr_path,
        workspace=settings.job_workspace_directory,
        stream="stderr",
    )
    print(
        json.dumps(
            {
                "mode": "native-log-path-preflight-no-read",
                "passed": True,
                "owner": owner,
                "slurm_job_id": arguments.job_id,
                "stdout_path_safe": True,
                "stderr_path_safe": True,
                "would_open_log": False,
                "would_read_log": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
