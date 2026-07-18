import os

import pytest


_SETTINGS_ENVIRONMENT_VARIABLES = (
    "SLURM_DATA_SOURCE",
    "SLURM_FIXTURE_DIRECTORY",
    "FIXTURE_JOB_OUTPUT_DIRECTORY",
    "JOB_WORKSPACE_DIRECTORY",
    "SLURM_COMMAND_TIMEOUT_SECONDS",
    "SLURM_QUERY_CACHE_TTL_SECONDS",
    "SLURM_MAX_JOBS",
    "DASHBOARD_OWNER",
    "DATABASE_URL",
    "NATIVE_SUBMISSION_ENABLED",
    "NATIVE_LOGS_ENABLED",
    "NATIVE_CANCEL_ENABLED",
    "NATIVE_CLONE_ENABLED",
    "NATIVE_MAX_ACTIVE_JOBS",
    "DEMO_FALLBACK_ENABLED",
    "DEMO_FALLBACK_COOLDOWN_SECONDS",
    "DEMO_FALLBACK_OWNER",
    "SERVE_FRONTEND",
    "FRONTEND_DIST_DIRECTORY",
)

# Test modules import the application during collection, before fixtures run.
for variable in _SETTINGS_ENVIRONMENT_VARIABLES:
    os.environ.pop(variable, None)
os.environ["DATABASE_URL"] = "sqlite://"


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _SETTINGS_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
