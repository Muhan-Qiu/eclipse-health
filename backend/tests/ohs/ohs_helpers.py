"""OHS test helpers (unique module name)."""

import pytest


def dpapi_available() -> bool:
    try:
        import win32crypt  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


requires_dpapi = pytest.mark.skipif(
    not dpapi_available(), reason="Windows DPAPI is required"
)



__all__ = ["dpapi_available","requires_dpapi"]
