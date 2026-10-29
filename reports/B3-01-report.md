# 报告 · B3-01 Cardia 简化模型 + 模块自带权重 + 启动 ≤3s
状态：完成（全量 pytest 受跨区测试收集冲突限制，见「跨区需求」）

## 交付
- 简化权重 `cardia_k4_best_sim.onnx`：放 `modules/official/cardia/models/`（随 `.ehmod` 发布），另存一份到 `backend/resources/models/cardia/` 供核心直调/测试；原图未动。
- `module.json`：`contributes.models[0]` 增加 `files[{path,sha256}]`、`runtime.format=onnx`、输入张量（`x[1,64,104]`、`dt[1,64]`）、输出 `logits[1,64,4]`、类别顺序、预处理版本、参数口径；`checksums.json` 覆盖权重；`pack_cardia.py` 打包前后各校验一次 manifest 权重哈希。
- 加载与回退：`analysis/model.py` 新增 `resolve_model_path`（显式路径 > `EH_CARDIA_MODEL=original` > `EH_CARDIA_MODEL_PATH` > 简化图 > 原图）、`ModelInfo.model_variant`、`prewarm()` 输出 `modelFile/modelVariant`，固定 batch 检测（批量窗口拆单窗，不改推理数学）；模块入口用 `configure_model()` 把模块内权重经 `EH_CARDIA_MODEL_PATH` 注入，缺失时回退原图；`health` 暴露 `model{file,sha256,variant,importSeconds,sessionInitSeconds}`。
- 测试：新增 `tests/analysis/test_model_selection.py`（9 项）、`test_alignment.py` 增加简化图 vs 原图 slow 对照；模块契约/e2e 断言权重与启动。

## 产物校验
| 文件 | 字节 | sha256 | 节点 | initializer / 元素 | 输入 |
|---|---|---|---|---|---|
| `cardia_k4_best.onnx`（原图，未改） | 5,594,712 | `9577b235…fe04110` | 24,330 | 46 / 721,972 | `batch` 动态 |
| `cardia_k4_best_sim.onnx`（新增） | 4,884,442 | `f5912861…8237bf53` | 11,491 | 177 / 727,939 | `x[1,64,104]`、`dt[1,64]` |

参数口径：modelCard `parameters=722327` 为 Torch 参数量；ONNX initializer 元素数原图 721,972、简化图 727,939（导出按 64 搏窗口展开常量），已在 manifest/README 写明。

## 数值对齐（硬门槛）
同一输入、同一 R 峰，原图 vs 简化图逐搏 softmax 概率最大差（阈值 1e-4）：

| 记录 | 心搏 | max\|Δp\| |
|---|---|---|
| 100 | 2,271 | 1.76e-07 |
| 200 | 2,600 | 3.78e-07 |
| 208 | 2,951 | 4.39e-07 |

B1-03 `test_alignment.py` 继续通过（默认会话现为简化图）。

## 启动与端到端
| 场景 | 耗时 |
|---|---|
| `InferenceSession` 初始化（简化图） | 1.19–1.35s（原图 150–200s） |
| 模块预热（宿主白名单环境、单进程） | **2.37–2.74s**（导入 1.1–1.4s + 初始化 1.2–1.3s） |
| 模块预热（pytest e2e，并行 Agent/AV 负载） | 5.9–8.2s |
| 实时 uvicorn：`/engine` startedAt→readyAt（含首次安装） | 6.39s |
| 实时 uvicorn：sample 100 `POST /analyses`→completed | 3.56s wall（durationMs 3374；2,270 搏、15 测量） |
| pytest e2e：`ready` → POST→completed | 3.4–4.2s（durationMs 3.3–4.1s） |

简化图固定 batch=1，`predict` 拆单窗前向（2,270 搏 35 窗共 0.275s），总分析时长与 B2 的 3.5s 持平。

## 验证
- `ruff check backend modules/official scripts` → All checks passed。
- `pytest backend/tests/analysis backend/tests/analysis_service -q` → **exit 0**（含 1 条 slow：简化图 vs 原图；1 条模块 e2e）。
- 全量 `pytest backend/tests -q --ignore=backend/tests/reports` → 收 339 项，全部通过、1 skipped、exit 0；不带 ignore 时在收集阶段失败（跨区，见下）。
- 打包 `scripts/pack_cardia.py` → `dist/cardia-1.0.0.ehmod`，5 文件、2,864,449 B、sha256 `db3e6acb…ec2ecce2`；打包后解压复验 checksum 与权重哈希。
- 回退：`EH_CARDIA_MODEL=original`、简化图缺失、模块权重缺失三条路径均有单测；原图会话在 slow 对照中真实加载成功。

## 未做 / 偏离
- `EH_CARDIA_MODEL` 到不了模块 worker：`modules/host.py` 只继承白名单环境；强制原图目前只在直调模式生效（跨区需求）。
- 模块 e2e 的 warmupSeconds 含 Python 导入且受并行负载影响，高于 ~1.5s 目标；干净 worker 实测 2.4–2.7s，会话初始化 1.2–1.35s。
- 未量化、未改模型结构/训练、未改 ORT 版本、未改分析 API/UI。

## 跨区需求（需要别的 Agent 或指挥官处理）
- `backend/tests/reports/test_api.py` 与 `tests/modules/test_api.py` 同名且测试目录无 `__init__.py` → 全量 pytest 收集冲突（`import file mismatch`）；需改文件名或加包。
- `modules/host.py` `_BASE_ENV_ALLOWLIST`：建议放行 `EH_CARDIA_MODEL` / `EH_CARDIA_MODEL_PATH`，让回退开关对模块生效。
- `backend/pyproject.toml` 的 `slow` marker 描述仍写「约 150 秒」，已过时。
- 本机内存紧张（并行 Agent 叠加）时，无关测试会因 OpenBLAS/ORT `bad allocation` 失败，重跑即过；属环境问题。

## 需要指挥官决策
- `warmupSeconds` 是否接受「含 Python 导入」的口径（干净 2.4–2.7s，会话 1.2–1.35s）。
- 4.88MB 权重同时存在于模块与 `backend/resources`（直调/测试用），是否保留双份。
- 模型卡参数量继续用 Torch 722,327、另列 ONNX initializer 口径，是否采纳。

## 建议下一批
- 每模块 venv：把 `analysis` 库依赖与 `preprocess.json` 移入模块，消除核心源码路径依赖。
- 模块预热拆阶段上报（导入 / ONNX 初始化），便于 UI 解释启动耗时。
