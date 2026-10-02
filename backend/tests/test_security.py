"""JWT and password hashing rules (AGENTS.md §3, §9)."""

import uuid

import pytest

from backend.core import security
from backend.core.config import settings
from backend.core.errors import UnauthorizedError


def test_password_hash_roundtrip() -> None:
    hashed = security.hash_password("passw0rd1")
    assert hashed != "passw0rd1"
    assert hashed.startswith("$2")  # bcrypt
    assert security.verify_password(hashed, "passw0rd1")
    assert not security.verify_password(hashed, "wrong-password")


def test_access_and_refresh_roundtrip() -> None:
    user_id = uuid.uuid4()
    access = security.create_access_token(user_id)
    refresh = security.create_refresh_token(user_id)
    assert security.decode_token(access, expected_type="access") == user_id
    assert security.decode_token(refresh, expected_type="refresh") == user_id


def test_token_type_is_enforced() -> None:
    access = security.create_access_token(uuid.uuid4())
    with pytest.raises(UnauthorizedError, match="type"):
        security.decode_token(access, expected_type="refresh")
    refresh = security.create_refresh_token(uuid.uuid4())
    with pytest.raises(UnauthorizedError, match="type"):
        security.decode_token(refresh, expected_type="access")


def test_expired_access_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_access_ttl_min", -1)
    token = security.create_access_token(uuid.uuid4())
    with pytest.raises(UnauthorizedError, match="expired"):
        security.decode_token(token, expected_type="access")


def test_garbage_and_tampered_tokens_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        security.decode_token("not.a.jwt", expected_type="access")
    token = security.create_access_token(uuid.uuid4())
    with pytest.raises(UnauthorizedError):
        security.decode_token(token + "x", expected_type="access")


def test_missing_jwt_secret_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", None)
    with pytest.raises(RuntimeError, match="jwt_secret"):
        security.create_access_token(uuid.uuid4())
