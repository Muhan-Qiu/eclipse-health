# eclipse health module design guide (agent edition)

> Hand this to your AI agent. Goal: produce an installable, scannable, submittable `.ehmod` module from scratch.
> Document version: 2026-11-01 · contract v2 (manifest `schemaVersion` and `apiVersion` are both `1.0`).
> Source of truth: `schemas/module.schema.json`. If this document and the schema disagree, the schema wins.

## 0. Boundaries first

- A module is a **separate Python process** that talks to the core over **stdio JSON-RPC 2.0**, one JSON document per line.
- The core **never imports module code**. Modules must not depend on core internals, its database, or its UI components.
- A module may only use permissions declared in the manifest and granted by the user; new permissions on upgrade must be re-approved.
- Every health-related output must state: not a medical device, not for diagnosis or treatment.
- Do not inline large results: a single message is capped at 4 MB. Write large results to a temp file and return its path and sha256.

## 1. Minimal workflow

1. Create `module.json`, `src/main.py`, `LICENSE`, `README.md`;
2. Write the worker: read stdin, dispatch by method, write stdout;
3. Self-test locally with `initialize` plus the main method;
4. Generate `checksums.json` and pack the `.ehmod`;
5. Install it in the app with "Install from local file";
6. Open a PR adding `marketplace/submissions/<module-id>/`.

## 2. `.ehmod` package layout

```text
my-module/
├── module.json          # required: manifest
├── src/
│   └── main.py          # required: the file entry.python points at
├── models/              # optional: ONNX / safetensors weights
├── ui/                  # optional: declarative UI resources
├── LICENSE              # required: full licence text
├── NOTICE               # required when Apache-2.0 or similar demands it
├── README.md            # recommended: purpose, permissions, data sources, upstream credits
└── checksums.json       # required: per-file sha256, generated at pack time
```

Installation and safety limits:

- Installed to `<dataDir>/modules/<id>/<version>/`; the directory is treated as read-only;
- single file ≤ 64 MB, unpacked ≤ 256 MB;
- symlinks, absolute paths, `..` and Windows reserved device names are rejected;
- never pack `venv/`, `.venv/`, `__pycache__/`, `.git/`, `node_modules/` or any secret;
- release packages must include `checksums.json`.

`checksums.json` format:

```json
{
  "algorithm": "sha256",
  "files": {
    "LICENSE": "…",
    "README.md": "…",
    "module.json": "…",
    "src/main.py": "…"
  }
}
```

## 3. `module.json`

Required fields: `schemaVersion`, `id`, `name`, `description`, `version`, `apiVersion`, `engines`, `type`, `author`, `license`, `permissions`, `entry`.

```json
{
  "schemaVersion": "1.0",
  "id": "io.github.example.heart-rate",
  "name": "Heart Rate Summary",
  "description": "Summarize heart rate from user-selected samples. Not a medical device; not for diagnosis.",
  "version": "0.1.0",
  "apiVersion": "1.0",
  "engines": { "eclipse": ">=1.0 <2.0" },
  "type": "ai-tool",
  "author": { "name": "Example Author", "url": "https://github.com/example" },
  "license": "MIT",
  "homepage": "https://github.com/example/heart-rate",
  "repository": "https://github.com/example/heart-rate",
  "permissions": ["files:user-selected", "records:write"],
  "dependencies": ["numpy>=2.0,<3"],
  "entry": { "python": "src/main.py", "factory": "create_module" },
  "contributes": {
    "tools": [
      {
        "id": "hr.summary",
        "name": "Heart rate summary",
        "description": "Return mean and max heart rate from a sample array.",
        "inputSchema": {
          "type": "object",
          "properties": { "samples": { "type": "array", "items": { "type": "number" } } },
          "required": ["samples"]
        },
        "permissions": []
      }
    ]
  },
  "resources": { "memoryMb": 256, "cpu": 0.5, "startupTimeoutMs": 8000 },
  "updateChannel": "stable"
}
```

Rules:

- ID: community modules must use `io.github.<GitHub user or org>.<module-name>`; `org.eclipsehealth.*` is reserved for maintainers.
- `type` determines required contributions: `device-adapter` → `importFormats`; `signal-engine` → `pipelines`; `analysis-model` → `models`; `dashboard-widget` → `ui.widgets`; `exporter` → `exporters`; `ai-tool` → `tools`; `health-domain`, `theme`, `locale`, `data-source` declare what they use.
- UI is declarative only; arbitrary React/JSX, inline scripts, `iframe` and template expressions are forbidden.
- `entry.python` is a package-relative path; never absolute.
- Any description claiming diagnosis, cure or replacement of a doctor is flagged high risk and may be rejected.

## 4. Minimal worker

`src/main.py` (change the ID and business methods):

```python
"""Minimal eclipse health module worker: one JSON document per line on stdio."""
from __future__ import annotations

import json
import sys
from typing import Any

MODULE_ID = "io.github.example.heart-rate"
API_VERSION = "1.0"
NON_DIAGNOSTIC = "Not a medical device; not for diagnosis or treatment."


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}


def write(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(method: str, params: dict[str, Any]) -> Any:
    if method == "initialize":
        return {
            "name": "Heart Rate Summary",
            "moduleId": MODULE_ID,
            "apiVersion": API_VERSION,
            "permissions": params.get("permissions") or [],
            "capabilities": ["initialize", "health", "summary", "deactivate"],
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method == "health":
        return {"ok": True, "nonDiagnostic": NON_DIAGNOSTIC}
    if method == "summary":
        samples = params.get("samples")
        if not isinstance(samples, list) or not samples:
            raise RpcError(-32602, "samples must be a non-empty array", {"code": "INVALID_INPUT"})
        values = [float(value) for value in samples]
        return {
            "mean": sum(values) / len(values),
            "max": max(values),
            "count": len(values),
            "nonDiagnostic": NON_DIAGNOSTIC,
        }
    if method in {"activate", "deactivate"}:
        return {"ok": True}
    raise RpcError(-32601, "method not found", {"code": "METHOD_NOT_FOUND"})


def create_module() -> dict[str, Any]:
    return {"handle": handle}


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            request_id = message.get("id")
            method = str(message.get("method") or "")
            params = message.get("params")
            if not isinstance(params, dict):
                params = {}
            write({"jsonrpc": "2.0", "id": request_id, "result": handle(method, params)})
            if method == "deactivate":
                break
        except RpcError as error:
            write({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": error.code, "message": error.message, "data": error.data},
            })
        except Exception as error:  # module boundary: never crash the worker
            write({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"internal error: {type(error).__name__}",
                    "data": {"code": "MODULE_ERROR"},
                },
            })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Protocol requirements:

- One JSON document per line; stdout carries protocol messages only, logs go to stderr;
- `initialize` must return `moduleId` and `apiVersion`, ideally with `capabilities` and `nonDiagnostic`;
- unknown method → `-32601`, invalid params → `-32602`, internal error → `-32603`;
- empty stdin and malformed input must never crash or hang the process;
- on `deactivate`, reply `{"ok": true}` then exit.

## 5. Permissions

Request only the minimum set you actually need:

| Permission | Purpose |
|---|---|
| `records:read` | Read records, measurements and analysis results |
| `records:write` | Create or update records |
| `records:delete` | Delete records; high risk, never granted by default |
| `files:user-selected` | Read files the user explicitly chooses |
| `files:export` | Write to a directory the user confirms |
| `network` | Access concrete hosts in `allowedHosts`; wildcards forbidden |
| `llm` | Call the LLM the user configured |
| `models:download` | Download model weights |
| `ui:custom` | Custom UI inside a sandbox |
| `system:notify` | System notifications |
| `system:background` | Keep running when minimised |

Declaring `network` requires `allowedHosts`, and every host must be a concrete domain.

## 6. Contributions (contract v2)

- `contributes.tools[]`: exposed to LLMs/agents; appears only when the `llm` permission is granted. Fields: `id`, `name`, `description`, `inputSchema` or `parameters` (one of), optional `outputSchema`, `longRunning`, `permissions`.
- `contributes.ui.widgets[]`: `id`, `title`, `size` (`sm`/`md`/`lg`), `dataSource` (fixed `module-rpc` plus a method name), `view` (`stat`/`sparkline`/`list`/`progress`/`text`/`bar`/`line`/`heatmap`), optional `link`.
- `contributes.ui.pages[]`: `id`, `title`, `layout`; block types are limited to `text`, `list`, `table`, `detail`, `form`.
- `contributes.recordTypes[]`: declare record types and their JSON Schema. A module may only read and write records it created or record types it declares, and may not create database tables.
- `contributes.importFormats` / `pipelines` / `models` / `exporters` are used according to module type.

Full fields and length limits: `docs/MODULE_CONTRACT_V2.md`.

## 7. Dependencies and models

- `dependencies` is a PEP 508 list installed into the module's own venv;
- only package names, extras, version ranges and environment markers are accepted;
- **rejected**: URLs, `git+`, local paths, `file:`, `-e`;
- models may only be `onnx` / `safetensors` / `remote`; pickle is forbidden; remote weights must carry a sha256;
- API keys live in the OS keychain and never in the manifest, logs or package.

## 8. Local tests

```python
# test_worker.py — keep in the repo, do not pack it
import json
import subprocess
import sys

proc = subprocess.Popen(
    [sys.executable, "src/main.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    cwd="my-module",
)


def call(request_id, method, params=None):
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


init = call(1, "initialize", {"permissions": ["files:user-selected"]})
assert init["result"]["moduleId"] == "io.github.example.heart-rate"
assert "apiVersion" in init["result"]

summary = call(2, "summary", {"samples": [60, 72, 66]})
assert summary["result"]["mean"] == 66.0

bad = call(3, "summary", {"samples": []})
assert bad["error"]["code"] == -32602

unknown = call(4, "nope")
assert unknown["error"]["code"] == -32601

print(call(5, "deactivate"))
proc.wait(timeout=5)
```

Checklist before submitting:

- `module.json` validates against `schemas/module.schema.json`;
- empty stdin, unknown methods and invalid params all return structured errors;
- `initialize` returns `moduleId` and `apiVersion`;
- no real user data is read, and no waveform or original filename is logged;
- after packing, unpack in a clean directory and run once more.

## 9. Packing the `.ehmod`

```python
# pack.py — keep outside the module directory, do not pack it
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path("my-module")
SKIP_DIRS = {"venv", ".venv", "__pycache__", ".git", "node_modules"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


files = {}
for path in sorted(ROOT.rglob("*")):
    relative = path.relative_to(ROOT)
    if not path.is_file() or any(part in SKIP_DIRS for part in relative.parts):
        continue
    if relative.as_posix() == "checksums.json":
        continue
    files[relative.as_posix()] = sha256(path)

(ROOT / "checksums.json").write_text(
    json.dumps({"algorithm": "sha256", "files": files}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

output = Path("io.github.example.heart-rate-0.1.0.ehmod")
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if path.is_file() and not any(part in SKIP_DIRS for part in relative.parts):
            archive.write(path, relative.as_posix())

print(output, output.stat().st_size, "bytes")
```

Install test: app → Modules → Install from local file → pick the `.ehmod` → check the manifest → confirm → start it and call the main method.

## 10. Submitting a PR

1. Fork `https://github.com/Muhan-Qiu/eclipse-health`;
2. Put `module.json`, `src/`, `LICENSE` and `README.md` (plus `NOTICE` for Apache-2.0) under `marketplace/submissions/<module-id>/`;
3. Run the local validator and packer; confirm the `.ehmod` unpacks and its checksums match;
4. Fill in the PR template: author, licence, upstream, permissions, tests, screenshots and the non-diagnostic notice;
5. CI checks schema, path safety, the licence allowlist, NOTICE and package integrity;
6. After merge, a maintainer uploads the `.ehmod` and re-signs the index.

Licence allowlist for the official index: MIT / ISC / BSD-2 / BSD-3 / Apache-2.0 / MPL-2.0 / GPL-2.0 / GPL-3.0 / LGPL. AGPL / SSPL / BUSL / no licence are rejected. The community index allows proprietary or paid modules but they must be clearly labelled.

## 11. Security red lines

- Never pack keys, private keys or tokens;
- no downloading and executing arbitrary code, no obfuscation, no `pickle` deserialisation;
- health data stays local by default; going online requires `network` and an explanation of why;
- logs may contain IDs and hashes only — never waveforms, notes or original filenames;
- every description must state: not a medical device; output is not for diagnosis or treatment.

## 12. Delivery checklist

Your reply to the user must include:

- the full directory tree and every file's content;
- the manifest's type and permission rationale;
- local test results (initialize, main method, error codes);
- the `.ehmod` pack command and output filename;
- install steps (in-app "Install from local file");
- remaining limits and unimplemented parts.

References:

- Contract v2: `docs/MODULE_CONTRACT_V2.md`
- Manifest schema: `schemas/module.schema.json`
- Developer page: https://eclipse-health.fit/en/developers.html
- Repository: https://github.com/Muhan-Qiu/eclipse-health
