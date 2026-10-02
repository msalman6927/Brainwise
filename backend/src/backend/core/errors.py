import logging
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """Base for every error that must surface as the API error envelope (AGENTS.md §9)."""

    code: str = "internal"
    status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UnauthorizedError(DomainError):
    code = "unauthorized"
    status = 401


class InvalidCredentialsError(DomainError):
    code = "invalid_credentials"
    status = 401


class ForbiddenError(DomainError):
    code = "forbidden"
    status = 403


class NotFoundError(DomainError):
    code = "not_found"
    status = 404


class InvalidPhaseError(DomainError):
    code = "invalid_phase"
    status = 409


class AlreadyAnsweredError(DomainError):
    code = "already_answered"
    status = 409


class UnsupportedTopicError(DomainError):
    code = "unsupported_topic"
    status = 422
    retryable = True


class RateLimitedError(DomainError):
    code = "rate_limited"
    status = 429
    retryable = True


class InvalidRequestError(DomainError):
    """Malformed request bodies/params — built by the RequestValidationError handler."""

    code = "invalid_request"
    status = 422


def error_envelope(exc: DomainError) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "retryable": exc.retryable,
        }
    }


def _validation_fields(errors: Sequence[Any]) -> list[dict[str, str]]:
    """Flatten pydantic errors into JSON-safe {loc, msg, type} records (§9 details.fields)."""
    fields: list[dict[str, str]] = []
    for err in errors:
        fields.append(
            {
                "loc": ".".join(str(part) for part in err.get("loc", ())),
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return fields


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = _validation_fields(exc.errors())
        logger.warning(
            "request_validation_failed path=%s locs=%s",
            request.url.path,
            [f["loc"] for f in fields],
        )
        error = InvalidRequestError("Request validation failed", details={"fields": fields})
        return JSONResponse(status_code=error.status, content=error_envelope(error))

    @app.exception_handler(ResponseValidationError)
    async def handle_response_validation(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        # Our own response_model failed — a server bug; never leak schema internals.
        logger.error(
            "response_validation_failed path=%s errors=%s",
            request.url.path,
            _validation_fields(exc.errors()),
            exc_info=exc,
        )
        error = DomainError("Internal server error")
        return JSONResponse(status_code=error.status, content=error_envelope(error))

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        log = logger.warning if exc.status < 500 else logger.error
        log(
            "domain_error code=%s path=%s message=%s",
            exc.code,
            request.url.path,
            exc.message,
        )
        return JSONResponse(status_code=exc.status, content=error_envelope(exc))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(status_code=500, content=error_envelope(DomainError(str(exc))))
