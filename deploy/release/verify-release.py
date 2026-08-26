#!/usr/bin/env python3
"""Verify files recorded in a 107 Dashboard release manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


RELEASE_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = RELEASE_ROOT / "release-manifest.json"


def digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="ascii"))
    checked = 0
    for entry in manifest["files"]:
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError(f"unsafe manifest path: {relative}")
        path = RELEASE_ROOT.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"release file is missing or unsafe: {relative}")
        if path.stat().st_size != entry["size"]:
            raise RuntimeError(f"release file size mismatch: {relative}")
        if digest(path) != entry["sha256"]:
            raise RuntimeError(f"release file checksum mismatch: {relative}")
        checked += 1
    print(f"Verified {checked} release files for commit {manifest['source_commit'][:8]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
