"""冻结版 sidecar 的 pip 入口：``eclipse-health-backend.exe pip_install.py install ...``。

PyInstaller 冻结后没有 python.exe，不能再 ``python -m venv`` / ``-m pip``。
模块依赖改为用随包 pip 安装到模块目录的 ``deps/``，worker 启动时把该目录加入 sys.path。
"""

from __future__ import annotations

import sys


def _patch_distlib_resources() -> None:
    """PyInstaller 的模块 loader 不在 distlib 的 finder 表里，pip 导入时会直接失败。"""
    try:
        from pip._vendor import distlib
        from pip._vendor.distlib import resources as distlib_resources

        distlib_resources.register_finder(distlib.__loader__, distlib_resources.ResourceFinder)
    except Exception:  # noqa: BLE001, S110 - 非冻结/旧 pip 无需此补丁
        pass


def main() -> int:
    _patch_distlib_resources()
    try:
        from pip._internal.cli.main import main as pip_main
    except ImportError:
        print("pip is not bundled", file=sys.stderr)
        return 2
    return int(pip_main(sys.argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
