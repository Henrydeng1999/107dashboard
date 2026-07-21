"""Unit tests for ProductService.test_provider().

Covers all branches of _test_connection through monkeypatched urllib:
  - Successful connection (200 + valid JSON)
  - HTTP 401 (auth failure)
  - HTTP 403 (auth failure, different code)
  - HTTP 500 (reachable but upstream error)
  - OSError / URLError (unreachable)
  - Malformed response JSON / missing keys
  - Provider not found (no DB row)
  - Exists but secret file missing (not configured)
"""

import json
import urllib.error
import urllib.request

import pytest

from app.repositories.product import ProductRepository
from app.services.product import (
    AiProviderNotConfigured,
    ProductService,
)


class _StubResponse:
    """Mimics http.client.HTTPResponse for urlopen monkeypatches."""

    def __init__(self, status: int, body: bytes, reason: str = "OK") -> None:
        self.status = status
        self.body = body
        self.reason = reason

    def __enter__(self) -> "_StubResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self, limit: int = -1) -> bytes:  # noqa: ARG002
        return self.body


def _stub_urlopen(body: bytes | None = None, status: int = 200, exc: type[Exception] | None = None):
    """Return a urlopen replacement. When exc is set, raise it unconditionally."""

    def urlopen(request: urllib.request.Request, timeout: float = 30) -> _StubResponse:
        if exc is not None:
            raise exc
        if status in (401, 403):
            raise urllib.error.HTTPError(
                url=request.full_url or "/stub",
                code=status,
                msg="Unauthorized" if status == 401 else "Forbidden",
                hdrs={},
                fp=None,
            )
        if status >= 500:
            raise urllib.error.HTTPError(
                url=request.full_url or "/stub",
                code=status,
                msg="Internal Server Error",
                hdrs={},
                fp=None,
            )
        return _StubResponse(status=status, body=body or b"{}")

    return urlopen


def _service(tmp_path) -> ProductService:
    repo = ProductRepository("sqlite://")
    repo.initialize()
    secret_dir = tmp_path / "secrets"
    secret_dir.mkdir(parents=True, exist_ok=True)
    svc = ProductService(owner="tester", repository=repo, secret_directory=secret_dir)

    # Insert a provider record
    repo.upsert_provider(
        owner="tester",
        provider_id="test-provider",
        name="Test AI",
        base_url="https://ai.test.example/v1",
        model="test-model-v1",
        key_hint="••••test",
    )
    # Write the secret file
    secret_path = secret_dir / "test-provider.key"
    secret_path.write_text("sk-test-secret", encoding="utf-8")
    return svc


class TestProviderTest:
    def test_not_found(self, tmp_path):
        """Provider record does not exist in DB."""
        repo = ProductRepository("sqlite://")
        repo.initialize()
        svc = ProductService(owner="tester", repository=repo, secret_directory=tmp_path / "secrets")
        with pytest.raises(AiProviderNotConfigured, match="not found"):
            svc.test_provider("nonexistent")

    def test_not_configured_no_secret(self, tmp_path):
        """Provider record exists but secret file is missing."""
        repo = ProductRepository("sqlite://")
        repo.initialize()
        secret_dir = tmp_path / "secrets"
        secret_dir.mkdir(parents=True, exist_ok=True)
        svc = ProductService(owner="tester", repository=repo, secret_directory=secret_dir)
        repo.upsert_provider(
            owner="tester",
            provider_id="no-key",
            name="No Key",
            base_url="https://no-key.example/v1",
            model="m",
            key_hint=None,
        )
        result = svc.test_provider("no-key")
        assert result.configured is False
        assert result.reachable is False
        assert result.authenticated is False
        assert result.error == "API key not configured"
        assert result.key_hint is None

    def test_success(self, tmp_path, monkeypatch):
        """200 with valid OpenAI-compatible response → all green."""
        svc = _service(tmp_path)
        valid_body = json.dumps(
            {
                "id": "cmpl-stub",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}}],
            }
        ).encode()
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(body=valid_body, status=200))
        result = svc.test_provider("test-provider")
        assert result.provider_id == "test-provider"
        assert result.configured is True
        assert result.reachable is True
        assert result.authenticated is True
        assert result.model == "test-model-v1"
        assert result.latency_ms is not None and result.latency_ms >= 0
        assert result.error is None
        assert result.key_hint == "••••test"

    def test_http_401_auth_failure(self, tmp_path, monkeypatch):
        """401 → reachable, not authenticated."""
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(body=None, status=401))
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is True
        assert result.authenticated is False
        assert result.error and "401" in result.error
        assert result.key_hint == "••••test"

    def test_http_403_auth_failure(self, tmp_path, monkeypatch):
        """403 → reachable, not authenticated."""
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(body=None, status=403))
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is True
        assert result.authenticated is False
        assert result.key_hint == "••••test"

    def test_http_500_upstream_error(self, tmp_path, monkeypatch):
        """500 → reachable but server error."""
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(body=None, status=500))
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is True
        assert result.authenticated is True  # 500 is not an auth error
        assert "500" in (result.error or "")
        assert result.key_hint == "••••test"

    def test_connection_error(self, tmp_path, monkeypatch):
        """URLError (DNS / network down) → not reachable."""
        monkeypatch.setattr(
            urllib.request, "urlopen", _stub_urlopen(exc=urllib.error.URLError("no route to host"))
        )
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is False
        assert result.authenticated is False
        assert result.error and "Connection failed" in result.error
        assert result.key_hint == "••••test"

    def test_malformed_response(self, tmp_path, monkeypatch):
        """Invalid JSON → reports response format error, still marks reachable + authenticated."""
        monkeypatch.setattr(
            urllib.request, "urlopen", _stub_urlopen(body=b"not-json", status=200)
        )
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is True
        assert result.authenticated is True
        assert result.error and "Unexpected response format" in result.error
        assert result.key_hint == "••••test"

    def test_missing_choices_key(self, tmp_path, monkeypatch):
        """Valid JSON but missing expected key → format error."""
        body = json.dumps({"id": "x", "object": "chat.completion"}).encode()
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(body=body, status=200))
        result = _service(tmp_path).test_provider("test-provider")
        assert result.error and "Unexpected response format" in result.error
        assert result.key_hint == "••••test"

    def test_oserror_reachable(self, tmp_path, monkeypatch):
        """OSError (e.g. connection reset) → not reachable, secret never returned."""
        monkeypatch.setattr(urllib.request, "urlopen", _stub_urlopen(exc=OSError("reset")))
        result = _service(tmp_path).test_provider("test-provider")
        assert result.configured is True
        assert result.reachable is False
        assert result.authenticated is False
        assert result.error and "Connection failed" in result.error
        assert result.key_hint == "••••test"
