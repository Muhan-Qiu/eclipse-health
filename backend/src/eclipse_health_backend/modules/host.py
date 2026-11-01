"""模块 worker 宿主：独立子进程 + stdio 按行 JSON-RPC 2.0（契约 §4/§5/§11）。"""

from __future__ import annotations

import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import (
    CORE_API_VERSION,
    DEFAULT_CALL_TIMEOUT_S,
    DEFAULT_STARTUP_TIMEOUT_S,
    MAX_INLINE_JSON_BYTES,
    MAX_LOG_BYTES,
    SHUTDOWN_TIMEOUT_S,
)
from .errors import ModuleError, code_from_rpc_error

CoreCallHandler = Callable[[str, dict[str, Any]], Any]

# 只传递 Python 与操作系统运行所需的最小环境变量，其余一律不继承。
_BASE_ENV_ALLOWLIST = {
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "TEMP",
    "TMP",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
}


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ModuleHost:
    """一个模块实例的进程宿主。线程安全：所有请求串行化。"""

    def __init__(
        self,
        *,
        module_id: str,
        module_dir: Path,
        entry_python: str,
        log_path: Path,
        permissions: list[str],
        locale: str,
        config: dict[str, Any] | None = None,
        startup_timeout_s: float = DEFAULT_STARTUP_TIMEOUT_S,
        call_timeout_s: float = DEFAULT_CALL_TIMEOUT_S,
        core_call_handler: CoreCallHandler | None = None,
        venv_path: Path | None = None,
    ) -> None:
        self.module_id = module_id
        self.module_dir = module_dir
        self.entry_python = entry_python
        self.log_path = log_path
        self.permissions = list(permissions)
        self.locale = locale
        self.config = config or {}
        self.startup_timeout_s = startup_timeout_s
        self.call_timeout_s = call_timeout_s
        self.core_call_handler = core_call_handler
        # B3 每模块 venv 的接口预留。
        self.venv_path = venv_path
        self.token = secrets.token_hex(24)
        self.capabilities: dict[str, Any] = {}

        self._process: subprocess.Popen[str] | None = None
        self._reader_thread: threading.Thread | None = None
        self._log_handle: Any = None
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._next_id = 1
        self._lock = threading.RLock()
        self._io_lock = threading.Lock()
        self._alive = False
        self._stopping = False

    # ------------------------------------------------------------------ 生命周期
    @property
    def alive(self) -> bool:
        process = self._process
        return bool(self._alive and process is not None and process.poll() is None)

    def _python_executable(self) -> str:
        if self.venv_path is not None:
            candidate = (
                self.venv_path / "Scripts" / "python.exe"
                if os.name == "nt"
                else self.venv_path / "bin" / "python"
            )
            if candidate.is_file():
                return str(candidate)
        return sys.executable

    def _build_env(self) -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key in _BASE_ENV_ALLOWLIST}
        env.update(
            {
                "ECLIPSE_MODULE_ID": self.module_id,
                "ECLIPSE_RPC_TOKEN": self.token,
                "ECLIPSE_API_VERSION": CORE_API_VERSION,
                "ECLIPSE_LOCALE": self.locale,
                "ECLIPSE_PERMISSIONS": ",".join(self.permissions),
                "ECLIPSE_MODULE_DIR": str(self.module_dir),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PYTHONUNBUFFERED": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
        )
        return env

    def _rotate_log(self) -> None:
        try:
            if self.log_path.is_file() and self.log_path.stat().st_size > MAX_LOG_BYTES:
                rotated = self.log_path.with_suffix(self.log_path.suffix + ".1")
                rotated.unlink(missing_ok=True)
                self.log_path.replace(rotated)
        except OSError:
            pass

    def _open_log(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._rotate_log()
        self._log_handle = self.log_path.open("a", encoding="utf-8", errors="replace")

    def _log(self, message: str) -> None:
        handle = self._log_handle
        if handle is None:
            return
        try:
            handle.write(f"[{_now_stamp()}] {message}\n")
            handle.flush()
        except (OSError, ValueError):
            pass

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.alive:
                return self.capabilities
            self._stopping = False
            self.token = secrets.token_hex(24)
            self._open_log()
            entry = self.module_dir / self.entry_python
            self._log(f"starting module {self.module_id} (pid pending)")
            try:
                self._process = subprocess.Popen(
                    [self._python_executable(), str(entry)],
                    cwd=str(self.module_dir),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self._log_handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self._build_env(),
                    creationflags=_creation_flags(),
                )
            except OSError as exc:
                self._close_log()
                raise ModuleError("MODULE_CRASH", "模块进程无法启动") from exc

            self._reader_thread = threading.Thread(
                target=self._read_loop,
                name=f"module-reader-{self.module_id}",
                daemon=True,
            )
            self._reader_thread.start()
            self._alive = True
            self._log(f"worker pid={self._process.pid}")

            try:
                result = self.request(
                    "initialize",
                    {
                        "apiVersion": CORE_API_VERSION,
                        "permissions": self.permissions,
                        "locale": self.locale,
                        "config": self.config,
                    },
                    timeout=self.startup_timeout_s,
                )
            except ModuleError:
                self.stop()
                raise
            self.capabilities = result if isinstance(result, dict) else {"result": result}
            self._log("initialize ok")
            return self.capabilities

    def stop(self) -> None:
        with self._lock:
            process = self._process
            if process is None:
                self._close_log()
                return
            self._stopping = True
            self._alive = False
            if process.poll() is None:
                try:
                    self._send_raw(
                        {
                            "jsonrpc": "2.0",
                            "id": self._next_id,
                            "method": "deactivate",
                            "params": {},
                        }
                    )
                    self._next_id += 1
                except (OSError, ValueError):
                    pass
                time.sleep(0.05)
                try:
                    process.wait(timeout=SHUTDOWN_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=SHUTDOWN_TIMEOUT_S)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        try:
                            process.wait(timeout=SHUTDOWN_TIMEOUT_S)
                        except subprocess.TimeoutExpired:
                            pass
            self._fail_pending(ModuleError("MODULE_CRASH", "模块已停止"))
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
            self._process = None
            reader = self._reader_thread
            if reader is not None and reader is not threading.current_thread():
                reader.join(timeout=2.0)
            self._reader_thread = None
            self._log("worker stopped")
            self._close_log()

    def _close_log(self) -> None:
        handle = self._log_handle
        self._log_handle = None
        if handle is not None:
            try:
                handle.close()
            except (OSError, ValueError):
                pass

    # ------------------------------------------------------------------ 读取
    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        try:
            for line in process.stdout:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    message = json.loads(stripped)
                except json.JSONDecodeError:
                    self._log(f"malformed worker output: {stripped[:160]}")
                    continue
                if not isinstance(message, dict):
                    continue
                self._dispatch_message(message)
        except (OSError, ValueError):
            pass
        exit_code = process.poll()
        self._alive = False
        if not self._stopping:
            self._log(f"worker exited unexpectedly code={exit_code}")
        self._fail_pending(ModuleError("MODULE_CRASH", "模块进程已退出"))

    def _dispatch_message(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        if "method" in message and isinstance(message_id, int):
            self._handle_core_request(message_id, message)
            return
        if "method" in message:
            self._handle_notification(message)
            return
        response_queue = self._pending.get(message_id) if isinstance(message_id, int) else None
        if response_queue is not None:
            try:
                response_queue.put_nowait(message)
            except queue.Full:
                self._log("duplicate response dropped")
        else:
            self._log("response without pending request")

    def _handle_notification(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))[:64]
        # 只记录元数据，绝不把模块 notify 的内容写进主进程 stdout。
        self._log(f"notification {method}")

    def _handle_core_request(self, message_id: int, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        params = message.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            if self.core_call_handler is None:
                raise ModuleError("NOT_IMPLEMENTED", "核心回调未接线")
            result = self.core_call_handler(method, params)
            response: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id, "result": result}
        except ModuleError as exc:
            response = {"jsonrpc": "2.0", "id": message_id, "error": exc.to_rpc_error()}
        except Exception:  # noqa: BLE001 - 模块边界必须兜底，不能让 reader 线程死掉
            response = {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": ModuleError("MODULE_ERROR", "核心回调失败").to_rpc_error(),
            }
        try:
            self._send_raw(response)
        except (OSError, ValueError):
            pass

    def _fail_pending(self, error: ModuleError) -> None:
        pending, self._pending = self._pending, {}
        for response_queue in pending.values():
            try:
                response_queue.put_nowait({"jsonrpc": "2.0", "id": None, "error": error.to_rpc_error()})
            except queue.Full:
                pass

    # ------------------------------------------------------------------ 发送
    def _send_raw(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise ModuleError("MODULE_CRASH", "模块进程不可用")
        line = json.dumps(message, ensure_ascii=False)
        with self._io_lock:
            process.stdin.write(line + "\n")
            process.stdin.flush()

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        with self._lock:
            if not self.alive:
                raise ModuleError("MODULE_CRASH", "模块进程未运行")
            request_id = self._next_id
            self._next_id += 1
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = response_queue
            message = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
            if len(json.dumps(message, ensure_ascii=False).encode("utf-8")) > MAX_INLINE_JSON_BYTES:
                self._pending.pop(request_id, None)
                raise ModuleError("RESOURCE_EXCEEDED", "单次调用参数超过 4MB；大数组请走文件句柄")
            try:
                self._send_raw(message)
            except (OSError, ValueError) as exc:
                self._pending.pop(request_id, None)
                raise ModuleError("MODULE_CRASH", "写入模块进程失败") from exc

            try:
                response = response_queue.get(timeout=timeout or self.call_timeout_s)
            except queue.Empty:
                self._pending.pop(request_id, None)
                self._log(f"timeout waiting for {method[:64]}")
                self._kill_after_timeout()
                raise ModuleError("MODULE_TIMEOUT", "模块调用超时", {"method": method[:64]}) from None

            if response.get("id") is None and "error" in response:
                # 由 _fail_pending 注入的崩溃错误。
                error = response.get("error") or {}
                raise ModuleError(code_from_rpc_error(error, "MODULE_CRASH"), str(error.get("message", "模块进程已退出")))
            error = response.get("error")
            if error:
                code = code_from_rpc_error(error, "MODULE_ERROR")
                message = str(error.get("message", "模块返回错误"))[:200]
                raise ModuleError(code, message, {"rpcCode": error.get("code")})
            return response.get("result")

    def _kill_after_timeout(self) -> None:
        process = self._process
        self._alive = False
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
