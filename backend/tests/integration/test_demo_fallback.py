from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.demo_fallback import DemoFallbackJobCatalog
from app.services.job_catalog import JobCatalog
from app.slurm import FixtureSlurmAdapter, SlurmCommandFailed, SlurmJob

PROJECT_ROOT = Path(__file__).parents[3]


class SwitchableNativeAdapter:
    def __init__(self) -> None:
        self.available = False
        self.calls = 0

    def list_queue(self, user: str) -> list[SlurmJob]:
        self.calls += 1
        if not self.available:
            raise SlurmCommandFailed(("squeue", f"--user={user}"), 1, "scheduler unavailable")
        return []

    def list_accounting(self, user: str) -> list[SlurmJob]:
        return []

    def list_partitions(self) -> list[object]:
        return []

    def get_usage(self, job_id: str) -> list[object]:
        return []


def _fallback_client(clock: list[float]) -> tuple[TestClient, SwitchableNativeAdapter]:
    native_adapter = SwitchableNativeAdapter()
    primary = JobCatalog(native_adapter, "demo-user", cache_ttl_seconds=0.1)
    fallback = JobCatalog(
        FixtureSlurmAdapter(PROJECT_ROOT / "fixtures" / "slurm"),
        "demo-user",
        cache_ttl_seconds=0.1,
        allow_fixture_submissions=False,
        fixture_job_output_directory=PROJECT_ROOT / "fixtures" / "job-output",
    )
    catalog = DemoFallbackJobCatalog(
        primary,
        fallback,
        cooldown_seconds=30,
        clock=lambda: clock[0],
    )
    settings = Settings(
        _env_file=None,
        slurm_data_source="native",
        dashboard_owner="demo-user",
        demo_fallback_enabled=True,
        native_submission_enabled=True,
        native_cancel_enabled=True,
        native_clone_enabled=True,
    )
    return TestClient(create_app(settings=settings, job_catalog=catalog)), native_adapter


def test_native_failure_activates_explicit_read_only_fixture_fallback() -> None:
    clock = [100.0]
    client, native_adapter = _fallback_client(clock)

    initial_runtime = client.get("/api/runtime").json()
    assert initial_runtime["serving_source"] == "native"
    assert initial_runtime["demo_fallback_enabled"] is True
    assert initial_runtime["capabilities"]["submit"] is True

    jobs = client.get("/api/jobs")
    degraded_runtime = client.get("/api/runtime").json()

    assert jobs.status_code == 200
    assert jobs.json()["total"] == 5
    assert degraded_runtime["serving_source"] == "fixture_fallback"
    assert degraded_runtime["degraded"] is True
    assert degraded_runtime["fallback_reason"] == "slurm_unavailable"
    assert degraded_runtime["read_only"] is True
    assert degraded_runtime["capabilities"]["submit"] is False
    assert degraded_runtime["capabilities"]["cancel"] is False
    assert degraded_runtime["capabilities"]["clone"] is False
    assert degraded_runtime["capabilities"]["logs"] is True

    write_attempt = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "fallback-must-not-write"},
        json={
            "name": "must-not-submit",
            "command": "python3 --version",
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {"cpus": 1, "memory_mb": 512, "gpus": 0, "time_limit_minutes": 1},
        },
    )
    assert write_attempt.status_code == 503
    assert client.post(
        "/api/jobs/slurm-900001/cancel",
        headers={"Idempotency-Key": "fallback-must-not-cancel"},
    ).status_code == 503
    assert client.post(
        "/api/jobs/slurm-899998/clone",
        headers={"Idempotency-Key": "fallback-must-not-clone"},
    ).status_code == 503
    assert native_adapter.calls == 1


def test_list_probe_recovers_native_after_cooldown() -> None:
    clock = [100.0]
    client, native_adapter = _fallback_client(clock)
    assert client.get("/api/jobs").json()["total"] == 5

    native_adapter.available = True
    clock[0] = 131.0
    recovered = client.get("/api/jobs")
    runtime = client.get("/api/runtime").json()

    assert recovered.status_code == 200
    assert recovered.json()["total"] == 0
    assert runtime["serving_source"] == "native"
    assert runtime["degraded"] is False
    assert runtime["capabilities"]["submit"] is True
