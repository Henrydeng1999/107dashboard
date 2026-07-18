import re
from pathlib import Path


class NativeLogPathError(ValueError):
    """A persisted Native log path is outside the controlled workspace layout."""


_SUBMISSION_DIRECTORY_PATTERN = re.compile(r"submission-[a-f0-9]{32}", re.ASCII)


def resolve_native_log_path(
    configured_value: str,
    *,
    workspace: Path,
    stream: str,
) -> Path:
    if stream not in {"stdout", "stderr"}:
        raise NativeLogPathError("Native log stream is invalid")
    configured_path = Path(configured_value)
    if not configured_path.is_absolute() or ".." in configured_path.parts:
        raise NativeLogPathError("Native log path is unsafe")

    resolved_workspace = workspace.resolve()
    configured_parent = configured_path.parent.resolve()
    expected_name = f"{stream}.log"
    if (
        configured_parent.parent != resolved_workspace
        or _SUBMISSION_DIRECTORY_PATTERN.fullmatch(configured_parent.name) is None
        or configured_path.name != expected_name
    ):
        raise NativeLogPathError("Native log path is unsafe")
    resolved_path = configured_path.resolve()
    if resolved_path.parent != configured_parent or resolved_path.name != expected_name:
        raise NativeLogPathError("Native log path is unsafe")
    return resolved_path
