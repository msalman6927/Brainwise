"""Auth endpoints (AGENTS.md §9): register, login, refresh, me."""

from fastapi import APIRouter

from backend.core.deps import CurrentUser, DbSession
from backend.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
    UserOut,
)
from backend.services import auth as auth_service

router = APIRouter()


@router.post("/register", response_model=RegisterResponse)
async def register(body: RegisterRequest, db: DbSession) -> RegisterResponse:
    return await auth_service.register(db, body)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginRequest, db: DbSession) -> TokenPair:
    return await auth_service.login(db, body)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshRequest, db: DbSession) -> TokenPair:
    return await auth_service.refresh(db, body)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
