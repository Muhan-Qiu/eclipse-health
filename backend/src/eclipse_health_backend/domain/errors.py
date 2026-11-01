"""业务异常：统一映射为 ``{code, message, details}`` 响应体。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Any = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


class NotFoundError(ApiError):
    status_code = 404
    code = "not_found"


class ConflictError(ApiError):
    status_code = 409
    code = "conflict"


class InvalidInputError(ApiError):
    status_code = 422
    code = "validation_error"


class StorageIntegrityError(ApiError):
    status_code = 500
    code = "storage_integrity_error"


def not_found(resource: str, identifier: str) -> NotFoundError:
    return NotFoundError(
        f"{resource} not found: {identifier}",
        code=f"{resource}_not_found",
        details={"id": identifier},
    )
