# B3-03 · 报告 PDF / PNG 分享卡 + 模板 + 历史

> 难度：困难 3/4 · 建议思考强度：**high** · 批次：B3 功能
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 约束：**不要新增 Python 依赖**（venv 没有 pip/uv）。用已装的 matplotlib + Pillow + Jinja2 完成。

## 1. 必读

- `docs/DATA_SCHEMA_V1.md`：§9 Report、§6 AnalysisResult、§7 Measurement。
- `docs/UI_COMPONENT_SPEC_V1.md`：§0 原则、§1 令牌、§7 图表。
- `docs/V3_FEATURE_BACKLOG.md`：E1 PDF、E2 模板、E3 PNG 分享卡、E4 脱敏/水印、E6 报告历史。
- `reports/B2-03-report.md`（记录/分析已可用）、`reports/B2-01-report.md`（分析结果形状）。
- 代码：`backend/src/.../storage/files.py`、`db/models.py`（reports 表）、`db/analysis_repo.py`、`api/records.py`、`src/pages/reports.tsx`、`src/lib/api/client.ts`。

## 2. 技术路线（硬约束）

- PDF：`matplotlib.backends.backend_pdf.PdfPages`，A4 纵向，多页；矢量波形/文字。
- PNG 分享卡：matplotlib `Figure` 保存 1080×1350（或 1080×1080）PNG；也可 Pillow 拼接。
- 中文字体：`C:\Windows\Fonts\msyh.ttc`（微软雅黑），回退 `simhei.ttf`/`simsun.ttc`；设置 `axes.unicode_minus=False`。字体缺失时明确报错，不输出方块。
- **禁止** WeasyPrint / wkhtmltopdf / 浏览器打印 / 新增依赖。报告生成必须在无网络、无浏览器的后端完成。
- 现有 `storage/files.py` 的原子写 + sha256 复用；文件放 `data/reports/<id>.<ext>`。

## 3. 你必须交付

### 后端

1. **报告生成器**
   - `backend/src/eclipse_health_backend/reports/`：`content.py`（从记录/分析组装报告数据）、`pdf.py`、`share_card.py`、`service.py`、`fonts.py`。
   - 内容：应用名/生成时间/报告 ID、记录日期/设备/导联/采样率/时长、波形（默认前 12 秒，含 R 峰）、摘要指标（HR/RMSSD/SDNN/N/SVEB/VEB/F/质量）、测量表、警告、模型卡摘要（Cardia 2.0 / 适用单导联 360Hz / MIT-BIH）、免责声明（研究/教育用途，不构成医疗诊断）。
   - 模板：
     - `simple`：1 页，波形 + 4 个关键指标 + 免责声明。
     - `detailed`：2 页，加全部测量、分类比例、质量/警告。
     - `doctor`：2 页，加参数/模型版本/技术细节与完整测量表（仍保留非诊断声明）。
   - 分享卡 `png`：关键指标 + 小波形 + 日期 + 水印；适合微信/小红书；不含姓名/备注。
   - 脱敏 `redact=true`（默认）：不显示成员姓名、notes、原始文件名；只显示「匿名」；水印「非诊断 · 仅供健康参考」。
2. **存储与 API**
   - `db/report_repo.py`：复用现有 `reports` 表；存 `id, recordId, analysisId, format, template, path, sha256, size, createdAt, redacted`。
   - `POST /records/{id}/reports`：body `{format:"pdf"|"png", template:"simple"|"detailed"|"doctor", redact?:true}` → 201 `{reportId, format, template, fileName, size, sha256, createdAt, downloadUrl}`。
   - `GET /records/{id}/reports`：历史列表。
   - `GET /reports/{id}`：元数据；`GET /reports/{id}/download`：文件（正确 Content-Type/Disposition）。
   - `DELETE /reports/{id}`：删记录 + 文件。
   - 记录无已完成分析时 409 `analysis_required`；未知模板/格式 422。
3. **测试**
   - 用 MIT-BIH 100 的已完成分析（可构造 fixture）生成 3 种模板 PDF 与 PNG：文件头 `%PDF`、页数 ≥1、大小 >20KB、PNG 尺寸正确、字体不缺失。
   - 脱敏：内容模型里不含姓名/notes；不脱敏时包含。
   - 下载/删除/历史/无分析 409。
   - 不联网；临时 `EH_DATA_DIR`。

### 前端

4. **报告页**（`src/pages/reports.tsx` + `src/features/reports/**`）
   - 记录选择（最近记录/搜索）；格式（PDF/PNG）、模板（简洁/详细/医生）、脱敏开关；生成按钮 + 进度/错误。
   - 报告历史列表：时间、记录、格式/模板、大小、下载、删除；空状态。
   - 下载走 `downloadUrl`；Tauri 下可用浏览器下载或后续接文件保存（本批不接 Tauri 插件）。
   - 生成后可在新标签/系统查看器打开 PDF；PNG 直接下载。
5. **i18n / 边界**
   - 用 feature-local bundle：`src/features/reports/i18n.ts`，在模块加载时 `i18n.addResourceBundle("zh-CN", "translation", zh, true, true)`（en-US 同）；**不要改** `src/lib/i18n/*`（B3-02 所有）。
   - 只 import 共享 `apiFetch`/类型，不改 `src/lib/api/*`。
   - 截图：`reports/screenshots/B3-03-reports-light.png`、`B3-03-report-preview.png`（若 PDF 预览不可截，截报告页 + PNG 卡片）。

## 4. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/reports/**
backend/src/eclipse_health_backend/api/reports.py
backend/src/eclipse_health_backend/db/report_repo.py
backend/tests/reports/**
src/pages/reports.tsx
src/features/reports/**
reports/screenshots/B3-03-*.png
```

不要动：`src/lib/api/**`、`src/lib/i18n/**`、`src/App.tsx`、`src/pages/{trends,assistant}.tsx`、`src/features/{trends,assistant}/**`、`src-tauri/**`、`backend/api/{analyses,records,trends,assistant}.py`、`modules/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 5. 与 B3-02 的契约

- 路由 `/reports` 已存在，你只替换页面组件；不要改 `App.tsx`。
- `apiFetch`、`useRecords` 等共享接口只读；需要新接口时在 `src/features/reports/api.ts` 里写 fetch。
- 不要改共享 i18n 文件。

## 6. 验收命令

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\reports -q
npm run build
# 启动后端 + dev，选一条有分析的记录，生成 3 种模板 + PNG，下载/删除
```

报告写：PDF/PNG 实际尺寸/页数/大小、字体方案、脱敏验证、模板差异、截图路径、未做项。

## 7. 明确不做

打印预览（E5 暂不加入）、报告邮件/云分享、电子签名、FHIR、Tauri 文件保存插件、趋势/LLM、12 导联报告、波形 PNG 单独导出（B7，B4）。
