"""Auth endpoint contracts (AGENTS.md §9): services patched, database never touched."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.core.deps import require_auth
from backend.core.errors import (
    InvalidCredentialsError,
    InvalidRequestError,
    UnauthorizedError,
)
from backend.main import create_app
from backend.models.user import User
from backend.schemas.auth import RegisterRequest, RegisterResponse, TokenPair, UserOut
from backend.services import auth as auth_service

VALID_BODY = {"email": "new@user.com", "password": "passw0rd", "name": "New"}


def make_user() -> User:
    return User(
        id=uuid4(),
        email="me@example.com",
        password_hash="x",
        name="Me",
        created_at=datetime.now(UTC),
    )


def make_token_pair() -> TokenPair:
    return TokenPair(access="access-token", refresh="refresh-token")


@pytest.fixture
async def anon_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


@pytest.fixture
async def authed_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[require_auth] = make_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_register_passes_normalized_payload_and_returns_pair(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[RegisterRequest] = []

    async def fake_register(db: object, payload: RegisterRequest) -> RegisterResponse:
        captured.append(payload)
        return RegisterResponse(
            access="access-token",
            refresh="refresh-token",
            user=UserOut(
                id=uuid4(),
                email=payload.email,
                name=payload.name,
                created_at=datetime.now(UTC),
            ),
        )

    monkeypatch.setattr(auth_service, "register", fake_register)
    resp = await anon_client.post(
        "/api/v1/auth/register",
        json={"email": " New@USER.com ", "password": "passw0rd", "name": "  New  "},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access"] == "access-token"
    assert body["refresh"] == "refresh-token"
    assert captured[0].email == "new@user.com"  # schema normalized before the service
    assert captured[0].name == "New"
    assert set(body["user"]) == {"id", "email", "name", "created_at"}


async def test_register_duplicate_email_uses_field_envelope(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_register(db: object, payload: object) -> RegisterResponse:
        raise InvalidRequestError(
            "Email already registered",
            details={
                "fields": [
                    {"loc": "body.email", "msg": "email already registered", "type": "value_error"}
                ]
            },
        )

    monkeypatch.setattr(auth_service, "register", fake_register)
    resp = await anon_client.post("/api/v1/auth/register", json=VALID_BODY)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_request"
    assert err["details"]["fields"][0]["loc"] == "body.email"


async def test_register_malformed_body_is_real_validation_path(
    anon_client: AsyncClient,
) -> None:
    resp = await anon_client.post("/api/v1/auth/register", json={"email": "bad"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_request"
    assert any(f["loc"] == "body.password" for f in err["details"]["fields"])


async def test_register_bad_response_model_is_internal(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_register(db: object, payload: object) -> TokenPair:
        return make_token_pair()  # wrong shape: missing 'user'

    monkeypatch.setattr(auth_service, "register", fake_register)
    resp = await anon_client.post("/api/v1/auth/register", json=VALID_BODY)
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal"


async def test_login_returns_exactly_the_token_pair(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_login(db: object, payload: object) -> TokenPair:
        return make_token_pair()

    monkeypatch.setattr(auth_service, "login", fake_login)
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"email": "a@b.co", "password": "whatever"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"access": "access-token", "refresh": "refresh-token"}


async def test_login_bad_credentials_envelope(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_login(db: object, payload: object) -> TokenPair:
        raise InvalidCredentialsError("Invalid email or password")

    monkeypatch.setattr(auth_service, "login", fake_login)
    resp = await anon_client.post(
        "/api/v1/auth/login", json={"email": "a@b.co", "password": "nope"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"


async def test_refresh_issues_new_pair(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_refresh(db: object, payload: object) -> TokenPair:
        return make_token_pair()

    monkeypatch.setattr(auth_service, "refresh", fake_refresh)
    resp = await anon_client.post("/api/v1/auth/refresh", json={"refresh": "any-token"})
    assert resp.status_code == 200
    assert resp.json() == {"access": "access-token", "refresh": "refresh-token"}


async def test_refresh_invalid_token_envelope(
    anon_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_refresh(db: object, payload: object) -> TokenPair:
        raise UnauthorizedError("Invalid token")

    monkeypatch.setattr(auth_service, "refresh", fake_refresh)
    resp = await anon_client.post("/api/v1/auth/refresh", json={"refresh": "garbage"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_without_header_is_401_envelope(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_with_garbage_bearer_is_401_envelope(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_me_returns_user(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "me@example.com"
    assert set(body) == {"id", "email", "name", "created_at"}
