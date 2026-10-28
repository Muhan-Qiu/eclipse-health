"""最小 SemVer 实现：解析 version 与 engines 范围，避免引入额外依赖。"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)
_PARTIAL_RE = re.compile(r"^(?P<major>0|[1-9]\d*)(?:\.(?P<minor>0|[1-9]\d*))?(?:\.(?P<patch>0|[1-9]\d*))?$")


@dataclass(frozen=True, order=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: str = ""

    @property
    def sort_key(self) -> tuple[int, int, int, int, str]:
        # 有预发布号的版本小于同号正式版。
        return (self.major, self.minor, self.patch, 0 if self.prerelease else 1, self.prerelease)


def parse_version(text: str) -> Version | None:
    match = _SEMVER_RE.match(text.strip())
    if not match:
        return None
    return Version(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        match.group("prerelease") or "",
    )


def _parse_partial(text: str) -> Version | None:
    match = _PARTIAL_RE.match(text.strip())
    if not match:
        return None
    return Version(
        int(match.group("major")),
        int(match.group("minor") or 0),
        int(match.group("patch") or 0),
    )


def _compare(version: Version, bound: Version) -> int:
    left = version.sort_key
    right = bound.sort_key
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _upper_for_partial(version: Version, parts: int) -> Version:
    if parts <= 1:
        return Version(version.major + 1, 0, 0)
    return Version(version.major, version.minor + 1, 0)


def _expand_token(token: str) -> list[tuple[str, Version]]:
    """把一个范围 token 展开为若干 (op, bound)。"""
    raw = token.strip()
    if not raw:
        return []
    for prefix, op in ((">=", ">="), ("<=", "<="), ("==", "="), (">", ">"), ("<", "<"), ("=", "=")):
        if raw.startswith(prefix):
            bound = _parse_partial(raw[len(prefix) :])
            return [(op, bound)] if bound else []
    if raw.startswith("^"):
        bound = _parse_partial(raw[1:])
        if not bound:
            return []
        if bound.major > 0:
            upper = Version(bound.major + 1, 0, 0)
        elif bound.minor > 0:
            upper = Version(0, bound.minor + 1, 0)
        else:
            upper = Version(0, 0, bound.patch + 1)
        return [(">=", bound), ("<", upper)]
    if raw.startswith("~"):
        bound = _parse_partial(raw[1:])
        if not bound:
            return []
        return [(">=", bound), ("<", Version(bound.major, bound.minor + 1, 0))]

    bound = _parse_partial(raw)
    if not bound:
        return []
    parts = len(raw.split("."))
    if parts >= 3:
        return [("=", bound)]
    upper = _upper_for_partial(bound, parts)
    return [(">=", bound), ("<", upper)]


def satisfies(version: str, spec: str) -> bool:
    """判断 version 是否落在 spec 范围内。spec 形如 ">=1.0 <2.0" / "^1.2.3"。

    解析失败视为不兼容（fail closed）。
    """
    parsed = parse_version(version)
    if parsed is None:
        return False
    tokens = [token for token in re.split(r"[,\s]+", spec.strip()) if token]
    if not tokens:
        return False
    for token in tokens:
        bounds = _expand_token(token)
        if not bounds:
            return False
        for op, bound in bounds:
            result = _compare(parsed, bound)
            if op == ">=" and result < 0:
                return False
            if op == "<=" and result > 0:
                return False
            if op == ">" and result <= 0:
                return False
            if op == "<" and result >= 0:
                return False
            if op == "=" and result != 0:
                return False
    return True
