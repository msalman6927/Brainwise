"""POST /chat request body and SSE event payload models (AGENTS.md §9)."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints, model_validator

from backend.agents.state import Phase
from backend.schemas.assessment import IQ_MAX, IQ_MIN, Level, OptionLetter
from backend.schemas.common import ErrorCode, StrictModel, normalize_text
from backend.schemas.topic import TopicTitle

ChatMessage = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=4000)
]


class MessageChatRequest(StrictModel):
    """Message mode: start a new topic or continue an existing thread (§9)."""

    thread_id: UUID | None = None
    topic: TopicTitle | None = None
    message: ChatMessage

    @model_validator(mode="after")
    def _exactly_one_target(self) -> MessageChatRequest:
        if (self.thread_id is None) == (self.topic is None):
            raise ValueError("provide exactly one of 'thread_id' or 'topic'")
        return self


class AnswerChatRequest(StrictModel):
    """Answer mode: reply to the current assessment question (§5) during ASSESSING."""

    thread_id: UUID
    question_id: UUID
    option: OptionLetter


# The POST /chat body is one of exactly two shapes (AGENTS.md §9).
ChatRequest = MessageChatRequest | AnswerChatRequest


class PhaseEvent(BaseModel):
    phase: Phase
    question_index: int | None = None
    total: int | None = None


class TokenEvent(BaseModel):
    delta: str


class ScoreEvent(BaseModel):
    iq_score: int = Field(ge=IQ_MIN, le=IQ_MAX)
    level: Level


class DoneEvent(BaseModel):
    thread_id: UUID
    phase: Phase


class ErrorEvent(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False


class ThreadContext(BaseModel):
    """Return of the get_thread_context tool (AGENTS.md §7) — model-facing summary."""

    topic: str
    phase: Phase
    level: Level | None = None
    iq_score: int | None = None
    recent_messages: list[dict[str, str]]
