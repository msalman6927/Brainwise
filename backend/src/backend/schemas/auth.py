"""Register/login/refresh/me request and response models (AGENTS.md §9)."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, field_validator

from backend.schemas.common import NormalizedEmail, StrictModel, normalize_text

NameText = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=120)
]
# Passwords are never trimmed or NFC-normalized: what was typed must hash-match on login.
NewPassword = Annotated[str, StringConstraints(min_length=8, max_length=72)]
ExistingPassword = Annotated[str, StringConstraints(min_length=1, max_length=72)]
RefreshToken = Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class RegisterRequest(StrictModel):
    email: NormalizedEmail
    password: NewPassword
    name: NameText

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            # bcrypt truncates at 72 bytes — reject rather than silently hash a prefix.
            raise ValueError("password must be at most 72 bytes")
        if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
            raise ValueError("password must contain at least one letter and one digit")
        return value


class LoginRequest(StrictModel):
    email: NormalizedEmail
    password: ExistingPassword


class RefreshRequest(StrictModel):
    refresh: RefreshToken


class TokenPair(BaseModel):
    access: str
    refresh: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str
    created_at: datetime


class RegisterResponse(TokenPair):
    user: UserOut
