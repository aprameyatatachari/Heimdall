"""Application errors and centralized exception handling.

Every error response uses one stable envelope::

    {
      "error": {
        "code": "portfolio_not_found",
        "message": "Portfolio not found.",
        "details": [{"field": "name", "message": "...", "code": "..."}],
        "request_id": "01J..."
      }
    }

Internal failures never leak a stack trace or an exception message to the client.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.common.logging import REQUEST_ID_HEADER, get_logger

logger = get_logger(__name__)

INTERNAL_ERROR_MESSAGE = "An unexpected error occurred. Please try again."


class ErrorDetail(BaseModel):
    """A single field-level or item-level error."""

    field: str | None = Field(default=None, description="Dotted path to the offending field.")
    message: str = Field(description="Human-readable description of the problem.")
    code: str | None = Field(default=None, description="Stable machine-readable detail code.")
    # Set by bulk operations such as CSV import, so a client can point the user at
    # the exact line of their file. Omitted everywhere else.
    row: int | None = Field(
        default=None,
        description="1-based line number in the uploaded file, including the header row.",
    )


class ErrorBody(BaseModel):
    """The body of an error response."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: list[ErrorDetail] | None = Field(default=None)
    request_id: str | None = Field(default=None)


class ErrorResponse(BaseModel):
    """The complete error envelope returned by the API."""

    error: ErrorBody


class AppError(Exception):
    """Base class for every expected application error.

    Subclasses set a stable `code` and an HTTP `status_code`. The `message` is
    safe to show to the client.
    """

    code: str = "internal_error"
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    message: str = INTERNAL_ERROR_MESSAGE

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    """A requested resource does not exist, or is not visible to the caller."""

    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND
    message = "The requested resource was not found."


class ValidationError(AppError):
    """Client input failed domain validation."""

    code = "validation_error"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    message = "The submitted data is invalid."


class ConflictError(AppError):
    """The request conflicts with the current state of the resource."""

    code = "conflict"
    status_code = status.HTTP_409_CONFLICT
    message = "The request conflicts with the current state of the resource."


class AuthenticationError(AppError):
    """The caller is not authenticated."""

    code = "not_authenticated"
    status_code = status.HTTP_401_UNAUTHORIZED
    message = "Authentication is required."


class PermissionDeniedError(AppError):
    """The caller is authenticated but not allowed to perform the action."""

    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN
    message = "You do not have permission to perform this action."


class ServiceUnavailableError(AppError):
    """A dependency the request needs is currently unavailable."""

    code = "service_unavailable"
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    message = "A required service is currently unavailable."


# HTTP status code -> stable error code, for framework-raised HTTP errors.
_STATUS_CODE_MAP: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "not_authenticated",
    status.HTTP_403_FORBIDDEN: "permission_denied",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_413_CONTENT_TOO_LARGE: "payload_too_large",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
    status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
}


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    """Build a JSON response using the standard error envelope."""
    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details, request_id=request_id)
    )
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render an `AppError` using the standard envelope."""
    assert isinstance(exc, AppError)  # noqa: S101 - handler registered for this type only
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=_request_id(request),
        details=exc.details,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render framework-raised HTTP exceptions using the standard envelope."""
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101
    code = _STATUS_CODE_MAP.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return build_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request_id=_request_id(request),
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render request-validation failures with field-level details."""
    assert isinstance(exc, RequestValidationError)  # noqa: S101
    details = [
        ErrorDetail(
            field=_format_location(error.get("loc", ())),
            message=str(error.get("msg", "Invalid value.")),
            code=str(error.get("type")) if error.get("type") else None,
        )
        for error in exc.errors()
    ]
    return build_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message="The submitted data is invalid.",
        request_id=_request_id(request),
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log an unexpected failure and return an opaque 500."""
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        exception_type=type(exc).__name__,
    )
    return build_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="internal_error",
        message=INTERNAL_ERROR_MESSAGE,
        request_id=_request_id(request),
    )


def _format_location(location: tuple[Any, ...] | list[Any]) -> str | None:
    """Turn a pydantic error location tuple into a dotted field path."""
    parts = [str(part) for part in location if part not in ("body", "query", "path", "header")]
    return ".".join(parts) if parts else None


def register_exception_handlers(app: FastAPI) -> None:
    """Attach every handler to the application."""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)


# OpenAPI-friendly reusable response declarations.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Not authenticated"},
    403: {"model": ErrorResponse, "description": "Permission denied"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}
