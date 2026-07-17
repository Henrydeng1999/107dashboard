from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.services.job_catalog import JobCatalog, NativeSlurmApiDisabled
from app.slurm import SlurmCommandFailed, SlurmJob


class FailingAdapter:
    def list_queue(self, user: str) -> list[SlurmJob]:
        raise SlurmCommandFailed(
            ("squeue", "--user=secret-owner", "--config=/private/path"),
            1,
            "sensitive scheduler stderr",
        )

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return []

    def list_partitions(self) -> list[object]:
        return []


def _fixture_client(**settings_overrides: object) -> TestClient:
    settings = Settings(_env_file=None, **settings_overrides)
    return TestClient(create_app(settings=settings))


def test_default_fixture_list_filter_pagination_and_nullable_contract() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs", params={"state": "RUNNING", "page": 1, "page_size": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert payload["updated_at"]
    assert payload["items"][0]["id"] == "slurm-900001"
    assert payload["items"][0]["command"] is None
    assert payload["items"][0]["submitted_at"] is None
    assert payload["items"][0]["resources"] == {
        "cpus": 2,
        "memory_mb": 4096,
        "gpus": 1,
        "time_limit_minutes": 60,
    }


def test_fixture_detail_uses_stable_dashboard_id() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/slurm-899998")

    assert response.status_code == 200
    assert response.json()["slurm_job_id"] == "899998"
    assert response.json()["owner"] == "demo-user"
    assert client.get("/api/jobs/899998").status_code == 404


def test_fixture_user_summary_counts_states_and_resource_coverage() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["total_jobs"] == 5
    assert summary["active_jobs"] == 2
    assert summary["successful_jobs"] == 1
    assert summary["unsuccessful_jobs"] == 2
    assert summary["state_counts"] == {
        "PENDING": 1,
        "RUNNING": 1,
        "COMPLETED": 1,
        "FAILED": 1,
        "CANCELLED": 1,
        "TIMEOUT": 0,
        "UNKNOWN": 0,
    }
    assert summary["resources"] == {
        "cpus": 6,
        "memory_mb": 12288,
        "gpus": 2,
        "time_limit_minutes": 180,
        "cpus_jobs": 4,
        "memory_jobs": 4,
        "gpus_jobs": 2,
        "time_limit_jobs": 4,
    }
    assert summary["resource_basis"] == "requested_or_allocated_snapshot"


def test_fixture_user_summary_updates_after_submission() -> None:
    client = _fixture_client()
    client.post("/api/jobs", json=_valid_submission())

    summary = client.get("/api/jobs/summary").json()

    assert summary["total_jobs"] == 6
    assert summary["state_counts"]["PENDING"] == 2
    assert summary["resources"]["cpus"] == 8
    assert summary["resources"]["memory_mb"] == 16384
    assert summary["resources"]["gpus"] == 3


def test_fixture_owner_is_server_configuration_not_request_input() -> None:
    client = _fixture_client(dashboard_owner="another-user")

    response = client.get("/api/jobs", params={"owner": "demo-user"})

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert client.get("/api/jobs/slurm-900001").status_code == 404


def test_native_command_error_maps_to_stable_sanitized_503() -> None:
    settings = Settings(
        _env_file=None,
        slurm_data_source="native",
        dashboard_owner="secret-owner",
    )
    catalog = JobCatalog(adapter=FailingAdapter(), owner=settings.dashboard_owner)
    client = TestClient(create_app(settings=settings, job_catalog=catalog))

    response = client.get("/api/jobs")

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "JOB_DATA_UNAVAILABLE"
    assert error["message"] == "Job data is temporarily unavailable"
    assert error["request_id"] == response.headers["X-Request-ID"]
    serialized = response.text
    assert "sensitive scheduler stderr" not in serialized
    assert "secret-owner" not in serialized
    assert "/private/path" not in serialized


def test_missing_or_malformed_fixture_maps_to_stable_503(tmp_path: Path) -> None:
    missing_client = _fixture_client(slurm_fixture_directory=tmp_path / "missing")
    malformed_directory = tmp_path / "malformed"
    malformed_directory.mkdir()
    (malformed_directory / "squeue.txt").write_text(
        "1|job|RUNNING|demo-user|partition|account|qos|node|None|two|4G||01:00:00",
        encoding="utf-8",
    )
    (malformed_directory / "sacct.txt").write_text("", encoding="utf-8")
    malformed_client = _fixture_client(slurm_fixture_directory=malformed_directory)

    for client in (missing_client, malformed_client):
        response = client.get("/api/jobs")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "JOB_DATA_UNAVAILABLE"
        assert str(tmp_path) not in response.text


def test_native_gate_blocks_app_before_subprocess(
    monkeypatch,
) -> None:
    calls: list[object] = []

    def unexpected_run(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(subprocess, "run", unexpected_run)

    with pytest.raises(NativeSlurmApiDisabled):
        create_app(Settings(_env_file=None, slurm_data_source="native"))

    assert calls == []


def test_error_envelope_and_openapi_responses() -> None:
    client = _fixture_client()

    not_found = client.get("/api/jobs/not-found")
    invalid = client.get("/api/jobs", params={"page": 0})
    schema = client.get("/openapi.json").json()

    for response, code in ((not_found, "JOB_NOT_FOUND"), (invalid, "INVALID_REQUEST")):
        assert response.json()["error"]["code"] == code
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert set(schema["paths"]["/api/jobs"]["get"]["responses"]) >= {"200", "422", "503"}
    assert set(schema["paths"]["/api/jobs/{job_id}"]["get"]["responses"]) >= {
        "200",
        "404",
        "422",
        "503",
    }
    assert set(schema["paths"]["/api/jobs"]["post"]["responses"]) >= {"201", "422", "503"}


def _valid_submission() -> dict[str, object]:
    return {
        "name": "course-training",
        "command": "python train.py --epochs 2",
        "partition": "Students",
        "account": "stu",
        "qos": "qos_stu_default",
        "resources": {
            "cpus": 2,
            "memory_mb": 4096,
            "gpus": 1,
            "time_limit_minutes": 60,
        },
    }


def test_fixture_submission_is_immediately_visible_in_list_and_detail() -> None:
    client = _fixture_client()

    response = client.post("/api/jobs", json=_valid_submission())

    assert response.status_code == 201
    job = response.json()
    assert job["id"] == "slurm-910000"
    assert job["state"] == "PENDING"
    assert job["command"] == "python train.py --epochs 2"
    assert job["resources"]["memory_mb"] == 4096
    assert client.get("/api/jobs/slurm-910000").json()["name"] == "course-training"
    assert client.get("/api/jobs").json()["items"][0]["id"] == "slurm-910000"


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("resources", "cpus"), 5),
        (("resources", "memory_mb"), 256),
        (("resources", "gpus"), 2),
        (("resources", "time_limit_minutes"), 241),
        (("partition",), "GPU-A100"),
        (("qos",), "qos_stu_medium_2gpu"),
        (("command",), "python train.py\nwhoami"),
    ],
)
def test_fixture_submission_rejects_unsafe_or_out_of_range_values(
    path: tuple[str, ...], value: object
) -> None:
    client = _fixture_client()
    payload = _valid_submission()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[assignment,index]
    target[path[-1]] = value  # type: ignore[index]

    response = client.post("/api/jobs", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_fixture_pending_job_can_be_cancelled_and_remains_visible() -> None:
    client = _fixture_client()
    submitted = client.post("/api/jobs", json=_valid_submission()).json()

    response = client.post(f"/api/jobs/{submitted['id']}/cancel")

    assert response.status_code == 200
    assert response.json()["state"] == "CANCELLED"
    assert response.json()["reason"] == "FixtureCancellation"
    assert response.json()["finished_at"] is not None
    assert client.get(f"/api/jobs/{submitted['id']}").json()["state"] == "CANCELLED"


def test_fixture_running_job_can_be_cancelled_but_terminal_job_cannot() -> None:
    client = _fixture_client()

    cancelled = client.post("/api/jobs/slurm-900001/cancel")
    conflict = client.post("/api/jobs/slurm-899999/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "JOB_OPERATION_CONFLICT"


def test_fixture_clone_revalidates_submission_and_creates_new_job() -> None:
    client = _fixture_client()
    original = client.post("/api/jobs", json=_valid_submission()).json()

    response = client.post(f"/api/jobs/{original['id']}/clone")

    assert response.status_code == 201
    cloned = response.json()
    assert cloned["id"] != original["id"]
    assert cloned["slurm_job_id"] == "910001"
    assert cloned["command"] == original["command"]
    assert cloned["resources"] == original["resources"]
    assert cloned["state"] == "PENDING"


def test_fixture_clone_rejects_read_only_job_without_submission_metadata() -> None:
    client = _fixture_client()

    response = client.post("/api/jobs/slurm-899999/clone")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_OPERATION_CONFLICT"


@pytest.mark.parametrize("operation", ["cancel", "clone"])
def test_fixture_job_operations_hide_unknown_jobs(operation: str) -> None:
    client = _fixture_client()

    response = client.post(f"/api/jobs/slurm-123456/{operation}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_fixture_stdout_log_supports_incremental_byte_offsets() -> None:
    client = _fixture_client()

    first = client.get(
        "/api/jobs/slurm-900001/logs",
        params={"stream": "stdout", "offset": 0, "limit": 32},
    )

    assert first.status_code == 200
    first_log = first.json()
    assert first_log["available"] is True
    assert first_log["offset"] == 0
    assert first_log["next_offset"] == 32
    assert first_log["eof"] is False
    assert first_log["content"].startswith("[dashboard fixture]")

    second = client.get(
        "/api/jobs/slurm-900001/logs",
        params={"stream": "stdout", "offset": first_log["next_offset"], "limit": 65536},
    ).json()
    assert second["offset"] == 32
    assert second["next_offset"] > 32
    assert second["eof"] is True


def test_fixture_stderr_and_missing_log_have_explicit_states() -> None:
    client = _fixture_client()

    stderr = client.get("/api/jobs/slurm-899999/logs", params={"stream": "stderr"})
    missing = client.get("/api/jobs/slurm-900002/logs", params={"stream": "stdout"})

    assert stderr.status_code == 200
    assert "simulated accelerator memory exhaustion" in stderr.json()["content"]
    assert missing.status_code == 200
    assert missing.json() == {
        "job_id": "slurm-900002",
        "stream": "stdout",
        "content": "",
        "offset": 0,
        "next_offset": 0,
        "eof": True,
        "available": False,
    }


@pytest.mark.parametrize(
    ("path", "expected_status", "expected_code"),
    [
        ("/api/jobs/slurm-123456/logs", 404, "JOB_NOT_FOUND"),
        ("/api/jobs/slurm-900001/logs?offset=999999", 416, "JOB_LOG_OFFSET_OUT_OF_RANGE"),
        ("/api/jobs/slurm-900001/logs?stream=combined", 422, "INVALID_REQUEST"),
        ("/api/jobs/slurm-900001/logs?limit=65537", 422, "INVALID_REQUEST"),
    ],
)
def test_fixture_log_errors_use_stable_envelopes(
    path: str, expected_status: int, expected_code: str
) -> None:
    client = _fixture_client()

    response = client.get(path)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_fixture_usage_distinguishes_requested_allocated_and_actual_metrics() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/slurm-899998/usage")

    assert response.status_code == 200
    usage = response.json()
    assert usage["requested"] == {
        "cpus": 2,
        "memory_mb": 4096,
        "gpus": 1,
        "time_limit_minutes": 60,
    }
    assert usage["allocated"]["cpus"] == 2
    assert usage["allocated"]["gpus"] == 1
    assert usage["elapsed_seconds"] == 751
    assert usage["time_limit_seconds"] == 3600
    assert usage["max_rss_kb"] == 768 * 1024
    assert usage["total_cpu_seconds"] == 1122.5
    assert usage["gpu_utilization_percent"] is None
    assert usage["gpu_memory_mb"] is None


def test_fixture_usage_preserves_missing_metrics_instead_of_inventing_zeroes() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/slurm-900002/usage")

    assert response.status_code == 200
    usage = response.json()
    assert usage["requested"] == {
        "cpus": None,
        "memory_mb": None,
        "gpus": None,
        "time_limit_minutes": None,
    }
    assert usage["allocated"] == usage["requested"]
    assert usage["elapsed_seconds"] is None
    assert usage["max_rss_kb"] is None


def test_fixture_usage_preserves_sub_megabyte_peak_memory_precision() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/slurm-899999/usage")

    assert response.status_code == 200
    assert response.json()["max_rss_kb"] == 260
    assert response.json()["total_cpu_seconds"] == 0.148


def test_fixture_usage_hides_unknown_jobs() -> None:
    client = _fixture_client()

    response = client.get("/api/jobs/slurm-123456/usage")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
