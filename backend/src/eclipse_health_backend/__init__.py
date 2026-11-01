"""eclipse health 后端。"""

from __future__ import annotations

__version__ = "0.1.0"


def main() -> None:
    """``eclipse-health-backend`` 入口：启动本地 API 服务。"""
    import uvicorn

    from .settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "eclipse_health_backend.app:app",
        host="127.0.0.1",
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


__all__ = ["__version__", "main"]
