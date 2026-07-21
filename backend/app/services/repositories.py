from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
import os
from pathlib import Path
import shutil
import stat
import subprocess

from app.schemas.repositories import (
    GitChangedFile,
    GitCommitDetail,
    GitCommitSummary,
    GitRepositoryDetail,
    GitRepositorySummary,
)

_FIELD_SEPARATOR = "\x1f"
_RECORD_SEPARATOR = "\x1e"
_README_LIMIT = 100_000
_OUTPUT_LIMIT = 2_000_000
_README_NAMES = ("README", "README.md", "README.rst", "README.txt")


class GitRepositoryNotFound(RuntimeError):
    pass


class GitRepositoryUnavailable(RuntimeError):
    pass


class GitRepositoryBrowser:
    def __init__(self, root: Path | None, scan_depth: int = 3, limit: int = 50) -> None:
        self._root = root.resolve() if root is not None else None
        self._scan_depth = scan_depth
        self._limit = limit
        self._git_executable = shutil.which("git")

    @property
    def enabled(self) -> bool:
        return self._root is not None and self._root.is_dir() and self._git_executable is not None

    def repositories(self) -> list[GitRepositorySummary]:
        return [self._summary(path) for path in self._catalog()]

    def detail(self, repository_id: str) -> GitRepositoryDetail:
        repository = self._resolve_id(repository_id)
        return GitRepositoryDetail(
            repository=self._summary(repository),
            changes=self._changes(repository),
            commits=self._commits(repository, 30),
            **self._readme(repository),
        )

    def commit(self, repository_id: str, revision: str) -> GitCommitDetail:
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise GitRepositoryNotFound
        repository = self._resolve_id(repository_id)
        output = self._git(
            repository,
            "show",
            "--no-ext-diff",
            "--no-renames",
            "--format=%H%x1f%h%x1f%s%x1f%an%x1f%aI%x1f%b%x1e",
            "--name-status",
            "-z",
            revision,
        )
        header, _, names = output.partition(_RECORD_SEPARATOR)
        fields = header.split(_FIELD_SEPARATOR, 5)
        if len(fields) != 6 or fields[0] != revision:
            raise GitRepositoryNotFound
        return GitCommitDetail(
            hash=fields[0],
            short_hash=fields[1],
            subject=fields[2],
            author_name=fields[3],
            authored_at=datetime.fromisoformat(fields[4]),
            body=fields[5].strip(),
            files=self._parse_name_status(names.lstrip("\0\n")),
        )

    def _discover(self) -> list[Path]:
        if not self.enabled or self._root is None:
            return []
        found: list[Path] = []
        for current, directories, _files in os.walk(self._root, followlinks=False):
            directory = Path(current)
            relative = directory.relative_to(self._root)
            depth = len(relative.parts)
            directories[:] = [
                name
                for name in directories
                if not name.startswith(".") and not (directory / name).is_symlink()
            ]
            git_marker = directory / ".git"
            if git_marker.is_dir() and not directory.is_symlink():
                found.append(directory.resolve())
                directories.clear()
                if len(found) >= self._limit:
                    break
            elif depth >= self._scan_depth:
                directories.clear()
        return sorted(found, key=lambda path: path.relative_to(self._root).as_posix().lower())

    def _resolve_id(self, repository_id: str) -> Path:
        if len(repository_id) != 16 or any(char not in "0123456789abcdef" for char in repository_id):
            raise GitRepositoryNotFound
        for repository in self._catalog():
            if self._identifier(repository) == repository_id:
                return repository
        raise GitRepositoryNotFound

    def _catalog(self) -> list[Path]:
        repositories: list[Path] = []
        for repository in self._discover():
            try:
                if self._git(
                    repository, "rev-parse", "--is-inside-work-tree", allow_failure=True
                ).strip() == "true":
                    repositories.append(repository)
            except (GitRepositoryNotFound, GitRepositoryUnavailable):
                continue
        return repositories

    @contextmanager
    def _open_repository(self, repository: Path):
        if self._root is None:
            raise GitRepositoryNotFound
        flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(repository, flags)
        except (OSError, ValueError) as exc:
            raise GitRepositoryNotFound from exc
        try:
            actual_path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            actual_path.relative_to(self._root)
            repository_status = os.fstat(descriptor)
            git_status = os.stat(".git", dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(repository_status.st_mode)
                or stat.S_ISLNK(git_status.st_mode)
                or not stat.S_ISDIR(git_status.st_mode)
            ):
                raise GitRepositoryNotFound
            yield descriptor
        except (OSError, ValueError) as exc:
            raise GitRepositoryNotFound from exc
        finally:
            os.close(descriptor)

    def _identifier(self, repository: Path) -> str:
        assert self._root is not None
        relative = repository.relative_to(self._root).as_posix()
        return sha256(relative.encode("utf-8")).hexdigest()[:16]

    def _summary(self, repository: Path) -> GitRepositorySummary:
        assert self._root is not None
        status = self._git(repository, "status", "--porcelain=v1", "--branch", "-z")
        records = [record for record in status.split("\0") if record]
        branch_header = records[0][3:] if records and records[0].startswith("## ") else "HEAD"
        branch = branch_header.split("...", 1)[0].strip()
        changes = records[1:] if records and records[0].startswith("## ") else records
        head = self._git(repository, "rev-parse", "--verify", "HEAD", allow_failure=True).strip()
        timestamp = self._git(repository, "log", "-1", "--format=%aI", allow_failure=True).strip()
        return GitRepositorySummary(
            id=self._identifier(repository),
            name=repository.name,
            relative_path=repository.relative_to(self._root).as_posix() or ".",
            branch=branch or "HEAD",
            head=head or None,
            dirty=bool(changes),
            changed_files=len(changes),
            last_commit_at=datetime.fromisoformat(timestamp) if timestamp else None,
        )

    def _changes(self, repository: Path) -> list[GitChangedFile]:
        output = self._git(repository, "status", "--porcelain=v1", "-z")
        records = [record for record in output.split("\0") if record and not record.startswith("## ")]
        changes: list[GitChangedFile] = []
        index = 0
        while index < len(records) and len(changes) < 200:
            record = records[index]
            status = record[:2].strip() or "?"
            path = record[3:]
            if "R" in record[:2] or "C" in record[:2]:
                index += 1
                if index < len(records):
                    path = f"{records[index]} → {path}"
            changes.append(GitChangedFile(status=status, path=path))
            index += 1
        return changes

    def _commits(self, repository: Path, limit: int) -> list[GitCommitSummary]:
        output = self._git(
            repository,
            "log",
            f"-{limit}",
            f"--format=%H{_FIELD_SEPARATOR}%h{_FIELD_SEPARATOR}%s{_FIELD_SEPARATOR}%an{_FIELD_SEPARATOR}%aI{_RECORD_SEPARATOR}",
            allow_failure=True,
        )
        commits: list[GitCommitSummary] = []
        for record in output.split(_RECORD_SEPARATOR):
            fields = record.strip().split(_FIELD_SEPARATOR)
            if len(fields) != 5:
                continue
            commits.append(
                GitCommitSummary(
                    hash=fields[0],
                    short_hash=fields[1],
                    subject=fields[2],
                    author_name=fields[3],
                    authored_at=datetime.fromisoformat(fields[4]),
                )
            )
        return commits

    def _readme(self, repository: Path) -> dict[str, str | bool | None]:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        with self._open_repository(repository) as repository_descriptor:
            readme_name: str | None = None
            readme_descriptor: int | None = None
            for candidate in _README_NAMES:
                try:
                    readme_descriptor = os.open(candidate, flags, dir_fd=repository_descriptor)
                    readme_name = candidate
                    break
                except FileNotFoundError:
                    continue
                except OSError:
                    continue
            if readme_descriptor is None or readme_name is None:
                return {"readme_name": None, "readme_content": None, "readme_truncated": False}
            try:
                file_status = os.fstat(readme_descriptor)
                if not stat.S_ISREG(file_status.st_mode) or file_status.st_nlink != 1:
                    raise GitRepositoryUnavailable
                content = os.read(readme_descriptor, _README_LIMIT + 1)
            finally:
                os.close(readme_descriptor)
        truncated = len(content) > _README_LIMIT
        return {
            "readme_name": readme_name,
            "readme_content": content[:_README_LIMIT].decode("utf-8", errors="replace"),
            "readme_truncated": truncated,
        }

    def _parse_name_status(self, output: str) -> list[GitChangedFile]:
        files: list[GitChangedFile] = []
        records = [record for record in output.split("\0") if record]
        index = 0
        while index + 1 < len(records) and len(files) < 200:
            status = records[index].strip()
            files.append(GitChangedFile(status=status, path=records[index + 1]))
            index += 2
        return files

    def _git(self, repository: Path, *arguments: str, allow_failure: bool = False) -> str:
        if self._git_executable is None:
            raise GitRepositoryUnavailable
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "PAGER": "cat",
        }
        try:
            with self._open_repository(repository) as repository_descriptor:
                completed = subprocess.run(
                    [
                        self._git_executable,
                        "--no-pager",
                        "--no-optional-locks",
                        "-c",
                        "core.fsmonitor=false",
                        "-c",
                        "core.hooksPath=/dev/null",
                        "-c",
                        "protocol.file.allow=never",
                        "-C",
                        f"/proc/self/fd/{repository_descriptor}",
                        *arguments,
                    ],
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                    env=environment,
                    pass_fds=(repository_descriptor,),
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitRepositoryUnavailable from exc
        if completed.returncode != 0:
            if allow_failure:
                return ""
            raise GitRepositoryUnavailable
        if len(completed.stdout.encode("utf-8")) > _OUTPUT_LIMIT:
            raise GitRepositoryUnavailable
        return completed.stdout
