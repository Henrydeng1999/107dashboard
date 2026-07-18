#!/usr/bin/env python3
"""Read one bounded Native log sample per stream without emitting log content."""

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import sys
from typing import Protocol

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import Settings  # noqa: E402
from app.core.identity import assert_deployment_owner, resolve_effective_unix_username  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas.jobs import JobLogResponse, JobLogStream  # noqa: E402
from app.schemas.system import RuntimeInfo  # noqa: E402

CONFIRMATION = "READ-ONE-NATIVE-JOB-LOG-SAMPLE"
ACCEPTANCE_JOB_ID = "24011"
READ_LIMIT_BYTES = 4096


class HttpResponse(Protocol):
    status_code: int

    def json(self) -> object: ...


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> HttpResponse: ...


def require_confirmation(value: str) -> None:
    if value != CONFIRMATION:
        raise PermissionError(f"confirmation must exactly equal {CONFIRMATION}")


def validate_settings(settings: Settings) -> None:
    if settings.slurm_data_source != "native":
        raise RuntimeError("SLURM_DATA_SOURCE must be native")
    if not settings.native_logs_enabled:
        raise RuntimeError("NATIVE_LOGS_ENABLED must be explicitly enabled")
    if settings.native_submission_enabled:
        raise RuntimeError("NATIVE_SUBMISSION_ENABLED must remain disabled")


def _validated_payload(response: HttpResponse, model: type[RuntimeInfo] | type[JobLogResponse]):
    if response.status_code != 200:
        raise RuntimeError("Native log acceptance API request failed safely")
    try:
        return model.model_validate(response.json())
    except (TypeError, ValueError, ValidationError):
        raise RuntimeError("Native log acceptance API response was invalid") from None


def collect_log_evidence(client: HttpClient, *, owner: str) -> dict[str, object]:
    runtime = _validated_payload(client.get("/api/runtime"), RuntimeInfo)
    if (
        runtime.data_source != "native"
        or not runtime.read_only
        or not runtime.capabilities.logs
        or runtime.capabilities.submit
        or runtime.capabilities.cancel
        or runtime.capabilities.clone
    ):
        raise RuntimeError("runtime capabilities are unsafe for log acceptance")

    dashboard_job_id = f"slurm-{ACCEPTANCE_JOB_ID}"
    streams: list[dict[str, object]] = []
    for stream in JobLogStream:
        response = client.get(
            f"/api/jobs/{dashboard_job_id}/logs",
            params={
                "stream": stream.value,
                "offset": 0,
                "limit": READ_LIMIT_BYTES,
            },
        )
        log = _validated_payload(response, JobLogResponse)
        bytes_read = log.next_offset - log.offset
        if (
            log.job_id != dashboard_job_id
            or log.stream != stream
            or log.offset != 0
            or not 0 <= bytes_read <= READ_LIMIT_BYTES
            or (not log.available and (log.content != "" or bytes_read != 0))
        ):
            raise RuntimeError("Native log acceptance response failed consistency checks")
        streams.append(
            {
                "stream": stream.value,
                "available": log.available,
                "offset": log.offset,
                "next_offset": log.next_offset,
                "bytes_read": bytes_read,
                "eof": log.eof,
                "content_redacted": True,
            }
        )

    return {
        "mode": "native-log-bounded-read-acceptance",
        "passed": True,
        "owner": owner,
        "slurm_job_id": ACCEPTANCE_JOB_ID,
        "read_limit_bytes_per_stream": READ_LIMIT_BYTES,
        "streams": streams,
        "raw_content_emitted": False,
        "http_submission_enabled": False,
        "http_cancel_enabled": False,
        "http_clone_enabled": False,
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

    from fastapi.testclient import TestClient

    with TestClient(create_app(settings)) as client:
        evidence = collect_log_evidence(client, owner=owner)
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
