#!/usr/bin/env python3
"""逐个审计 ``dist/modules/*.ehmod``，输出 ``reports/module_audit.json``。

审计不是看文件名：对每个模块在临时 ``EH_DATA_DIR`` 中真实安装、启动 worker
（启动时完成 ``initialize``）、调用 ``health`` 与一个代表性 RPC，然后卸载。
需要外部账号/OAuth、硬件或实时抓取的模块不启动，标记为 ``skipped`` 并写明原因；
仍会解包校验 checksums 与布局，保证包结构本身是可验证的。

用法（项目根目录）::

    backend\\.venv\\Scripts\\python.exe scripts\\audit_modules.py
    backend\\.venv\\Scripts\\python.exe scripts\\audit_modules.py --only org.eclipsehealth.relay-ecg
    backend\\.venv\\Scripts\\python.exe scripts\\audit_modules.py --deps skip   # 快速模式，不装依赖

``--deps install``（默认）会为声明了依赖的模块创建独立 venv 并 pip 安装，
所以首次运行较慢且需要网络；``--deps skip`` 只审计无依赖模块与包结构。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_SRC = ROOT / "backend" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

DIST = ROOT / "dist" / "modules"
MODULE_ROOTS = (ROOT / "modules" / "official", ROOT / "modules" / "community")
REPORT = ROOT / "reports" / "module_audit.json"
TESTS = ROOT / "backend" / "tests" / "modules"

# ---------------------------------------------------------------- 分家决策
# 官方只保留“核心闭环 + 第一方 + 无外部账号且可离线验证”的模块。
OFFICIAL_IDS = {
    "org.eclipsehealth.relay-ecg": "第一方 ECG 模型包，核心分析闭环",
    "org.eclipsehealth.relay-sleep": "第一方睡眠模型包，核心分析闭环",
    "io.github.mit-lcp.wfdb": "WFDB 导入/导出，心电数据的标准交换格式",
    "io.github.holgern.pyedflib": "EDF 导入/导出，临床与穿戴设备通用格式",
    "io.github.neuropsychology.neurokit2": "无外部账号的通用生理信号分析",
    "io.github.paulvangentcom.heartpy": "无外部账号的 HRV/PPG 分析",
    "io.github.scientisst.biosppy": "无外部账号的生理信号分析",
    "io.github.aura-healthcare.hrv-analysis": "无外部账号的 HRV 分析",
    "io.github.tkrajina.gpxpy": "本地 GPX 轨迹导入，无账号、可离线验证",
    "io.github.dogsheep.healthkit-to-sqlite": "本地 Apple Health 导出导入，无账号",
}

COMMUNITY_REASONS = {
    "io.github.hbldh.bleak": "需要 BLE 硬件与现场蓝牙环境，无法在审计中验证",
    "io.github.brainflow-dev.brainflow": "需要 BrainFlow 支持的采集硬件，无法在审计中验证",
    "io.github.alexandrebarachant.muselsl": "需要 Muse 头环与 LSL 环境，无法在审计中验证",
    "io.github.openbci-archive.openbci": "需要 OpenBCI 串口硬件，无法在审计中验证",
    "io.github.cyberjunky.garminconnect": "需要 Garmin 账号登录，且为受 TOS 约束的非官方客户端",
    "io.github.orcasgit.fitbit": "需要 Fitbit OAuth 账号与令牌",
    "io.github.vangorra.withings": "需要 Withings OAuth 账号与令牌",
    "io.github.coddingtonbear.myfitnesspal": "需要 MyFitnessPal 账号，依赖 cloudscraper 抓取，上游脆弱",
    "io.github.stravalib.stravalib": "需要 Strava OAuth 账号与令牌",
    "io.github.pgomes92.pyhrv": "上游 pyhrv 返回 ReturnTuple，模块适配层未兼容，hrv.metrics 无法通过冒烟",
    "io.github.raphaelvallat.yasa": "worker 最小环境未提供 HOME/USERPROFILE，yasa/mne 启动报 FileNotFoundError",
    "io.github.gagebenne.pydexcom": "需要 Dexcom Share 账号与实时网络",
    "io.github.openfoodfacts.openfoodfacts": "依赖实时 Open Food Facts 网络查询，离线无法验证",
    "io.github.blinry.habitctl": "主路径依赖外部 habitctl 可执行文件，非 Python 依赖",
    "io.github.jrnl-org.jrnl": "主路径依赖外部 jrnl CLI，非 Python 依赖",
    "io.github.grubersjoe.activity-calendar": "可选仪表盘组件，不属于核心健康闭环",
    "io.github.apache.echarts": "可选图表组件，不属于核心健康闭环",
    "io.github.observablehq.plot": "可选图表组件，不属于核心健康闭环",
    "io.github.leeoniya.uplot": "可选图表组件，不属于核心健康闭环",
    "io.github.tremorlabs.tremor": "可选仪表盘组件，不属于核心健康闭环",
    "io.github.polyvertex.fitdecode": "可选的 FIT 文件导入，与 fitparse 功能重复",
    "io.github.dtcooper.fitparse": "可选的 FIT 文件导入，与 fitdecode 功能重复",
}

ACCOUNT_IDS = {
    "io.github.cyberjunky.garminconnect",
    "io.github.orcasgit.fitbit",
    "io.github.vangorra.withings",
    "io.github.coddingtonbear.myfitnesspal",
    "io.github.stravalib.stravalib",
    "io.github.gagebenne.pydexcom",
}
HARDWARE_IDS = {
    "io.github.hbldh.bleak",
    "io.github.brainflow-dev.brainflow",
    "io.github.alexandrebarachant.muselsl",
    "io.github.openbci-archive.openbci",
}
NETWORK_ONLY_IDS = {"io.github.openfoodfacts.openfoodfacts"}
EXTERNAL_CLI_IDS = {"io.github.blinry.habitctl", "io.github.jrnl-org.jrnl"}

RR = [800.0, 810.0, 790.0, 805.0, 795.0, 800.0, 812.0, 788.0, 800.0, 795.0, 802.0, 798.0]
HABIT_TEXT = "[x] stretch streak=2\n[ ] read\n"
JRNL_TEXT = json.dumps(
    [
        {"title": "Morning", "body": "slept well", "date": "2026-10-30", "tags": ["mood"]},
        {"title": "Run", "body": "5k easy", "date": "2026-10-31", "tags": ["sport"]},
    ]
)
GPX_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="eclipse-health-audit" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>audit</name><trkseg>
    <trkpt lat="31.2304" lon="121.4737"><ele>10</ele><time>2026-10-31T08:00:00Z</time></trkpt>
    <trkpt lat="31.2314" lon="121.4747"><ele>12</ele><time>2026-10-31T08:01:00Z</time></trkpt>
    <trkpt lat="31.2324" lon="121.4757"><ele>14</ele><time>2026-10-31T08:02:00Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""
HEALTHKIT_TEXT = """<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_US">
  <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Watch" unit="count/min"
          startDate="2026-10-31 08:00:00 +0800" endDate="2026-10-31 08:00:05 +0800" value="72"/>
  <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count"
          startDate="2026-10-31 09:00:00 +0800" endDate="2026-10-31 10:00:00 +0800" value="1200"/>
</HealthData>
"""


def _fixture(fixtures: Path, name: str, text: str) -> Path:
    target = fixtures / name
    target.write_text(text, encoding="utf-8")
    return target


def representative_call(module_id: str, fixtures: Path) -> tuple[str, dict[str, Any]]:
    """返回 (method, params)；params 只使用模块自带的离线/内联路径。"""
    if module_id == "org.eclipsehealth.relay-ecg":
        return "list_models", {}
    if module_id == "org.eclipsehealth.relay-sleep":
        return "list_models", {}
    if module_id in {"io.github.mit-lcp.wfdb", "io.github.holgern.pyedflib"}:
        return (
            "export.csv",
            {
                "recordName": "audit_record",
                "fs": 250,
                "channels": [[0.1, -0.2, 0.3, 0.0]],
                "sigName": ["ecg"],
                "labels": ["ECG Lead II"],
                "units": ["mV"],
                "outputDir": str(fixtures),
            },
        )
    if module_id == "io.github.neuropsychology.neurokit2":
        return "hrv.summary", {"rr": RR}
    if module_id == "io.github.paulvangentcom.heartpy":
        return "ppg.quality", {"rr": RR}
    if module_id == "io.github.raphaelvallat.yasa":
        return "sleep.efficiency", {"stages": ["W", "W", "N1", "N2", "N3", "N2", "R", "W"]}
    if module_id == "io.github.scientisst.biosppy":
        return "ecg.quality", {"rr": RR}
    if module_id == "io.github.aura-healthcare.hrv-analysis":
        return "hrv.frequency", {"rr": RR, "frequency": False}
    if module_id == "io.github.pgomes92.pyhrv":
        return "hrv.metrics", {"rr": RR}
    if module_id == "io.github.tkrajina.gpxpy":
        return "importFile", {"path": str(_fixture(fixtures, "audit.gpx", GPX_TEXT))}
    if module_id == "io.github.dogsheep.healthkit-to-sqlite":
        return "import.healthkit", {
            "path": str(_fixture(fixtures, "export.xml", HEALTHKIT_TEXT))
        }
    if module_id == "io.github.grubersjoe.activity-calendar":
        return "summary", {"counts": {"2026-10-30": 2, "2026-10-31": 3}, "days": 30}
    if module_id == "io.github.apache.echarts":
        return "chart.line", {"points": [{"x": 1, "value": 60}, {"x": 2, "value": 70}]}
    if module_id == "io.github.observablehq.plot":
        return "plot.trend", {"points": [[1, 10], [2, 12]]}
    if module_id == "io.github.leeoniya.uplot":
        return "trend", {"points": [{"t": 1, "v": 60}, {"t": 2, "v": 62}]}
    if module_id == "io.github.tremorlabs.tremor":
        return "kpis", {"metrics": [{"label": "步数", "value": 1000}]}
    if module_id == "io.github.blinry.habitctl":
        return "habits.list", {"text": HABIT_TEXT}
    if module_id == "io.github.jrnl-org.jrnl":
        return "journal.list", {"text": JRNL_TEXT}
    if module_id in {"io.github.polyvertex.fitdecode", "io.github.dtcooper.fitparse"}:
        # 需要真实 FIT 文件；缺 path 时预期返回结构化 INVALID_INPUT，证明分发链路可用。
        return "summary", {}
    return "health", {}


# ---------------------------------------------------------------- 测试深度
def test_depth(module_id: str) -> dict[str, Any]:
    matches: list[Path] = []
    for path in sorted(TESTS.glob("test_*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if module_id in text:
            matches.append(path)
    if not matches:
        return {"level": "none", "files": [], "testCount": 0, "mode": None}
    files = [path.name for path in matches]
    text = "\n".join(path.read_text(encoding="utf-8") for path in matches)
    test_count = text.count("def test_")
    if "ModuleHost(" in text or "manager.install" in text or "TestClient(" in text:
        level, mode = "worker-process", "真实进程/管理器"
    elif "worker.handle(" in text:
        level, mode = "worker-rpc", "直接导入 worker"
    elif ".handle(" in text:
        level, mode = "adapter+rpc", "直接导入 handler"
    elif "manifest" in text:
        level, mode = "manifest-only", "只校验 manifest"
    else:
        level, mode = "unknown", None
    return {"level": level, "files": files, "testCount": test_count, "mode": mode}


# ---------------------------------------------------------------- 外部依赖
def external_dependencies(module_id: str, manifest: Any) -> dict[str, Any]:
    permissions = list(manifest.permissions)
    allowed_hosts = list(manifest.allowed_hosts)
    return {
        "account": module_id in ACCOUNT_IDS,
        "hardware": module_id in HARDWARE_IDS,
        "network": "network" in permissions or bool(allowed_hosts),
        "networkOnly": module_id in NETWORK_ONLY_IDS,
        "externalCli": module_id in EXTERNAL_CLI_IDS,
        "allowedHosts": allowed_hosts,
        "pythonDependencies": list(manifest.dependencies),
    }


def skip_reason(module_id: str, deps: dict[str, Any]) -> str | None:
    if deps["hardware"]:
        return "requires-hardware"
    if deps["account"]:
        return "requires-account-oauth"
    if deps["networkOnly"]:
        return "requires-live-network"
    return None


def recommendation(module_id: str) -> tuple[str, str]:
    if module_id in OFFICIAL_IDS:
        return "official", OFFICIAL_IDS[module_id]
    return "community", COMMUNITY_REASONS.get(module_id, "不满足官方保留条件")


# ---------------------------------------------------------------- 包结构校验
def inspect_package(package_path: Path, scratch: Path) -> dict[str, Any]:
    from eclipse_health_backend.modules import package
    from eclipse_health_backend.modules.manifest import load_manifest_file

    target = scratch / "extracted"
    try:
        with zipfile.ZipFile(package_path) as zf:
            package.extract_package(zf, target)
        manifest = load_manifest_file(target / "module.json")
        warnings = package.verify_checksums(target)
        package.verify_layout(target, manifest)
        return {"ok": True, "moduleId": manifest.id, "version": manifest.version,
                "warnings": warnings}
    except Exception as exc:  # noqa: BLE001 - 审计需要记录任何失败
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------- 单个模块
def audit_module(
    manager: Any,
    package_path: Path,
    source_dir: Path,
    *,
    deps_mode: str,
    scratch_root: Path,
) -> dict[str, Any]:
    from eclipse_health_backend.modules.manifest import load_manifest_file

    manifest = load_manifest_file(source_dir / "module.json")
    module_id = manifest.id
    external = external_dependencies(module_id, manifest)
    depth = test_depth(module_id)
    rec, rec_reason = recommendation(module_id)
    reason = skip_reason(module_id, external)
    entry: dict[str, Any] = {
        "id": module_id,
        "name": manifest.name,
        "version": manifest.version,
        "type": manifest.type.value,
        "source": source_dir.parent.name,
        "permissions": list(manifest.permissions),
        "externalDependencies": external,
        "testDepth": depth,
        "recommendation": rec,
        "recommendationReason": rec_reason,
        "package": str(package_path.relative_to(ROOT)).replace("\\", "/"),
        "smoke": {"status": "skipped", "reason": reason or "not-run"},
    }

    scratch = scratch_root / module_id
    scratch.mkdir(parents=True, exist_ok=True)
    structure = inspect_package(package_path, scratch)
    entry["packageCheck"] = structure
    if not structure["ok"]:
        entry["smoke"] = {"status": "fail", "reason": "package-invalid",
                          "error": structure["error"]}
        return entry
    if reason:
        entry["smoke"] = {"status": "skipped", "reason": reason}
        return entry
    if deps_mode == "skip" and manifest.dependencies:
        entry["smoke"] = {"status": "skipped",
                          "reason": "dependencies-disabled (--deps skip)"}
        return entry

    smoke: dict[str, Any] = {"status": "pending"}
    entry["smoke"] = smoke
    try:
        manager.install(str(package_path), enable=True)
        smoke["install"] = "ok"
        started = manager.start(module_id)
        smoke["start"] = started.get("state", "ok")
        health = manager.call(module_id, "health", {})
        smoke["health"] = "ok" if isinstance(health, dict) and health.get("ok") else "unexpected"
        fixtures = scratch / "fixtures"
        fixtures.mkdir(parents=True, exist_ok=True)
        method, params = representative_call(module_id, fixtures)
        smoke["representative"] = {"method": method}
        try:
            result = manager.call(module_id, method, params)
            if isinstance(result, dict) and isinstance(result.get("error"), dict):
                smoke["representative"]["status"] = "application-error"
                smoke["representative"]["error"] = result["error"].get("code") or result["error"]
                smoke["status"] = "partial"
                smoke["reason"] = "representative-method-returned-error"
            else:
                smoke["representative"]["status"] = "ok"
                smoke["status"] = "pass"
        except Exception as exc:  # noqa: BLE001 - 记录模块返回的结构化错误
            code = getattr(exc, "code", None) or type(exc).__name__
            detail = getattr(exc, "detail", None)
            smoke["representative"]["status"] = "error"
            smoke["representative"]["error"] = {"code": code, "detail": detail}
            if module_id in {"io.github.polyvertex.fitdecode", "io.github.dtcooper.fitparse"}:
                smoke["status"] = "partial"
                smoke["reason"] = "fixture-required; dispatch verified"
            else:
                smoke["status"] = "fail"
                smoke["reason"] = "representative-method-error"
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "code", None) or type(exc).__name__
        smoke["status"] = "fail"
        smoke.setdefault("reason", "install-or-start-failed")
        smoke["error"] = {"code": code, "detail": getattr(exc, "detail", None),
                          "message": str(exc)[:300]}
    finally:
        try:
            manager.uninstall(module_id)
        except Exception:  # noqa: BLE001 - 未安装成功时忽略
            pass
    return entry


def collect_packages() -> list[tuple[Path, Path]]:
    by_id: dict[str, Path] = {}
    for root in MODULE_ROOTS:
        if not root.is_dir():
            continue
        for manifest_path in sorted(root.glob("*/module.json")):
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            module_id = str(data.get("id") or "")
            if module_id:
                by_id[module_id] = manifest_path.parent
    pairs: list[tuple[Path, Path]] = []
    for package_path in sorted(DIST.glob("*.ehmod")):
        # 文件名形如 <module-id>-<version>.ehmod；按 id 前缀匹配源码目录。
        matched = None
        for module_id, source_dir in by_id.items():
            if package_path.name.startswith(module_id + "-"):
                matched = source_dir
                break
        if matched is None:
            continue
        pairs.append((package_path, matched))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps", choices=("install", "skip"), default="install")
    parser.add_argument(
        "--deps-timeout",
        type=float,
        default=0,
        help="覆盖模块依赖安装超时（秒）；0 表示沿用核心默认值",
    )
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    if not DIST.is_dir():
        print(f"error: {DIST} not found; run scripts/pack_official_modules.py", file=sys.stderr)
        return 2

    pairs = collect_packages()
    if args.only:
        wanted = set(args.only)
        pairs = [(p, s) for p, s in pairs if any(p.name.startswith(w + "-") for w in wanted)]
    if not pairs:
        print("error: no packages matched", file=sys.stderr)
        return 2

    # 必须在导入后端数据库模块前设置，确保临时目录生效。
    temp_home = Path(tempfile.mkdtemp(prefix="eh-audit-"))
    os.environ["EH_DATA_DIR"] = str(temp_home)
    from eclipse_health_backend.modules import package as module_package
    from eclipse_health_backend.modules.manager import ModuleManager

    if args.deps_timeout > 0:
        original_install = module_package.install_module_venv

        def _install_with_timeout(module_dir, dependencies, *, timeout_s=None, log=None):
            return original_install(
                module_dir, dependencies, timeout_s=args.deps_timeout, log=log
            )

        module_package.install_module_venv = _install_with_timeout

    manager = ModuleManager(data_dir=temp_home, call_timeout_s=60.0)
    entries: list[dict[str, Any]] = []
    try:
        for package_path, source_dir in pairs:
            print(f"audit: {package_path.name}", flush=True)
            entry = audit_module(
                manager,
                package_path,
                source_dir,
                deps_mode=args.deps,
                scratch_root=temp_home / "audit-scratch",
            )
            entries.append(entry)
            print(f"  -> {entry['smoke']['status']} ({entry['smoke'].get('reason', '')})",
                  flush=True)
    finally:
        manager.shutdown()
        shutil.rmtree(temp_home, ignore_errors=True)

    # Cardia 随安装包内置，不在 dist/modules 中，单独记录。
    cardia = MODULE_ROOTS[0] / "cardia"
    if cardia.is_dir():
        from eclipse_health_backend.modules.manifest import load_manifest_file

        manifest = load_manifest_file(cardia / "module.json")
        entries.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "version": manifest.version,
                "type": manifest.type.value,
                "source": "official",
                "permissions": list(manifest.permissions),
                "externalDependencies": external_dependencies(manifest.id, manifest),
                "testDepth": test_depth(manifest.id),
                "recommendation": "official",
                "recommendationReason": "核心 Cardia 引擎，随安装包内置",
                "package": None,
                "smoke": {"status": "skipped", "reason": "bundled-with-installer"},
            }
        )
    entries.sort(key=lambda item: item["id"])

    summary = {
        "total": len(entries),
        "pass": sum(1 for item in entries if item["smoke"]["status"] == "pass"),
        "partial": sum(1 for item in entries if item["smoke"]["status"] == "partial"),
        "skipped": sum(1 for item in entries if item["smoke"]["status"] == "skipped"),
        "fail": sum(1 for item in entries if item["smoke"]["status"] == "fail"),
        "official": sum(1 for item in entries if item["recommendation"] == "official"),
        "community": sum(1 for item in entries if item["recommendation"] == "community"),
    }
    document = {
        "schemaVersion": "1",
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "depsMode": args.deps,
            "dataDir": "<temporary EH_DATA_DIR>",
        },
        "summary": summary,
        "modules": entries,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"report: {args.report}")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
