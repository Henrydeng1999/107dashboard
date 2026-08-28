#!/usr/bin/env python3
"""Build a Linux deployment archive from the current working tree."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "releases"
LOCAL_RELEASE_PATHS = (
    Path("deploy/release"),
    Path("deploy/proxy/107-dashboard.nginx.conf.example"),
    Path("scripts/build-release.py"),
)
FORBIDDEN_PARTS = {".git", ".venv", "node_modules", "data", "__pycache__"}
CLIENT_ONLY_ROOTS = {"windows-client"}
CLIENT_ONLY_PATHS = {
    Path("scripts/build-windows-client.py"),
    Path("scripts/run-windows-client.ps1"),
    Path("backend/tests/unit/test_build_windows_client.py"),
}
ALLOWED_ENV_FILES = {".env.example", "frontend/.env.navigation"}


def run(*arguments: str, cwd: Path = PROJECT_ROOT) -> str:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def build_frontend() -> None:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if npm is None:
        raise RuntimeError("npm is required to build the frontend release")
    run(npm, "ci", cwd=PROJECT_ROOT / "frontend")
    run(npm, "run", "build:navigation", cwd=PROJECT_ROOT / "frontend")


def validate_frontend() -> None:
    dist = PROJECT_ROOT / "frontend" / "dist"
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError("frontend/dist/index.html is missing")
    if "/107-dashboard/assets/" not in index.read_text(encoding="utf-8"):
        raise RuntimeError("frontend release is missing the /107-dashboard/assets/ prefix")
    assets = dist / "assets"
    asset_files = [path for path in assets.rglob("*") if path.is_file()]
    if not any(b"/107-dashboard/api" in path.read_bytes() for path in asset_files):
        raise RuntimeError("frontend release is missing the /107-dashboard/api prefix")
    forbidden = (b"http://localhost:", b"http://127.0.0.1:")
    for path in [index, *asset_files]:
        content = path.read_bytes()
        if any(marker in content for marker in forbidden):
            raise RuntimeError(f"frontend release contains a development URL: {path}")


def tracked_files() -> set[Path]:
    output = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=PROJECT_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    return {Path(item.decode("utf-8")) for item in output.split(b"\0") if item}


def expand_local_path(relative: Path) -> set[Path]:
    absolute = PROJECT_ROOT / relative
    if absolute.is_file():
        return {relative}
    if absolute.is_dir():
        expanded: set[Path] = set()
        for path in absolute.rglob("*"):
            candidate = path.relative_to(PROJECT_ROOT)
            if (
                path.is_file()
                and path.suffix != ".pyc"
                and not any(part in FORBIDDEN_PARTS for part in candidate.parts)
            ):
                expanded.add(candidate)
        return expanded
    raise RuntimeError(f"required release path is missing: {relative.as_posix()}")


def release_files() -> list[Path]:
    files = tracked_files()
    for path in LOCAL_RELEASE_PATHS:
        files.update(expand_local_path(path))
    dist = PROJECT_ROOT / "frontend" / "dist"
    files.update(
        path.relative_to(PROJECT_ROOT) for path in dist.rglob("*") if path.is_file()
    )
    normalized: list[Path] = []
    for path in sorted(files, key=lambda item: item.as_posix()):
        posix = PurePosixPath(path.as_posix())
        if path in CLIENT_ONLY_PATHS or (posix.parts and posix.parts[0] in CLIENT_ONLY_ROOTS):
            continue
        if any(part in FORBIDDEN_PARTS for part in posix.parts):
            raise RuntimeError(f"forbidden runtime path selected for release: {posix}")
        if path.name.startswith(".env") and path.as_posix() not in ALLOWED_ENV_FILES:
            raise RuntimeError(f"private environment file selected for release: {posix}")
        absolute = PROJECT_ROOT / path
        if absolute.is_symlink() or not absolute.is_file():
            raise RuntimeError(f"release inputs must be regular files: {posix}")
        normalized.append(path)
    return normalized


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_release_file(source: Path, target: Path) -> None:
    if source.suffix.lower() == ".sh":
        contents = source.read_bytes()
        target.write_bytes(contents.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        return
    shutil.copy2(source, target)


def copy_release_files(paths: list[Path], destination: Path) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for relative in paths:
        source = PROJECT_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_release_file(source, target)
        entries.append(
            {
                "path": relative.as_posix(),
                "size": target.stat().st_size,
                "sha256": file_digest(target),
            }
        )
    return entries


def validate_shell_line_endings(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() != ".sh":
            continue
        if b"\r" in path.read_bytes():
            relative = path.relative_to(root).as_posix()
            raise RuntimeError(f"release shell script contains carriage returns: {relative}")


def archive_filter(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    if info.isdir():
        info.mode = 0o755
    elif info.name.endswith(".sh") or info.name.endswith("/scripts/build-release.py"):
        info.mode = 0o755
    else:
        info.mode = 0o644
    return info


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory for the tar.gz archive and checksum",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="Package the existing validated frontend/dist directory",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Refuse to package a dirty Git working tree",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    dirty = bool(run("git", "status", "--porcelain"))
    if arguments.require_clean and dirty:
        raise RuntimeError("the working tree is dirty; commit or stash changes before release")
    if not arguments.skip_frontend_build:
        build_frontend()
    validate_frontend()

    package_metadata = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text("utf-8"))
    version = str(package_metadata["version"])
    commit = run("git", "rev-parse", "HEAD")
    suffix = "-local" if dirty else ""
    release_name = f"107dashboard-{version}-{commit[:8]}{suffix}"
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    archive_path = output_directory / f"{release_name}.tar.gz"

    paths = release_files()
    with tempfile.TemporaryDirectory(prefix="107dashboard-release-") as temporary:
        release_root = Path(temporary) / release_name
        release_root.mkdir()
        entries = copy_release_files(paths, release_root)
        validate_shell_line_endings(release_root)
        (release_root / "VERSION").write_text(
            f"version={version}\ncommit={commit}\ndirty={str(dirty).lower()}\n",
            encoding="ascii",
        )
        manifest = {
            "name": "107 Dashboard",
            "version": version,
            "source_commit": commit,
            "built_from_dirty_worktree": dirty,
            "created_at": datetime.now(UTC).isoformat(),
            "target": "linux-x86_64-python3.12",
            "files": entries,
        }
        (release_root / "release-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
            encoding="ascii",
        )
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(release_root, arcname=release_name, filter=archive_filter)

    archive_sha256 = file_digest(archive_path)
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(f"{archive_sha256}  {archive_path.name}\n", encoding="ascii")
    print(f"Release archive: {archive_path}")
    print(f"SHA-256: {archive_sha256}")
    print(f"Files: {len(paths)}")
    if dirty:
        print("Warning: this local trial package was built from a dirty working tree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
