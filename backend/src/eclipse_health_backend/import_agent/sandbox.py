"""受限 Python 沙箱：独立子进程 + 清空环境 + 超时 + 输出上限。

安全说明（必须保持）：

- 源码模式用 ``python -I -B -X utf8`` 启动；冻结模式复用 sidecar 的
  ``runpy`` 脚本入口（见 ``packaging/serve.py::maybe_run_module_worker``）。
- 只保留 Windows 运行必需的环境变量；代理、API Key、``EH_*`` 一律不传。
- stdout / stderr 各 64 KB 上限；超时或取消会终止进程树。
- **Windows 下这不是 OS 级硬沙箱**：子进程仍能读文件系统。真正的边界是
  “只把本次上传文件复制进 session + 工具路径校验 + 候选记录再校验”。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import limits, store
from .errors import ImportAgentError

_ENV_ALLOWLIST = {
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "PROCESSOR_IDENTIFIER",
    "LOCALAPPDATA",
    "APPDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES",
}


class SandboxError(RuntimeError):
    pass


@dataclass(slots=True)
class SandboxResult:
    ok: bool
    exitCode: int | None
    stdout: str
    stderr: str
    timedOut: bool
    cancelled: bool
    stdoutTruncated: bool
    stderrTruncated: bool
    durationMs: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def assets_dir() -> Path:
    """runner.py / eh_import_helpers.py 所在目录（冻结后位于 ``_MEIPASS``）。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "eclipse_health_backend" / "import_agent" / "sandbox_assets"
    else:
        candidate = Path(__file__).resolve().parent / "sandbox_assets"
    if not (candidate / "runner.py").is_file():
        raise SandboxError(f"import-agent sandbox assets missing: {candidate}")
    return candidate


def _build_env(session_id: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
    workspace = store.session_path(session_id)
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "EH_IMPORT_INPUT": str(workspace / store.INPUT_DIR),
            "EH_IMPORT_WORK": str(workspace / store.WORK_DIR),
            "EH_IMPORT_OUTPUT": str(workspace / store.OUTPUT_DIR),
            "EH_IMPORT_NETWORK": "0",
        }
    )
    return env


def _command(script: Path, args: list[str]) -> list[str]:
    runner = assets_dir() / "runner.py"
    if getattr(sys, "frozen", False):
        return [sys.executable, str(runner), str(script), *args]
    return [sys.executable, "-I", "-B", "-X", "utf8", str(runner), str(script), *args]


def _drain(pipe, cap: int, sink: bytearray, flags: list[bool]) -> None:
    while True:
        chunk = pipe.read(16384)
        if not chunk:
            break
        room = cap - len(sink)
        if room > 0:
            sink.extend(chunk[:room])
        if len(chunk) > room:
            flags[0] = True


def _kill_tree(process: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        else:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except Exception:  # noqa: BLE001 - 进程可能已退出
        try:
            process.kill()
        except Exception:  # noqa: BLE001, S110 - 已退出
            pass


def resolve_script(session_id: str, raw: str) -> tuple[Path, str]:
    name = str(raw or "").strip()
    if not name:
        raise ImportAgentError("script is required", code="invalid_argument")
    candidate = store.work_path(session_id, name)
    relative = name
    if not candidate.is_file() and not name.endswith(".py"):
        relative = f"scripts/{name}.py"
        candidate = store.work_path(session_id, relative)
    if not candidate.is_file():
        raise ImportAgentError(
            "script not found; call write_script first",
            code="not_found",
            details={"script": name},
        )
    if candidate.suffix.lower() != ".py":
        raise ImportAgentError("only .py scripts can be executed", code="invalid_argument")
    return candidate, relative


def run_script(
    session_id: str,
    script: str,
    *,
    args: list[str] | None = None,
    timeout_s: float = limits.DEFAULT_RUN_TIMEOUT_SECONDS,
    cancel: object | None = None,
) -> SandboxResult:
    path, _relative = resolve_script(session_id, script)
    cleaned_args = [str(item)[: limits.MAX_RUN_ARG_CHARS] for item in (args or [])]
    if len(cleaned_args) > limits.MAX_RUN_ARGS:
        raise ImportAgentError(
            f"at most {limits.MAX_RUN_ARGS} script arguments",
            code="invalid_argument",
            details={"count": len(cleaned_args)},
        )
    try:
        timeout = float(timeout_s)
    except (TypeError, ValueError):
        raise ImportAgentError("timeout must be a number", code="invalid_argument") from None
    timeout = max(limits.MIN_RUN_TIMEOUT_SECONDS, min(timeout, limits.MAX_RUN_TIMEOUT_SECONDS))

    workspace = store.session_path(session_id)
    work = workspace / store.WORK_DIR
    work.mkdir(parents=True, exist_ok=True)
    cmd = _command(path, cleaned_args)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(work),
            env=_build_env(session_id),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        raise SandboxError(f"failed to start sandbox process: {exc}") from exc

    stdout = bytearray()
    stderr = bytearray()
    flags: list[list[bool]] = [[False], [False]]
    assert process.stdout is not None and process.stderr is not None
    stdout_thread = threading.Thread(
        target=_drain,
        args=(process.stdout, limits.MAX_STDOUT_BYTES, stdout, flags[0]),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain,
        args=(process.stderr, limits.MAX_STDERR_BYTES, stderr, flags[1]),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    deadline = started + timeout
    timed_out = False
    cancelled = False
    while process.poll() is None:
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            cancelled = True
            _kill_tree(process)
            break
        if time.monotonic() > deadline:
            timed_out = True
            _kill_tree(process)
            break
        time.sleep(0.05)

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        process.wait(timeout=5)

    stdout_thread.join(timeout=3)
    stderr_thread.join(timeout=3)
    duration_ms = int((time.monotonic() - started) * 1000)
    exit_code = process.returncode
    return SandboxResult(
        ok=(exit_code == 0 and not timed_out and not cancelled),
        exitCode=exit_code,
        stdout=bytes(stdout).decode("utf-8", errors="replace"),
        stderr=bytes(stderr).decode("utf-8", errors="replace"),
        timedOut=timed_out,
        cancelled=cancelled,
        stdoutTruncated=bool(flags[0][0]),
        stderrTruncated=bool(flags[1][0]),
        durationMs=duration_ms,
    )


__all__ = ["SandboxError", "SandboxResult", "assets_dir", "resolve_script", "run_script"]
