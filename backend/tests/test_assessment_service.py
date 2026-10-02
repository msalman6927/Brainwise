"""Question generation, ladder, and grading rules (AGENTS.md §5, §6).

Model seams are monkeypatched except for two deliberately live calls (easy + hard)
that verify the real structured-output contract without spending more tokens.
"""

import pytest

from backend.agents import factory
from backend.core.errors import AlreadyAnsweredError, DomainError, UnsupportedTopicError
from backend.models.assessment import AssessmentQuestion, QuestionDifficulty
from backend.schemas.assessment import GeneratedQuestion, QuestionOptions
from backend.services import assessment as assessment_service


def _generated(difficulty: str, prompt: str = "What powers the cell?") -> GeneratedQuestion:
    return GeneratedQuestion(
        difficulty=difficulty,  # type: ignore[arg-type]
        prompt=prompt,
        options=QuestionOptions(
            A="Mitochondria",
            B="Ribosomes",
            C="Golgi apparatus",
            D="Cell wall",
        ),
        correct_option="A",
    )


async def test_ladder_branches_on_correctness() -> None:
    assert assessment_service.next_difficulty(True) == "hard"
    assert assessment_service.next_difficulty(False) == "easy"


async def test_generate_retries_once_on_difficulty_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    async def fake_call(
        topic: str, difficulty: str, ordinal: int, feedback: str | None
    ) -> GeneratedQuestion:
        attempts.append(difficulty or "")
        if len(attempts) == 1:
            return _generated("easy")  # wrong echo for a requested "hard" question
        assert "difficulty must be exactly 'hard'" in (feedback or "")
        return _generated(difficulty or "hard")

    monkeypatch.setattr(factory, "call_question_model", fake_call)
    question = await assessment_service.generate_question("photosynthesis", "hard", 2)
    assert question.difficulty == "hard"
    assert len(attempts) == 2


async def test_generate_raises_unsupported_after_two_invalid_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def fake_call(
        topic: str, difficulty: str, ordinal: int, feedback: str | None
    ) -> GeneratedQuestion:
        calls.append(1)
        return _generated(difficulty, prompt="UNSUPPORTED")

    monkeypatch.setattr(factory, "call_question_model", fake_call)
    with pytest.raises(UnsupportedTopicError) as exc:
        await assessment_service.generate_question("kitchen sink noises", "medium", 1)
    assert exc.value.retryable is True
    assert len(calls) == 2


async def test_generate_surfaces_call_failures_as_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def fake_call(
        topic: str, difficulty: str, ordinal: int, feedback: str | None
    ) -> GeneratedQuestion:
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(factory, "call_question_model", fake_call)
    with pytest.raises(DomainError):
        await assessment_service.generate_question("photosynthesis", "medium", 1)
    assert len(calls) == 2  # one retry even for transport failures


async def test_generate_rejects_duplicate_options(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = _generated("medium")
    bad.options = QuestionOptions(A="Same", B="Same", C="Other", D="Another")
    feedbacks: list[str | None] = []

    async def fake_call(
        topic: str, difficulty: str, ordinal: int, feedback: str | None
    ) -> GeneratedQuestion:
        feedbacks.append(feedback)
        return bad if len(feedbacks) == 1 else _generated(difficulty)

    monkeypatch.setattr(factory, "call_question_model", fake_call)
    question = await assessment_service.generate_question("topic", "medium", 1)
    assert question.options.A != question.options.B
    assert len(feedbacks) == 2
    assert feedbacks[1] is not None and "distinct" in feedbacks[1]


async def test_grade_answer_is_exact_match_and_idempotent() -> None:
    row = AssessmentQuestion(
        assessment_id=None,  # type: ignore[arg-type]
        ordinal=1,
        difficulty=QuestionDifficulty.MEDIUM,
        prompt="p",
        options={"A": "a", "B": "b", "C": "c", "D": "d"},
        correct_option="B",
    )
    assert assessment_service.grade_answer(row, "B") is True
    assert row.chosen_option == "B"
    assert row.answered_at is not None
    with pytest.raises(AlreadyAnsweredError):
        assessment_service.grade_answer(row, "A")


@pytest.mark.parametrize("difficulty", ["easy", "hard"])
async def test_live_question_generation_contract(difficulty: str) -> None:
    """Two real (small) calls: the model must honour the difficulty echo and schema."""
    question = await assessment_service.generate_question("photosynthesis", difficulty, 1)  # type: ignore[arg-type]
    assert question.difficulty == difficulty  # type: ignore[comparison-overlap]
    assert question.prompt != "UNSUPPORTED"
    texts = {
        question.options.A.lower(),
        question.options.B.lower(),
        question.options.C.lower(),
        question.options.D.lower(),
    }
    assert len(texts) == 4
    assert question.correct_option in {"A", "B", "C", "D"}
