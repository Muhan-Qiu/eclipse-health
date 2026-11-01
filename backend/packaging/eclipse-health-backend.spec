# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec：eclipse health 后端 sidecar。

输出：``dist/eclipse-health-backend/eclipse-health-backend.exe`` + ``_internal/``
（``scripts/build_release.ps1`` 负责按 Tauri externalBin 命名拷贝 exe，并把
``_internal`` 同步到 ``src-tauri/_internal``，安装后二者在同一个目录里）。

为什么用 onedir 而不是 onefile：

- onefile 每次启动都要把 ~270MB 解压到临时目录，实测冷启动 ~28s，模块 worker
  还要再解压一次；onedir 只做内存映射，冷启动降到秒级；
- 模块宿主用 ``sys.executable`` 启动 ``src/main.py``，onedir 下同样复用 sidecar 自身，
  不需要系统 Python。

随包资源（冻结后按 ``sys._MEIPASS`` 解析，见 ``backend/packaging/serve.py``）：

- ``modules/official/cardia`` → 启动前安装到数据目录；
- ``backend/resources/models/cardia`` → 核心模型目录（preprocess/权重）；
- ``backend/resources/samples`` → MIT-BIH 100/200/208，供离线冒烟与调试；
- ``schemas/module.schema.json`` → 放到 ``eclipse_health_backend/modules/``，
  命中 manifest 的第二个候选路径，免去运行时改路径。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPEC_DIR = Path(SPECPATH)
BACKEND_DIR = SPEC_DIR.parent          # backend/
ROOT = BACKEND_DIR.parent              # 仓库根目录

datas = []
binaries = []
hiddenimports = []


def _collect(package: str) -> None:
    """collect_all 对部分包会因可选依赖报错；缺一个包不应拖垮整个构建。"""
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception as exc:  # pragma: no cover - 构建期诊断
        print(f"[spec] skip collect_all({package}): {exc}")
        return
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hidden)


# 任务要求的运行时依赖：全部带上动态子模块（uvicorn 的 loop/http 实现、
# litellm 的 provider、pydantic_ai 的模型后端运行时才发现）。
for _package in (
    "uvicorn",
    "sqlmodel",
    "sqlalchemy",
    "onnxruntime",
    "wfdb",
    "neurokit2",
    "scipy",
    "matplotlib",
    "PIL",
    "litellm",
    "pydantic_ai",
    "sse_starlette",
    "jsonschema",
    "openpyxl",
    "orjson",
    "pandas",
    "pydantic",
    "pypdf",
    "pydantic_settings",
    "fastapi",
    "starlette",
    "httpx",
    "httptools",
    "watchfiles",
    "websockets",
    "multipart",
    "pywt",
    "jinja2",
):
    _collect(_package)

# 运行时按字符串惰性导入的模块（importers / reports / assistant / 模块系统）。
hiddenimports += collect_submodules("eclipse_health_backend")
hiddenimports += [
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

datas += [
    # A5：Agent 数据导入沙箱的 runner / helper（冻结后由子进程 runpy 执行）。
    (
        str(BACKEND_DIR / "src" / "eclipse_health_backend" / "import_agent" / "sandbox_assets"),
        "eclipse_health_backend/import_agent/sandbox_assets",
    ),
    (str(ROOT / "modules" / "official" / "cardia"), "modules/official/cardia"),
    (str(BACKEND_DIR / "resources" / "models" / "cardia"), "backend/resources/models/cardia"),
    (str(BACKEND_DIR / "resources" / "samples"), "backend/resources/samples"),
    (str(ROOT / "schemas" / "module.schema.json"), "eclipse_health_backend/modules"),
    (str(ROOT / "marketplace" / "official" / "index.json"), "eclipse_health_backend/marketplace/indexes/official"),
    (str(ROOT / "marketplace" / "community" / "index.json"), "eclipse_health_backend/marketplace/indexes/community"),
    (str(BACKEND_DIR / "src" / "eclipse_health_backend" / "marketplace" / "public_key.txt"), "eclipse_health_backend/marketplace"),
    (str(ROOT / "dist" / "modules"), "eclipse_health_backend/marketplace/packages"),
]

a = Analysis(
    [str(SPEC_DIR / "serve.py")],
    pathex=[str(BACKEND_DIR / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    # 只收 Agg：sidecar 永远无 GUI，避免构建期去探测 Qt/Tk，也避免带进无用的后端。
    hooksconfig={"matplotlib": {"backends": ["Agg"]}},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_asyncio",
        "ruff",
        "_pytest",
        "torch",
        "torchvision",
        "tensorboard",
        "tkinter",
        "IPython",
        "notebook",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="eclipse-health-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="eclipse-health-backend",
)
