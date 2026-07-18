import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.jobs import JobSubmitRequest
from app.services.test_projects import (
    TestProjectCatalog as ProjectCatalog,
    TestProjectError as ProjectError,
)
from app.slurm.submission import (
    SubmissionValidationError,
    build_submission_plan,
    materialize_submission,
)


def create_project(root: Path, project_id: str = "cpu-smoke") -> Path:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    root.chmod(0o700)
    directory = root / project_id
    directory.mkdir(mode=0o700)
    manifest = directory / "project.json"
    manifest.write_text(
        json.dumps(
            {
                "id": project_id,
                "name": "CPU smoke",
                "description": "Controlled test project",
                "entrypoint": "main.py",
                "expected_outcome": "COMPLETED",
                "resources": {
                    "cpus": 1,
                    "memory_mb": 512,
                    "gpus": 0,
                    "time_limit_minutes": 2,
                },
            }
        ),
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    source = directory / "main.py"
    source.write_text('print("ok", flush=True)\n', encoding="utf-8")
    source.chmod(0o600)
    return directory


def submission(command: str = "python3 @project/cpu-smoke") -> JobSubmitRequest:
    return JobSubmitRequest.model_validate(
        {
            "name": "accept-cpu-smoke",
            "command": command,
            "partition": "Students",
            "account": "stu",
            "qos": "qos_stu_default",
            "resources": {
                "cpus": 1,
                "memory_mb": 512,
                "gpus": 0,
                "time_limit_minutes": 2,
            },
        }
    )


def test_registered_project_is_listed_without_exposing_paths(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    create_project(root)
    project = ProjectCatalog(root).list_projects()[0]

    assert project.id == "cpu-smoke"
    assert project.command == "python3 @project/cpu-smoke"
    assert project.resources.memory_mb == 512


def test_projects_api_returns_registered_metadata_without_source_path(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    create_project(root)
    settings = Settings(
        _env_file=None,
        test_project_directory=root,
        database_url="sqlite://",
    )

    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/projects")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["command"] == "python3 @project/cpu-smoke"
    assert str(root) not in response.text


def test_registered_project_is_copied_into_private_submission_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    create_project(root)
    plan = build_submission_plan(
        submission(),
        owner="demo-user",
        workspace_root=tmp_path / "jobs",
        submission_id="submission-0123456789abcdef0123456789abcdef",
        project_catalog=ProjectCatalog(root),
    )

    materialize_submission(plan)

    snapshot = plan.directory / "source" / "main.py"
    assert snapshot.read_text(encoding="utf-8") == 'print("ok", flush=True)\n'
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert "source/main.py" in plan.script_path.read_text(encoding="utf-8")
    assert "@project" not in plan.script_path.read_text(encoding="utf-8")


def test_unknown_project_fails_before_workspace_write(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    create_project(root)
    workspace = tmp_path / "jobs"

    with pytest.raises(SubmissionValidationError):
        build_submission_plan(
            submission("python3 @project/not-found"),
            owner="demo-user",
            workspace_root=workspace,
            project_catalog=ProjectCatalog(root),
        )

    assert not workspace.exists()


def test_symlink_and_group_writable_sources_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    directory = create_project(root)
    source = directory / "main.py"
    target = directory / "actual.py"
    source.rename(target)
    source.symlink_to(target)
    with pytest.raises(ProjectError):
        ProjectCatalog(root).get("cpu-smoke")

    source.unlink()
    target.rename(source)
    source.chmod(0o620)
    with pytest.raises(ProjectError):
        ProjectCatalog(root).get("cpu-smoke")
