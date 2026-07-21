import json

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.ai_tools import AiReadTools, AiReadToolError
from app.services.product import ProductService


def _configured_client(tmp_path) -> TestClient:
    settings = Settings(
        database_url="sqlite://",
        slurm_data_source="fixture",
        dashboard_owner="demo-user",
        ai_secret_directory=tmp_path / "ai-secrets",
    )
    client = TestClient(create_app(settings=settings))
    response = client.put(
        "/api/ai/providers/school",
        json={
            "name": "School AI",
            "base_url": "https://ai.example.edu/v1",
            "model": "school-chat-pro",
            "api_key": "test-secret-value",
        },
    )
    assert response.status_code == 200
    return client


def test_registry_contains_only_explicit_read_tools() -> None:
    names = {item["function"]["name"] for item in AiReadTools.definitions()}
    assert names == {
        "get_runtime",
        "list_jobs",
        "get_job_summary",
        "get_job",
        "get_job_usage",
        "read_job_log",
        "list_reports",
        "get_report",
        "list_evaluation_projects",
        "get_evaluation_project",
        "list_test_projects",
        "list_repositories",
        "get_repository",
        "get_commit",
    }
    assert all(
        item["function"]["parameters"]["additionalProperties"] is False
        for item in AiReadTools.definitions()
    )


def test_tool_calling_loop_queries_backend_and_redacts_jobs(tmp_path, monkeypatch) -> None:
    client = _configured_client(tmp_path)
    provider_messages: list[list[dict[str, object]]] = []

    def completion(self, provider, messages, tools):
        provider_messages.append(messages.copy())
        if tools and not any(message.get("role") == "tool" for message in messages):
            assert all(item["function"]["name"] != "submit_job" for item in tools)
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "list_jobs", "arguments": '{"page_size":2}'},
                    }
                ],
            }
        return {"content": "查询后共有作业记录。"}

    monkeypatch.setattr(ProductService, "_provider_completion", completion)
    response = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "现在有哪些作业？", "job_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "查询后共有作业记录。"
    assert response.json()["tools_used"] == ["list_jobs"]

    tool_message = provider_messages[1][-1]
    assert tool_message["role"] == "tool"
    payload = json.loads(tool_message["content"])
    assert payload["source"] == "107-dashboard:list_jobs"
    assert payload["trust"] == "untrusted_data"
    assert payload["result"]["items"]
    for job in payload["result"]["items"]:
        assert "owner" not in job
        assert "command" not in job
        assert "node" not in job
        assert "account" not in job
        assert "qos" not in job


def test_unknown_or_write_tool_is_rejected(tmp_path) -> None:
    client = _configured_client(tmp_path)
    app = client.app
    tools = AiReadTools(
        runtime_info_provider=app.state.runtime_info_provider,
        jobs=app.state.job_catalog,
        product=app.state.product_service,
        repositories=app.state.git_repository_browser,
        test_projects=app.state.test_project_catalog,
    )
    for name in ("submit_job", "cancel_job", "http_get", "read_file"):
        try:
            tools.execute(name, {})
        except AiReadToolError:
            pass
        else:
            raise AssertionError(f"forbidden tool was accepted: {name}")

    try:
        tools.execute("list_jobs", {"page_size": 2, "method": "DELETE"})
    except AiReadToolError:
        pass
    else:
        raise AssertionError("unknown arguments were accepted")

    for name, arguments in (
        ("get_job", {"job_id": "../../etc/passwd"}),
        ("get_evaluation_project", {"project_id": "project-not-a-valid-id"}),
        ("get_repository", {"repository_id": "../repository"}),
        ("get_commit", {"repository_id": "0" * 16, "revision": "HEAD"}),
    ):
        try:
            tools.execute(name, arguments)
        except AiReadToolError:
            pass
        else:
            raise AssertionError(f"invalid identifier was accepted: {name}")
