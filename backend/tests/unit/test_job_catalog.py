from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_ROOT, Settings
from app.schemas.jobs import JobState
from app.services.job_catalog import JobCatalog, build_slurm_adapter
from app.slurm import FixtureSlurmAdapter, NativeSlurmAdapter, SlurmJob, SlurmResources
from app.slurm.runner import SubprocessCommandRunner


class StaticAdapter:
    def __init__(
        self, queue: list[SlurmJob] | None = None, accounting: list[SlurmJob] | None = None
    ) -> None:
        self.queue = queue or []
        self.accounting = accounting or []
        self.queue_calls = 0
        self.accounting_calls = 0

    def list_queue(self, user: str) -> list[SlurmJob]:
        self.queue_calls += 1
        return self.queue

    def list_accounting(self, user: str) -> list[SlurmJob]:
        self.accounting_calls += 1
        return self.accounting

    def list_partitions(self) -> list[object]:
        return []


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_catalog_deduplicates_by_slurm_id_with_queue_record_priority() -> None:
    adapter = StaticAdapter(
        queue=[
            SlurmJob(
                job_id="42",
                user="demo-user",
                state="RUNNING",
                nodes="live-node",
                reason="live-reason",
                allocated=SlurmResources(cpus=2),
            )
        ],
        accounting=[
            SlurmJob(
                job_id="42",
                user="demo-user",
                name="accounting-name",
                state="COMPLETED",
                nodes="old-node",
                reason="old-reason",
                exit_code="0:0",
                allocated=SlurmResources(cpus=8, memory_mb=4096, gpus=1),
            ),
            SlurmJob(job_id="43", user="other-user", state="FAILED"),
        ],
    )

    response = JobCatalog(adapter=adapter, owner="demo-user").list_jobs(None, 1, 20)

    assert response.total == 1
    assert response.items[0].id == "slurm-42"
    assert response.items[0].state == JobState.RUNNING
    assert response.items[0].name == "accounting-name"
    assert response.items[0].node == "live-node"
    assert response.items[0].reason == "live-reason"
    assert response.items[0].resources.cpus == 2
    assert response.items[0].resources.memory_mb == 4096
    assert response.items[0].resources.gpus == 1
    assert response.items[0].exit_code == "0:0"


def test_catalog_paginates_after_state_filtering() -> None:
    adapter = StaticAdapter(
        accounting=[
            SlurmJob(job_id="1", user="demo-user", state="FAILED"),
            SlurmJob(job_id="2", user="demo-user", state="COMPLETED"),
            SlurmJob(job_id="3", user="demo-user", state="FAILED"),
        ]
    )

    response = JobCatalog(adapter=adapter, owner="demo-user").list_jobs(JobState.FAILED, 2, 1)

    assert response.total == 2
    assert [job.slurm_job_id for job in response.items] == ["1"]
    assert response.items[0].updated_at == response.updated_at


def test_factory_builds_fixture_adapter() -> None:
    fixture = build_slurm_adapter(Settings(_env_file=None))

    assert isinstance(fixture, FixtureSlurmAdapter)


def test_native_factory_builds_read_only_adapter_with_configured_timeout() -> None:
    adapter = build_slurm_adapter(
        Settings(
            _env_file=None,
            slurm_data_source="native",
            slurm_command_timeout_seconds=7,
        )
    )

    assert isinstance(adapter, NativeSlurmAdapter)
    assert isinstance(adapter.runner, SubprocessCommandRunner)
    assert adapter.runner.timeout_seconds == 7


def test_catalog_reuses_snapshot_until_cache_expires() -> None:
    adapter = StaticAdapter(accounting=[SlurmJob(job_id="1", user="demo-user")])
    clock = FakeClock()
    catalog = JobCatalog(adapter, "demo-user", cache_ttl_seconds=1, clock=clock)

    first = catalog.list_jobs(None, 1, 20)
    second = catalog.get_job("slurm-1")

    assert second is not None
    assert adapter.queue_calls == 1
    assert adapter.accounting_calls == 1
    assert second.updated_at == first.updated_at

    clock.advance(1.01)
    catalog.list_jobs(None, 1, 20)

    assert adapter.queue_calls == 2
    assert adapter.accounting_calls == 2


def test_catalog_limits_jobs_after_stable_sorting() -> None:
    adapter = StaticAdapter(
        accounting=[SlurmJob(job_id=job_id, user="demo-user") for job_id in ("2", "10", "3", "1")]
    )

    response = JobCatalog(adapter, "demo-user", max_jobs=2).list_jobs(None, 1, 20)

    assert response.total == 2
    assert [job.slurm_job_id for job in response.items] == ["10", "3"]


def test_polling_pages_remain_stable_when_adapter_order_changes() -> None:
    adapter = StaticAdapter(
        accounting=[SlurmJob(job_id=job_id, user="demo-user") for job_id in ("1", "4", "2", "3")]
    )
    clock = FakeClock()
    catalog = JobCatalog(adapter, "demo-user", cache_ttl_seconds=1, clock=clock)

    first_poll = [
        job.slurm_job_id for page in (1, 2) for job in catalog.list_jobs(None, page, 2).items
    ]
    adapter.accounting.reverse()
    clock.advance(1.01)
    second_poll = [
        job.slurm_job_id for page in (1, 2) for job in catalog.list_jobs(None, page, 2).items
    ]

    assert first_poll == second_poll == ["4", "3", "2", "1"]


def test_relative_fixture_path_is_resolved_from_project_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=None, slurm_fixture_directory="fixtures/slurm")

    assert settings.slurm_fixture_directory == PROJECT_ROOT / "fixtures" / "slurm"


def test_relative_sqlite_path_is_resolved_from_project_root() -> None:
    settings = Settings(_env_file=None, database_url="sqlite:///./data/dashboard.sqlite3")

    assert settings.database_url == f"sqlite:///{(PROJECT_ROOT / 'data/dashboard.sqlite3').as_posix()}"


def test_dotenv_path_is_anchored_to_project_root() -> None:
    assert Settings.model_config["env_file"] == PROJECT_ROOT / ".env"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("slurm_command_timeout_seconds", 0),
        ("slurm_command_timeout_seconds", 121),
        ("slurm_query_cache_ttl_seconds", 0),
        ("slurm_query_cache_ttl_seconds", 61),
        ("slurm_max_jobs", 0),
        ("slurm_max_jobs", 10001),
        ("native_max_active_jobs", 0),
        ("native_max_active_jobs", 101),
    ],
)
def test_slurm_query_settings_have_bounded_values(field: str, value: Any) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(_env_file=None, **{field: value})


def test_unknown_data_source_fails_during_settings_construction() -> None:
    with pytest.raises(ValidationError, match="slurm_data_source"):
        Settings(_env_file=None, slurm_data_source="unknown")  # type: ignore[arg-type]


def test_unsafe_trusted_owner_fails_during_settings_construction() -> None:
    with pytest.raises(ValidationError, match="dashboard_owner"):
        Settings(_env_file=None, dashboard_owner="demo-user,other-user")
