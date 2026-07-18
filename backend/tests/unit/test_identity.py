from types import SimpleNamespace

import pytest

from app.core.identity import (
    TrustedIdentityError,
    assert_deployment_owner,
    resolve_effective_unix_username,
)


def test_resolve_effective_unix_username_uses_effective_uid() -> None:
    requested_uids: list[int] = []

    def getpwuid(uid: int) -> SimpleNamespace:
        requested_uids.append(uid)
        return SimpleNamespace(pw_name="student_user")

    username = resolve_effective_unix_username(geteuid=lambda: 1007, getpwuid=getpwuid)

    assert username == "student_user"
    assert requested_uids == [1007]


def test_resolve_effective_unix_username_rejects_unknown_uid() -> None:
    def getpwuid(_uid: int) -> SimpleNamespace:
        raise KeyError("missing")

    with pytest.raises(TrustedIdentityError, match="no resolvable account"):
        resolve_effective_unix_username(geteuid=lambda: 1007, getpwuid=getpwuid)


def test_resolve_effective_unix_username_rejects_invalid_account_name() -> None:
    with pytest.raises(TrustedIdentityError, match="account name is invalid"):
        resolve_effective_unix_username(
            geteuid=lambda: 1007,
            getpwuid=lambda _uid: SimpleNamespace(pw_name="student;id"),
        )


def test_assert_deployment_owner_accepts_exact_match() -> None:
    assert assert_deployment_owner("student_user", "student_user") == "student_user"


def test_assert_deployment_owner_rejects_mismatch() -> None:
    with pytest.raises(TrustedIdentityError, match="does not match"):
        assert_deployment_owner("configured_user", "effective_user")
