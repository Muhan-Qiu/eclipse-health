# 报告 · B2-02 导入链路（WFDB / CSV）+ 参数校正
状态：完成

## 交付
- `importers/base.py`：`ImportAdapter` 抽象类、`Detection`/`ImportSource`/`ParseParameters`/`ParsedImport`、单位与导联归一、校正收尾（极性/导联/采样率）。
- `importers/registry.py`：注册与按置信度探测；未知格式 422 `unsupported_format`；`hintFormat` 不匹配时回退自动探测。
- `importers/wfdb_adapter.py`：文件夹 / `.zip` / `.hea`（自动找同名 `.dat`/`.atr`）；优先 MLII；`.atr` 只当参考 R 峰（`hasAnnotations`/数量/解析期标注），不当诊断标签。
- `importers/csv_adapter.py`：自动识别 `, ; \t |`/空白分隔、有无表头、时间/索引列、单导联列；UTF-8(BOM)/GB18030(GBK)/Latin-1；错误带原始行列号；支持显式 `leadColumn`/`timeColumn`/`samplingRate`/`unit`/`polarity`。
- `importers/placeholders.py`：`samsung`/`huawei`/`apple`/`scp-ecg` 注册但 `supported=False`，显式返回「等待真实样本，B3 实现」，无猜测性解析。
- `importers/store.py`：`<data>/imports/<importId>/` 工作区、流式落盘、ZIP 安全解压、meta、commit/delete/24h TTL 清理。
- `importers/api.py`：`POST /imports/preview`、`POST /imports/{id}/commit`、`DELETE /imports/{id}`；入库复用 `db/repositories`、`storage/files`。
- 测试 `backend/tests/imports/`：58 例（WFDB/CSV/提交/TTL/安全）。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend` → **All checks passed**。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\imports` → **58 passed in 3.28s**。
- 回归抽查 `pytest backend/tests/core backend/tests/api` → **80 passed in 1.06s**。
- 实测 100/200/208（preview 与 `.hea` 一致；commit 后逐元素读回）：

  | 样本 | fs | leads | 时长 | 读回误差 |
  |---|---|---|---|---|
  | 100 | 360 | MLII, V5 | 1805.5556s (650000 点) | max abs 1.14e-7 |
  | 200 | 360 | MLII, V1 | 同上 | <1e-6 |
  | 208 | 360 | MLII, V1 | 同上 | <1e-6 |

- 真实服务手工链路（uvicorn 8799 + B2-01 已挂载的 `/api/v1/imports`）：
  preview(100.hea) → commit 201 → `GET /records/{id}` → `GET /records/{id}/signal?lead=MLII`
  返回 2600000 字节、`X-Signal-Fs: 360`，naive 读回 maxdiff 1.14e-7；provenance 为文件/文件名 sha256。

## 自动识别规则
- WFDB：`.hea`、ZIP 解压后含 `.hea`、目录含 `.hea`（1.0）；单独 `.dat` 且同目录有同名 `.hea`（0.9）；多个 `.hea` 返回 422 并列出候选。
- CSV：`.csv/.tsv/.txt`（0.9）；未知扩展名但内容为多行数值表格（0.6）。
- 无法确定导联/采样率/单位时只标 `requires`，不硬猜；提交前强制确认缺失项。

## 未做 / 偏离
- 统一以 **mV** 入库（分析引擎基准）；`parameters.unit` 表示「文件原始单位」，解析时换算到 mV，`metadata.sourceUnit` 记录原单位，`record.unit` 恒为 `mV`。
- CSV 只取单导联列；多导联 CSV 不支持（B2 单导联优先）。WFDB 多导联全部入库，`parameters.lead` 只重命名主导联。
- `source` 仅写 `kind="import"`：WFDB/CSV 无可靠的 manufacturer/model，未臆造。
- `.atr` 位置不入库（仅 count + 解析期参考标注），避免 metadata 超限与体积。
- CSV preview 需要整文件读入内存；200MB 边界未实际压测，靠上限拦截。带引号且字段内含分隔符的表格未支持。
- Python `zipfile` 读取时会把反斜杠归一成 `/`，反斜杠守卫保留但只能单测覆盖。

## 跨区需求（需要别的 Agent 或指挥官处理）
- B2-01 已在 `api/__init__.py` 运行时挂载 `importers.api.router`（已核实，无需再改）；本包只提供 `router`，未动 `app.py` / `api/__init__.py`。
- 分析链路（B2-01）可直接消费导入记录的 `metadata`：`adapterId`、`sourceUnit`、`hasAnnotations`、`annotationCount`。

## 需要指挥官决策
- CSV 无单位标注时，提交是否必须确认 `unit`（当前强制 422 `unit_required`；可改为默认 mV + 警告）。
- 非 360Hz WFDB 提交是否必须显式确认 `samplingRate`（当前强制，符合 G2 参数校正）。
- `.atr` 参考 R 峰是否需要长期保存位置（当前只存数量）。

## 为 Samsung 留的接口点
- `ImportAdapter` 三方法（`detect`/`preview`/`parse`）+ `ImportSource`/`ParsedImport`；厂商适配器只需实现解析并把结果填进 `ParsedImport`，入库/校验/清理全部复用。
- `registry._unsupported_placeholder` 给出统一 422 形状；接样本后把 `supported=True` 并实现 `detect` 即可。

## 建议下一批
- Samsung/华为/Apple/SCP-ECG 真实适配（需样本）；EDF；CSV 多导联；批量导入。
- UI（G2）按 `requires` 渲染校正面板，直接回传 `parameters`。
