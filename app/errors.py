"""One JSON error format for the whole API.

Every error response has this body:

    {"error": {"code": "...", "message": "...", "details": [...]}}

`details` is present only for validation errors.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for errors the API reports to the client."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: list[dict] | None = None, headers: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        self.headers = headers


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Not authenticated"):
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class InvalidInputError(AppError):
    """A rule that the request models cannot check on their own, such as a reversed date range."""

    status_code = 422
    code = "validation_error"

    def __init__(self, field: str, message: str):
        super().__init__("Request validation failed", details=[{"field": field, "message": message}])


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[dict] | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, details=exc.details, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Only the location and the message are passed on. The rejected input
        # is left out, so a password that fails validation is not echoed back.
        details = [
            {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
            for error in exc.errors()
        ]
        return error_response(422, "validation_error", "Request validation failed", details=details)

    @app.exception_handler(StarletteHTTPException)
    def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # The details go to the log, never to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return error_response(500, "internal_error", "Internal server error")
