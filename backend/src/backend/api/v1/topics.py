"""Topic thread endpoints (AGENTS.md §9): list, create, messages, soft delete."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Path, Response

from backend.core.deps import CurrentUser, DbSession
from backend.schemas.topic import MessageOut, TopicCreate, TopicOut
from backend.services import topics as topics_service

router = APIRouter()

TopicId = Annotated[uuid.UUID, Path(description="Thread id")]


@router.get("", response_model=list[TopicOut])
async def list_topics(user: CurrentUser, db: DbSession) -> list[TopicOut]:
    return await topics_service.list_topics(db, user.id)


@router.post("", response_model=TopicOut)
async def create_topic(body: TopicCreate, user: CurrentUser, db: DbSession) -> TopicOut:
    return await topics_service.create_topic(db, user.id, body)


@router.get("/{topic_id}/messages", response_model=list[MessageOut])
async def list_messages(topic_id: TopicId, user: CurrentUser, db: DbSession) -> list[MessageOut]:
    return await topics_service.list_messages(db, user.id, topic_id)


@router.delete("/{topic_id}", status_code=204)
async def delete_topic(topic_id: TopicId, user: CurrentUser, db: DbSession) -> Response:
    await topics_service.delete_topic(db, user.id, topic_id)
    return Response(status_code=204)
