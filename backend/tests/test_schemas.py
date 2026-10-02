"""Schema-level validation rules (AGENTS.md §5, §6, §9)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from backend.agents.state import Phase
from backend.schemas.assessment import (
    AnswerRequest,
    GeneratedQuestion,
    QuestionOptions,
    ScoreResult,
)
from backend.schemas.auth import LoginRequest, RegisterRequest
from backend.schemas.chat import (
    AnswerChatRequest,
    ChatRequest,
    MessageChatRequest,
    ScoreEvent,
)
from backend.schemas.common import ErrorEnvelope
from backend.schemas.topic import TopicCreate, TopicOut

VALID_PASSWORD = "passw0rd"


def register(**overrides: object) -> RegisterRequest:
    payload: dict[str, object] = {
        "email": "foo@example.com",
        "password": VALID_PASSWORD,
        "name": "Ali",
    }
    payload.update(overrides)
    return RegisterRequest(**payload)  # type: ignore[arg-type]


def question(**overrides: object) -> GeneratedQuestion:
    payload: dict[str, object] = {
        "difficulty": "medium",
        "prompt": "What is ATP?",
        "options": {"A": "a cell", "B": "an energy molecule", "C": "a vitamin", "D": "an ion"},
        "correct_option": "B",
    }
    payload.update(overrides)
    return GeneratedQuestion(**payload)  # type: ignore[arg-type]


# --- email -----------------------------------------------------------------


def test_email_is_trimmed_and_lowercased() -> None:
    assert register(email="  Foo@EXAMPLE.com ").email == "foo@example.com"


def test_invalid_email_rejected() -> None:
    with pytest.raises(ValidationError):
        register(email="not-an-email")


def test_empty_email_rejected() -> None:
    with pytest.raises(ValidationError):
        register(email="   ")


# --- password --------------------------------------------------------------


def test_password_requires_letter_and_digit() -> None:
    with pytest.raises(ValidationError) as exc:
        register(password="abcdefgh")
    assert "letter and one digit" in str(exc.value)
    with pytest.raises(ValidationError):
        register(password="12345678")


def test_password_minimum_eight_characters() -> None:
    with pytest.raises(ValidationError):
        register(password="ab1")


def test_password_byte_cap_protects_bcrypt() -> None:
    # 44 chars but 84 UTF-8 bytes: bcrypt would silently truncate without this rule.
    with pytest.raises(ValidationError) as exc:
        register(password="w0rd" + "\u00e9" * 40)
    assert "72 bytes" in str(exc.value)


def test_login_password_has_no_composition_policy() -> None:
    assert LoginRequest(email="a@b.co", password="x").password == "x"


# --- names, titles, messages (trim + NFC + reject empty) -------------------


def test_name_trimmed_and_empty_rejected() -> None:
    assert register(name="  Ali  ").name == "Ali"
    with pytest.raises(ValidationError):
        register(name="   ")


def test_title_is_nfc_normalized_and_trimmed() -> None:
    assert TopicCreate(title="  e\u0301clair  ").title == "\u00e9clair"


def test_title_empty_and_overlong_rejected() -> None:
    with pytest.raises(ValidationError):
        TopicCreate(title="   ")
    with pytest.raises(ValidationError):
        TopicCreate(title="x" * 201)
    assert TopicCreate(title="x" * 200).title == "x" * 200


def test_extra_fields_forbidden_on_requests() -> None:
    with pytest.raises(ValidationError) as exc:
        register(is_admin=True)
    assert exc.value.errors()[0]["type"] == "extra_forbidden"


# --- chat ------------------------------------------------------------------


def test_chat_requires_exactly_one_target() -> None:
    with pytest.raises(ValidationError) as exc:
        MessageChatRequest(message="hi")
    assert "exactly one" in str(exc.value)
    with pytest.raises(ValidationError):
        MessageChatRequest(thread_id=uuid4(), topic="Photosynthesis", message="hi")


def test_chat_thread_and_topic_shapes_accepted() -> None:
    assert MessageChatRequest(thread_id=uuid4(), message="hi").thread_id is not None
    only_topic = MessageChatRequest(topic="  Photosynthesis ", message="hi")
    assert only_topic.topic == "Photosynthesis"
    assert only_topic.thread_id is None


def test_chat_message_cap_and_trim() -> None:
    assert MessageChatRequest(thread_id=uuid4(), message="  hello  ").message == "hello"
    MessageChatRequest(thread_id=uuid4(), message="x" * 4000)
    with pytest.raises(ValidationError):
        MessageChatRequest(thread_id=uuid4(), message="x" * 4001)
    with pytest.raises(ValidationError):
        MessageChatRequest(thread_id=uuid4(), message="   ")


def test_answer_mode_requires_thread_and_question() -> None:
    answer = AnswerChatRequest(thread_id=uuid4(), question_id=uuid4(), option="c")
    assert answer.option == "C"
    with pytest.raises(ValidationError):
        AnswerChatRequest(question_id=uuid4(), option="A")  # no thread
    with pytest.raises(ValidationError):
        AnswerChatRequest(thread_id=uuid4(), option="A")  # no question
    with pytest.raises(ValidationError):
        AnswerChatRequest(thread_id=uuid4(), question_id=uuid4(), option="Z")


def test_chat_union_routes_by_shape() -> None:
    adapter = TypeAdapter(ChatRequest)
    thread = uuid4()
    as_message = adapter.validate_python({"thread_id": str(thread), "message": "hi"})
    assert isinstance(as_message, MessageChatRequest)
    as_answer = adapter.validate_python(
        {"thread_id": str(thread), "question_id": str(uuid4()), "option": "b"}
    )
    assert isinstance(as_answer, AnswerChatRequest)
    assert as_answer.option == "B"
    # Mixed shapes (message + question fields) match neither mode.
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "thread_id": str(thread),
                "message": "hi",
                "question_id": str(uuid4()),
                "option": "B",
            }
        )


# --- answers, scores, LLM output ------------------------------------------


def test_answer_option_case_insensitive_but_contract_uppercase() -> None:
    answer = AnswerRequest(question_id=uuid4(), option="b")
    assert answer.option == "B"
    with pytest.raises(ValidationError):
        AnswerRequest(question_id=uuid4(), option="E")
    with pytest.raises(ValidationError):
        AnswerRequest(question_id="not-a-uuid", option="A")


def test_score_band_85_to_130_and_fixed_levels() -> None:
    ScoreResult(iq_score=85, level="Foundation")
    ScoreResult(iq_score=130, level="Advanced")
    with pytest.raises(ValidationError):
        ScoreResult(iq_score=84, level="Advanced")
    with pytest.raises(ValidationError):
        ScoreResult(iq_score=131, level="Advanced")
    with pytest.raises(ValidationError):
        ScoreResult(iq_score=110, level="Genius")


def test_topic_out_score_optional_within_band() -> None:
    TopicOut(id=uuid4(), title="t", phase=Phase.TOPIC_SET, updated_at=datetime.now(UTC))
    TopicOut(
        id=uuid4(),
        title="t",
        phase=Phase.FOLLOW_UP,
        iq_score=110,
        level="Intermediate",
        updated_at=datetime.now(UTC),
    )
    with pytest.raises(ValidationError):
        TopicOut(
            id=uuid4(), title="t", phase=Phase.TOPIC_SET, iq_score=84, updated_at=datetime.now(UTC)
        )


def test_generated_question_rules() -> None:
    assert question(correct_option="d").correct_option == "D"
    assert question(prompt="  Why?  ").prompt == "Why?"
    question(prompt="x" * 1000)
    for bad in (
        {"difficulty": "brutal"},
        {"prompt": "x" * 1001},
        {"prompt": "   "},
        {"options": {"A": "a", "B": "b", "C": "c"}},
        {"options": {"A": "a", "B": "b", "C": "c", "D": "d", "E": "e"}},
        {"correct_option": "E"},
        {"citation": "made up"},
    ):
        with pytest.raises(ValidationError):
            question(**bad)


def test_question_options_reject_extra_keys() -> None:
    with pytest.raises(ValidationError):
        QuestionOptions(A="1", B="2", C="3", D="4", E="5")


def test_sse_score_event_uses_same_band() -> None:
    assert ScoreEvent(iq_score=128, level="Advanced").iq_score == 128
    with pytest.raises(ValidationError):
        ScoreEvent(iq_score=84, level="Advanced")


def test_error_envelope_code_is_closed_set() -> None:
    ErrorEnvelope(error={"code": "invalid_request", "message": "bad"})
    ErrorEnvelope(error={"code": "internal", "message": "boom"})
    with pytest.raises(ValidationError):
        ErrorEnvelope(error={"code": "kaboom", "message": "bad"})
