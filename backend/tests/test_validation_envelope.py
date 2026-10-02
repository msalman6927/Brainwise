"""Malformed requests must surface the §9 envelope with code invalid_request."""

from collections.abc import AsyncIterator
from unittest.mock import ANY

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.schemas.auth import RegisterRequest
from backend.schemas.chat import MessageChatRequest

THREAD_ID = "12345678-1234-5678-1234-567812345678"


def build_app():
    # The real auth/chat routes do not exist yet (§4 marks them ○); a throwaway
    # router lets us verify the shared handler create_app() installs.
    app = create_app()
    router = APIRouter()

    @router.post("/_test/register")
    async def _register(body: RegisterRequest) -> dict[str, bool]:
        return {"ok": True}

    @router.post("/_test/chat")
    async def _chat(body: MessageChatRequest) -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return app


@pytest.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=build_app()), base_url="http://test"
    ) as client:
        yield client


def error_of(resp_json: dict) -> dict:
    return resp_json["error"]


async def test_missing_field_returns_envelope(app_client: AsyncClient) -> None:
    resp = await app_client.post("/_test/register", json={"email": "a@b.co", "name": "Ali"})
    assert resp.status_code == 422
    err = error_of(resp.json())
    assert err["code"] == "invalid_request"
    assert err["retryable"] is False
    assert set(err) == {"code", "message", "details", "retryable"}
    assert {"loc": "body.password", "msg": ANY, "type": "missing"} in err["details"]["fields"]


async def test_unknown_field_rejected_with_field_path(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/_test/register",
        json={
            "email": "a@b.co",
            "password": "passw0rd",
            "name": "Ali",
            "is_admin": True,
        },
    )
    assert resp.status_code == 422
    fields = error_of(resp.json())["details"]["fields"]
    assert {"loc": "body.is_admin", "msg": ANY, "type": "extra_forbidden"} in fields


async def test_invalid_email_reported_on_its_field(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/_test/register", json={"email": "nope", "password": "passw0rd", "name": "Ali"}
    )
    assert resp.status_code == 422
    fields = error_of(resp.json())["details"]["fields"]
    assert any(f["loc"] == "body.email" for f in fields)


async def test_malformed_uuid_reported_on_its_field(app_client: AsyncClient) -> None:
    resp = await app_client.post("/_test/chat", json={"thread_id": "not-a-uuid", "message": "hi"})
    assert resp.status_code == 422
    fields = error_of(resp.json())["details"]["fields"]
    assert any(f["loc"] == "body.thread_id" for f in fields)


@pytest.mark.parametrize(
    "body",
    [
        {"thread_id": THREAD_ID, "topic": "T", "message": "hi"},  # both targets
        {"message": "hi"},  # neither target
    ],
)
async def test_chat_target_xor_is_a_422_envelope(app_client: AsyncClient, body: dict) -> None:
    resp = await app_client.post("/_test/chat", json=body)
    assert resp.status_code == 422
    err = error_of(resp.json())
    assert err["code"] == "invalid_request"
    assert any("exactly one" in f["msg"] for f in err["details"]["fields"])


async def test_valid_request_passes_through(app_client: AsyncClient) -> None:
    resp = await app_client.post(
        "/_test/register", json={"email": "a@b.co", "password": "passw0rd", "name": "Ali"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
