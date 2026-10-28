"""核心分析服务：Cardia 模块、分析 API、引擎预热的状态与生命周期。

对外只暴露这四项 + 单例获取；具体实现见 ``service.py`` / ``bridge.py``。
"""

from __future__ import annotations

from .bridge import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    CardiaBridge,
)
from .service import (
    AnalysisService,
    EngineState,
    JobError,
    get_analysis_service,
    init_analysis_service,
    set_analysis_service,
    shutdown_analysis_service,
)

__all__ = [
    "CARDIA_ENGINE",
    "CARDIA_MODEL_ID",
    "CARDIA_MODEL_VERSION",
    "CARDIA_MODULE_ID",
    "AnalysisService",
    "CardiaBridge",
    "EngineState",
    "JobError",
    "get_analysis_service",
    "init_analysis_service",
    "set_analysis_service",
    "shutdown_analysis_service",
]
