"""导入链路的业务异常，统一映射为 ``{code, message, details}``。"""

from __future__ import annotations

from typing import Any

from ..domain.errors import ApiError, NotFoundError


class ImportApiError(ApiError):
    status_code = 422
    code = "invalid_file"


class InvalidImportFileError(ImportApiError):
    code = "invalid_file"


class UnsupportedFormatError(ImportApiError):
    code = "unsupported_format"


class ImportTooLargeError(ApiError):
    status_code = 413
    code = "file_too_large"


class ImportNotFoundError(NotFoundError):
    code = "import_not_found"


class ImportConflictError(ApiError):
    status_code = 409
    code = "conflict"


def invalid_file(message: str, *, code: str = "invalid_file", details: Any = None) -> InvalidImportFileError:
    return InvalidImportFileError(message, code=code, details=details)


def unsupported_format(message: str, *, details: Any = None) -> UnsupportedFormatError:
    return UnsupportedFormatError(message, details=details)


__all__ = [
    "ImportApiError",
    "ImportConflictError",
    "ImportNotFoundError",
    "ImportTooLargeError",
    "InvalidImportFileError",
    "UnsupportedFormatError",
    "invalid_file",
    "unsupported_format",
]
