import json
from io import BytesIO
import urllib.error
import urllib.request

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app
from app.services.ai_tools import AiReadTools, AiReadToolError
from app.services.product import (
    AiProviderUnavailable,
    AiToolsUnsupported,
    ProductService,
)


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


def test_tool_budget_keeps_assistant_and_tool_messages_complete(tmp_path, monkeypatch) -> None:
    client = _configured_client(tmp_path)
    captured: list[list[dict[str, object]]] = []

    def completion(self, provider, messages, tools):
        captured.append(messages.copy())
        if tools:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{index}",
                        "type": "function",
                        "function": {"name": "get_runtime", "arguments": "{}"},
                    }
                    for index in range(12)
                ],
            }
        return {"content": "预算内查询完成。"}

    monkeypatch.setattr(ProductService, "_provider_completion", completion)
    response = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "检查运行状态", "job_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["tools_used"] == ["get_runtime"] * 8
    final_messages = captured[-1]
    assistant = next(message for message in final_messages if message.get("role") == "assistant")
    tool_messages = [message for message in final_messages if message.get("role") == "tool"]
    assert len(assistant["tool_calls"]) == 8
    assert {call["id"] for call in assistant["tool_calls"]} == {
        message["tool_call_id"] for message in tool_messages
    }


def test_provider_completion_only_downgrades_explicit_unsupported_tools(
    tmp_path, monkeypatch
) -> None:
    service = _configured_client(tmp_path).app.state.product_service
    provider = service.repository.get_provider(service.owner, "school")
    assert provider is not None
    messages = [{"role": "user", "content": "test"}]
    definitions = AiReadTools.definitions()

    def unsupported(_request, timeout=30):
        raise urllib.error.HTTPError(
            "https://ai.example.edu/v1/chat/completions",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"error":{"message":"Unsupported parameter: tools"}}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", unsupported)
    with pytest.raises(AiToolsUnsupported):
        service._provider_completion(provider, messages, definitions)

    def ordinary_bad_request(_request, timeout=30):
        raise urllib.error.HTTPError(
            "https://ai.example.edu/v1/chat/completions",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"error":{"message":"invalid model"}}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", ordinary_bad_request)
    with pytest.raises(AiProviderUnavailable):
        service._provider_completion(provider, messages, definitions)


def test_explicit_unsupported_tools_falls_back_once(tmp_path, monkeypatch) -> None:
    client = _configured_client(tmp_path)
    calls: list[bool] = []

    def completion(self, provider, messages, tools):
        calls.append(tools is not None)
        if tools is not None:
            raise AiToolsUnsupported("unsupported")
        return {"content": "当前 Provider 使用所选结构化上下文回答。"}

    monkeypatch.setattr(ProductService, "_provider_completion", completion)
    response = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "解释当前情况", "job_ids": []},
    )
    assert response.status_code == 200
    assert calls == [True, False]
    assert response.json()["tools_used"] == []


@pytest.mark.parametrize(
    "tool_calls",
    [
        "not-a-list",
        [{"id": "", "type": "function", "function": {"name": "get_runtime", "arguments": "{}"}}],
        [
            {"id": "duplicate", "type": "function", "function": {"name": "get_runtime", "arguments": "{}"}},
            {"id": "duplicate", "type": "function", "function": {"name": "get_runtime", "arguments": "{}"}},
        ],
        [{"id": "call-1", "type": "other", "function": {"name": "get_runtime", "arguments": "{}"}}],
        [{"id": "call-1", "type": "function", "function": {"name": "", "arguments": "{}"}}],
    ],
)
def test_invalid_provider_tool_call_protocol_returns_503(
    tmp_path, monkeypatch, tool_calls
) -> None:
    client = _configured_client(tmp_path)

    monkeypatch.setattr(
        ProductService,
        "_provider_completion",
        lambda self, provider, messages, tools: {
            "content": None,
            "tool_calls": tool_calls,
        },
    )
    response = client.post(
        "/api/ai/chat",
        json={"provider_id": "school", "message": "检查状态", "job_ids": []},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_PROVIDER_UNAVAILABLE"


def test_repository_tools_exclude_free_text_and_paths(tmp_path) -> None:
    client = _configured_client(tmp_path)
    tools = AiReadTools(
        runtime_info_provider=client.app.state.runtime_info_provider,
        jobs=client.app.state.job_catalog,
        product=client.app.state.product_service,
        repositories=client.app.state.git_repository_browser,
        test_projects=client.app.state.test_project_catalog,
    )
    assert "read_job_log" not in {item["function"]["name"] for item in tools.definitions()}
    assert "read_job_log" not in str(tools.definitions())

    repositories = json.loads(tools.execute("list_repositories", {}))["result"]["items"]
    if repositories:
        detail = json.loads(
            tools.execute("get_repository", {"repository_id": repositories[0]["id"]})
        )["result"]
        assert "readme_content" not in detail
        assert "changes" not in detail
        assert "relative_path" not in detail["repository"]
        assert all("author_name" not in commit for commit in detail["commits"])
