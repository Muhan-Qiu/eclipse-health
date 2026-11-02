# B2-02 · 导入链路（WFDB / CSV）+ 参数校正

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B2 贯通
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：任何一条本地 ECG 文件，经「预览 → 校正 → 提交」变成库里的 `HealthRecord` + `Signal`。Samsung/Apple/华为/SCP-ECG 本批只留接口，不猜格式。

## 1. 必读

- `docs/INTERNAL_API_V1.md`：§2 导入接口、§0 通用、§4 数据形状。
- `docs/DATA_SCHEMA_V1.md`：§4 HealthRecord、§5 Signal、§11 存储、§15 隐私。
- `docs/V3_FEATURE_BACKLOG.md`：G1 格式识别、G2 参数校正。
- `reports/01-backend-core-report.md`（记录/信号 API 与 storage）、`reports/03-cardia-engine-report.md`（ingest 可复用）。
- 代码：`analysis/ingest.py`、`storage/files.py`、`db/repositories.py`、`api/records.py`、`domain/models.py`。

## 2. 目标

实现 `ImportAdapter` 体系和两步导入 API；用 MIT-BIH 100/200/208 与合成 CSV 验证；解析结果必须能直接喂给 B1-03 的 `analysis.analyze`。

## 3. 你必须交付

1. **适配器接口（为以后厂商格式留位）**
   - `importers/base.py`：`ImportAdapter` 协议/抽象类，方法：
     - `adapter_id: str`（如 `org.eclipsehealth.wfdb`）
     - `detect(source) -> Detection`（format、confidence、reason）
     - `preview(source) -> ImportPreview`（fs、leads、durationSec、unit、requires、warnings、前 2000 点）
     - `parse(source, parameters) -> EcgSignal + metadata`
   - `importers/registry.py`：注册/按顺序探测；未知格式返回 422 `unsupported_format`。
   - 注册占位适配器：`samsung`、`huawei`、`apple`、`scp-ecg`，`supported=False`，说明「等待样本，B3 实现」；**不要**写猜测性解析。
2. **WFDB 适配器**
   - 支持：文件夹路径（调试）、`.zip` 包、或选中 `.hea` 时自动找同目录同名 `.dat`/`.atr`。
   - 优先 `MLII`，否则第一导联；物理单位 mV；非 360Hz 保留原采样率并在 preview 标 `requires.samplingRate=true`（B2 不强制重采样，交给分析引擎）。
   - 读取 `.atr`（若存在）作为参考 R 峰，记录 `hasAnnotations`；不要把它当诊断标签。
3. **CSV 适配器**
   - 自动识别分隔符、表头/无表头、时间列/索引列、单导联列；支持显式 `leadColumn`、`timeColumn`、`samplingRate`、`unit`、`polarity`。
   - 列名含 `MLII/II/ECG/voltage` 等常见词时给高置信度；无法确定时 `requires.lead=true` / `requires.samplingRate=true`，不硬猜。
   - 大小写、BOM、GBK/UTF-8 容错；解析失败给行列号。
4. **两步导入 API**（`importers/api.py`，`router` 路径以 `/imports/...` 开头）
   - `POST /imports/preview`：`multipart/form-data`（`file`）或调试用 `path`；`hintFormat`。返回契约 §2.1 结构。
   - `POST /imports/{importId}/commit`：body 契约 §2.2；创建记录 + 信号，返回 201 `{recordId, record}`。
   - `DELETE /imports/{importId}`：204。
   - 临时目录 `backend/.data/imports/<importId>/`；commit/delete/24h TTL 清理；文件名不落库，只存哈希。
   - 约束：≤200MB、拒绝路径穿越、ZIP 炸弹防护（解压总量 ≤300MB、文件数 ≤200）、并发 importId 隔离。
5. **入库**
   - 复用 `db/repositories.py` 与 `storage/files.py`，不要复制一套。
   - `recordType="org.eclipsehealth.ecg"`；`moduleId=adapter_id`；`source` 记录 manufacturer/model（若文件元数据有）；`provenance.fileNameHash/fileHash/adapterVersion`。
   - `parameters.polarity="inverted"` → 翻转样本并写 `metadata.polarity`；`samplingRate/lead/unit` 校正写回。
   - 多导联：B2 单导联优先；若文件天然多导联，`signals` 数组全部入库，记录 `leads` 列表；报告说明。
6. **测试**
   - `backend/tests/imports/`：WFDB 文件夹、WFDB zip、CSV（带/不带表头、分号、时间列、GBK）、坏文件、未知格式、超大文件、zip 穿越、提交后记录/信号/哈希、极性翻转、参数校正、TTL/清理。
   - 用 `100/200/208` 验证：preview 的 fs/leads/duration 与 `.hea` 一致；commit 后 `GET /records/{id}/signal` 读回与源一致（容差 1e-6）。
   - 不联网；临时 `EH_DATA_DIR`。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/importers/**
backend/tests/imports/**
backend/tests/fixtures/imports/**
```

只读：`analysis/ingest.py`、`storage/`、`db/`、`api/records.py`、`domain/models.py`。

不要动：`api/__init__.py`、`app.py`、`pyproject.toml`、`modules/`、`src/`、`docs/`、`prompts/`、`uploads/`。需要 B2-01 挂载或改核心，写进报告。

## 5. 与 B2-01 的契约

- 你提供 `eclipse_health_backend/importers/api.py` 的 `router`；路径以 `/imports/preview`、`/imports/{id}/commit`、`/imports/{id}` 开头。
- B2-01 负责 `app.include_router(imports_router, prefix="/api/v1")`；你不要改 `app.py`。
- 如果开工时 B2-01 还没挂载，测试可直接 `TestClient` 构造临时 app 挂你的 router。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\imports -q
# 手工：preview sample 100 → commit → GET /records/{id} → GET /records/{id}/signal
```

报告写：支持的格式、自动识别规则、3 个样本的 fs/leads/时长、未支持项、为 Samsung 留的接口点。

## 7. 明确不做

Samsung/华为/Apple/SCP-ECG 真实解析、PDF 报告导入、云同步、批量导入、UI（B2-03）、分析（B2-01）、重采样（分析引擎负责）。本批不猜未知格式。
