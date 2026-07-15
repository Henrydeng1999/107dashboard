from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_list_jobs_returns_demo_jobs() -> None:
    response = client.get("/api/jobs")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["slurm_job_id"] == "21482"


def test_list_jobs_filters_by_state() -> None:
    response = client.get("/api/jobs", params={"state": "COMPLETED"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["state"] == "COMPLETED"


def test_job_detail_hides_unknown_job() -> None:
    response = client.get("/api/jobs/not-found")

    assert response.status_code == 404
