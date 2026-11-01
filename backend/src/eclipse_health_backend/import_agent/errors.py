"""导入 Agent 的业务异常（由全局 ApiError handler 统一序列化）。"""

from __future__ import annotations

from typing import Any

from ..domain.errors import ApiError, NotFoundError


class ImportAgentError(ApiError):
    status_code = 422
    code = "invalid_file"


class ImportAgentNotFoundError(NotFoundError):
    code = "session_not_found"


class ImportAgentConflictError(ApiError):
    status_code = 409
    code = "conflict"


class RecordValidationError(ValueError):
    """单条候选记录不合法；由工具层转换成 ``invalid_record``。"""

    def __init__(
        self, message: str, *, code: str = "invalid_record", details: Any = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def session_not_found(session_id: str) -> ImportAgentNotFoundError:
    return ImportAgentNotFoundError(
        "import agent session not found",
        code="session_not_found",
        details={"id": session_id},
    )


def session_expired(session_id: str) -> ImportAgentNotFoundError:
    return ImportAgentNotFoundError(
        "import agent session expired",
        code="session_expired",
        details={"id": session_id},
    )


def invalid_file(message: str, *, code: str = "invalid_file", details: Any = None) -> ImportAgentError:
    return ImportAgentError(message, code=code, details=details)


__all__ = [
    "ImportAgentConflictError",
    "ImportAgentError",
    "ImportAgentNotFoundError",
    "RecordValidationError",
    "invalid_file",
    "session_expired",
    "session_not_found",
]
