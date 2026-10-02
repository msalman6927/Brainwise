"""Password hashing and JWT issue/verify (AGENTS.md §3, §9)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher

from backend.core.config import settings
from backend.core.errors import UnauthorizedError

# Explicit bcrypt hasher: PasswordHash.recommended() would need the argon2 extra,
# which is not installed (AGENTS.md §3 pins pwdlib/bcrypt).
_password_hash = PasswordHash([BcryptHasher()])


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(hashed: str, password: str) -> bool:
    # pwdlib's argument order is (password, hash).
    return _password_hash.verify(password, hashed)


def _secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("jwt_secret is not configured in backend/.env")
    return settings.jwt_secret


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=settings.jwt_access_ttl_min),
        },
        _secret(),
        algorithm="HS256",
    )


def create_refresh_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=settings.jwt_refresh_ttl_days),
        },
        _secret(),
        algorithm="HS256",
    )


def decode_token(token: str, *, expected_type: str) -> uuid.UUID:
    """Verify signature, expiry and token type; return the subject user id.

    Every failure raises UnauthorizedError so the API answers with the §9 envelope.
    """
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token") from exc
    if claims.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    try:
        return uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc
