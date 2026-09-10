"""
PRAMAAN API error handling.

Centralised exception handlers + custom exception types.
Design: all HTTP errors return a structured ErrorResponse JSON body.
Stack traces and filesystem paths are never exposed to clients.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from backend.api.schemas import ErrorResponse

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception types (raised in routes, handled here)
# ---------------------------------------------------------------------------

class AssessmentNotFound(Exception):
    """Raised when an assessment_id does not exist in the DB."""

    def __init__(self, assessment_id: str) -> None:
        self.assessment_id = assessment_id
        super().__init__(assessment_id)


class InvalidAssetPath(Exception):
    """
    Raised when a user-supplied path fails security validation:
      - Not absolute
      - Resolves outside trusted roots
      - Does not exist
      - Exceeds size limit
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class UnsupportedFormat(Exception):
    """Raised when a format string is not in the allowed set."""

    def __init__(self, value: str, allowed: list[str]) -> None:
        self.value = value
        self.allowed = allowed
        super().__init__(f"{value!r} not in {allowed}")


class AssessmentExecutionError(Exception):
    """Raised when AssessmentService returns a FAILED result."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class DependencyUnavailable(Exception):
    """Raised when a required optional dependency (e.g. onnx) is missing."""

    def __init__(self, dep: str) -> None:
        self.dep = dep
        super().__init__(dep)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

def _json_error(
    code: int,
    error: str,
    message: str,
    detail: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content=ErrorResponse(error=error, message=message, detail=detail).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""

    @app.exception_handler(AssessmentNotFound)
    async def handle_not_found(request: Request, exc: AssessmentNotFound) -> JSONResponse:
        return _json_error(
            status.HTTP_404_NOT_FOUND,
            "assessment_not_found",
            f"Assessment '{exc.assessment_id}' was not found.",
        )

    @app.exception_handler(InvalidAssetPath)
    async def handle_invalid_path(request: Request, exc: InvalidAssetPath) -> JSONResponse:
        log.warning("Invalid asset path rejected: %s", exc.reason)
        return _json_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_asset_path",
            "The supplied asset path failed security validation.",
            detail=exc.reason,
        )

    @app.exception_handler(UnsupportedFormat)
    async def handle_format(request: Request, exc: UnsupportedFormat) -> JSONResponse:
        return _json_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "unsupported_format",
            f"Format {exc.value!r} is not supported.",
            detail=f"Allowed: {exc.allowed}",
        )

    @app.exception_handler(AssessmentExecutionError)
    async def handle_exec_error(request: Request, exc: AssessmentExecutionError) -> JSONResponse:
        log.error("Assessment execution failed: %s", exc.reason)
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "assessment_failed",
            "The assessment engine reported a failure.",
            detail=exc.reason,
        )

    @app.exception_handler(DependencyUnavailable)
    async def handle_dependency(request: Request, exc: DependencyUnavailable) -> JSONResponse:
        return _json_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "dependency_unavailable",
            f"Optional dependency '{exc.dep}' is not installed.",
            detail="Install the [models] extra: pip install -e '.[models]'",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the real error locally but NEVER expose internals to the client.
        log.exception("Unexpected error on %s %s", request.method, request.url.path)
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred. Check server logs for details.",
        )
