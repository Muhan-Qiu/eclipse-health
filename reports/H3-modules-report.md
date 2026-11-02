# 报告 · H3 模块适配包（候选 1–6）

状态：完成（B 类上游库未安装，依赖安装路径未实测）

## 交付
- `modules/official/neurokit2/` · `io.github.neuropsychology.neurokit2` · analysis-model · deps `[]`（E，核心 venv 已装 neurokit2 0.2.13）
- `modules/official/heartpy/` · `io.github.paulvangentcom.heartpy` · analysis-model · deps `heartpy>=1.2,<2`
- `modules/official/hrv-analysis/` · `io.github.aura-healthcare.hrv-analysis` · analysis-model · deps `hrv-analysis/pandas/numpy/scipy/astropy/nolds`
- `modules/official/pyhrv/` · `io.github.pgomes92.pyhrv` · analysis-model · deps `pyhrv/biosppy/nolds/spectrum/numpy/scipy`
- `modules/official/biosppy/` · `io.github.scientisst.biosppy` · analysis-model · deps `biosppy/numpy/scipy/h5py/scikit-learn`
- `modules/official/yasa/` · `io.github.raphaelvallat.yasa` · analysis-model · deps `yasa/mne/lightgbm/pooch/pandas/numpy`
- 每个模块含 `module.json`、`README.md`、`LICENSE`（GPL-3.0 全文）、`NOTICE`、`src/main.py`、`src/adapter.py`。
- Worker 统一实现 `initialize / warmup / health / analyze / stats / <tool> / deactivate`；stdio UTF-8，业务错误 `{"error":{code,message}}`，输入错误 JSON-RPC `INVALID_INPUT`；所有结果带「非医疗器械，不用于诊断」。
- contributes：6 个均声明 `models` + `tools` + `recordTypes` + `ui.widgets` + `ui.pages`；只使用 `stat/sparkline` 视图与受控页面块。
- 测试：`backend/tests/modules/test_official_{neurokit2,heartpy,hrv-analysis,pyhrv,biosppy,yasa}.py`，每个覆盖 manifest schema、纯函数成功路径、非法输入错误路径、worker RPC 成功/错误。

## 验证
- `backend\.venv\Scripts\python.exe -m pytest`（上述 6 个文件）：**47 passed，约 3 秒**。
- `backend\.venv\Scripts\python.exe -m ruff check`（6 个模块 + 6 个测试）：**All checks passed**。
- `load_manifest_file` + `check_compatibility`（核心解析器）对 6 个 manifest 全部通过，`dependencies` 已被 schema 接受（无需 pending）。
- 上游库可用性：`neurokit2 0.2.13` 已安装；`heartpy/hrv-analysis/pyhrv/biosppy/yasa` 未安装，相关分支未在真实库上实测。

## 未做 / 偏离
- 候选表将 HeartPy 标为 E（numpy/scipy 已满足），但核心 venv 没有 `heartpy` 包本身，故 `dependencies` 写 `heartpy>=1.2,<2` 以保证模块可运行；这是唯一一处对候选表的偏离。
- B 类依赖未实际 `pip install`（禁止污染核心 venv），版本上限为初稿，安装时可能需按解析结果调整（尤其 pyhrv 对 numpy 2.x 的兼容性）。
- 未打包 `.ehmod`、未生成 `checksums.json`（本批不要求；打包脚本 `scripts/pack_cardia.py` 可参考）。
- 波形输入只支持核心传入的 float32 临时文件（`signalRef`，sha256 校验）；PSG 的 `signals` 走内联数组，未做文件句柄版本。
- 上游 LICENSE 只成功获取 NeuroKit2（来自已装 dist-info，MIT）；其余因本机 `raw.githubusercontent.com` 不可达，NOTICE 中标注「上游许可见 URL」，未放入 `LICENSES/*-upstream.txt`。
- YASA 内置训练权重未复制、未分发，随上游包进入模块 venv；权重许可需单独核对。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 核心尚未实现 widget/page 数据通道与工具目录执行（契约 §11），当前 manifest 声明只做聚合，不会自动渲染/调用。
- 若官方模块统一入库校验，建议把 6 个 manifest 加入 `test_legacy_manifests_still_pass` 或独立参数化用例（该文件非本 Agent 所有权）。
- 上游 LICENSE 抓取需要可用网络或人工补入 `LICENSES/<slug>-upstream.txt`。

## 需要指挥官决策
- B 类依赖版本上限是否按 PyPI 实际解析结果统一锁定（尤其 numpy 2.x 与 pyhrv/biospy 的兼容性）。
- 上游许可文件缺失时，是否接受 NOTICE 中的 URL 声明作为过渡。

## 建议下一批
- 在 H1 模块 venv 就绪后，对 5 个 B 类模块做一次真实安装 + `health/analyze` 冒烟，修正版本约束。
- 为 6 个模块补 `checksums.json` 与 `.ehmod` 打包冒烟。
