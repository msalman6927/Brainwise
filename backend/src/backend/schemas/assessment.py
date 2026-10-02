"""Question, answer submission, and score payload models (AGENTS.md §5, §6)."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, StringConstraints

from backend.schemas.common import StrictModel, normalize_text

Difficulty = Literal["easy", "medium", "hard"]
Level = Literal["Foundation", "Basic", "Intermediate", "Advanced"]

# §6: compute_iq() only ever returns 85/95/110/128; the API admits the §1 band (85–130).
IQ_MIN = 85
IQ_MAX = 130

QuestionPrompt = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=1000)
]
OptionText = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=300)
]


def _upper_letter(value: object) -> object:
    if isinstance(value, str):
        return value.strip().upper()
    return value


OptionLetter = Annotated[Literal["A", "B", "C", "D"], BeforeValidator(_upper_letter)]


class QuestionOptions(StrictModel):
    A: OptionText
    B: OptionText
    C: OptionText
    D: OptionText


class GeneratedQuestion(StrictModel):
    """One question exactly as the model must return it (§5 structured output, §8 rules)."""

    difficulty: Difficulty
    prompt: QuestionPrompt
    options: QuestionOptions
    correct_option: OptionLetter


class QuestionPayload(BaseModel):
    """The SSE 'question' event body (§9); also what assessment tools hand to the agent.

    thread_id is additive to the §9 example so the client always knows which thread a
    question belongs to, even if the stream drops before the final 'done' frame.
    """

    question_id: UUID
    difficulty: Difficulty
    text: str
    options: QuestionOptions
    thread_id: UUID | None = None


class AnswerRequest(StrictModel):
    question_id: UUID
    option: OptionLetter


class ScoreResult(BaseModel):
    iq_score: int = Field(ge=IQ_MIN, le=IQ_MAX)
    level: Level


class AssessmentProgress(BaseModel):
    """Return of the submit_answer tool (AGENTS.md §7): stored result, next step."""

    question_id: UUID
    correct: bool
    next_question: QuestionPayload | None = None
    score: ScoreResult | None = None
