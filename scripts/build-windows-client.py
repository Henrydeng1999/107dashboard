#!/usr/bin/env python3
"""Build a self-contained Windows client with an embedded Linux server package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = PROJECT_ROOT / "windows-client/src/Dashboard107.Client/Dashboard107.Client.csproj"
SOLUTION_FILE = PROJECT_ROOT / "windows-client/107Dashboard.Client.sln"
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "data/releases"
BUILD_DIRECTORY = PROJECT_ROOT / "data/windows-client-build"


def run(*arguments: str) -> None:
    subprocess.run(arguments, cwd=PROJECT_ROOT, check=True)


def find_dotnet() -> str:
    configured = os.environ.get("DOTNET_EXE")
    candidates = [
        configured,
        shutil.which("dotnet"),
        str(Path.home() / ".dotnet/dotnet.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(".NET 8 SDK was not found; set DOTNET_EXE to dotnet.exe")


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def read_release_metadata(archive_path: Path) -> tuple[str, str]:
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest = next(
            member for member in archive.getmembers()
            if member.name.endswith("/release-manifest.json")
        )
        source = archive.extractfile(manifest)
        if source is None:
            raise RuntimeError("server release manifest could not be read")
        metadata = json.load(source)
    return str(metadata["version"]), str(metadata["source_commit"])


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory for the Windows EXE and checksum",
    )
    parser.add_argument(
        "--skip-frontend-build",
        action="store_true",
        help="Use the existing validated frontend/dist directory",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="Refuse to build a formal client from a dirty Git working tree",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    dotnet = find_dotnet()
    if BUILD_DIRECTORY.exists():
        shutil.rmtree(BUILD_DIRECTORY)
    server_output = BUILD_DIRECTORY / "server"
    publish_output = BUILD_DIRECTORY / "publish"
    server_output.mkdir(parents=True)

    release_command = [
        sys.executable,
        "scripts/build-release.py",
        "--output-directory",
        str(server_output),
    ]
    if arguments.skip_frontend_build:
        release_command.append("--skip-frontend-build")
    if arguments.require_clean:
        release_command.append("--require-clean")
    run(*release_command)
    archives = list(server_output.glob("*.tar.gz"))
    if len(archives) != 1:
        raise RuntimeError("expected exactly one Linux server release archive")
    archive_path = archives[0].resolve()
    version, commit = read_release_metadata(archive_path)

    run(dotnet, "test", str(SOLUTION_FILE), "-c", "Release", "--nologo")
    run(
        dotnet,
        "publish",
        str(PROJECT_FILE),
        "-c",
        "Release",
        "-r",
        "win-x64",
        "--self-contained",
        "true",
        "-p:PublishSingleFile=true",
        "-p:EnableCompressionInSingleFile=true",
        "-p:IncludeNativeLibrariesForSelfExtract=true",
        "-p:DebugType=None",
        "-p:DebugSymbols=false",
        f"-p:PayloadPath={archive_path}",
        "-o",
        str(publish_output),
    )

    built_exe = publish_output / "107Dashboard.exe"
    if not built_exe.is_file():
        raise RuntimeError("published Windows executable is missing")
    output_directory = arguments.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"107Dashboard-Windows-x64-{version}-{commit[:8]}.exe"
    shutil.copy2(built_exe, output_path)
    checksum = digest(output_path)
    checksum_path = output_path.with_suffix(output_path.suffix + ".sha256")
    checksum_path.write_text(f"{checksum}  {output_path.name}\n", encoding="ascii")
    print(f"Windows client: {output_path}")
    print(f"SHA-256: {checksum}")
    print(f"Size: {output_path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
