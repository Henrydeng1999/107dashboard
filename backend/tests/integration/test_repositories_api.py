from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_repository_api_is_disabled_without_configured_root() -> None:
    client = TestClient(create_app(Settings(database_url="sqlite://")))
    response = client.get("/api/repositories")
    assert response.status_code == 200
    assert response.json() == {"enabled": False, "items": []}


def test_repository_api_returns_only_safe_read_data(tmp_path: Path) -> None:
    repository = tmp_path / "demo"
    repository.mkdir()
    subprocess.run(["git", "-C", str(repository), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "API Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "api@example.invalid"],
        check=True,
    )
    (repository / "README.md").write_text("# Demo\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-q", "-m", "API commit"], check=True)

    client = TestClient(
        create_app(Settings(database_url="sqlite://", git_repository_root=tmp_path))
    )
    listed = client.get("/api/repositories")
    assert listed.status_code == 200
    repository_id = listed.json()["items"][0]["id"]
    assert str(tmp_path) not in listed.text

    detail = client.get(f"/api/repositories/{repository_id}")
    assert detail.status_code == 200
    assert detail.json()["readme_content"] == "# Demo\n"
    revision = detail.json()["commits"][0]["hash"]
    commit = client.get(f"/api/repositories/{repository_id}/commits/{revision}")
    assert commit.status_code == 200
    assert commit.json()["subject"] == "API commit"

    assert client.get("/api/repositories/not-a-valid-id").status_code == 422
    assert client.get(f"/api/repositories/{repository_id}/commits/HEAD").status_code == 422
