# B4-03 · 设备/医院格式适配器

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 1）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：把 EDF、SCP-ECG、Apple、Samsung、华为接进现有导入链路；**验证过的写 verified，没样本的写 experimental，不猜**。

## 1. 必读

- `docs/INTERNAL_API_V1.md`：§2 导入、§0 通用。
- `docs/DATA_SCHEMA_V1.md`：§4 HealthRecord、§5 Signal、§15 隐私。
- `docs/FORMATS/**`、`uploads/samples/index.json`（B4-02 产出；若还没到，先看现有 `importers/` 和公开规范）。
- `reports/B2-02-report.md`（适配器接口、WFDB/CSV、占位符）。
- 代码：`backend/src/.../importers/{base,registry,placeholders,wfdb_adapter,csv_adapter}.py`。

## 2. 你必须交付

1. **适配器（复用 `ImportAdapter` 接口）**
   - `edf`：EDF/EDF+ 头部（256B 固定 + 信号定义）、数字→物理换算、起始时间、采样率、通道标签；按 `ECG/ECG I/MLII` 等标签选导联；多导联全部入库；标注（如有）只作参考。
   - `scp-ecg`：最小可用解析（section 0 指针、1 头、2 导联、3 数据；12/16-bit）；解析不了的段返回明确 `unsupported_section`，不要输出错数据；标记 `experimental` 直到样本验证。
   - `apple`：Health `electrocardiograms.csv`（时间戳、电压、采样间隔）；单导联；mV；BOM/时区/缺列处理。
   - `samsung`：按公开 CSV/JSON 字段映射；识别采样率、时间、电压、单位；样本缺失时 `experimental`，并在 preview 里说明「未用真实样本验证」。
   - `huawei`：同上；公开资料/样本最少，允许 `experimental` + 明确 `requires`；不要编字段。
   - 所有适配器：`detect` 置信度、`preview` 前 2000 点、`parse` 返回 `ParsedImport`；单位统一 mV；时区/采样率/导联可校正；文件名只存哈希。
2. **注册与优先级**
   - 更新 `registry.py`：按扩展名/魔数/内容探测；WFDB/CSV 仍优先；同扩展名冲突时给候选让用户选。
   - `placeholders.py` 中已被真实实现的厂商移除占位；未实现的保留并返回「需样本」。
3. **测试**
   - 每个格式至少：正常样本、缺列/坏文件、单位/采样率/导联 `requires`、提交后记录/信号读回。
   - 有真实公开样本的格式必须用真实样本跑通；没有的用合成夹具并标 `synthetic`。
   - 不联网；临时 `EH_DATA_DIR`；不复制大文件进 git。
4. **能力矩阵**
   - 报告里列出：格式 / 真实样本验证 / 合成验证 / 支持字段 / 已知限制 / 需要用户补什么。
5. **报告** `reports/B4-03-report.md`。

## 3. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/importers/**     # 新增适配器 + registry/placeholders
backend/tests/imports/**
backend/tests/fixtures/imports/**                   # 仅小样本/合成
reports/B4-03-report.md
```

只读：`docs/FORMATS/**`、`uploads/samples/**`、`analysis/ingest.py`、`storage/`、`db/`、`api/records.py`。
不要动：`api/__init__.py`、`app.py`、`pyproject.toml`、`modules/`、`src/`、`src-tauri/`、其他 `docs/**`、`prompts/**`。

## 4. 与 B4-02 的契约

- B4-02 写 `uploads/samples/index.json` 与 `docs/FORMATS/*.md`；你只读。
- 若你开工时样本还没到：先实现 EDF/SCP-ECG/Apple（公开规范足够），Samsung/华为先写「按文档 + 合成夹具」，等样本出现后补真实验证；不要空等。
- 不要修改 `uploads/`（B4-02 独占）。

## 5. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\imports -q
# 手工：对每个格式 preview → commit → GET /records/{id}/signal 读回
```

## 6. 明确不做

不做分析/UI/报告、不做 PDF 导入、不做云同步、不做批量导入、不新增 Python 依赖（EDF 用标准库 + numpy；SCP-ECG 最小解析用标准库）、不猜未知字段。真实样本不可得时明确 `experimental`，不要声称 verified。
