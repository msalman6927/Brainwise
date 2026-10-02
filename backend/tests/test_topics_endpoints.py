"""Topic endpoint contracts (AGENTS.md §9): services patched, database never touched."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from backend.agents.state import Phase
from backend.core.deps import require_auth
from backend.core.errors import NotFoundError
from backend.main import create_app
from backend.models.user import User
from backend.schemas.topic import MessageOut, TopicCreate, TopicOut
from backend.services import topics as topics_service

THREAD_ID = "12345678-1234-5678-1234-567812345678"


def make_user() -> User:
    return User(
        id=uuid4(),
        email="me@example.com",
        password_hash="x",
        name="Me",
        created_at=datetime.now(UTC),
    )


def make_topic(**overrides: object) -> TopicOut:
    payload: dict[str, object] = {
        "id": uuid4(),
        "title": "Photosynthesis",
        "phase": Phase.TOPIC_SET,
        "updated_at": datetime.now(UTC),
    }
    payload.update(overrides)
    return TopicOut(**payload)  # type: ignore[arg-type]


@pytest.fixture
async def authed_client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[require_auth] = make_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def anon_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def test_list_topics_contract(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_list(db: object, user_id: object) -> list[TopicOut]:
        return [make_topic(), make_topic(iq_score=110, level="Intermediate", phase=Phase.FOLLOW_UP)]

    monkeypatch.setattr(topics_service, "list_topics", fake_list)
    resp = await authed_client.get("/api/v1/topics")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert set(items[0]) == {"id", "title", "phase", "iq_score", "level", "updated_at"}
    assert items[0]["iq_score"] is None
    assert items[1]["iq_score"] == 110
    assert items[1]["level"] == "Intermediate"


async def test_create_topic_normalizes_title(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[TopicCreate] = []

    async def fake_create(db: object, user_id: object, payload: TopicCreate) -> TopicOut:
        captured.append(payload)
        return make_topic(title=payload.title)

    monkeypatch.setattr(topics_service, "create_topic", fake_create)
    resp = await authed_client.post("/api/v1/topics", json={"title": "  Linear Algebra  "})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Linear Algebra"
    assert captured[0].title == "Linear Algebra"


async def test_create_topic_rejects_blank_title(
    authed_client: AsyncClient,
) -> None:
    resp = await authed_client.post("/api/v1/topics", json={"title": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "invalid_request"


async def test_list_messages_contract(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[object, object]] = []

    async def fake_messages(db: object, user_id: object, topic_id: object) -> list[MessageOut]:
        captured.append((user_id, topic_id))
        return [
            MessageOut(
                id=uuid4(),
                role="user",
                content="photosynthesis",
                phase=Phase.TOPIC_SET,
                created_at=datetime.now(UTC),
            )
        ]

    monkeypatch.setattr(topics_service, "list_messages", fake_messages)
    resp = await authed_client.get(f"/api/v1/topics/{THREAD_ID}/messages")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert set(items[0]) == {"id", "role", "content", "phase", "created_at"}
    assert items[0]["role"] == "user"
    assert captured[0][1].hex == THREAD_ID.replace("-", "")


async def test_messages_on_foreign_or_missing_thread_is_404(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_messages(db: object, user_id: object, topic_id: object) -> list[MessageOut]:
        raise NotFoundError("Topic not found")

    monkeypatch.setattr(topics_service, "list_messages", fake_messages)
    resp = await authed_client.get(f"/api/v1/topics/{THREAD_ID}/messages")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_delete_topic_returns_204(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    deleted: list[object] = []

    async def fake_delete(db: object, user_id: object, topic_id: object) -> None:
        deleted.append(topic_id)

    monkeypatch.setattr(topics_service, "delete_topic", fake_delete)
    resp = await authed_client.delete(f"/api/v1/topics/{THREAD_ID}")
    assert resp.status_code == 204
    assert resp.content == b""
    assert deleted[0].hex == THREAD_ID.replace("-", "")


async def test_delete_missing_thread_is_404_envelope(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_delete(db: object, user_id: object, topic_id: object) -> None:
        raise NotFoundError("Topic not found")

    monkeypatch.setattr(topics_service, "delete_topic", fake_delete)
    resp = await authed_client.delete(f"/api/v1/topics/{THREAD_ID}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_malformed_thread_id_is_422_envelope(authed_client: AsyncClient) -> None:
    resp = await authed_client.get("/api/v1/topics/not-a-uuid/messages")
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_request"
    assert any(f["loc"] == "path.topic_id" for f in err["details"]["fields"])


async def test_topics_require_auth(anon_client: AsyncClient) -> None:
    resp = await anon_client.get("/api/v1/topics")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"
