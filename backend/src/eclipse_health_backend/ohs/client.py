"""Open Health Sync HTTP 客户端。

事实约束（来自 OHS 文档摘要）：

- REST base 默认 ``http://localhost:8080``；
- 认证头 ``Authorization: Bearer <tenant key | user token>``；
- 关键读接口 ``/v1/users``、``/v1/users/{id}/daily``。

本模块只做只读调用，不代理 OHS 的 MCP，也不做任何安装管理。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Self
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from ..domain.errors import ApiError, InvalidInputError

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_TOKEN_LENGTH = 4096
USER_AGENT = "eclipse-health/ohs-connector"


class OhsError(ApiError):
    status_code = 502
    code = "ohs_error"


class OhsUnreachableError(OhsError):
    status_code = 502
    code = "ohs_unreachable"


class OhsAuthError(OhsError):
    status_code = 401
    code = "ohs_auth_failed"


class OhsPermissionError(OhsError):
    status_code = 403
    code = "ohs_forbidden"


class OhsProtocolError(OhsError):
    status_code = 502
    code = "ohs_bad_response"


def normalize_base_url(raw: str | None) -> str:
    """只接受 http/https，去掉尾部斜杠；拒绝凭据、查询串与片段。"""
    value = (raw or "").strip() or DEFAULT_BASE_URL
    split = urlsplit(value)
    if split.scheme.lower() not in {"http", "https"}:
        raise InvalidInputError(
            "OHS 地址必须以 http:// 或 https:// 开头",
            code="ohs_invalid_base_url",
            details={"baseUrl": value[:200]},
        )
    if not split.hostname:
        raise InvalidInputError(
            "OHS 地址缺少主机名",
            code="ohs_invalid_base_url",
            details={"baseUrl": value[:200]},
        )
    if split.username or split.password:
        raise InvalidInputError(
            "OHS 地址不能包含用户名或密码",
            code="ohs_invalid_base_url",
        )
    if split.query or split.fragment:
        raise InvalidInputError(
            "OHS 地址不能包含查询串或片段",
            code="ohs_invalid_base_url",
        )
    path = split.path.rstrip("/")
    return urlunsplit((split.scheme.lower(), split.netloc, path, "", ""))


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "users", "data", "results", "daily", "days", "entries"):
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
            if isinstance(nested, dict):
                deeper = _as_list(nested)
                if deeper:
                    return deeper
    return []


def extract_users(payload: Any) -> list[dict[str, Any]]:
    """兼容 ``[...]``、``{"users": [...]}``、``{"data": {"users": [...]}}``。"""
    users: list[dict[str, Any]] = []
    for item in _as_list(payload):
        if not isinstance(item, dict):
            continue
        identifier = (
            item.get("id")
            or item.get("userId")
            or item.get("user_id")
            or item.get("key")
        )
        if identifier is None or str(identifier).strip() == "":
            continue
        name = item.get("name") or item.get("displayName") or item.get("display_name")
        users.append(
            {
                "id": str(identifier),
                "name": str(name) if name is not None else "",
            }
        )
    return users


def extract_daily_entries(payload: Any) -> list[dict[str, Any]]:
    entries = [item for item in _as_list(payload) if isinstance(item, dict)]
    if entries:
        return entries
    # 单日对象也接受，避免因包装层差异丢掉数据。
    if isinstance(payload, dict):
        for key in ("daily", "day", "summary", "data"):
            nested = payload.get(key)
            if isinstance(nested, dict) and _looks_like_daily(nested):
                return [nested]
        if _looks_like_daily(payload):
            return [payload]
    return []


def _looks_like_daily(value: dict[str, Any]) -> bool:
    keys = {str(key).lower() for key in value}
    return bool(
        keys
        & {
            "date",
            "day",
            "steps",
            "restingheartrate",
            "sleepminutes",
            "weightkg",
            "bloodpressure",
        }
    )


class OhsClient:
    """同步 httpx 客户端；每次实例化只服务一次设置/同步动作。"""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url)
        token = (token or "").strip()
        if not token:
            raise InvalidInputError(
                "请先填写 OHS token",
                code="ohs_token_required",
            )
        if len(token) > MAX_TOKEN_LENGTH:
            raise InvalidInputError(
                "OHS token 过长",
                code="ohs_token_invalid",
            )
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _request(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            return self._client.get(f"{self.base_url}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise OhsUnreachableError(
                "连接 OHS 超时（10 秒）",
                code="ohs_timeout",
                details={"baseUrl": self.base_url},
            ) from exc
        except httpx.HTTPError as exc:
            raise OhsUnreachableError(
                "无法连接 OHS，请确认服务已启动且地址正确",
                code="ohs_unreachable",
                details={"baseUrl": self.base_url},
            ) from exc

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise OhsProtocolError(
                "OHS 返回了无法解析的响应",
                code="ohs_bad_response",
                details={"status": response.status_code},
            ) from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401,):
            raise OhsAuthError(
                "OHS 拒绝了该 token（401）",
                code="ohs_auth_failed",
                details={"status": response.status_code},
            )
        if response.status_code in (403,):
            raise OhsPermissionError(
                "该 OHS token 没有读取权限（403）",
                code="ohs_forbidden",
                details={"status": response.status_code},
            )
        if response.status_code == 404:
            raise OhsProtocolError(
                "OHS 没有提供该接口，版本可能不匹配",
                code="ohs_endpoint_missing",
                details={"status": response.status_code},
            )
        if response.status_code >= 400:
            raise OhsProtocolError(
                f"OHS 返回 HTTP {response.status_code}",
                code="ohs_bad_response",
                details={"status": response.status_code},
            )

    def test_connection(self) -> dict[str, Any]:
        """调用 ``GET /v1/users``；成功返回认证类型与用户列表。

        tenant key 通常能列出用户；只读 user token 可能返回 403，
        此时服务本身可达，返回 ``user`` 类型并附警告。
        """
        response = self._request("/v1/users")
        if response.status_code == 403:
            return {
                "ok": True,
                "baseUrl": self.base_url,
                "authType": "user",
                "userCount": 0,
                "users": [],
                "warnings": [
                    {
                        "code": "ohs_user_token_limited",
                        "message": "该 token 不能列出用户；同步时请手动填写 user id。",
                    }
                ],
            }
        self._raise_for_status(response)
        users = extract_users(self._json(response))
        return {
            "ok": True,
            "baseUrl": self.base_url,
            "authType": "tenant" if len(users) != 1 else "user",
            "userCount": len(users),
            "users": users,
            "warnings": [] if users else [
                {
                    "code": "ohs_no_users",
                    "message": "连接成功，但 /v1/users 没有返回用户。",
                }
            ],
        }

    def list_users(self) -> list[dict[str, Any]]:
        response = self._request("/v1/users")
        self._raise_for_status(response)
        return extract_users(self._json(response))

    def fetch_daily(
        self,
        user_id: str,
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        """读取 ``GET /v1/users/{id}/daily?from=...&to=...``。

        参数名按 OHS 文档摘要使用 ``from`` / ``to``；字段解析的容错在 ``sync`` 中。
        """
        if not str(user_id or "").strip():
            raise InvalidInputError("请先确定 OHS user id", code="ohs_user_required")
        path = f"/v1/users/{quote(str(user_id).strip(), safe='')}/daily"
        response = self._request(
            path,
            params={"from": start.isoformat(), "to": end.isoformat()},
        )
        self._raise_for_status(response)
        return extract_daily_entries(self._json(response))


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "OhsAuthError",
    "OhsClient",
    "OhsError",
    "OhsPermissionError",
    "OhsProtocolError",
    "OhsUnreachableError",
    "extract_daily_entries",
    "extract_users",
    "normalize_base_url",
]
