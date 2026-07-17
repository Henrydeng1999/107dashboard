from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _submission() -> dict[str, object]:
    return {
        "name": "demo-training",
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


def test_fixture_mvp_story_runs_as_one_repeatable_flow() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))

    assert client.get("/api/health").status_code == 200
    initial_jobs = client.get("/api/jobs").json()
    assert initial_jobs["total"] == 5

    completed_id = "slurm-899998"
    assert client.get(f"/api/jobs/{completed_id}").json()["state"] == "COMPLETED"
    stdout = client.get(
        f"/api/jobs/{completed_id}/logs",
        params={"stream": "stdout", "limit": 32},
    ).json()
    assert stdout["available"] is True
    assert stdout["next_offset"] == 32
    assert client.get(
        f"/api/jobs/{completed_id}/logs",
        params={"stream": "stdout", "offset": stdout["next_offset"]},
    ).status_code == 200
    usage = client.get(f"/api/jobs/{completed_id}/usage").json()
    assert usage["allocated"]["gpus"] == 1
    assert usage["gpu_utilization_percent"] is None

    submitted = client.post("/api/jobs", json=_submission())
    assert submitted.status_code == 201
    submitted_job = submitted.json()
    assert submitted_job["state"] == "PENDING"
    assert client.get(f"/api/jobs/{submitted_job['id']}").status_code == 200
    assert client.get(f"/api/jobs/{submitted_job['id']}/logs").json()["available"] is False

    cancelled = client.post(f"/api/jobs/{submitted_job['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"

    cloned = client.post(f"/api/jobs/{submitted_job['id']}/clone")
    assert cloned.status_code == 201
    assert cloned.json()["id"] != submitted_job["id"]
    assert cloned.json()["state"] == "PENDING"

    summary = client.get("/api/jobs/summary").json()
    assert summary["total_jobs"] == 7
    assert summary["state_counts"]["CANCELLED"] == 2
    assert summary["state_counts"]["PENDING"] == 2
    assert summary["resources"]["gpus"] == 4
