"""HTTP-shaped error types.

Deliberately has NO shared-core import. Tests that only touch this module
produce no coverage edge into ``packages/shared-core``, which is what makes
the test impact analysis demo interesting: a shared-core change must not
select ``tests/test_errors.py``.
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "ApiError",
    "BadRequest",
    "NotFound",
    "Conflict",
    "UnprocessableEntity",
    "STATUS_TEXT",
    "status_text",
    "error_payload",
]

STATUS_TEXT = {
    400: "Bad Request",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
}


def status_text(status: int) -> str:
    """Reason phrase for ``status``, or ``"Unknown"``."""
    return STATUS_TEXT.get(status, "Unknown")


class ApiError(Exception):
    """Base class for everything the API surfaces to a caller."""

    status = 500
    code = "internal_error"

    def __init__(self, message: str, detail: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = dict(detail or {})

    def __repr__(self) -> str:
        return "{0}(status={1}, code={2!r}, message={3!r})".format(
            type(self).__name__, self.status, self.code, self.message
        )


class BadRequest(ApiError):
    status = 400
    code = "bad_request"


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class UnprocessableEntity(ApiError):
    status = 422
    code = "unprocessable_entity"


def error_payload(error: ApiError) -> dict:
    """Serialise an :class:`ApiError` into the API's wire shape."""
    if not isinstance(error, ApiError):
        raise TypeError("error_payload() expects an ApiError")
    payload = {
        "error": {
            "status": error.status,
            "reason": status_text(error.status),
            "code": error.code,
            "message": error.message,
        }
    }
    if error.detail:
        payload["error"]["detail"] = error.detail
    return payload
