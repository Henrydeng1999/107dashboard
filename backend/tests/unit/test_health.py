from fastapi.testclient import TestClient

from app.main import app


def test_health_check() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "dashboard-api"


def test_default_runtime_reports_fixture_capabilities() -> None:
    response = TestClient(app).get("/api/runtime")

    assert response.status_code == 200
    assert response.json() == {
        "data_source": "fixture",
        "read_only": False,
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
