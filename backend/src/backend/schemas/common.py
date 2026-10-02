"""Cross-schema building blocks: error codes, strict base, text normalization (AGENTS.md §9)."""

import unicodedata
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

# AGENTS.md §9 — the closed set of error codes the API may ever emit.
ErrorCode = Literal[
    "unauthorized",
    "invalid_credentials",
    "forbidden",
    "not_found",
    "invalid_phase",
    "already_answered",
    "unsupported_topic",
    "rate_limited",
    "invalid_request",
    "internal",
]


class StrictModel(BaseModel):
    """Request/LLM payloads: an unknown key is a client or model bug, never noise to drop."""

    model_config = ConfigDict(extra="forbid")


def normalize_text(value: object) -> object:
    """NFC-normalize and strip edges; length constraints apply to the cleaned value."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip()
    return value


def normalize_email(value: object) -> object:
    """Trim, NFC-normalize and lowercase so 'Foo@X.com' cannot create a second account."""
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value).strip().lower()
    return value


# email-validator (via fastapi[standard]) enforces RFC address limits well under the
# 320-char DB column, so no separate length rule is needed here.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(normalize_email)]


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False


class ErrorEnvelope(BaseModel):
    error: ErrorBody
