# V4 问题清单（BUGS）

状态图例：`NEW` 待确认 / `REPRO` 已复现 / `ROOT CAUSE` 根因已定位 / `FIXING` 修复中 / `FIXED` 已修复待验证 / `DONE` 已验证

---

## BUG-001 功能型模块在他人电脑上无法安装/导入

- **状态**：`FIXED`（代码与单测完成；待安装包实机验收）
- **优先级**：P0
- **用户描述**（2026-11-06）：
  > 模块导入有问题，其他人电脑上这个太依赖电脑各种库以及 python 的版本了（猜测原因），导致功能型模块都很难导入。
  >
  > 补充：报「安装不了」；**UI 类模块可以正常安装使用**。对方机器装了 Python 但版本/库不一致。
- **现象归纳**：
  - 无依赖模块（UI 组件类）安装正常；
  - 声明了 `dependencies` 的功能型模块（biosppy / heartpy / hrv-analysis / pyedflib / gpxpy 等）安装失败。

### 根因

1. **依赖安装强依赖联网 PyPI**：`backend/src/eclipse_health_backend/modules/package.py`
   的冻结分支（`_install_deps_frozen`）与源码分支都直接 `pip install <deps>`，
   没有任何本地索引/离线仓库；国内网络、代理、离线机器上会超时或解析失败。
   V3 只在安装包内置了 `.ehmod`（模块源码），**没有内置依赖 wheel**。
2. **没有二进制优先策略**：未使用 `--prefer-binary`，部分环境会尝试从 sdist 编译，
   用户机没有编译器 → 失败。
3. **pip 无重试/超时调优**：仅有一个 300 秒总超时，弱网下容易整段失败。
4. **错误不可诊断**：失败统一报「依赖安装失败（网络、版本冲突或包不可用）」，
   看不出缺哪个包、走的是离线还是联网。
5. **源码模式 venv 版本不校验**：`.ready` 只比对依赖 hash，不比对 Python 版本，
   核心升级 Python 后旧 venv 仍被复用，导致 `ImportError`/ABI 错误。
6. **官方模块声明了核心已内置的依赖**：relay-ecg / relay-sleep 声明
   `numpy / onnxruntime / wfdb`，核心本来就有，却触发一次不必要的重装，
   放大了失败面。

### 修复

| 文件 | 变更 |
|---|---|
| `scripts/build_module_wheelhouse.py`（新增） | 构建期解析官方（可选社区）模块依赖，`pip wheel` 产出完整 wheel 仓库与 `index.json`（含 sha256） |
| `backend/packaging/eclipse-health-backend.spec` | 存在 wheelhouse 时打进 `_internal/wheelhouse` |
| `backend/src/eclipse_health_backend/modules/package.py` | 依赖安装改为 **离线优先**：`--no-index --find-links <wheelhouse>` → 失败再联网兜底；`--prefer-binary`；`PIP_RETRIES=3`、`PIP_TIMEOUT=60`；错误详情带 `depsMode` 与 `missing` 包名；`.ready/.deps-ready` 记录并校验 Python 主次版本 |
| `modules/official/relay-ecg/module.json`、`relay-sleep/module.json` | `dependencies` 置空（numpy / onnxruntime / wfdb 由核心运行时提供） |
| `scripts/build_release.ps1` | 新增 wheelhouse 构建步骤；`dist/modules` 缺失时自动调用打包脚本；提供 `-SkipWheelhouse`、`-WheelhouseCommunity` |
| `backend/tests/modules/test_module_venv.py` | 新增离线优先、联网兜底、纯离线、缺 wheelhouse、Python 版本失配 5 组用例 |

### 行为变化

- `EH_MODULE_DEPS_MODE` 环境变量：`auto`（默认，离线优先、联网兜底）、
  `offline`（只允许离线，缺 wheel 直接报错）、`online`（保持旧行为）。
- 安装失败时 `details.reason` 新增 `offline-wheel-missing`，
  `details.missing` 给出缺失包名，`details.depsMode` 给出实际模式。

### 验收

- [x] 离线仓库构建：`scripts/build_module_wheelhouse.py --verify` → 34 wheels / 105.4 MB，
      biosppy、gpxpy、heartpy、hrv-analysis、pyedflib 全部 `verify ok`；
- [x] 源码模式离线安装：`EH_MODULE_DEPS_MODE=offline` 安装 `gpxpy>=1.6,<2` → `pipMode=offline`，
      venv 内 `import gpxpy` 成功；
- [x] 重依赖离线安装：hrv-analysis 全套依赖 → numpy 1.26.4 + scipy 1.16.3，`import hrvanalysis` 成功；
- [x] 冻结安装器（`pip_install.py --target`）离线安装 gpxpy 成功并可导入；
- [x] `pytest tests/modules`：416 passed, 7 skipped；`ruff check` 全部通过；
- [ ] 全新 Windows（无 Python、断网）安装包实机验收（需要出安装包）；
- [ ] 有网但访问 PyPI 受限时走离线仓库（逻辑已由单测覆盖）。

### 回滚点

- 修复前基线：`84b77fd`
- 本次修复提交：见 `git log --grep="BUG-001"`

---

## BUG-002 构建链缺步骤：全新克隆无法直接出安装包

- **状态**：`FIXED`（已顺手修复，待完整构建验证）
- **根因**：`scripts/build_release.ps1` 未调用 `pack_official_modules.py`，
  而 PyInstaller spec 强依赖 `dist/modules`。
- **修复**：`dist/modules` 缺失时自动打包后再继续。

---

## 待补充

后续 bug 按同样格式追加：现象、复现、根因（file:line）、修复、验证、回滚点。
