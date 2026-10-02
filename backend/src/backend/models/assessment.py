import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, enum_values

if TYPE_CHECKING:
    from backend.models.topic import Topic


class QuestionDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class AssessmentStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Assessment(Base):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("topics.id", ondelete="CASCADE"), unique=True
    )
    correct_count: Mapped[int] = mapped_column(Integer)
    iq_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[AssessmentStatus] = mapped_column(
        SAEnum(AssessmentStatus, name="assessment_status", values_callable=enum_values),
        default=AssessmentStatus.IN_PROGRESS,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("correct_count >= 0 AND correct_count <= 3", name="correct_count_range"),
    )

    topic: Mapped[Topic] = relationship(back_populates="assessment", lazy="raise")
    questions: Mapped[list[AssessmentQuestion]] = relationship(
        back_populates="assessment",
        lazy="raise",
        passive_deletes=True,
        order_by="AssessmentQuestion.ordinal",
    )


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assessments.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[QuestionDifficulty] = mapped_column(
        SAEnum(QuestionDifficulty, name="question_difficulty", values_callable=enum_values)
    )
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[dict[str, str]] = mapped_column(JSONB)
    correct_option: Mapped[str] = mapped_column(String(1))
    chosen_option: Mapped[str | None] = mapped_column(String(1), nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("assessment_id", "ordinal"),
        CheckConstraint("ordinal >= 1 AND ordinal <= 3", name="ordinal_range"),
        CheckConstraint("correct_option IN ('A', 'B', 'C', 'D')", name="correct_option_letter"),
        CheckConstraint(
            "chosen_option IS NULL OR chosen_option IN ('A', 'B', 'C', 'D')",
            name="chosen_option_letter",
        ),
        CheckConstraint(
            "options ? 'A' AND options ? 'B' AND options ? 'C' AND options ? 'D'",
            name="option_keys",
        ),
        CheckConstraint("(chosen_option IS NULL) = (answered_at IS NULL)", name="answered_pairing"),
    )

    assessment: Mapped[Assessment] = relationship(back_populates="questions", lazy="raise")
