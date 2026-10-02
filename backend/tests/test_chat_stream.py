"""SSE frame contract for chat_events (AGENTS.md §9): order, invariants, error mapping.

LLM streams and persistence are monkeypatched — no network, no database, no tokens.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from backend.agents import factory
from backend.core.errors import UnsupportedTopicError
from backend.schemas.assessment import QuestionOptions, QuestionPayload, ScoreResult
from backend.services import chat as chat_service
from backend.services.chat import Dispatch


def _frame_bytes(frames: list[bytes]) -> str:
    return b"".join(frames).decode()


def _parse(frames: list[bytes]) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in _frame_bytes(frames).split("\n\n"):
        if not block:
            continue
        lines = block.splitlines()
        assert lines[0].startswith("event: "), f"missing event line in {block!r}"
        assert lines[1].startswith("data: "), f"missing data line in {block!r}"
        events.append((lines[0][7:], json.loads(lines[1][6:])))
    return events


def _question_payload() -> QuestionPayload:
    return QuestionPayload(
        question_id=uuid.uuid4(),
        difficulty="medium",
        text="What powers the cell?",
        options=QuestionOptions(A="Mitochondria", B="Ribosomes", C="Golgi", D="Wall"),
        thread_id=uuid.uuid4(),
    )


async def _collect(dispatch: Dispatch) -> list[bytes]:
    return [frame async for frame in chat_service.chat_events(dispatch, uuid.uuid4())]


async def test_assess_stream_frame_order_and_done() -> None:
    payload = _question_payload()
    dispatch = Dispatch(
        kind="assess", thread_id=payload.thread_id or uuid.uuid4(), question=payload, index=1
    )
    events = _parse(await _collect(dispatch))
    assert [name for name, _ in events] == ["phase", "question", "done"]
    phase, question, done = (data for _, data in events)
    assert phase == {"phase": "assessing", "question_index": 1, "total": 3}
    assert question["question_id"] == str(payload.question_id)
    assert question["thread_id"] == str(payload.thread_id)
    assert done == {"thread_id": str(payload.thread_id), "phase": "assessing"}


async def test_finish_stream_emits_scoring_then_score_then_tokens_then_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stream(topic: str, iq: int, level: str) -> AsyncIterator[str]:
        yield "Integrals "
        yield "are fun."

    async def fake_persist(thread_id: uuid.UUID, text: str) -> None:
        assert text == "Integrals are fun."

    monkeypatch.setattr(factory, "stream_explanation", fake_stream)
    monkeypatch.setattr(chat_service, "_persist_explanation", fake_persist)
    dispatch = Dispatch(
        kind="finish",
        thread_id=uuid.uuid4(),
        title="calculus",
        score=ScoreResult.model_validate({"iq_score": 110, "level": "Intermediate"}),
        emit_scoring=True,
    )
    events = _parse(await _collect(dispatch))
    assert [name for name, _ in events] == [
        "phase",
        "phase",
        "score",
        "token",
        "token",
        "done",
    ]
    assert events[0][1]["phase"] == "scoring"
    assert events[1][1]["phase"] == "explaining"
    assert events[2][1] == {"iq_score": 110, "level": "Intermediate"}
    assert events[-1][1]["phase"] == "follow_up"


async def test_finish_resume_skips_scoring_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stream(topic: str, iq: int, level: str) -> AsyncIterator[str]:
        yield "ok"

    async def fake_persist(thread_id: uuid.UUID, text: str) -> None:
        return None

    monkeypatch.setattr(factory, "stream_explanation", fake_stream)
    monkeypatch.setattr(chat_service, "_persist_explanation", fake_persist)
    dispatch = Dispatch(
        kind="finish",
        thread_id=uuid.uuid4(),
        title="t",
        score=ScoreResult.model_validate({"iq_score": 85, "level": "Foundation"}),
        emit_scoring=False,
    )
    events = _parse(await _collect(dispatch))
    assert [name for name, _ in events] == ["phase", "score", "token", "done"]


async def test_mid_stream_failure_ends_with_error_not_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_stream(topic: str, iq: int, level: str) -> AsyncIterator[str]:
        yield "partial "
        raise RuntimeError("connection to provider lost")

    async def fake_persist(thread_id: uuid.UUID, text: str) -> None:
        raise AssertionError("must not persist a failed explanation")

    monkeypatch.setattr(factory, "stream_explanation", failing_stream)
    monkeypatch.setattr(chat_service, "_persist_explanation", fake_persist)
    dispatch = Dispatch(
        kind="finish",
        thread_id=uuid.uuid4(),
        title="t",
        score=ScoreResult.model_validate({"iq_score": 95, "level": "Basic"}),
        emit_scoring=True,
    )
    events = _parse(await _collect(dispatch))
    names = [name for name, _ in events]
    assert names[-1] == "error"
    assert "done" not in names
    assert events[-1][1] == {
        "code": "internal",
        "message": "Something went wrong while generating a response",
        "retryable": False,
    }
    # one token was flushed before the failure, then the error frame
    assert names == ["phase", "phase", "score", "token", "error"]


async def test_error_frames_map_domain_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_stream(topic: str, iq: int, level: str) -> AsyncIterator[str]:
        raise UnsupportedTopicError("cannot assess that")
        yield  # pragma: no cover — makes this an async generator

    monkeypatch.setattr(factory, "stream_explanation", failing_stream)

    async def noop_persist(*args: object) -> None:
        return None

    monkeypatch.setattr(chat_service, "_persist_explanation", noop_persist)
    dispatch = Dispatch(
        kind="finish",
        thread_id=uuid.uuid4(),
        title="t",
        score=ScoreResult.model_validate({"iq_score": 128, "level": "Advanced"}),
        emit_scoring=False,
    )
    events = _parse(await _collect(dispatch))
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "unsupported_topic"
    assert events[-1][1]["retryable"] is True


async def test_followup_stream_merges_tokens_and_persists_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[str] = []

    async def fake_agent(
        *, system_prompt: str, tools: list[Any], user_message: str, on_delta: Any
    ) -> None:
        assert "photosynthesis" in system_prompt
        on_delta("Chlorophyll ")
        on_delta("absorbs light.")

    async def fake_persist(thread_id: uuid.UUID, text: str) -> None:
        persisted.append(text)

    monkeypatch.setattr(factory, "run_followup_agent", fake_agent)
    monkeypatch.setattr(chat_service, "_persist_reply", fake_persist)
    thread_id = uuid.uuid4()
    dispatch = Dispatch(
        kind="followup",
        thread_id=thread_id,
        title="photosynthesis",
        score=ScoreResult.model_validate({"iq_score": 110, "level": "Intermediate"}),
        user_message="What is chlorophyll?",
    )
    events = _parse(await _collect(dispatch))
    assert [name for name, _ in events] == ["token", "token", "done"]
    assert events[-1][1] == {"thread_id": str(thread_id), "phase": "follow_up"}
    assert persisted == ["Chlorophyll absorbs light."]


async def test_agent_failure_ends_with_error_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_agent(
        *, system_prompt: str, tools: list[Any], user_message: str, on_delta: Any
    ) -> None:
        on_delta("partial answer")
        raise RuntimeError("recursion limit hit")

    async def fake_persist(thread_id: uuid.UUID, text: str) -> None:
        raise AssertionError("must not persist a failed reply")

    monkeypatch.setattr(factory, "run_followup_agent", failing_agent)
    monkeypatch.setattr(chat_service, "_persist_reply", fake_persist)
    dispatch = Dispatch(
        kind="followup",
        thread_id=uuid.uuid4(),
        title="t",
        score=ScoreResult.model_validate({"iq_score": 85, "level": "Foundation"}),
        user_message="hello",
    )
    events = _parse(await _collect(dispatch))
    names = [name for name, _ in events]
    assert names == ["token", "error"]
    assert events[-1][1]["code"] == "internal"


async def test_every_stream_ends_with_exactly_one_terminal_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ok_stream(topic: str, iq: int, level: str) -> AsyncIterator[str]:
        yield "text"

    monkeypatch.setattr(factory, "stream_explanation", ok_stream)

    async def noop_persist(*args: object) -> None:
        return None

    monkeypatch.setattr(chat_service, "_persist_explanation", noop_persist)
    terminal = {"done", "error"}
    for kind, dispatch in [
        (
            "assess",
            Dispatch(kind="assess", thread_id=uuid.uuid4(), question=_question_payload(), index=2),
        ),
        (
            "finish",
            Dispatch(
                kind="finish",
                thread_id=uuid.uuid4(),
                title="t",
                score=ScoreResult.model_validate({"iq_score": 85, "level": "Foundation"}),
                emit_scoring=True,
            ),
        ),
    ]:
        events = _parse(await _collect(dispatch))
        terminals = [name for name, _ in events if name in terminal]
        assert len(terminals) == 1, f"{kind}: {terminals}"
