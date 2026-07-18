import os
import re
from collections.abc import Callable
from typing import Protocol


class _PasswordEntry(Protocol):
    pw_name: str


class TrustedIdentityError(RuntimeError):
    """Raised when the backend cannot establish its trusted Unix identity."""


_USERNAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}", re.ASCII)


def resolve_effective_unix_username(
    *,
    geteuid: Callable[[], int] | None = None,
    getpwuid: Callable[[int], _PasswordEntry] | None = None,
) -> str:
    """Resolve the account behind the process effective UID without HTTP input."""
    if geteuid is None or getpwuid is None:
        try:
            import pwd
        except ImportError as exc:
            raise TrustedIdentityError("effective Unix identity is unavailable") from exc

        geteuid = os.geteuid
        getpwuid = pwd.getpwuid

    try:
        username = getpwuid(geteuid()).pw_name
    except (KeyError, OSError) as exc:
        raise TrustedIdentityError("effective Unix UID has no resolvable account") from exc

    if _USERNAME_PATTERN.fullmatch(username) is None:
        raise TrustedIdentityError("effective Unix account name is invalid")
    return username


def assert_deployment_owner(expected_owner: str, effective_username: str) -> str:
    """Fail closed unless deployment configuration matches the effective account."""
    if _USERNAME_PATTERN.fullmatch(expected_owner) is None:
        raise TrustedIdentityError("configured deployment owner is invalid")
    if expected_owner != effective_username:
        raise TrustedIdentityError("configured deployment owner does not match effective Unix account")
    return effective_username
