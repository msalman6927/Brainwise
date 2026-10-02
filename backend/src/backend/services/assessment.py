"""Question generation, grading, and scoring orchestration (AGENTS.md §5, §6)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.agents import factory, prompts
from backend.agents.state import Phase, assert_transition
from backend.core.errors import (
    AlreadyAnsweredError,
    DomainError,
    InvalidPhaseError,
    NotFoundError,
    UnsupportedTopicError,
)
from backend.models.assessment import Assessment, AssessmentQuestion, AssessmentStatus
from backend.models.assessment import QuestionDifficulty as QuestionDifficultyEnum
from backend.models.message import Message, MessageRole
from backend.models.topic import Topic
from backend.schemas.assessment import (
    Difficulty,
    GeneratedQuestion,
    QuestionPayload,
    ScoreResult,
)
from backend.services.topics import get_owned_topic

logger = logging.getLogger(__name__)

IQ_TABLE: dict[int, int] = {0: 85, 1: 95, 2: 110, 3: 128}

LEVELS: tuple[tuple[int, str], ...] = (
    (0, "Foundation"),
    (95, "Basic"),
    (110, "Intermediate"),
    (128, "Advanced"),
)


def compute_iq(correct: int) -> int:
    if correct not in IQ_TABLE:
        raise ValueError(f"correct must be in 0..3, got {correct}")
    return IQ_TABLE[correct]


def level_for(iq: int) -> str:
    label = LEVELS[0][1]
    for lower, name in LEVELS:
        if iq >= lower:
            label = name
    return label


def next_difficulty(was_correct: bool) -> Difficulty:
    """AGENTS.md §5 ladder: Q(n+1) is HARD iff Q(n) was answered correctly."""
    return "hard" if was_correct else "easy"


def _validation_problems(question: GeneratedQuestion, difficulty: Difficulty) -> list[str]:
    problems: list[str] = []
    if question.prompt.strip().upper() == "UNSUPPORTED":
        problems.append("the topic cannot be assessed with multiple-choice questions")
    if question.difficulty != difficulty:
        problems.append(f"difficulty must be exactly '{difficulty}'")
    texts = [
        question.options.A.strip().lower(),
        question.options.B.strip().lower(),
        question.options.C.strip().lower(),
        question.options.D.strip().lower(),
    ]
    if len(set(texts)) != 4:
        problems.append("the four options must be distinct")
    return problems


async def generate_question(topic: str, difficulty: Difficulty, ordinal: int) -> GeneratedQuestion:
    """One structured-output model call per question; retry once with feedback (§5)."""
    feedback: str | None = None
    call_error: Exception | None = None
    for _attempt in range(2):
        try:
            question = await factory.call_question_model(topic, difficulty, ordinal, feedback)
        except Exception as exc:  # noqa: BLE001 — every model failure type retries once
            call_error = exc
            feedback = prompts.question_feedback([f"the call failed with {type(exc).__name__}"])
            logger.warning(
                "question_call_failed topic=%r difficulty=%s ordinal=%d error=%s",
                topic,
                difficulty,
                ordinal,
                type(exc).__name__,
            )
            continue
        call_error = None
        problems = _validation_problems(question, difficulty)
        if not problems:
            return question
        feedback = prompts.question_feedback(problems)
        logger.warning(
            "question_validation_failed topic=%r difficulty=%s ordinal=%d problems=%s",
            topic,
            difficulty,
            ordinal,
            problems,
        )
    if call_error is not None:
        raise DomainError("The question generator is unavailable; please retry") from call_error
    raise UnsupportedTopicError(
        "This topic cannot be assessed with multiple-choice questions; try rephrasing it",
    )


def grade_answer(question: AssessmentQuestion, option: str) -> bool:
    """Exact option match — the LLM never grades (§5)."""
    if question.chosen_option is not None:
        raise AlreadyAnsweredError("Question already answered")
    question.chosen_option = option
    question.answered_at = datetime.now(UTC)
    return option == question.correct_option


async def load_assessment(
    db: AsyncSession, topic_id: uuid.UUID
) -> tuple[Assessment | None, list[AssessmentQuestion]]:
    assessment = await db.scalar(
        select(Assessment)
        .where(Assessment.topic_id == topic_id)
        .options(selectinload(Assessment.questions))
    )
    questions = list(assessment.questions) if assessment is not None else []
    return assessment, questions


async def finish_assessment(db: AsyncSession, topic: Topic, assessment: Assessment) -> ScoreResult:
    """Score the finished assessment with the pure IQ table (§6); idempotent."""
    if (
        topic.iq_score is not None
        and topic.level is not None
        and assessment.status is AssessmentStatus.COMPLETED
    ):
        result = ScoreResult.model_validate({"iq_score": topic.iq_score, "level": topic.level})
        if topic.phase is Phase.SCORING:
            assert_transition(Phase.SCORING, Phase.EXPLAINING)
            topic.phase = Phase.EXPLAINING
            await db.commit()
        return result

    correct = sum(1 for q in assessment.questions if q.chosen_option == q.correct_option)
    iq = compute_iq(correct)
    level = level_for(iq)
    assessment.correct_count = correct
    assessment.iq_score = iq
    assessment.level = level
    assessment.status = AssessmentStatus.COMPLETED
    assessment.completed_at = datetime.now(UTC)
    topic.iq_score = iq
    topic.level = level
    if topic.phase is Phase.SCORING:
        assert_transition(Phase.SCORING, Phase.EXPLAINING)
        topic.phase = Phase.EXPLAINING
    await db.commit()
    logger.info(
        "assessment_completed thread_id=%s correct=%d iq=%d level=%s",
        topic.id,
        correct,
        iq,
        level,
    )
    return ScoreResult.model_validate({"iq_score": iq, "level": level})


async def resume_explanation(db: AsyncSession, topic: Topic) -> ScoreResult:
    """Message-mode recovery when a thread sits in SCORING/EXPLAINING (§9 resumable)."""
    assessment, _questions = await load_assessment(db, topic.id)
    if assessment is None:
        raise InvalidPhaseError("This thread has no assessment to finish")
    return await finish_assessment(db, topic, assessment)


async def start_assessment(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    user_message: str | None = None,
    thread: Topic | None = None,
) -> tuple[Topic, QuestionPayload]:
    """Create (or arm) a thread, generate Q1 at medium, set phase ASSESSING (§7).

    Question generation runs first so a failed generation leaves no orphan thread.
    """
    generated = await generate_question(title, "medium", 1)
    if thread is None:
        topic = Topic(user_id=user_id, title=title, phase=Phase.TOPIC_SET)
        db.add(topic)
        await db.flush()
    else:
        topic = thread
        if topic.phase is not Phase.TOPIC_SET:
            raise InvalidPhaseError(
                f"This thread is already at phase '{topic.phase}'; no question to start"
            )
    assert_transition(Phase.TOPIC_SET, Phase.ASSESSING)
    topic.phase = Phase.ASSESSING
    assessment = Assessment(topic_id=topic.id, correct_count=0)
    db.add(assessment)
    await db.flush()
    row = AssessmentQuestion(
        assessment_id=assessment.id,
        ordinal=1,
        difficulty=QuestionDifficultyEnum(generated.difficulty),
        prompt=generated.prompt,
        options=generated.options.model_dump(),
        correct_option=generated.correct_option,
    )
    db.add(row)
    await db.flush()
    payload = QuestionPayload(
        question_id=row.id,
        difficulty=generated.difficulty,
        text=generated.prompt,
        options=generated.options,
        thread_id=topic.id,
    )
    if user_message is not None:
        db.add(
            Message(
                topic_id=topic.id,
                role=MessageRole.USER,
                content=user_message,
                phase=Phase.TOPIC_SET,
            )
        )
    db.add(
        Message(
            topic_id=topic.id,
            role=MessageRole.ASSISTANT,
            content=payload.model_dump_json(),
            phase=Phase.ASSESSING,
        )
    )
    await db.commit()
    logger.info("assessment_started thread_id=%s user_id=%s", topic.id, user_id)
    return topic, payload


@dataclass
class AnswerOutcome:
    """Result of answer submission: either the next question or the final score."""

    thread_id: uuid.UUID
    title: str
    question: QuestionPayload | None = None
    index: int | None = None
    score: ScoreResult | None = None
    emit_scoring: bool = False
    correct: bool | None = None


async def _next_question(
    db: AsyncSession, topic: Topic, assessment: Assessment, answered: AssessmentQuestion
) -> AnswerOutcome:
    was_correct = answered.chosen_option == answered.correct_option
    difficulty = next_difficulty(was_correct)
    ordinal = answered.ordinal + 1
    generated = await generate_question(topic.title, difficulty, ordinal)
    row = AssessmentQuestion(
        assessment_id=assessment.id,
        ordinal=ordinal,
        difficulty=QuestionDifficultyEnum(generated.difficulty),
        prompt=generated.prompt,
        options=generated.options.model_dump(),
        correct_option=generated.correct_option,
    )
    db.add(row)
    await db.flush()
    payload = QuestionPayload(
        question_id=row.id,
        difficulty=generated.difficulty,
        text=generated.prompt,
        options=generated.options,
        thread_id=topic.id,
    )
    db.add(
        Message(
            topic_id=topic.id,
            role=MessageRole.ASSISTANT,
            content=payload.model_dump_json(),
            phase=Phase.ASSESSING,
        )
    )
    topic.updated_at = datetime.now(UTC)
    await db.commit()
    return AnswerOutcome(
        thread_id=topic.id,
        title=topic.title,
        question=payload,
        index=ordinal,
        correct=was_correct,
    )


async def answer_question(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    thread_id: uuid.UUID,
    question_id: uuid.UUID,
    option: str,
) -> AnswerOutcome:
    """Grade exactly, persist, then generate the next question or finalise the score.

    Grading commits before generation so a generation failure leaves a resumable
    state (the same answer resubmitted regenerates the missing question, §7
    idempotency) instead of double-counting.
    """
    topic = await get_owned_topic(db, user_id, thread_id)
    if topic.phase is Phase.TOPIC_SET:
        raise InvalidPhaseError("No question has been asked in this thread yet")
    if topic.phase is Phase.FOLLOW_UP:
        raise InvalidPhaseError("The assessment for this thread is already complete")
    assessment, questions = await load_assessment(db, topic.id)
    if assessment is None or not questions:
        raise InvalidPhaseError("This thread has no active assessment")
    target = next((q for q in questions if q.id == question_id), None)
    if target is None:
        raise NotFoundError("Question not found")

    if topic.phase in (Phase.SCORING, Phase.EXPLAINING):
        if target.ordinal != 3 or target.chosen_option is None:
            raise InvalidPhaseError("The score is being finalised; wait for the score event")
        was_scoring = topic.phase is Phase.SCORING
        score = await finish_assessment(db, topic, assessment)
        return AnswerOutcome(
            thread_id=topic.id,
            title=topic.title,
            score=score,
            emit_scoring=was_scoring,
            correct=target.chosen_option == target.correct_option,
        )

    last = questions[-1]
    if target.id != last.id:
        if target.chosen_option is not None:
            raise AlreadyAnsweredError("Question already answered")
        raise NotFoundError("Question not found")
    if last.chosen_option is not None:
        # Resume: the answer is stored but the next question never got generated.
        if last.ordinal >= 3 or len(questions) > last.ordinal:
            raise AlreadyAnsweredError("Question already answered")
        return await _next_question(db, topic, assessment, answered=last)

    was_correct = grade_answer(last, option)
    db.add(
        Message(
            topic_id=topic.id,
            role=MessageRole.USER,
            content=last.options[option],
            phase=Phase.ASSESSING,
        )
    )
    if last.ordinal == 3:
        assert_transition(Phase.ASSESSING, Phase.SCORING)
        topic.phase = Phase.SCORING
        await db.commit()
        score = await finish_assessment(db, topic, assessment)
        logger.info(
            "answer_graded thread_id=%s question_id=%s correct=%s",
            topic.id,
            last.id,
            was_correct,
        )
        return AnswerOutcome(
            thread_id=topic.id,
            title=topic.title,
            score=score,
            emit_scoring=True,
            correct=was_correct,
        )
    await db.commit()
    logger.info(
        "answer_graded thread_id=%s question_id=%s correct=%s",
        topic.id,
        last.id,
        was_correct,
    )
    return await _next_question(db, topic, assessment, answered=last)
