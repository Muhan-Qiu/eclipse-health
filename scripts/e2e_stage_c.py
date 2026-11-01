#!/usr/bin/env python
"""Stage C 端到端验收：真实安装 → 卡片/工具/页面 → 禁用/启用 → 卸载。

用法（项目根目录）：

    backend\\.venv\\Scripts\\python.exe scripts\\e2e_stage_c.py

脚本只用临时 ``EH_DATA_DIR`` 与端口 8790（可用 ``--port`` 覆盖），
成功后清理后端进程、模块目录与临时数据；任一步失败退出码为 1。

``--hold-seconds N`` 会在「重新启用后」停留 N 秒，供人工/Playwright
打开前端截图；之后继续执行禁用与卸载。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
FIXTURE_DIR = BACKEND_DIR / "tests" / "fixtures" / "modules" / "e2e"
MODULE_ID = "io.github.example.stage-c-e2e"
DEFAULT_PORT = 8790
BASE_PATH = "/api/v1"
WIDGET_IDS = {"e2e-stat", "e2e-list"}
PAGE_IDS = {"e2e"}
TOOL_IDS = {"e2e.echo"}


class E2EFailure(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(f"{step}: {message}")
        self.step = step
        self.message = message


def _venv_python() -> Path:
    if os.name == "nt":
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    return BACKEND_DIR / ".venv" / "bin" / "python"


def _creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _pass(name: str, detail: str = "") -> None:
    print(f"[PASS] {name}" + (f" — {detail}" if detail else ""))


def _check(condition: Any, name: str, detail: str = "") -> None:
    if not condition:
        raise E2EFailure(name, detail or "assertion failed")
    _pass(name, detail)


def _tail(path: Path, lines: int = 40) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


class Backend:
    """临时数据目录下的真实后端进程。"""

    def __init__(self, data_dir: Path, port: int) -> None:
        self.data_dir = data_dir
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}{BASE_PATH}"
        self.log_path = data_dir / "backend-e2e.log"
        self._log_handle: Any = None
        self.process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        if not _venv_python().is_file():
            raise E2EFailure("backend", f"缺少后端虚拟环境：{_venv_python()}")
        if not _port_free(self.port):
            raise E2EFailure("backend", f"端口 {self.port} 已被占用；先停止旧进程或改用 --port")

        env = os.environ.copy()
        env["EH_DATA_DIR"] = str(self.data_dir)
        env["EH_LOG_LEVEL"] = "WARNING"
        env["PYTHONUNBUFFERED"] = "1"
        self._log_handle = self.log_path.open("wb")
        self.process = subprocess.Popen(
            [
                str(_venv_python()),
                "-m",
                "uvicorn",
                "eclipse_health_backend.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "warning",
            ],
            cwd=str(BACKEND_DIR),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            creationflags=_creation_flags(),
        )
        self._wait_ready()

    def _wait_ready(self, timeout_s: float = 90.0) -> None:
        import httpx

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise E2EFailure(
                    "backend",
                    f"后端提前退出（code={self.process.returncode}）\n{_tail(self.log_path)}",
                )
            try:
                response = httpx.get(f"{self.base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.4)
        raise E2EFailure("backend", f"90s 内未就绪\n{_tail(self.log_path)}")

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self.process = None
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None


class Api:
    def __init__(self, base_url: str) -> None:
        import httpx

        self._client = httpx.Client(base_url=base_url, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def get(self, path: str) -> Any:
        return self._expect("GET", path, 200)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._expect("POST", path, 200, body)

    def delete(self, path: str) -> Any:
        return self._expect("DELETE", path, 200)

    def _expect(
        self,
        method: str,
        path: str,
        status: int,
        body: dict[str, Any] | None = None,
    ) -> Any:
        response = self._client.request(method, path, json=body)
        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text[:400]}
        if response.status_code != status:
            raise E2EFailure(
                f"{method} {path}",
                f"期望 HTTP {status}，实际 {response.status_code}：{json.dumps(payload, ensure_ascii=False)[:400]}",
            )
        return payload

    def expect_error(
        self,
        method: str,
        path: str,
        status: int,
        code: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.request(method, path, json=body)
        payload = response.json()
        if response.status_code != status or payload.get("code") != code:
            raise E2EFailure(
                f"{method} {path}",
                f"期望 {status} {code}，实际 {response.status_code} {payload.get('code')}",
            )
        return payload


def _build_package(tmp_root: Path) -> Path:
    from eclipse_health_backend.modules.package import pack_directory, write_checksums

    source = tmp_root / "stage-c-e2e-src"
    shutil.copytree(
        FIXTURE_DIR,
        source,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    write_checksums(source)
    output = tmp_root / "stage-c-e2e.ehmod"
    pack_directory(source, output)
    return output


def _mine(payload: dict[str, Any], kind: str) -> dict[str, str]:
    items = payload.get(kind)
    if not isinstance(items, list):
        return {}
    return {
        item["id"]: item.get("moduleId", "")
        for item in items
        if isinstance(item, dict) and item.get("moduleId") == MODULE_ID
    }


def _contributions(api: Api) -> dict[str, Any]:
    return api.get("/modules/contributions")


def _rpc(api: Api, method: str, params: dict[str, Any] | None = None) -> Any:
    payload = api.post(
        f"/modules/{MODULE_ID}/rpc",
        {"method": method, "params": params or {}},
    )
    return payload.get("result")


def _module_dir(data_dir: Path) -> Path:
    return data_dir / "modules" / MODULE_ID


def _assistant_check(data_dir: Path, member_id: str) -> None:
    """直接验证助手实际消费的 ToolBox 目录与执行路径（不经 HTTP）。"""
    from eclipse_health_backend.db.base import session_scope
    from eclipse_health_backend.llm.tools import ToolBox, module_tool_alias
    from eclipse_health_backend.modules.manager import ModuleManager

    expected = module_tool_alias(MODULE_ID, "e2e.echo")
    manager = ModuleManager(data_dir=data_dir)
    try:
        with session_scope() as session:
            toolbox = ToolBox(session, member_id, manager=manager)
            specs = toolbox.tool_specs()
            names = [spec["function"]["name"] for spec in specs]
            if expected not in names:
                raise E2EFailure(
                    "assistant tool table",
                    f"ToolBox.tool_specs() 未包含 {expected}；模块工具={[n for n in names if n.startswith('m_')]}",
                )
            spec = next(item for item in specs if item["function"]["name"] == expected)
            if spec["function"]["parameters"].get("additionalProperties") is not False:
                raise E2EFailure("assistant tool table", "inputSchema 未归一化为 additionalProperties=false")
            outcome = toolbox.execute(expected, {"text": "assistant"})
            if not outcome.get("ok") or outcome["result"].get("text") != "assistant":
                raise E2EFailure("assistant tool execute", json.dumps(outcome, ensure_ascii=False)[:400])
    finally:
        manager.shutdown()
    _pass("assistant tool table 含 m_ 别名", expected)
    _pass("assistant tool execute echo", "result.text=assistant")


def _check_contributions(
    payload: dict[str, Any],
    *,
    widgets: set[str],
    pages: set[str],
    tools: set[str],
    step: str,
) -> None:
    actual = {
        "widgets": set(_mine(payload, "widgets")),
        "pages": set(_mine(payload, "pages")),
        "tools": set(_mine(payload, "tools")),
    }
    if actual != {"widgets": widgets, "pages": pages, "tools": tools}:
        raise E2EFailure(
            step,
            f"contributions 不符合预期：{ {k: sorted(v) for k, v in actual.items()} }",
        )
    _pass(
        step,
        f"widgets={payload['counts']['widgets']} pages={payload['counts']['pages']} "
        f"tools={payload['counts']['tools']}",
    )


def run(args: argparse.Namespace) -> None:
    tmp_root = Path(tempfile.mkdtemp(prefix="eh-e2e-"))
    data_dir = tmp_root / "data"
    data_dir.mkdir()
    # 脚本内的助手目录检查会导入后端包；引擎在导入时读这个变量，
    # 必须指向临时目录，绝不能碰 backend/.data。
    os.environ["EH_DATA_DIR"] = str(data_dir)
    os.environ.setdefault("EH_LOG_LEVEL", "WARNING")
    backend = Backend(data_dir, args.port)
    api: Api | None = None
    engine_imported = False

    try:
        backend.start()
        _pass("backend ready", f"{backend.base_url}/health")
        api = Api(backend.base_url)

        baseline = _contributions(api)
        _check(
            all(count == 0 for count in baseline["counts"].values()),
            "贡献注册表初始为空",
            json.dumps(baseline["counts"]),
        )

        package = _build_package(tmp_root)
        _pass(".ehmod 打包完成", f"{package.name} {package.stat().st_size} bytes")

        installed = api.post(
            "/modules/install",
            {"path": str(package), "enable": False},
        )
        _check(
            installed["id"] == MODULE_ID and installed["enabled"] is False,
            "安装（未启用）",
            f"state={installed['state']} granted={installed['grantedPermissions']}",
        )
        _check(
            set(installed["grantedPermissions"]) == {"records:read", "llm"},
            "默认授权 records:read + llm",
            ",".join(installed["grantedPermissions"]),
        )
        _check_contributions(
            _contributions(api),
            widgets=set(),
            pages=set(),
            tools=set(),
            step="未启用时无贡献",
        )

        for scope in ("records:read", "llm"):
            granted = api.post(f"/modules/{MODULE_ID}/permissions/{scope}")
            _check(scope in granted["granted"], f"授权 {scope}")

        enabled = api.post(f"/modules/{MODULE_ID}/enable")
        _check(enabled["enabled"] is True, "启用模块", f"state={enabled['state']}")
        contributions = _contributions(api)
        _check_contributions(
            contributions,
            widgets=WIDGET_IDS,
            pages=PAGE_IDS,
            tools=TOOL_IDS,
            step="启用后 widgets/pages/tools 同时出现",
        )
        for kind in ("widgets", "pages", "tools"):
            meta = next(item for item in contributions[kind] if item["moduleId"] == MODULE_ID)
            _check(
                meta.get("moduleName") and meta.get("moduleVersion") == "0.1.0",
                f"{kind} 带模块归属",
                f"{meta.get('moduleName')} {meta.get('moduleVersion')}",
            )

        started = api.post(f"/modules/{MODULE_ID}/start")
        _check(started["running"] is True, "启动 worker", f"state={started['state']}")

        health = _rpc(api, "health")
        _check(health["status"] == "ok", "RPC health", f"rows={health['rows']}")
        stats = _rpc(api, "widget.stats", {"days": 7})
        _check(stats["latest"]["bpm"] == 72, "widget stat 数据", "latest.bpm=72")
        listing = _rpc(api, "widget.list")
        _check(len(listing["items"]) == 3, "widget list 数据", f"items={len(listing['items'])}")
        page_form = _rpc(api, "page.form")
        _check(page_form["note"] == "seed-note", "page form 初值", "note=seed-note")
        before = _rpc(api, "page.list")
        _check(len(before["items"]) == 2, "page table 数据", f"rows={len(before['items'])}")
        echo = _rpc(api, "e2e.echo", {"text": "stage-c"})
        _check(echo["text"] == "stage-c" and echo["length"] == 7, "tool RPC echo", f"calls={echo['calls']}")

        submitted = _rpc(
            api,
            "page.submit",
            {"note": "c2-submit", "value": 71.5, "date": "2026-10-30", "done": True},
        )
        _check(
            submitted["saved"] is True and submitted["count"] == 3 and submitted["row"]["note"] == "c2-submit",
            "page form 提交",
            f"count={submitted['count']}",
        )
        after = _rpc(api, "page.list")
        _check(
            any(row["note"] == "c2-submit" for row in after["items"]),
            "提交后表格可见新行",
            f"rows={len(after['items'])}",
        )

        api.expect_error(
            "POST",
            f"/modules/{MODULE_ID}/rpc",
            422,
            "INVALID_INPUT",
            {"method": "e2e.echo", "params": {}},
        )
        _pass("边界：tool 缺参数 → 422 INVALID_INPUT")
        api.expect_error(
            "POST",
            f"/modules/{MODULE_ID}/rpc",
            404,
            "METHOD_NOT_FOUND",
            {"method": "missing.method", "params": {}},
        )
        _pass("边界：未知方法 → 404 METHOD_NOT_FOUND")
        api.expect_error("GET", "/modules/contributions?type=bogus", 422, "INVALID_INPUT")
        _pass("边界：未知贡献类型 → 422")

        members = api.get("/members")
        engine_imported = True
        _assistant_check(data_dir, members[0]["id"])

        revoked = api.delete(f"/modules/{MODULE_ID}/permissions/llm")
        _check("llm" not in revoked["granted"], "撤销 llm 授权")
        contributions = _contributions(api)
        _check(
            not _mine(contributions, "tools"),
            "撤销 llm 后工具消失",
            f"tools={contributions['counts']['tools']}",
        )
        _check(
            set(_mine(contributions, "widgets")) == WIDGET_IDS
            and set(_mine(contributions, "pages")) == PAGE_IDS,
            "撤销 llm 不影响 widgets/pages",
        )
        api.post(f"/modules/{MODULE_ID}/permissions/llm")
        _check(
            set(_mine(_contributions(api), "tools")) == TOOL_IDS,
            "重新授予 llm 后工具恢复",
        )

        disabled = api.post(f"/modules/{MODULE_ID}/disable")
        _check(disabled["enabled"] is False, "禁用模块", f"state={disabled['state']}")
        _check_contributions(
            _contributions(api),
            widgets=set(),
            pages=set(),
            tools=set(),
            step="禁用后三类贡献同时消失",
        )
        _check(_module_dir(data_dir).is_dir(), "禁用不删除文件")
        api.expect_error(
            "POST",
            f"/modules/{MODULE_ID}/rpc",
            409,
            "MODULE_DISABLED",
            {"method": "health", "params": {}},
        )
        _pass("禁用后 RPC → 409 MODULE_DISABLED")

        api.post(f"/modules/{MODULE_ID}/enable")
        contributions = _contributions(api)
        _check_contributions(
            contributions,
            widgets=WIDGET_IDS,
            pages=PAGE_IDS,
            tools=TOOL_IDS,
            step="重新启用后三类贡献恢复",
        )
        restarted = api.post(f"/modules/{MODULE_ID}/start")
        _check(restarted["running"] is True, "重新启动 worker", f"state={restarted['state']}")
        _check(_rpc(api, "health")["status"] == "ok", "恢复后 RPC 可用")

        if args.hold_seconds > 0:
            print(
                f"[HOLD] 模块保持启用 {args.hold_seconds}s；后端 {backend.base_url}，"
                f"模块页 #/modules/{MODULE_ID}/pages/e2e",
                flush=True,
            )
            time.sleep(args.hold_seconds)

        removed = api.delete(f"/modules/{MODULE_ID}?keepData=false")
        _check(removed.get("uninstalled") is True, "卸载模块")
        _check(not _module_dir(data_dir).exists(), "卸载后模块目录消失")
        api.expect_error("GET", f"/modules/{MODULE_ID}", 404, "MODULE_NOT_FOUND")
        _pass("卸载后模块详情 → 404")
        empty = _contributions(api)
        _check(
            all(count == 0 for count in empty["counts"].values()),
            "卸载后贡献注册表清空",
            json.dumps(empty["counts"]),
        )
        _check(
            all(not _mine(empty, kind) for kind in ("widgets", "pages", "tools")),
            "卸载后无残留条目",
        )

        print("[OK] Stage C E2E 全部通过")
    finally:
        if api is not None:
            api.close()
        backend.stop()
        if engine_imported:
            try:
                from eclipse_health_backend.db.base import engine

                engine.dispose()
            except Exception:  # noqa: BLE001, S110 - 清理阶段不能掩盖原始失败
                pass
        for _ in range(5):
            shutil.rmtree(tmp_root, ignore_errors=True)
            if not tmp_root.exists():
                break
            time.sleep(0.4)
        if tmp_root.exists():
            print(f"[WARN] 临时目录未能删除：{tmp_root}", file=sys.stderr)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Stage C 端到端验收")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=0,
        help="重新启用后停留 N 秒供截图，再继续禁用/卸载",
    )
    args = parser.parse_args()
    try:
        run(args)
    except E2EFailure as exc:
        print(f"[FAIL] {exc.step}: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
