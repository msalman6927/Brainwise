"""Orchestrates the state machine and agent invocation; owns the SSE stream (AGENTS.md §4, §9).

Two-phase handling keeps the HTTP status meaningful:
- prepare() runs eagerly in the endpoint — validation, ownership, grading and question
  generation — so failures return an HTTP error envelope before any SSE frame is sent;
- chat_events() is the stream itself — explanation/agent work that can fail mid-flight
  surfaces as an `error` frame. Every stream ends with exactly one `done` or `error`.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents import factory, prompts
from backend.agents.state import Phase, assert_transition
from backend.agents.tools import ToolContext, make_tools
from backend.core.errors import DomainError, InvalidPhaseError, InvalidRequestError
from backend.db.session import SessionLocal
from backend.models.message import Message, MessageRole
from backend.models.topic import Topic
from backend.schemas.assessment import QuestionPayload, ScoreResult
from backend.schemas.chat import (
    AnswerChatRequest,
    ChatRequest,
    DoneEvent,
    ErrorEvent,
    MessageChatRequest,
    PhaseEvent,
    TokenEvent,
)
from backend.schemas.common import ErrorCode
from backend.services import assessment as assessment_service
from backend.services import topics as topics_service

logger = logging.getLogger(__name__)


@dataclass
class Dispatch:
    """What the stream should do; built by prepare() after all eager checks pass."""

    kind: Literal["assess", "finish", "followup"]
    thread_id: uuid.UUID
    question: QuestionPayload | None = None
    index: int | None = None
    title: str = ""
    score: ScoreResult | None = None
    emit_scoring: bool = False
    user_message: str | None = None


async def prepare(db: AsyncSession, user_id: uuid.UUID, payload: ChatRequest) -> Dispatch:
    """Eager dispatch: everything here raises DomainError → HTTP envelope (§9)."""
    if isinstance(payload, AnswerChatRequest):
        outcome = await assessment_service.answer_question(
            db,
            user_id,
            thread_id=payload.thread_id,
            question_id=payload.question_id,
            option=payload.option,
        )
        if outcome.question is not None:
            return Dispatch(
                kind="assess",
                thread_id=outcome.thread_id,
                question=outcome.question,
                index=outcome.index,
                title=outcome.title,
            )
        return Dispatch(
            kind="finish",
            thread_id=outcome.thread_id,
            title=outcome.title,
            score=outcome.score,
            emit_scoring=outcome.emit_scoring,
        )

    assert isinstance(payload, MessageChatRequest)
    if payload.topic is not None:
        topic, question = await assessment_service.start_assessment(
            db, user_id, title=payload.topic, user_message=payload.message
        )
        return Dispatch(
            kind="assess",
            thread_id=topic.id,
            question=question,
            index=1,
            title=topic.title,
        )

    if payload.thread_id is None:
        # Unreachable: the schema already enforces the thread_id/topic XOR (§9).
        raise InvalidRequestError("thread_id is required")
    topic = await topics_service.get_owned_topic(db, user_id, payload.thread_id)
    if topic.phase is Phase.TOPIC_SET:
        topic, question = await assessment_service.start_assessment(
            db, user_id, title=topic.title, user_message=payload.message, thread=topic
        )
        return Dispatch(
            kind="assess",
            thread_id=topic.id,
            question=question,
            index=1,
            title=topic.title,
        )
    if topic.phase is Phase.ASSESSING:
        raise InvalidPhaseError("Answer the current question instead of sending a message")
    if topic.phase in (Phase.SCORING, Phase.EXPLAINING):
        score = await assessment_service.resume_explanation(db, topic)
        return Dispatch(
            kind="finish",
            thread_id=topic.id,
            title=topic.title,
            score=score,
            emit_scoring=False,
        )
    if topic.phase is Phase.FOLLOW_UP:
        db.add(
            Message(
                topic_id=topic.id,
                role=MessageRole.USER,
                content=payload.message,
                phase=Phase.FOLLOW_UP,
            )
        )
        topic.updated_at = datetime.now(UTC)
        await db.commit()
        score = ScoreResult.model_validate({"iq_score": topic.iq_score, "level": topic.level})
        return Dispatch(
            kind="followup",
            thread_id=topic.id,
            title=topic.title,
            score=score,
            user_message=payload.message,
        )
    raise InvalidPhaseError(f"Thread is at phase '{topic.phase}' and cannot accept messages")


def _frame(event: str, payload: BaseModel) -> bytes:
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n".encode()


def _error_event(exc: Exception) -> ErrorEvent:
    if isinstance(exc, DomainError):
        return ErrorEvent(
            code=cast(ErrorCode, exc.code), message=exc.message, retryable=exc.retryable
        )
    return ErrorEvent(
        code="internal", message="Something went wrong while generating a response", retryable=False
    )


async def _persist_explanation(thread_id: uuid.UUID, text: str) -> None:
    if not text:
        return
    async with SessionLocal() as db:
        topic = await db.get(Topic, thread_id)
        if topic is None or topic.deleted_at is not None:
            return
        if topic.phase is Phase.EXPLAINING:
            assert_transition(Phase.EXPLAINING, Phase.FOLLOW_UP)
            topic.phase = Phase.FOLLOW_UP
        db.add(
            Message(
                topic_id=topic.id,
                role=MessageRole.ASSISTANT,
                content=text,
                phase=Phase.EXPLAINING,
            )
        )
        topic.updated_at = datetime.now(UTC)
        await db.commit()


async def _persist_reply(thread_id: uuid.UUID, text: str) -> None:
    if not text:
        return
    async with SessionLocal() as db:
        topic = await db.get(Topic, thread_id)
        if topic is None or topic.deleted_at is not None:
            return
        db.add(
            Message(
                topic_id=topic.id,
                role=MessageRole.ASSISTANT,
                content=text,
                phase=Phase.FOLLOW_UP,
            )
        )
        topic.updated_at = datetime.now(UTC)
        await db.commit()


async def _followup_frames(dispatch: Dispatch, user_id: uuid.UUID) -> AsyncIterator[bytes]:
    """Run the follow-up agent, interleaving token frames with tool-emitted frames."""
    score = dispatch.score
    message = dispatch.user_message
    if score is None or message is None:
        raise DomainError("Dispatch is missing its score or message")
    queue: asyncio.Queue[tuple[str, BaseModel] | None] = asyncio.Queue()

    def emit(event: str, payload: BaseModel) -> None:
        queue.put_nowait((event, payload))

    reply_parts: list[str] = []

    def on_delta(delta: str) -> None:
        reply_parts.append(delta)
        queue.put_nowait(("token", TokenEvent(delta=delta)))

    ctx = ToolContext(user_id=user_id, thread_id=dispatch.thread_id, emit=emit)
    system = prompts.follow_up_system(dispatch.title, score.iq_score, score.level)
    producer_errors: list[Exception] = []

    async def produce() -> None:
        try:
            await factory.run_followup_agent(
                system_prompt=system,
                tools=make_tools(ctx),
                user_message=message,
                on_delta=on_delta,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as an SSE error frame
            producer_errors.append(exc)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            event, payload = item
            yield _frame(event, payload)
        if producer_errors:
            raise producer_errors[0]
        await _persist_reply(dispatch.thread_id, "".join(reply_parts))
        switched = ctx.thread_id != dispatch.thread_id
        yield _frame(
            "done",
            DoneEvent(
                thread_id=ctx.thread_id,
                phase=Phase.ASSESSING if switched else Phase.FOLLOW_UP,
            ),
        )
    finally:
        task.cancel()


async def chat_events(dispatch: Dispatch, user_id: uuid.UUID) -> AsyncIterator[bytes]:
    """The SSE stream: frames per §9; terminates with exactly one done or error."""
    try:
        if dispatch.kind == "assess":
            if dispatch.question is None or dispatch.index is None:
                raise DomainError("Dispatch is missing its question")
            yield _frame(
                "phase",
                PhaseEvent(phase=Phase.ASSESSING, question_index=dispatch.index, total=3),
            )
            yield _frame("question", dispatch.question)
            yield _frame("done", DoneEvent(thread_id=dispatch.thread_id, phase=Phase.ASSESSING))
            return

        if dispatch.kind == "finish":
            if dispatch.score is None:
                raise DomainError("Dispatch is missing its score")
            if dispatch.emit_scoring:
                yield _frame("phase", PhaseEvent(phase=Phase.SCORING))
            yield _frame("phase", PhaseEvent(phase=Phase.EXPLAINING))
            yield _frame("score", dispatch.score)
            parts: list[str] = []
            async for delta in factory.stream_explanation(
                dispatch.title, dispatch.score.iq_score, dispatch.score.level
            ):
                parts.append(delta)
                yield _frame("token", TokenEvent(delta=delta))
            await _persist_explanation(dispatch.thread_id, "".join(parts))
            yield _frame("done", DoneEvent(thread_id=dispatch.thread_id, phase=Phase.FOLLOW_UP))
            return

        async for frame in _followup_frames(dispatch, user_id):
            yield frame
    except Exception as exc:  # noqa: BLE001 — domain or model failure mid-stream
        logger.error(
            "chat_stream_failed thread_id=%s kind=%s error=%s",
            dispatch.thread_id,
            dispatch.kind,
            type(exc).__name__,
            exc_info=exc,
        )
        yield _frame("error", _error_event(exc))
