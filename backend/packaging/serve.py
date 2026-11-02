"""PyInstaller 冻结入口（生产 sidecar）。

职责（按 `prompts/31-packaging.md`）：

1. **模块 worker 复用自身可执行文件**：模块宿主用 ``sys.executable`` 启动
   ``src/main.py``。冻结后 ``sys.executable`` 就是本 sidecar，所以这里先识别
   “argv[1] 是 .py 文件”的调用形态，用 ``runpy`` 直接跑模块脚本，不再经过 uvicorn。
2. **冻结路径修正**：核心用 ``Path(__file__).parents[n]`` 定位仓库资源，冻结后
   这些路径不再指向仓库，这里把 ``DEFAULT_MODEL_DIR`` 指到包内
   ``backend/resources/models/cardia``。
3. **生产数据目录**：默认 ``%LOCALAPPDATA%\\eclipse-health``，与 dev 的
   ``backend/.data`` 完全隔离。
4. **启动前安装 Cardia 模块**：从随包 ``modules/official/cardia`` 打包安装到数据目录，
   已在注册表则跳过；失败只记录，不阻塞服务启动。
5. 启动 uvicorn（单进程、无 reload），日志同时写 ``<data>/logs/backend.log``。

非冻结状态下（直接 `python backend/packaging/serve.py`）也能跑，便于冒烟测试；
此时资源从仓库根目录解析，数据目录沿用 ``EH_DATA_DIR`` 的默认值。
"""

from __future__ import annotations

import argparse
import logging
import os
import runpy
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_DIR_NAME = "eclipse-health"
CARDIA_MODULE_ID = "org.eclipsehealth.cardia"
LOG_FILE_NAME = "backend.log"
LOG_MAX_BYTES = 10 * 1024 * 1024

logger = logging.getLogger("eclipse_health_backend.frozen")


# --------------------------------------------------------------------------- 环境
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    """随包资源的根目录：onefile 解压目录；源码运行时是仓库根目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_DIR_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / APP_DIR_NAME
    return Path.home() / ".local" / "share" / APP_DIR_NAME


def apply_environment(data_dir: Path | None, port: int | None, log_level: str | None) -> Path:
    """在导入应用之前落定环境变量（settings 是 lru_cache，越早越好）。"""
    if data_dir is not None:
        os.environ["EH_DATA_DIR"] = str(data_dir)
    elif is_frozen():
        os.environ.setdefault("EH_DATA_DIR", str(default_data_dir()))

    if port is not None:
        os.environ["EH_PORT"] = str(port)
    if log_level:
        os.environ["EH_LOG_LEVEL"] = log_level.upper()

    # matplotlib 在无 GUI 的 sidecar 里固定用 Agg，避免尝试打开显示后端。
    os.environ.setdefault("MPLBACKEND", "Agg")
    _apply_thread_env()
    # LiteLLM 会写用户目录缓存/日志；关掉它的遥测与本地日志，保持本地优先。
    os.environ.setdefault("LITELLM_LOG", "ERROR")
    os.environ.setdefault("LITELLM_TELEMETRY", "False")

    # 随包 tiktoken 词表缓存：离线也能完成 token 计数（LiteLLM 首次调用依赖它）。
    if is_frozen():
        token_cache = bundle_root() / "tiktoken_cache"
        if token_cache.is_dir():
            os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(token_cache))

    return Path(os.environ.get("EH_DATA_DIR") or (default_data_dir()))


def _apply_thread_env() -> None:
    """限制 BLAS/OpenMP 线程数。

    桌面场景通常是单条记录分析，线程给太多只会放大内存峰值（低配 Windows
    + 页文件较小时 OpenBLAS 会直接 malloc 失败）。用户显式设置时不覆盖。
    只影响并行度，不影响任何数值。
    """
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(name, "4")


# --------------------------------------------------------------------------- 路径修正
class _AnalysisPathHook:
    """延迟修正 ``eclipse_health_backend.analysis`` 的模型目录。

    冻结后 ``types.py`` 的 ``Path(__file__).parents[3]`` 指向临时解压目录的父级，
    找不到 ``resources/models/cardia``。这里不能一上来就 import 整个 analysis 包：
    模块 worker 的 ``initialize`` 只有 10 秒预算，而 analysis 会连带 scipy/wfdb/
    neurokit2。于是用 import hook，在包真正被导入后再改写模块级常量。
    """

    _target = "eclipse_health_backend.analysis"

    def find_spec(self, fullname, path=None, target=None):  # type: ignore[no-untyped-def]
        if fullname != self._target:
            return None
        # 冻结后包在 PYZ 里，由 PyInstaller 的 finder 解析；这里按 meta_path 顺序
        # 委托给除自己以外的第一个 finder，而不是 PathFinder（源码树才适用）。
        spec = None
        for finder in sys.meta_path:
            if finder is self:
                continue
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is not None:
                break
        if spec is None or spec.loader is None:
            return spec
        original_exec = spec.loader.exec_module

        def exec_module(module):  # type: ignore[no-untyped-def]
            original_exec(module)
            _apply_model_dir()

        spec.loader.exec_module = exec_module  # type: ignore[method-assign]
        return spec


_model_dir_logged = False


def _apply_model_dir() -> None:
    """把已导入的 analysis 相关模块的 DEFAULT_MODEL_DIR 指到包内资源。"""
    global _model_dir_logged
    if not is_frozen():
        return
    model_dir = bundle_root() / "backend" / "resources" / "models" / "cardia"
    if not model_dir.is_dir():
        logger.warning("bundled model dir missing: %s", model_dir)
        return
    for name in (
        "eclipse_health_backend.analysis",
        "eclipse_health_backend.analysis.types",
        "eclipse_health_backend.analysis.model",
    ):
        module = sys.modules.get(name)
        if module is not None:
            module.DEFAULT_MODEL_DIR = model_dir  # type: ignore[attr-defined]
    if not _model_dir_logged:
        _model_dir_logged = True
        logger.info("frozen model dir -> %s", model_dir)


_hook_installed = False


def install_frozen_path_hook() -> None:
    global _hook_installed
    if not is_frozen():
        return
    if _hook_installed:
        return
    sys.meta_path.insert(0, _AnalysisPathHook())
    _hook_installed = True
    # 已经导入过（例如外部先 import 了包）时立即修正一次。
    _apply_model_dir()


def _bundled_module_dir() -> Path:
    return bundle_root() / "modules" / "official" / "cardia"


def _repair_bridge_source_dir() -> None:
    """bridge 用仓库相对路径找内置模块；冻结后改到包内目录。"""
    import eclipse_health_backend.analysis_service.bridge as bridge_mod

    source = _bundled_module_dir()
    if source.is_dir():
        bridge_mod.CARDIA_SOURCE_DIR = source  # type: ignore[assignment]


# --------------------------------------------------------------------------- 日志
def configure_logging(data_dir: Path, level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handlers: list[logging.Handler] = []
    try:
        # 用 RotatingFileHandler 而不是 FileHandler：核心的 diagnostics.logging_setup
        # 在 lifespan 里按“已有同路径 RotatingFileHandler 就跳过”去重，否则日志会写两遍。
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=3,
            encoding="utf-8",
            errors="replace",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    except OSError:
        pass
    # 冻结后没有控制台；保留 stderr 便于从父进程日志里看首屏错误。
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)


# --------------------------------------------------------------------------- 模块预装
def ensure_bundled_module(data_dir: Path) -> None:
    """启动前确保 Cardia 模块已安装（随包源码 → 临时 .ehmod → 数据目录）。"""
    source = _bundled_module_dir()
    if not (source / "module.json").is_file():
        logger.warning("bundled cardia module not found at %s; analysis stays unavailable", source)
        return

    from eclipse_health_backend.analysis_service.bridge import CardiaBridge
    from eclipse_health_backend.db.base import init_db
    from eclipse_health_backend.modules.api import get_manager, shutdown_module_system
    from eclipse_health_backend.settings import get_settings

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    bridge = CardiaBridge(get_manager)
    try:
        installed = bridge.ensure_installed()
        logger.info(
            "cardia module ready: id=%s version=%s state=%s",
            installed.get("id"),
            installed.get("version"),
            installed.get("state"),
        )
    except Exception:  # 模块装不上也要能起服务，错误留给 /engine
        logger.exception("bundled cardia module install failed")
    finally:
        # uvicorn lifespan 会重新初始化模块系统，这里先释放，避免两个 manager 并存。
        shutdown_module_system()


# --------------------------------------------------------------------------- 模块 worker
def maybe_run_module_worker(argv: list[str]) -> bool:
    """识别 ``sidecar <module>/src/main.py`` 形态，作为模块 worker 直接执行脚本。"""
    if len(argv) < 2:
        return False
    candidate = Path(argv[1])
    if candidate.suffix.lower() != ".py" or not candidate.is_file():
        return False

    sys.argv = [str(candidate), *argv[2:]]
    sys.path.insert(0, str(candidate.parent))
    deps = os.environ.get("EH_MODULE_DEPS")
    if deps and Path(deps).is_dir():
        # 冻结版模块依赖装在模块目录 deps/；优先于随包模块。
        sys.path.insert(0, deps)
    _apply_thread_env()
    install_frozen_path_hook()
    runpy.run_path(str(candidate), run_name="__main__")
    return True


# --------------------------------------------------------------------------- 主流程
def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="eclipse health backend sidecar")
    parser.add_argument("--host", default=os.environ.get("EH_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=None, help="默认读 EH_PORT / 8765")
    parser.add_argument("--data-dir", type=Path, default=None, help="默认读 EH_DATA_DIR")
    parser.add_argument("--log-level", default=None, help="默认读 EH_LOG_LEVEL / INFO")
    return parser.parse_args(argv)


def serve(argv: list[str]) -> int:
    args = _parse_args(argv)
    data_dir = apply_environment(args.data_dir, args.port, args.log_level)
    level_name = os.environ.get("EH_LOG_LEVEL", "INFO")
    configure_logging(data_dir, level_name)

    install_frozen_path_hook()
    _repair_bridge_source_dir()
    ensure_bundled_module(data_dir)

    import uvicorn

    from eclipse_health_backend.app import app
    from eclipse_health_backend.settings import get_settings

    settings = get_settings()
    host = args.host or "127.0.0.1"
    port = args.port or settings.port
    logger.info("starting sidecar host=%s port=%s data=%s", host, port, settings.data_dir)

    # log_config=None：沿用上面的 basicConfig，把 uvicorn 日志也写进 backend.log。
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=level_name.lower(),
        log_config=None,
        access_log=False,
    )
    uvicorn.Server(config).run()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    try:
        if maybe_run_module_worker(argv):
            return 0
        return serve(argv[1:])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
