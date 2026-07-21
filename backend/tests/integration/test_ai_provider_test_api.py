"""Integration tests for the POST /api/ai/providers/{provider_id}/test endpoint.

These tests exercise the full FastAPI stack with a TestClient.
The actual HTTP call is monkeypatched at the urllib level so no real
outbound network requests are made.
"""

import json
import urllib.error
import urllib.request

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


class _StubResponse:
    def __init__(self, status: int, body: bytes, reason: str = "OK") -> None:
        self.status = status
        self.body = body
        self.reason = reason

    def __enter__(self) -> "_StubResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self, limit: int = -1) -> bytes:
        return self.body


def _make_client(tmp_path):
    settings = Settings(
        database_url="sqlite://",
        slurm_data_source="fixture",
        dashboard_owner="integration-tester",
        ai_secret_directory=tmp_path / "ai-secrets",
    )
    return TestClient(create_app(settings=settings))


VALID_COMPLETION = json.dumps(
    {
        "id": "cmpl-int",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi there"}}],
    }
).encode()


class TestAiProviderTestApi:
    def test_not_found_returns_404(self, tmp_path):
        """POST to a provider_id that has no DB record → 404."""
        client = _make_client(tmp_path)
        resp = client.post("/api/ai/providers/ghost-provider/test")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"]["code"] == "AI_PROVIDER_NOT_FOUND"

    def test_not_configured(self, tmp_path):
        """Provider in DB but without secret file → 200 with configured=False."""
        client = _make_client(tmp_path)
        # Create the provider without an API key
        client.put(
            "/api/ai/providers/no-key",
            json={
                "name": "No Secret",
                "base_url": "https://no-key.example/v1",
                "model": "m",
            },
        )
        resp = client.post("/api/ai/providers/no-key/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["reachable"] is False
        assert body["authenticated"] is False
        assert "not configured" in (body["error"] or "")

    def test_success(self, tmp_path, monkeypatch):
        """Happy path → 200 with full success result."""
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda _request, timeout=30: _StubResponse(200, VALID_COMPLETION),
        )
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/good-ai",
            json={
                "name": "Good AI",
                "base_url": "https://good.example.com/v1",
                "model": "gpt-4",
                "api_key": "sk-good-key-1234",
            },
        )
        resp = client.post("/api/ai/providers/good-ai/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_id"] == "good-ai"
        assert body["configured"] is True
        assert body["reachable"] is True
        assert body["authenticated"] is True
        assert body["model"] == "gpt-4"
        assert body["latency_ms"] is not None and body["latency_ms"] >= 0
        assert body["error"] is None
        # The API key must never appear in the response
        assert "sk-good-key-1234" not in resp.text

    def test_auth_failure(self, tmp_path, monkeypatch):
        """401 from upstream → authenticated=False, no key leak."""
        def _fail_auth(request, timeout=30):
            raise urllib.error.HTTPError(
                url=request.full_url or "/stub",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fail_auth)
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/auth-bad",
            json={
                "name": "Bad Auth",
                "base_url": "https://bad-auth.example/v1",
                "model": "m",
                "api_key": "sk-bad-secret",
            },
        )
        resp = client.post("/api/ai/providers/auth-bad/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["reachable"] is True
        assert body["authenticated"] is False
        assert "401" in (body["error"] or "")
        assert "sk-bad-secret" not in resp.text

    def test_upstream_error(self, tmp_path, monkeypatch):
        """500 from upstream → reachable=True, authenticated=True."""
        def _fail_500(request, timeout=30):
            raise urllib.error.HTTPError(
                url=request.full_url or "/stub",
                code=500,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fail_500)
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/err-ai",
            json={
                "name": "Error",
                "base_url": "https://error.example/v1",
                "model": "m",
                "api_key": "sk-err-secret",
            },
        )
        resp = client.post("/api/ai/providers/err-ai/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["reachable"] is True
        assert body["authenticated"] is True  # 500 is not auth failure
        assert "500" in (body["error"] or "")

    def test_unreachable(self, tmp_path, monkeypatch):
        """Network error → configured=True, reachable=False."""
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda _request, timeout=30: (_ for _ in ()).throw(
                urllib.error.URLError("no route to host")
            ),
        )
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/down-ai",
            json={
                "name": "Down",
                "base_url": "https://down.example/v1",
                "model": "m",
                "api_key": "sk-down-secret",
            },
        )
        resp = client.post("/api/ai/providers/down-ai/test")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is True
        assert body["reachable"] is False
        assert body["authenticated"] is False
        assert body.get("key_hint") is not None

    def test_invalid_provider_id_returns_422(self, tmp_path):
        """Non-conforming provider_id (e.g. dots) → 422."""
        client = _make_client(tmp_path)
        resp = client.post("/api/ai/providers/invalid.id/test")
        assert resp.status_code == 422

    def test_does_not_replay_secret_in_response(self, tmp_path, monkeypatch):
        """Guard: full response text must never contain the raw API key."""
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda _request, timeout=30: _StubResponse(200, VALID_COMPLETION),
        )
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/secret-guard",
            json={
                "name": "Secret Guard",
                "base_url": "https://guard.example/v1",
                "model": "g",
                "api_key": "super-secret-key-9999",
            },
        )
        resp = client.post("/api/ai/providers/secret-guard/test")
        assert resp.status_code == 200
        assert "super-secret-key-9999" not in resp.text


class TestAiProviderModelsApi:
    def test_discovers_sanitized_models(self, tmp_path, monkeypatch):
        body = json.dumps(
            {
                "data": [
                    {"id": "qwen3.5"},
                    {"id": "deepseek-v4-pro"},
                    {"id": "qwen3.5"},
                    {"id": "invalid model"},
                    {"unexpected": "ignored"},
                ]
            }
        ).encode()
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda _request, timeout=30: _StubResponse(200, body),
        )
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )

        response = client.get("/api/ai/providers/school/models")

        assert response.status_code == 200
        assert response.json()["models"] == ["deepseek-v4-pro", "qwen3.5"]
        assert response.json()["count"] == 2
        assert response.json()["latency_ms"] >= 0
        assert "school-secret-key" not in response.text

    def test_model_discovery_requires_configured_provider(self, tmp_path):
        client = _make_client(tmp_path)
        response = client.get("/api/ai/providers/missing/models")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "AI_PROVIDER_NOT_FOUND"

    def test_model_discovery_hides_upstream_error(self, tmp_path, monkeypatch):
        def _fail(request, timeout=30):
            raise urllib.error.HTTPError(
                url=request.full_url or "/stub",
                code=502,
                msg="upstream-secret-detail",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fail)
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )
        response = client.get("/api/ai/providers/school/models")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_PROVIDER_UNAVAILABLE"
        assert "upstream-secret-detail" not in response.text
        assert "school-secret-key" not in response.text

    def test_selected_model_can_be_tested_without_saving(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda _request, timeout=30: _StubResponse(200, VALID_COMPLETION),
        )
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )
        response = client.post(
            "/api/ai/providers/school/models/test",
            json={"model": "qwen3.5"},
        )
        assert response.status_code == 200
        assert response.json()["model"] == "qwen3.5"
        provider = client.get("/api/ai/providers").json()["items"][0]
        assert provider["model"] == "deepseek-v4-pro"
        assert "school-secret-key" not in response.text

    def test_add_set_default_and_delete_models(self, tmp_path):
        client = _make_client(tmp_path)
        created = client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )
        assert created.json()["models"] == ["deepseek-v4-pro"]

        added = client.post(
            "/api/ai/providers/school/models",
            json={"model": "qwen3.5"},
        )
        assert added.status_code == 200
        assert added.json()["models"] == ["deepseek-v4-pro", "qwen3.5"]
        assert added.json()["model"] == "deepseek-v4-pro"

        selected = client.put(
            "/api/ai/providers/school/models/default",
            json={"model": "qwen3.5"},
        )
        assert selected.status_code == 200
        assert selected.json()["model"] == "qwen3.5"

        deleted = client.delete(
            "/api/ai/providers/school/models",
            params={"model": "qwen3.5"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["models"] == ["deepseek-v4-pro"]
        assert deleted.json()["model"] == "deepseek-v4-pro"

    def test_cannot_delete_last_model(self, tmp_path):
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )
        response = client.delete(
            "/api/ai/providers/school/models",
            params={"model": "deepseek-v4-pro"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "AI_PROVIDER_MODEL_REQUIRED"

    def test_rejects_unknown_default_and_invalid_delete_model(self, tmp_path):
        client = _make_client(tmp_path)
        client.put(
            "/api/ai/providers/school",
            json={
                "name": "School AI",
                "base_url": "https://school.example/v1",
                "model": "deepseek-v4-pro",
                "api_key": "school-secret-key",
            },
        )
        unknown = client.put(
            "/api/ai/providers/school/models/default",
            json={"model": "not-added"},
        )
        invalid = client.delete(
            "/api/ai/providers/school/models",
            params={"model": "bad model"},
        )
        assert unknown.status_code == 404
        assert invalid.status_code == 422
