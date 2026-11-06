# eclipse health V4 更新日志

> 面向用户的行为变化。技术细节与根因见 `BUGS.md`。

## [未发布] V4 开发中

### 修复

- **模块安装不再依赖用户机网络（BUG-001）**：安装包内置官方模块依赖的离线 wheel
  仓库，安装功能型模块时优先离线安装，失败才联网兜底。UI 类模块不受影响。
- **依赖安装错误可诊断**：失败时返回实际模式（`depsMode`）、缺失包名（`missing`），
  并新增 `offline-wheel-missing` 原因。
- **核心 Python 升级后自动重建模块环境**：不再复用旧版本 venv/deps。
- **relay-ecg / relay-sleep 不再重复安装核心已内置的 numpy / onnxruntime / wfdb**。
- **构建链补全**：一键脚本会自动打包 `dist/modules` 并生成离线依赖仓库。

### 新增

- 环境变量 `EH_MODULE_DEPS_MODE`：`auto`（默认）/ `offline` / `online`。
- 脚本 `scripts/build_module_wheelhouse.py`（构建期生成离线 wheel 仓库）。

### 说明

- V4 基线来自 V3 `feat/ui-alignment`（commit `84b77fd`）。
