# eclipse health 模块设计文档（Agent 版）

> 交给你的 AI Agent 阅读。目标：从零做出一个可安装、可扫描、可提交的 `.ehmod` 模块。
> 文档版本：2026-11-01 · 契约 v2（manifest `schemaVersion` / `apiVersion` 均为 `1.0`）。
> 事实源：`schemas/module.schema.json`。文档与 schema 冲突时以 schema 为准。

## 0. 先明确边界

- 模块是**独立 Python 进程**，通过 **stdio JSON-RPC 2.0** 与核心通信，每行一条 JSON。
- 核心**不会 import 模块代码**。模块不能依赖核心的内部模块、数据库或 UI 组件。
- 模块只能使用 manifest 中声明并被用户授予的权限；升级新增权限必须重新确认。
- 所有健康相关输出必须声明「非医疗器械，不用于诊断或治疗」。
- 大结果不要内联：单条消息上限 4 MB，超过时写临时文件并返回路径与 sha256。

## 1. 最小工作流

1. 建目录：`module.json`、`src/main.py`、`LICENSE`、`README.md`；
2. 写 worker：读 stdin、按方法分发、写回 stdout；
3. 本地用 `initialize` + 主方法自测；
4. 生成 `checksums.json`，压成 `.ehmod`；
5. 在应用里用「从本地文件安装」验证；
6. 提交 PR 到 `marketplace/submissions/<module-id>/`。

## 2. `.ehmod` 包结构

```text
my-module/
├── module.json          # 必需：manifest
├── src/
│   └── main.py          # 必需：entry.python 指向的文件
├── models/              # 可选：ONNX / safetensors 权重
├── ui/                  # 可选：声明式 UI 资源
├── LICENSE              # 必需：完整许可证文本
├── NOTICE               # Apache-2.0 等要求时必需
├── README.md            # 建议：用途、权限、数据来源、上游署名
└── checksums.json       # 必需：逐文件 sha256（打包时生成）
```

安装与安全限制：

- 安装到 `<dataDir>/modules/<id>/<version>/`，目录视为只读；
- 单文件 ≤ 64 MB，解压后 ≤ 256 MB；
- 禁止符号链接、绝对路径、`..` 与 Windows 保留设备名；
- 不要打包 `venv/`、`.venv/`、`__pycache__/`、`.git/`、`node_modules/` 或任何密钥；
- 发布包必须包含 `checksums.json`。

`checksums.json` 格式：

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

必需字段：`schemaVersion`、`id`、`name`、`description`、`version`、`apiVersion`、`engines`、`type`、`author`、`license`、`permissions`、`entry`。

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

规则：

- ID：社区模块必须是 `io.github.<GitHub 用户名或组织>.<模块名>`；`org.eclipsehealth.*` 保留给项目维护者。
- `type` 决定必须声明的贡献：`device-adapter` → `importFormats`；`signal-engine` → `pipelines`；`analysis-model` → `models`；`dashboard-widget` → `ui.widgets`；`exporter` → `exporters`；`ai-tool` → `tools`；`health-domain`、`theme`、`locale`、`data-source` 按需声明。
- UI 只能用受控组件；禁止任意 React/JSX、内联脚本、`iframe` 与模板表达式。
- `entries.python` 是包内相对路径，不要写绝对路径。
- 任何声明诊断、治愈或替代医生的描述都会被标记为高风险并可能拒绝。

## 4. Worker 最小实现

`src/main.py`（可直接改 ID 与业务方法）：

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

协议要求：

- 每行一条 JSON；stdout 只写协议消息，日志写 stderr；
- `initialize` 必须返回 `moduleId` 与 `apiVersion`，建议附带 `capabilities` 与 `nonDiagnostic`；
- 未知方法返回 `-32601`，非法参数返回 `-32602`，内部错误返回 `-32603`；
- 空 stdin、异常输入都不能让进程崩溃或挂起；
- 收到 `deactivate` 回 `{"ok": true}` 后退出。

## 5. 权限

只申请实际需要的最小集合：

| 权限 | 用途 |
|---|---|
| `records:read` | 读取记录、测量与分析结果 |
| `records:write` | 创建或更新记录 |
| `records:delete` | 删除记录，高风险，默认不授予 |
| `files:user-selected` | 读取用户主动选择的文件 |
| `files:export` | 写入用户确认的目录 |
| `network` | 访问 `allowedHosts` 中的具体主机，禁止 `*` |
| `llm` | 调用用户配置的 LLM |
| `models:download` | 下载模型权重 |
| `ui:custom` | 沙箱中的自定义界面 |
| `system:notify` | 系统通知 |
| `system:background` | 最小化后继续运行 |

声明 `network` 时必须同时提供 `allowedHosts`，每个主机必须是具体域名。

## 6. 贡献点（契约 v2）

- `contributes.tools[]`：暴露给 LLM/Agent，必须有 `llm` 权限才会出现在工具目录；字段 `id`、`name`、`description`、`inputSchema`/`parameters` 二选一、可选 `outputSchema`、`longRunning`、`permissions`。
- `contributes.ui.widgets[]`：`id`、`title`、`size`（`sm`/`md`/`lg`）、`dataSource`（固定 `module-rpc` + 方法名）、`view`（`stat`/`sparkline`/`list`/`progress`/`text`/`bar`/`line`/`heatmap`）、可选 `link`。
- `contributes.ui.pages[]`：`id`、`title`、`layout`，块类型只有 `text`、`list`、`table`、`detail`、`form`。
- `contributes.recordTypes[]`：声明模块写入的记录类型与 JSON Schema；模块只能读写自己创建的记录或自己声明类型的记录，不能新建数据库表。
- `contributes.importFormats` / `pipelines` / `models` / `exporters` 按模块类型使用。

完整字段与长度限制见 `docs/MODULE_CONTRACT_V2.md`。

## 7. 依赖与模型

- `dependencies` 是 PEP 508 列表，安装到模块自己的 venv；
- 只接受包名、extras、版本范围与环境标记；
- **拒绝** URL、`git+`、本地路径、`file:` 与 `-e`；
- 模型只允许 `onnx` / `safetensors` / `remote`，禁止 pickle；远程权重必须带 sha256；
- API Key 存 OS 密钥库，不能写进 manifest、日志或包。

## 8. 本地测试

```python
# test_worker.py — 放在仓库里，不打包
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

提交前检查：

- `module.json` 通过 `schemas/module.schema.json`；
- 空 stdin、未知方法、非法参数都返回结构化错误；
- `initialize` 返回 `moduleId` 与 `apiVersion`；
- 不读取真实用户数据，不记录波形或原始文件名；
- 打包后在干净目录解包再跑一次。

## 9. 打包 `.ehmod`

```python
# pack.py — 放在模块目录之外，不打包
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

安装验证：应用 → 模块 → 从本地文件安装 → 选择 `.ehmod` → 核对 manifest → 确认 → 启动并调用主方法。

## 10. 提交 PR

1. Fork `https://github.com/Muhan-Qiu/ecg-agent`；
2. 在 `marketplace/submissions/<module-id>/` 放入 `module.json`、`src/`、`LICENSE`、`README.md`（Apache-2.0 另需 `NOTICE`）；
3. 运行本地校验与打包，确认 `.ehmod` 可解包、校验和一致；
4. 填写 PR 模板：作者、许可证、上游、权限、测试、截图与非诊断声明；
5. CI 检查 schema、路径安全、许可证白名单、NOTICE 与包完整性；
6. 合并后由维护者上传 `.ehmod` 并重新签名索引。

许可证白名单：MIT / ISC / BSD-2 / BSD-3 / Apache-2.0 / MPL-2.0 / GPL-2.0 / GPL-3.0 / LGPL 可进入官方索引；AGPL / SSPL / BUSL / 无许可证会被拒绝。社区索引允许专有/付费，但必须显著标注。

## 11. 安全红线

- 不打包密钥、私钥、令牌；
- 不下载并执行任意代码，不混淆，不用 `pickle` 反序列化；
- 健康数据默认不出本机，联网必须声明 `network` 并解释用途；
- 日志只允许 ID 与哈希，不得包含波形、备注或原始文件名；
- 描述中必须写明「不是医疗器械，输出不用于诊断或治疗」。

## 12. 交付清单

给用户的回复至少包含：

- 完整目录结构与每个文件内容；
- `module.json` 的权限与类型说明；
- 本地测试结果（initialize、主方法、错误码）；
- `.ehmod` 打包命令与输出文件名；
- 安装步骤（应用内「从本地文件安装」）；
- 仍存在的限制与未实现项。

参考链接：

- 契约 v2：`docs/MODULE_CONTRACT_V2.md`
- Manifest schema：`schemas/module.schema.json`
- 开发者页：https://eclipse-health.fit/developers.html
- 仓库：https://github.com/Muhan-Qiu/ecg-agent
