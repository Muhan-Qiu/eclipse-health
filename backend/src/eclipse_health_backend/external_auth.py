"""对外 API Key 的创建、校验与 scope 检查（F3）。

安全约定：

- 明文 token 形如 ``eh_ext_<urlsafe 32 bytes>``，只在 ``POST /external/keys`` 返回一次；
- 数据库只存 SHA-256，列表接口只返回 ``prefix``（不足以反推 token）；
- 撤销立即生效；``last_used_at`` 在每次成功认证时更新。
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass

from sqlmodel import Session, select

from .db.models import ExternalApiKeyTable
from .domain.common import utc_now
from .domain.errors import ApiError, InvalidInputError
from .domain.ids import uuid7

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "eh_ext_"
TOKEN_BYTES = 32
PREFIX_DISPLAY_LENGTH = 16
VALID_SCOPES: tuple[str, ...] = ("read", "write", "assistant")
_MAX_NAME = 80


class InvalidApiKeyError(ApiError):
    status_code = 401
    code = "invalid_api_key"


class InsufficientScopeError(ApiError):
    status_code = 403
    code = "insufficient_scope"


@dataclass(frozen=True)
class ExternalKey:
    """一次认证通过的 key 视图；不含 hash 与明文。"""

    id: str
    name: str
    scopes: tuple[str, ...]

    def has(self, scope: str) -> bool:
        return scope in self.scopes


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_scopes(raw: list[str]) -> tuple[str, ...]:
    scopes: list[str] = []
    for item in raw:
        scope = str(item).strip().lower()
        if not scope:
            continue
        if scope not in VALID_SCOPES:
            raise InvalidInputError(
                "unknown scope",
                code="invalid_scope",
                details={"scope": scope, "allowed": list(VALID_SCOPES)},
            )
        if scope not in scopes:
            scopes.append(scope)
    if not scopes:
        raise InvalidInputError(
            "at least one scope is required",
            code="invalid_scope",
            details={"allowed": list(VALID_SCOPES)},
        )
    return tuple(scopes)


def create_key(
    session: Session, *, name: str, scopes: list[str]
) -> tuple[ExternalApiKeyTable, str]:
    cleaned_name = (name or "").strip()
    if not cleaned_name or len(cleaned_name) > _MAX_NAME:
        raise InvalidInputError(
            "name must be 1-80 characters", code="invalid_key_name"
        )
    normalized = normalize_scopes(scopes)

    token = ""
    for _ in range(5):
        candidate = f"{TOKEN_PREFIX}{secrets.token_urlsafe(TOKEN_BYTES)}"
        digest = hash_token(candidate)
        exists = session.exec(
            select(ExternalApiKeyTable).where(ExternalApiKeyTable.key_hash == digest)
        ).first()
        if exists is None:
            token = candidate
            break
    if not token:  # pragma: no cover - 2^256 空间下实际不会发生
        raise ApiError("could not allocate a unique key", status_code=500)

    row = ExternalApiKeyTable(
        id=f"key_{uuid7()}",
        name=cleaned_name,
        prefix=token[:PREFIX_DISPLAY_LENGTH],
        key_hash=hash_token(token),
        scopes=list(normalized),
        created_at=utc_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    logger.info("external key created id=%s scopes=%s", row.id, ",".join(normalized))
    return row, token


def list_keys(session: Session) -> list[ExternalApiKeyTable]:
    statement = select(ExternalApiKeyTable).order_by(
        ExternalApiKeyTable.created_at.desc(), ExternalApiKeyTable.id.desc()
    )
    return list(session.exec(statement))


def revoke_key(session: Session, key_id: str) -> ExternalApiKeyTable | None:
    row = session.get(ExternalApiKeyTable, key_id)
    if row is None:
        return None
    if row.revoked_at is None:
        row.revoked_at = utc_now()
        session.add(row)
        session.commit()
        session.refresh(row)
        logger.info("external key revoked id=%s", key_id)
    return row


def key_to_dict(row: ExternalApiKeyTable) -> dict[str, object]:
    """只输出展示字段；绝不包含 ``key_hash`` 或明文。"""
    return {
        "id": row.id,
        "name": row.name,
        "prefix": row.prefix,
        "scopes": list(row.scopes or []),
        "createdAt": row.created_at,
        "lastUsedAt": row.last_used_at,
        "revokedAt": row.revoked_at,
        "revoked": row.revoked_at is not None,
    }


def extract_token(
    authorization: str | None, x_api_key: str | None
) -> str | None:
    """支持 ``Authorization: Bearer`` 与 ``X-API-Key``；都没有返回 None。"""
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()
    if x_api_key and x_api_key.strip():
        return x_api_key.strip()
    return None


def authenticate(session: Session, token: str) -> ExternalKey:
    digest = hash_token(token)
    row = session.exec(
        select(ExternalApiKeyTable).where(ExternalApiKeyTable.key_hash == digest)
    ).first()
    if row is None or row.revoked_at is not None:
        raise InvalidApiKeyError("API key is invalid or revoked")
    # 常量时间比较，避免理论上通过响应时间探测 hash 前缀。
    if not hmac.compare_digest(row.key_hash, digest):  # pragma: no cover - 查询已匹配
        raise InvalidApiKeyError("API key is invalid or revoked")
    row.last_used_at = utc_now()
    session.add(row)
    session.commit()
    return ExternalKey(id=row.id, name=row.name, scopes=tuple(row.scopes or []))


def require_scope(key: ExternalKey, scope: str) -> None:
    if not key.has(scope):
        raise InsufficientScopeError(
            f"API key lacks the '{scope}' scope",
            details={"required": scope, "granted": list(key.scopes)},
        )


__all__ = [
    "PREFIX_DISPLAY_LENGTH",
    "TOKEN_PREFIX",
    "VALID_SCOPES",
    "ExternalKey",
    "InsufficientScopeError",
    "InvalidApiKeyError",
    "authenticate",
    "create_key",
    "extract_token",
    "hash_token",
    "key_to_dict",
    "list_keys",
    "normalize_scopes",
    "require_scope",
    "revoke_key",
]
