"""沙箱：路径穿越、超时、输出上限、无网络、无子进程。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from import_agent_helpers import CSV_PULSE, upload_session

from eclipse_health_backend.import_agent import store
from eclipse_health_backend.import_agent.tools import ToolBox


def _box(client: TestClient, providers_file) -> tuple[str, dict, ToolBox]:
    session = upload_session(client, {"pulse.csv": CSV_PULSE})
    workspace, meta = store.load_session(session["sessionId"])
    assert workspace.is_dir()
    return session["sessionId"], meta, ToolBox(session["sessionId"], meta)


def _run(box: ToolBox, code: str, *, name: str = "probe.py", timeout: float = 10):
    written = box.execute("write_script", {"name": name, "code": code})
    assert written.ok, written.result
    return box.execute("run_python", {"script": f"scripts/{name}", "timeout": timeout})


def test_path_traversal_is_rejected(client: TestClient, providers_file) -> None:
    _session_id, _meta, box = _box(client, providers_file)
    read = box.execute("read_text_file", {"path": "../meta.json"})
    assert read.ok is False
    assert read.result["error"]["code"] == "path_escape"

    write = box.execute("write_output", {"path": "../evil.txt", "content": "x"})
    assert write.ok is False
    assert write.result["error"]["code"] == "path_escape"

    drive = box.execute("write_output", {"path": "C:/evil.txt", "content": "x"})
    assert drive.ok is False

    run = box.execute("run_python", {"script": "../../evil.py"})
    assert run.ok is False
    assert run.result["error"]["code"] == "path_escape"


def test_write_script_sanitises_name(client: TestClient, providers_file) -> None:
    _session_id, meta, box = _box(client, providers_file)
    written = box.execute("write_script", {"name": "../evil.py", "code": "print(1)"})
    assert written.ok is True
    assert written.result["path"].startswith("scripts/")
    assert ".." not in written.result["path"]
    assert meta is not None


def test_timeout_kills_process(client: TestClient, providers_file) -> None:
    _session_id, _meta, box = _box(client, providers_file)
    outcome = _run(box, "import time\ntime.sleep(30)\nprint('never')\n", timeout=0.5)
    assert outcome.ok is True
    result = outcome.result
    assert result["timedOut"] is True
    assert result["ok"] is False
    assert result["durationMs"] < 5000


def test_output_is_capped(client: TestClient, providers_file) -> None:
    _session_id, _meta, box = _box(client, providers_file)
    outcome = _run(box, "print('x' * 200000)\n")
    result = outcome.result
    assert result["stdoutTruncated"] is True
    assert len(result["stdout"]) <= 64 * 1024


def test_network_and_processes_are_blocked(client: TestClient, providers_file) -> None:
    _session_id, _meta, box = _box(client, providers_file)
    code = """
import json, os, socket, subprocess
result = {
    "proxyKeys": [k for k in os.environ if "PROXY" in k.upper()],
    "apiKey": os.environ.get("OPENAI_API_KEY"),
    "socketBlocked": None,
    "processBlocked": None,
}
try:
    socket.create_connection(("example.com", 80), timeout=1)
except Exception as exc:
    result["socketBlocked"] = type(exc).__name__
try:
    subprocess.run(["cmd", "/c", "echo", "hi"])
except Exception as exc:
    result["processBlocked"] = type(exc).__name__
print(json.dumps(result))
"""
    outcome = _run(box, code)
    assert outcome.result["exitCode"] == 0, outcome.result
    payload = json.loads(outcome.result["stdout"].strip())
    assert payload["proxyKeys"] == []
    assert payload["apiKey"] is None
    assert payload["socketBlocked"] == "PermissionError"
    assert payload["processBlocked"] == "PermissionError"


def test_helpers_read_input_and_write_output(client: TestClient, providers_file) -> None:
    session_id, _meta, box = _box(client, providers_file)
    code = """
import json
import eh_import_helpers as h
data = h.read_csv_rows("pulse.csv")
h.write_output_json("rows.json", data)
print(json.dumps({"headers": data["headers"], "rows": len(data["rows"])}))
"""
    outcome = _run(box, code)
    assert outcome.result["exitCode"] == 0, outcome.result
    printed = json.loads(outcome.result["stdout"].strip())
    assert any("Pulse" in header for header in printed["headers"])
    assert printed["rows"] == 2

    read = box.execute("read_output", {"path": "rows.json"})
    assert read.ok is True
    assert "headers" in read.result["text"]
    assert (store.session_path(session_id) / "output" / "rows.json").is_file()


def test_script_errors_are_reported(client: TestClient, providers_file) -> None:
    _session_id, _meta, box = _box(client, providers_file)
    outcome = _run(box, "raise RuntimeError('boom')\n")
    assert outcome.ok is True
    assert outcome.result["exitCode"] == 1
    assert "boom" in outcome.result["stderr"]
