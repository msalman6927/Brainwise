"""Thread create/list/delete models (AGENTS.md §9)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints

from backend.agents.state import Phase
from backend.schemas.assessment import IQ_MAX, IQ_MIN, Level
from backend.schemas.common import StrictModel, normalize_text

TopicTitle = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=200)
]


class TopicCreate(StrictModel):
    title: TopicTitle


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    phase: Phase
    iq_score: int | None = Field(default=None, ge=IQ_MIN, le=IQ_MAX)
    level: Level | None = None
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    phase: Phase
    created_at: datetime
