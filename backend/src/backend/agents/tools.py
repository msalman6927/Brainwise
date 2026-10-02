"""langchain-core @tool wrappers; validate input, delegate to backend.services (AGENTS.md §7)."""

import functools
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select

from backend.agents.state import Phase
from backend.db.session import SessionLocal
from backend.models.message import Message
from backend.schemas.assessment import AssessmentProgress
from backend.schemas.chat import PhaseEvent, ThreadContext
from backend.schemas.topic import MessageOut, TopicTitle
from backend.services import assessment as assessment_service
from backend.services import topics as topics_service

logger = logging.getLogger(__name__)

_TITLE = TypeAdapter(TopicTitle)
_EMITTED = Callable[[str, BaseModel], None]


@dataclass
class ToolContext:
    """Per-request state shared by every tool (§7: bound, never model-supplied)."""

    user_id: uuid.UUID
    thread_id: uuid.UUID  # rebound by start_assessment so later calls target the new thread
    emit: _EMITTED


def _logged(
    name: str, ctx: ToolContext
) -> Callable[[Callable[..., Awaitable[str]]], Callable[..., Awaitable[str]]]:
    def deco(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                logger.info(
                    "tool_call name=%s user_id=%s thread_id=%s latency_ms=%d",
                    name,
                    ctx.user_id,
                    ctx.thread_id,
                    int((time.perf_counter() - start) * 1000),
                )

        return wrapper

    return deco


def make_tools(ctx: ToolContext) -> list[BaseTool]:
    """Build the five §7 tools bound to this request's context and database."""

    @tool
    @_logged("get_thread_context", ctx)
    async def get_thread_context() -> str:
        """Current topic title, phase, assessed level, and a short message summary."""
        async with SessionLocal() as db:
            topic = await topics_service.get_owned_topic(db, ctx.user_id, ctx.thread_id)
            rows = await db.scalars(
                select(Message)
                .where(Message.topic_id == topic.id)
                .order_by(Message.created_at.desc())
                .limit(6)
            )
            recent = [
                {"role": m.role.value, "content": m.content[:400]} for m in reversed(list(rows))
            ]
            context = ThreadContext.model_validate(
                {
                    "topic": topic.title,
                    "phase": topic.phase,
                    "level": topic.level,
                    "iq_score": topic.iq_score,
                    "recent_messages": recent,
                }
            )
            return context.model_dump_json()

    @tool
    @_logged("list_followup_history", ctx)
    async def list_followup_history(limit: int = 10) -> str:
        """Recent conversation turns in the current thread, oldest first."""
        capped = max(1, min(limit, 50))
        async with SessionLocal() as db:
            topic = await topics_service.get_owned_topic(db, ctx.user_id, ctx.thread_id)
            rows = await db.scalars(
                select(Message)
                .where(Message.topic_id == topic.id)
                .order_by(Message.created_at.desc())
                .limit(capped)
            )
            outs = [MessageOut.model_validate(m) for m in reversed(list(rows))]
        return json.dumps([out.model_dump(mode="json") for out in outs])

    @tool
    @_logged("submit_answer", ctx)
    async def submit_answer(question_id: str, option: str) -> str:
        """Answer the current assessment question (option letter A-D)."""
        letter = option.strip().upper()
        if letter not in {"A", "B", "C", "D"}:
            raise ValueError("option must be one of A, B, C, D")
        async with SessionLocal() as db:
            outcome = await assessment_service.answer_question(
                db,
                ctx.user_id,
                thread_id=ctx.thread_id,
                question_id=uuid.UUID(question_id),
                option=letter,
            )
        if outcome.question is not None:
            ctx.emit(
                "phase",
                PhaseEvent(phase=Phase.ASSESSING, question_index=outcome.index, total=3),
            )
            ctx.emit("question", outcome.question)
        progress = AssessmentProgress(
            question_id=uuid.UUID(question_id),
            correct=bool(outcome.correct),
            next_question=outcome.question,
            score=outcome.score,
        )
        return progress.model_dump_json()

    @tool
    @_logged("complete_assessment", ctx)
    async def complete_assessment() -> str:
        """Finalise scoring for this thread and return {iq_score, level} (idempotent)."""
        async with SessionLocal() as db:
            topic = await topics_service.get_owned_topic(db, ctx.user_id, ctx.thread_id)
            score = await assessment_service.resume_explanation(db, topic)
        return score.model_dump_json()

    @tool
    @_logged("start_assessment", ctx)
    async def start_assessment(topic: str) -> str:
        """Start a NEW assessment thread on a different topic; returns its first question."""
        title = _TITLE.validate_python(topic)
        async with SessionLocal() as db:
            new_topic, payload = await assessment_service.start_assessment(
                db, ctx.user_id, title=title
            )
        ctx.thread_id = new_topic.id
        ctx.emit("phase", PhaseEvent(phase=Phase.ASSESSING, question_index=1, total=3))
        ctx.emit("question", payload)
        return payload.model_dump_json()

    return [
        get_thread_context,
        list_followup_history,
        submit_answer,
        complete_assessment,
        start_assessment,
    ]
