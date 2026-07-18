import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "read-native-log-acceptance.py"


def load_acceptance_module():
    spec = spec_from_file_location("native_log_acceptance", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self.payload


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def get(self, url: str, *, params=None) -> FakeResponse:
        self.calls.append((url, params))
        if url == "/api/runtime":
            return FakeResponse(
                {
                    "data_source": "native",
                    "serving_source": "native",
                    "read_only": True,
                    "degraded": False,
                    "demo_fallback_enabled": False,
                    "fallback_reason": None,
                    "capabilities": {
                        "submit": False,
                        "cancel": False,
                        "clone": False,
                        "logs": True,
                    },
                }
            )
        stream = str(params["stream"])
        content = "sensitive stdout text" if stream == "stdout" else ""
        return FakeResponse(
            {
                "job_id": "slurm-24011",
                "stream": stream,
                "content": content,
                "offset": 0,
                "next_offset": 21 if stream == "stdout" else 0,
                "eof": True,
                "available": stream == "stdout",
            }
        )


def test_exact_confirmation_is_required() -> None:
    module = load_acceptance_module()
    with pytest.raises(PermissionError):
        module.require_confirmation("yes")
    module.require_confirmation(module.CONFIRMATION)


def test_native_read_only_settings_are_required() -> None:
    module = load_acceptance_module()
    module.validate_settings(
        Settings(
            _env_file=None,
            slurm_data_source="native",
            native_logs_enabled=True,
            native_submission_enabled=False,
        )
    )
    with pytest.raises(RuntimeError, match="SUBMISSION"):
        module.validate_settings(
            Settings(
                _env_file=None,
                slurm_data_source="native",
                native_logs_enabled=True,
                native_submission_enabled=True,
            )
        )


def test_acceptance_reads_each_stream_once_without_emitting_content() -> None:
    module = load_acceptance_module()
    client = FakeClient()

    evidence = module.collect_log_evidence(client, owner="pb24030760")

    assert len(client.calls) == 3
    assert [call[1]["stream"] for call in client.calls[1:]] == ["stdout", "stderr"]
    assert all(call[1]["offset"] == 0 for call in client.calls[1:])
    assert all(call[1]["limit"] == 4096 for call in client.calls[1:])
    assert evidence["raw_content_emitted"] is False
    assert evidence["streams"][0]["bytes_read"] == 21
    assert "sensitive stdout text" not in json.dumps(evidence)


def test_unsafe_runtime_capabilities_stop_before_log_read() -> None:
    module = load_acceptance_module()

    class UnsafeClient(FakeClient):
        def get(self, url: str, *, params=None) -> FakeResponse:
            response = super().get(url, params=params)
            if url == "/api/runtime":
                response.payload["capabilities"]["submit"] = True
            return response

    client = UnsafeClient()
    with pytest.raises(RuntimeError, match="unsafe"):
        module.collect_log_evidence(client, owner="pb24030760")
    assert len(client.calls) == 1
