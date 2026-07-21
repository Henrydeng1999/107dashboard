import os
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.product import ProductService


def test_reports_projects_and_ai_workspace(tmp_path, monkeypatch) -> None:
    settings = Settings(
        database_url="sqlite://",
        slurm_data_source="fixture",
        dashboard_owner="demo-user",
        ai_secret_directory=tmp_path / "ai-secrets",
    )
    client = TestClient(create_app(settings=settings))

    reports = client.get("/api/reports")
    assert reports.status_code == 200
    report_items = reports.json()["items"]
    assert len(report_items) == 5
    assert all(item["evidence"] for item in report_items)
    assert all(0 <= item["health_score"] <= 100 for item in report_items)

    jobs = client.get("/api/jobs?page=1&page_size=20").json()["items"]
    unknown_project = client.post(
        "/api/evaluation-projects",
        json={"name": "invalid-review", "description": "", "job_ids": ["job-missing"]},
    )
    assert unknown_project.status_code == 404

    project = client.post(
        "/api/evaluation-projects",
        json={
            "name": "fixture-review",
            "description": "local integration",
            "job_ids": [jobs[0]["id"], jobs[1]["id"]],
        },
    )
    assert project.status_code == 201
    assert len(project.json()["jobs"]) == 2
    assert 0 <= project.json()["evidence_coverage_percent"] <= 100
    assert client.get("/api/evaluation-projects").json()["items"][0]["id"] == project.json()["id"]

    unconfigured = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "解释作业", "job_ids": []},
    )
    assert unconfigured.status_code == 409

    provider = client.put(
        "/api/ai/providers/school",
        json={
            "name": "学校 AI 服务",
            "base_url": "https://ai.example.edu/v1",
            "model": "school-chat-pro",
            "api_key": "test-secret-value",
        },
    )
    assert provider.status_code == 200
    assert provider.json()["configured"] is True
    assert provider.json()["models"] == ["school-chat-pro"]
    assert provider.json()["key_hint"] == "••••alue"
    assert "test-secret-value" not in provider.text
    assert "test-secret-value" not in client.get("/api/ai/providers").text
    secret_path = tmp_path / "ai-secrets" / "school.key"
    assert secret_path.read_text(encoding="utf-8") == "test-secret-value"
    if os.name != "nt":
        assert secret_path.stat().st_mode & 0o777 == 0o600

    prompts: list[str] = []

    def answer(self, metadata, prompt, tools=None):
        prompts.append(prompt)
        return "基于结构化证据的测试回答", []

    monkeypatch.setattr(ProductService, "_call_provider", answer)
    chat = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "解释作业", "job_ids": [jobs[0]["id"]]},
    )
    assert chat.status_code == 200
    assert chat.json()["answer"] == "基于结构化证据的测试回答"
    assert chat.json()["model"] == "school-chat-pro"

    templates = client.get("/api/ai/templates").json()["items"]
    assert all(item["customized"] is False for item in templates)
    edited = client.put(
        "/api/ai/templates/job-diagnosis",
        json={"system_prompt": "优先比较退出码和资源效率。"},
    )
    assert edited.status_code == 200
    assert edited.json()["customized"] is True

    repository_id = "a" * 16
    client.app.state.git_repository_browser = SimpleNamespace(
        detail=lambda selected: SimpleNamespace(
            repository=SimpleNamespace(
                id=selected,
                name="demo-repository",
                branch="master",
                head="b" * 40,
                dirty=False,
                changed_files=0,
            ),
            commits=[SimpleNamespace(
                hash="b" * 40,
                subject="test commit",
                authored_at=datetime.now(UTC),
            )],
        )
    )
    contextual = client.post(
        "/api/ai/chat",
        json={
            "provider_id": "school",
            "message": "结合仓库分析作业",
            "job_ids": [jobs[0]["id"]],
            "repository_ids": [repository_id],
            "template_id": "job-diagnosis",
        },
    )
    assert contextual.status_code == 200
    assert contextual.json()["evidence_repository_ids"] == [repository_id]
    assert contextual.json()["template_id"] == "job-diagnosis"
    assert "优先比较退出码和资源效率" in prompts[-1]
    assert "demo-repository" in prompts[-1]
    restored = client.delete("/api/ai/templates/job-diagnosis")
    assert restored.status_code == 200
    assert restored.json()["customized"] is False

    client.post(
        "/api/ai/providers/school/models",
        json={"model": "second-model"},
    )
    selected_chat = client.post(
        "/api/ai/chat",
        json={
            "provider_id": "school",
            "model": "second-model",
            "message": "使用指定模型",
            "job_ids": [],
        },
    )
    assert selected_chat.status_code == 200
    assert selected_chat.json()["model"] == "second-model"
    unknown_model = client.post(
        "/api/ai/chat",
        json={
            "provider_id": "school",
            "model": "not-added",
            "message": "不应调用",
            "job_ids": [],
        },
    )
    assert unknown_model.status_code == 409
    assert client.get("/api/ai/calls").json()["items"][0]["status"] == "SUCCEEDED"
    assert len(client.get("/api/ai/templates").json()["items"]) == 2

    invalid_provider = client.put(
        "/api/ai/providers/not.valid",
        json={
            "name": "Invalid",
            "base_url": "https://ai.example.edu/v1",
            "model": "test-model",
            "api_key": "another-secret",
        },
    )
    assert invalid_provider.status_code == 422
    assert not (tmp_path / "ai-secrets" / "not.valid.key").exists()
