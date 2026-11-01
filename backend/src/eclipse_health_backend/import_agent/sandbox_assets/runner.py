"""Agent 沙箱 bootstrap。

由主进程用 ``-I``（源码模式）或无参数（冻结模式）启动：

    python -I -B -X utf8 runner.py <script.py> [args...]
    eclipse-health-backend.exe runner.py <script.py> [args...]

职责：关闭字节码缓存、安装纵深防御（禁网/禁子进程）、把 helper 目录加入
``sys.path`` 后执行 Agent 写的脚本。**这不是 OS 级沙箱**，只是减少误操作面。
"""

from __future__ import annotations

import os
import runpy
import sys
import traceback
from pathlib import Path


def _deny_network() -> None:
    if os.environ.get("EH_IMPORT_NETWORK") == "1":
        return
    import socket

    def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("network access is disabled in the import sandbox")

    socket.socket.connect = deny  # type: ignore[method-assign]
    socket.socket.connect_ex = deny  # type: ignore[method-assign]
    socket.create_connection = deny  # type: ignore[assignment]
    socket.getaddrinfo = deny  # type: ignore[assignment]
    socket.gethostbyname = deny  # type: ignore[assignment]
    socket.gethostbyname_ex = deny  # type: ignore[assignment]


def _deny_processes() -> None:
    import subprocess

    def deny(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("starting processes is disabled in the import sandbox")

    for name in (
        "Popen",
        "run",
        "call",
        "check_call",
        "check_output",
        "getoutput",
        "getstatusoutput",
    ):
        if hasattr(subprocess, name):
            setattr(subprocess, name, deny)
    for name in (
        "system",
        "popen",
        "execv",
        "execve",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "execvp",
        "execvpe",
        "spawnv",
        "spawnve",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "spawnvp",
        "spawnvpe",
    ):
        if hasattr(os, name):
            setattr(os, name, deny)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: runner.py <script.py> [args...]", file=sys.stderr)
        return 2
    script = str(Path(sys.argv[1]).resolve())
    args = sys.argv[2:]
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    _deny_network()
    _deny_processes()
    sys.argv = [script, *args]
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        return code if isinstance(code, int) else 1
    except BaseException:  # noqa: BLE001 - 脚本异常原样回传
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
