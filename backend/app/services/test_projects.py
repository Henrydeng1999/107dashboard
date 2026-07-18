from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat

from app.schemas.jobs import JobSubmitResources


class TestProjectError(ValueError):
    """A registered test project is missing or violates the controlled boundary."""


_PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{1,31}", re.ASCII)
_ENTRYPOINT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.py", re.ASCII)
_MAX_SOURCE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class TestProject:
    id: str
    name: str
    description: str
    entrypoint: str
    expected_outcome: str
    resources: JobSubmitResources
    source_path: Path

    @property
    def command(self) -> str:
        return f"python3 @project/{self.id}"


class TestProjectCatalog:
    def __init__(self, root: Path) -> None:
        self._root = root.absolute()

    def list_projects(self) -> list[TestProject]:
        if not self._root.is_dir():
            return []
        self._require_private_owner_path(self._root)
        projects = [self._load(path.name) for path in self._root.iterdir() if path.is_dir()]
        return sorted(projects, key=lambda project: project.id)

    def get(self, project_id: str) -> TestProject:
        if _PROJECT_ID.fullmatch(project_id) is None:
            raise TestProjectError("test project identifier is invalid")
        self._require_private_owner_path(self._root)
        return self._load(project_id)

    def _load(self, project_id: str) -> TestProject:
        if _PROJECT_ID.fullmatch(project_id) is None:
            raise TestProjectError("test project identifier is invalid")
        directory = (self._root / project_id).resolve()
        if not directory.is_relative_to(self._root) or not directory.is_dir():
            raise TestProjectError("test project is unavailable")
        self._require_private_owner_path(directory)
        manifest_path = directory / "project.json"
        self._require_private_owner_file(manifest_path, 16 * 1024)
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("id") != project_id:
                raise TestProjectError("test project manifest does not match its directory")
            name = self._text(payload, "name", 64)
            description = self._text(payload, "description", 240)
            expected_outcome = self._text(payload, "expected_outcome", 32)
            if expected_outcome not in {"COMPLETED", "FAILED", "CANCELLED"}:
                raise TestProjectError("test project expected outcome is invalid")
            entrypoint = self._text(payload, "entrypoint", 64)
            if _ENTRYPOINT.fullmatch(entrypoint) is None:
                raise TestProjectError("test project entrypoint is invalid")
            resources = JobSubmitResources.model_validate(payload.get("resources"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise TestProjectError("test project manifest is unavailable") from exc
        source_path = directory / entrypoint
        self._require_private_owner_file(source_path, _MAX_SOURCE_BYTES)
        return TestProject(
            id=project_id,
            name=name,
            description=description,
            entrypoint=entrypoint,
            expected_outcome=expected_outcome,
            resources=resources,
            source_path=source_path,
        )

    @staticmethod
    def _text(payload: dict[str, object], key: str, maximum: int) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value or len(value) > maximum or not value.isprintable():
            raise TestProjectError(f"test project {key} is invalid")
        return value

    @staticmethod
    def _require_private_owner_path(path: Path) -> None:
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
            raise TestProjectError("test project directory is unsafe")
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise TestProjectError("test project directory ownership or permissions are unsafe")

    @staticmethod
    def _require_private_owner_file(path: Path, maximum_bytes: int) -> None:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise TestProjectError("test project file is unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
            raise TestProjectError("test project file is unsafe")
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise TestProjectError("test project file ownership or permissions are unsafe")
        if metadata.st_size > maximum_bytes:
            raise TestProjectError("test project file exceeds the size limit")
