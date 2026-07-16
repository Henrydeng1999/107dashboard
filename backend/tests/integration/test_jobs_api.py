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
