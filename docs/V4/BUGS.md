# V4 问题清单（BUGS）

状态图例：`NEW` 待确认 / `REPRO` 已复现 / `ROOT CAUSE` 根因已定位 / `FIXING` 修复中 / `FIXED` 已修复待验证 / `DONE` 已验证

---

## BUG-001 功能型模块在他人电脑上无法导入/启动

- **状态**：`ROOT CAUSE`（调查中，待子代理报告汇总）
- **优先级**：P0
- **用户描述**（2026-11-06）：
  > 模块导入有问题，其他人电脑上这个太依赖电脑各种库以及 python 的版本了（猜测原因），导致功能型模块都很难导入。
- **影响范围**：安装版（非开发机）上的所有需要第三方依赖的模块；可能包括官方模块。
- **初步定位**：
  - `BUILD.md:72-73` 说明：无依赖模块由冻结 sidecar 通过 `runpy` 执行，不依赖系统 Python；**有依赖模块必须先创建 per-module venv**。
  - `backend/tests/modules/test_module_venv.py:152` 表明 venv 用 `sys.executable -m venv` 创建；冻结后 `sys.executable` 是 sidecar 自身而非 Python。
    → 安装版上「声明了 dependencies 的模块」创建 venv 必然失败，安装回滚，表现为「模块导入不了」。
- **待验证**：冻结产物中 `install_module_venv` 是否已有降级路径；官方模块各自声明了哪些依赖。
- **修复方向（候选）**：
  1. 随安装包内置独立 Python 运行时（python-build-standalone / python-embed），模块 venv 统一用它创建；
  2. 构建期预生成官方模块的 venv / 预下载 wheel，离线可用；
  3. 未就绪时给出明确可操作的错误与「安装运行时」引导，而不是静默失败；
  4. 解释器选择优先级：`EH_MODULE_PYTHON` → 随包运行时 → 真实系统 Python → `sys.executable`（仅非冻结）。
- **验收**：
  - 全新 Windows（无 Python）安装后，安装一个带 dependencies 的模块成功、能启动、能调用；
  - 断网环境下安装官方模块成功（预置 wheel 或预建 venv）；
  - 失败时错误信息可定位到具体缺失项。
- **回滚点**：`84b77fd`（V4 基线）

---

## 待补充

后续 bug 按同样格式追加：现象、复现、根因（file:line）、修复、验证、回滚点。
