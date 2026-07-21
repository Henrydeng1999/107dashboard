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
