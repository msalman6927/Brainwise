"""Registration, login and refresh (AGENTS.md §9). One transaction per call."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import (
    InvalidCredentialsError,
    InvalidRequestError,
    UnauthorizedError,
)
from backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.models.user import User
from backend.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
    UserOut,
)

logger = logging.getLogger(__name__)

# Logged-in-unknown-email still runs one bcrypt verify against this hash, so login
# timing does not reveal whether an account exists.
_DUMMY_HASH = hash_password(uuid.uuid4().hex)


def _tokens(user_id: uuid.UUID) -> TokenPair:
    return TokenPair(access=create_access_token(user_id), refresh=create_refresh_token(user_id))


async def register(db: AsyncSession, payload: RegisterRequest) -> RegisterResponse:
    existing = (await db.scalars(select(User).where(User.email == payload.email))).first()
    if existing is not None:
        # §9 decision: duplicate email = invalid_request with a field-level detail,
        # not a separate conflict code.
        raise InvalidRequestError(
            "Email already registered",
            details={
                "fields": [
                    {"loc": "body.email", "msg": "email already registered", "type": "value_error"}
                ]
            },
        )
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    await db.flush()
    await db.commit()
    logger.info("user_registered user_id=%s", user.id)
    return RegisterResponse(
        access=create_access_token(user.id),
        refresh=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


async def login(db: AsyncSession, payload: LoginRequest) -> TokenPair:
    user = (await db.scalars(select(User).where(User.email == payload.email))).first()
    if user is None:
        verify_password(_DUMMY_HASH, payload.password)
        raise InvalidCredentialsError("Invalid email or password")
    if not verify_password(user.password_hash, payload.password):
        raise InvalidCredentialsError("Invalid email or password")
    logger.info("login_ok user_id=%s", user.id)
    return _tokens(user.id)


async def refresh(db: AsyncSession, payload: RefreshRequest) -> TokenPair:
    # Stateless refresh (§9 decision): valid until exp; no revocation store in v1.
    user_id = decode_token(payload.refresh, expected_type="refresh")
    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Account no longer exists")
    return _tokens(user.id)
