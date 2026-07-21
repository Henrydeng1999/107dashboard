from pathlib import Path
import subprocess

import pytest

from app.schemas.repositories import GitChangedFile
from app.services.repositories import GitRepositoryBrowser, GitRepositoryNotFound


def git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_repository(root: Path, name: str = "project") -> Path:
    repository = root / name
    repository.mkdir()
    git(repository, "init", "-q")
    git(repository, "config", "user.name", "Test User")
    git(repository, "config", "user.email", "test@example.invalid")
    (repository / "README.md").write_text("# Safe repository\n", encoding="utf-8")
    (repository / "tracked.txt").write_text("first\n", encoding="utf-8")
    git(repository, "add", "README.md", "tracked.txt")
    git(repository, "commit", "-q", "-m", "Initial commit")
    return repository


def test_lists_details_and_commit_without_remote_metadata(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)
    git(repository, "remote", "add", "origin", "https://secret-user:secret@example.invalid/repo.git")
    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")

    browser = GitRepositoryBrowser(tmp_path)
    summaries = browser.repositories()

    assert len(summaries) == 1
    assert summaries[0].name == "project"
    assert summaries[0].relative_path == "project"
    assert summaries[0].dirty is True
    assert summaries[0].changed_files == 1
    assert "secret" not in summaries[0].model_dump_json()

    detail = browser.detail(summaries[0].id)
    assert detail.readme_content == "# Safe repository\n"
    assert detail.changes[0].path == "tracked.txt"
    assert detail.commits[0].subject == "Initial commit"

    commit = browser.commit(summaries[0].id, detail.commits[0].hash)
    assert commit.subject == "Initial commit"
    assert {item.path for item in commit.files} == {"README.md", "tracked.txt"}
    assert "secret" not in commit.model_dump_json()


def test_rejects_unknown_ids_and_symlink_repositories(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    create_repository(outside, "private")
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside / "private", target_is_directory=True)

    browser = GitRepositoryBrowser(root)

    assert browser.repositories() == []
    with pytest.raises(GitRepositoryNotFound):
        browser.detail("0" * 16)


def test_skips_directories_with_fake_git_markers(tmp_path: Path) -> None:
    fake = tmp_path / "not-a-repository"
    (fake / ".git").mkdir(parents=True)
    real = create_repository(tmp_path, "real")

    repositories = GitRepositoryBrowser(tmp_path).repositories()

    assert [item.name for item in repositories] == [real.name]


def test_scan_depth_and_readme_limit(tmp_path: Path) -> None:
    nested = tmp_path / "one" / "two"
    nested.mkdir(parents=True)
    repository = create_repository(nested, "project")
    (repository / "README.md").write_text("x" * 100_001, encoding="utf-8")

    assert GitRepositoryBrowser(tmp_path, scan_depth=1).repositories() == []
    browser = GitRepositoryBrowser(tmp_path, scan_depth=3)
    summary = browser.repositories()[0]
    detail = browser.detail(summary.id)
    assert detail.readme_truncated is True
    assert len(detail.readme_content or "") == 100_000


def test_readme_symlink_is_not_exposed(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)
    (repository / "README.md").unlink()
    secret = tmp_path / "secret.txt"
    secret.write_text("do not expose", encoding="utf-8")
    (repository / "README.md").symlink_to(secret)

    detail = GitRepositoryBrowser(tmp_path).detail(
        GitRepositoryBrowser(tmp_path).repositories()[0].id
    )

    assert detail.readme_content is None


def test_git_invocation_is_noninteractive_and_disables_repository_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = create_repository(tmp_path)
    browser = GitRepositoryBrowser(tmp_path)
    original_run = subprocess.run
    observed: dict[str, object] = {}

    def inspect_run(arguments, **kwargs):
        observed.update({"arguments": arguments, **kwargs})
        return original_run(arguments, **kwargs)

    monkeypatch.setattr(subprocess, "run", inspect_run)
    browser.repositories()

    arguments = observed["arguments"]
    environment = observed["env"]
    assert isinstance(arguments, list)
    assert "--no-optional-locks" in arguments
    assert "core.fsmonitor=false" in arguments
    assert "core.hooksPath=/dev/null" in arguments
    assert "protocol.file.allow=never" in arguments
    assert observed["shell"] is False
    assert observed["stdin"] == subprocess.DEVNULL
    assert isinstance(environment, dict)
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"
    assert environment["PATH"] == "/usr/local/bin:/usr/bin:/bin"
    assert observed["pass_fds"]


def test_handles_newlines_in_file_names_without_response_corruption(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)
    unusual = "line\nbreak.txt"
    (repository / unusual).write_text("content", encoding="utf-8")
    git(repository, "add", unusual)
    git(repository, "commit", "-q", "-m", "Unusual filename")

    browser = GitRepositoryBrowser(tmp_path)
    summary = browser.repositories()[0]
    detail = browser.detail(summary.id)
    commit = browser.commit(summary.id, detail.commits[0].hash)

    assert commit.files == [GitChangedFile(status="A", path=unusual)]
