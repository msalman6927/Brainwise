import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.agents.state import Phase
from backend.db.base import Base, enum_values
from backend.models.assessment import Assessment
from backend.models.message import Message
from backend.models.user import User


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    phase: Mapped[Phase] = mapped_column(
        SAEnum(Phase, name="phase", values_callable=enum_values),
        default=Phase.TOPIC_SET,
    )
    iq_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # AGENTS.md §9 DELETE /topics is a soft delete: rows survive, readers filter on this.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_topics_user_id_updated_at", "user_id", updated_at.desc()),)

    owner: Mapped[User] = relationship(back_populates="topics", lazy="raise")
    messages: Mapped[list[Message]] = relationship(
        back_populates="topic",
        lazy="raise",
        passive_deletes=True,
        order_by=Message.created_at,
    )
    assessment: Mapped[Assessment | None] = relationship(
        back_populates="topic", lazy="raise", passive_deletes=True
    )
