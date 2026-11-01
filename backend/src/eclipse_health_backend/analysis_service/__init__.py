"""核心分析服务：Cardia 模块、分析 API、引擎预热的状态与生命周期。

对外只暴露这些 + 单例获取；具体实现见 ``service.py`` / ``bridge.py`` / ``engines.py``。
"""

from .bridge import (
    CARDIA_ENGINE,
    CARDIA_MODEL_ID,
    CARDIA_MODEL_VERSION,
    CARDIA_MODULE_ID,
    CardiaBridge,
)
from .engines import EngineDescriptor, get_engine, list_engines
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
    "EngineDescriptor",
    "EngineState",
    "JobError",
    "get_analysis_service",
    "get_engine",
    "init_analysis_service",
    "list_engines",
    "set_analysis_service",
    "shutdown_analysis_service",
]
