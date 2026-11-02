# B3-01 · Cardia 简化模型 + 模块自带权重 + 启动 ≤3s

> 难度：中等偏难 3/4 · 建议思考强度：**high** · 批次：B3 功能
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 这是 B2 遗留的第一优先级：把 ONNX 冷启动从 ~150s 降到 ~2s，且不改坏数值。

## 1. 必读

- `reports/B2-01-ort-spike.md`（根因、实测、onnxsim 方案）
- `reports/B2-01-report.md`（模块、分析服务、`/engine`、测试）
- `docs/MODULE_CONTRACT_V1.md`：§2 manifest、§8 模型贡献、§11 安全
- `docs/INTERNAL_API_V1.md`：§3.3 `GET /engine`
- 代码：`modules/official/cardia/`、`scripts/pack_cardia.py`、`analysis/model.py`、`analysis_service/`、`backend/tests/analysis/`

## 2. 现成材料（先确认再动手）

B2-01 spike 在临时目录留下了产物，**先验证再用**：

- `C:\Users\qiumuhan\AppData\Local\Temp\ehspike\cardia_sim.onnx`（4.88MB，onnxsim 固定形状）
- `C:\Users\qiumuhan\AppData\Local\Temp\ehspike\pylibs\`（onnx 1.17 + onnxsim 0.8.1，可用 `PYTHONPATH` 调）
- 复现脚本：同目录 `simplify.py`、`scaling_and_equiv.py`、`ort_timing.py`

临时目录可能消失；要么先复制到安全位置，要么用 pylibs 重新生成。产物必须校验：输入输出名/形状、节点数（约 11,491）、文件 sha256。

## 3. 你必须交付

1. **简化权重进模块**
   - 放 `modules/official/cardia/models/cardia_k4_best_sim.onnx`；原模型 `backend/resources/models/cardia/cardia_k4_best.onnx` **保持不动**。
   - 模块 `module.json`：`contributes.models` 指向模块内权重，写清 `runtime: onnx`、输入契约、类别顺序、预处理版本、校验和、模型卡摘要。
   - `checksums.json` 包含新权重；`scripts/pack_cardia.py` 打出带权重的 `.ehmod`。
2. **加载与回退**
   - 模块入口默认加载模块内简化模型；`EH_CARDIA_MODEL=original` 或简化模型缺失时回退原模型。
   - `analysis/model.py` 只增加「模型路径/环境变量选择」与耗时记录，**不改推理数学**。
   - `GET /engine` 的 `message`/`warmupSeconds` 如实反映；预热后应 ≤3s（目标 ~1.5s）。
3. **数值对齐（硬门槛）**
   - 在 100/200/208 上跑原模型 vs 简化模型：同一输入、同一 R 峰，逐搏概率最大差 **< 1e-4**（预期 ~5e-7）；记录实测值。
   - B1-03 的 `test_alignment.py` 继续通过；新增简化模型的对照测试或参数化。
   - 若任何样本超阈值，立即停止并回退，报告差异。
4. **启动与回归**
   - 实测：`InferenceSession` 初始化、`warmup`、首次 `POST /analyses` 到完成的总时长。
   - 更新 B2-01 的慢测试预期（从 150s 级降到 3s 级），但**不能跳过真实 ONNX 测试**。
   - 全量 `pytest backend/tests`、`ruff` 通过。
5. **文档/报告**
   - `reports/B3-01-report.md`：产物哈希、节点数、初始化/推理/端到端耗时、对齐表、回退验证。
   - 模型卡参数口径：ONNX initializer 元素数 ≈722k（导出展开常量），写清楚。

## 4. 文件所有权（只能改这些）

```
modules/official/cardia/**
scripts/pack_cardia.py
backend/src/eclipse_health_backend/analysis/model.py     # 仅模型选择/耗时
backend/resources/models/cardia/cardia_k4_best_sim.onnx  # 新文件
backend/tests/analysis/**
backend/tests/analysis_service/**
reports/B3-01-report.md
```

不要动：原模型、`analysis/engine.py` 的数学、`analysis/features.py`、`api/`、`src/`、`docs/`、`prompts/`、`uploads/`。

## 5. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend modules/official scripts
backend\.venv\Scripts\python.exe -m pytest backend\tests\analysis backend\tests\analysis_service -q
# 全链路：打包 → 启动 → GET /engine（应 ≤3s ready）→ POST 分析 sample 100
backend\.venv\Scripts\python.exe scripts\pack_cardia.py
```

## 6. 明确不做

不改模型结构/训练、不做量化、不改 ONNX Runtime 版本、不改 B2 的分析 API/UI、不做 beatsRef/SSE/每模块 venv。只做「简化权重 + 模块自带 + 对齐 + 启动」。
