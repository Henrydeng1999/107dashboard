import os

import pytest


_SETTINGS_ENVIRONMENT_VARIABLES = (
    "SLURM_DATA_SOURCE",
    "SLURM_FIXTURE_DIRECTORY",
    "SLURM_COMMAND_TIMEOUT_SECONDS",
    "SLURM_QUERY_CACHE_TTL_SECONDS",
    "SLURM_MAX_JOBS",
    "DASHBOARD_OWNER",
)

# Test modules import the application during collection, before fixtures run.
for variable in _SETTINGS_ENVIRONMENT_VARIABLES:
    os.environ.pop(variable, None)


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _SETTINGS_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
