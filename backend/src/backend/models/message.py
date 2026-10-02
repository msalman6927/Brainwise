import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.agents.state import Phase
from backend.db.base import Base, enum_values

if TYPE_CHECKING:
    from backend.models.topic import Topic


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("topics.id", ondelete="CASCADE"))
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="message_role", values_callable=enum_values)
    )
    content: Mapped[str] = mapped_column(Text)
    phase: Mapped[Phase] = mapped_column(SAEnum(Phase, name="phase", values_callable=enum_values))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_messages_topic_id_created_at", "topic_id", created_at.desc()),)

    topic: Mapped[Topic] = relationship(back_populates="messages", lazy="raise")
