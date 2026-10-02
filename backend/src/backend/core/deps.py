"""FastAPI dependencies: get_db, get_current_user, require_auth (AGENTS.md §4)."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import UnauthorizedError
from backend.core.security import decode_token
from backend.db.session import SessionLocal
from backend.models.user import User


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request; services commit explicitly (AGENTS.md §11)."""
    async with SessionLocal() as session:
        yield session


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Authorization bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise UnauthorizedError("Authorization bearer token required")
    user_id = decode_token(token, expected_type="access")
    user = await db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Account no longer exists")
    return user


# §4 names both; every v1 route requires auth, so one strict implementation serves both.
require_auth = get_current_user

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_auth)]
