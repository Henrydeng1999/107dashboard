from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "107 Dashboard API"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_log_level: str = "INFO"
    database_url: str = "sqlite:///./data/dashboard.sqlite3"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    slurm_data_source: Literal["fixture", "native"] = "fixture"
    slurm_fixture_directory: Path = PROJECT_ROOT / "fixtures" / "slurm"
    fixture_job_output_directory: Path = PROJECT_ROOT / "fixtures" / "job-output"
    job_workspace_directory: Path = PROJECT_ROOT / "data" / "jobs"
    slurm_command_timeout_seconds: float = 10.0
    slurm_query_cache_ttl_seconds: float = 2.0
    slurm_max_jobs: int = 1000
    dashboard_owner: str = "demo-user"
    native_submission_enabled: bool = False
    native_max_active_jobs: int = 1
    native_logs_enabled: bool = False
    native_cancel_enabled: bool = False
    native_clone_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @field_validator(
        "slurm_fixture_directory",
        "fixture_job_output_directory",
        "job_workspace_directory",
        mode="before",
    )
    @classmethod
    def resolve_fixture_directory(cls, value: object) -> Path:
        path = Path(value) if isinstance(value, (str, Path)) else Path(str(value))
        return path if path.is_absolute() else PROJECT_ROOT / path

    @field_validator("database_url", mode="before")
    @classmethod
    def resolve_database_url(cls, value: object) -> str:
        database_url = str(value)
        relative_prefix = "sqlite:///./"
        if database_url.startswith(relative_prefix):
            database_path = PROJECT_ROOT / database_url.removeprefix(relative_prefix)
            return f"sqlite:///{database_path.as_posix()}"
        return database_url

    @field_validator("slurm_command_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 0.1 <= value <= 120:
            raise ValueError("SLURM_COMMAND_TIMEOUT_SECONDS must be between 0.1 and 120")
        return value

    @field_validator("slurm_query_cache_ttl_seconds")
    @classmethod
    def validate_cache_ttl(cls, value: float) -> float:
        if not 0.1 <= value <= 60:
            raise ValueError("SLURM_QUERY_CACHE_TTL_SECONDS must be between 0.1 and 60")
        return value

    @field_validator("slurm_max_jobs")
    @classmethod
    def validate_max_jobs(cls, value: int) -> int:
        if not 1 <= value <= 10000:
            raise ValueError("SLURM_MAX_JOBS must be between 1 and 10000")
        return value

    @field_validator("native_max_active_jobs")
    @classmethod
    def validate_native_max_active_jobs(cls, value: int) -> int:
        if not 1 <= value <= 100:
            raise ValueError("NATIVE_MAX_ACTIVE_JOBS must be between 1 and 100")
        return value

    @field_validator("dashboard_owner")
    @classmethod
    def validate_dashboard_owner(cls, value: str) -> str:
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", value, re.ASCII) is None:
            raise ValueError("DASHBOARD_OWNER must be one platform username")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
