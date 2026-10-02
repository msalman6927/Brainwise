"""Thread CRUD (AGENTS.md §9). Services own transactions and ownership checks."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.errors import NotFoundError
from backend.models.message import Message
from backend.models.topic import Topic
from backend.schemas.topic import MessageOut, TopicCreate, TopicOut

logger = logging.getLogger(__name__)


async def get_owned_topic(db: AsyncSession, user_id: uuid.UUID, topic_id: uuid.UUID) -> Topic:
    topic = await db.get(Topic, topic_id)
    # One 404 for missing, soft-deleted or foreign threads — no existence oracle.
    if topic is None or topic.deleted_at is not None or topic.user_id != user_id:
        raise NotFoundError("Topic not found")
    return topic


async def list_topics(db: AsyncSession, user_id: uuid.UUID) -> list[TopicOut]:
    rows = await db.scalars(
        select(Topic)
        .where(Topic.user_id == user_id, Topic.deleted_at.is_(None))
        .order_by(Topic.updated_at.desc())
    )
    return [TopicOut.model_validate(topic) for topic in rows]


async def create_topic(db: AsyncSession, user_id: uuid.UUID, payload: TopicCreate) -> TopicOut:
    topic = Topic(user_id=user_id, title=payload.title)
    db.add(topic)
    await db.flush()
    await db.commit()
    logger.info("topic_created thread_id=%s user_id=%s", topic.id, user_id)
    return TopicOut.model_validate(topic)


async def list_messages(
    db: AsyncSession, user_id: uuid.UUID, topic_id: uuid.UUID
) -> list[MessageOut]:
    topic = await get_owned_topic(db, user_id, topic_id)
    rows = await db.scalars(
        select(Message).where(Message.topic_id == topic.id).order_by(Message.created_at.asc())
    )
    return [MessageOut.model_validate(message) for message in rows]


async def delete_topic(db: AsyncSession, user_id: uuid.UUID, topic_id: uuid.UUID) -> None:
    topic = await get_owned_topic(db, user_id, topic_id)
    topic.deleted_at = datetime.now(UTC)
    await db.commit()
    logger.info("topic_deleted thread_id=%s user_id=%s", topic_id, user_id)
