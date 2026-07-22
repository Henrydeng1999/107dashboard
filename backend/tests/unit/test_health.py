from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import app, create_app


def test_health_check() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "dashboard-api"


def test_explicit_test_runtime_reports_fixture_capabilities() -> None:
    response = TestClient(app).get("/api/runtime")

    assert response.status_code == 200
    assert response.json() == {
        "data_source": "fixture",
        "serving_source": "fixture",
        "read_only": False,
        "degraded": False,
        "demo_fallback_enabled": False,
        "fallback_reason": None,
        "capabilities": {
            "list_jobs": True,
            "job_details": True,
            "usage": True,
            "submit": True,
            "cancel": True,
            "clone": True,
            "logs": True,
        },
    }


def test_built_frontend_can_be_served_without_hiding_api(tmp_path) -> None:
    (tmp_path / "index.html").write_text("<h1>Dashboard</h1>", encoding="utf-8")
    client = TestClient(
        create_app(
            Settings(
                _env_file=None,
                serve_frontend=True,
                frontend_dist_directory=tmp_path,
                database_url=f"sqlite:///{(tmp_path / 'dashboard.sqlite3').as_posix()}",
            )
        )
    )

    frontend_response = client.get("/")
    assert frontend_response.text == "<h1>Dashboard</h1>"
    assert frontend_response.headers["cache-control"] == "no-cache, must-revalidate"
    assert client.get("/api/health").json()["status"] == "ok"


def test_frontend_serving_fails_fast_when_build_is_missing(tmp_path) -> None:
    with pytest.raises(ValueError, match="built frontend"):
        create_app(
            Settings(
                _env_file=None,
                serve_frontend=True,
                frontend_dist_directory=tmp_path,
                database_url=f"sqlite:///{(tmp_path / 'dashboard.sqlite3').as_posix()}",
            )
        )
