# 报告 · B3-03 报告 PDF / PNG 分享卡 + 模板 + 历史

状态：完成（路由接线需共享层一行改动，见「跨区需求」）

## 交付

- 后端 `reports/`：`content.py` 组装记录/信号/分析；`pdf.py` 三模板 A4 矢量多页；`share_card.py` 1080×1350 PNG；`fonts.py` 注册微软雅黑并校验中文字形；`service.py` 校验→渲染→原子写→落库；`errors.py`。
- 模板：`simple` 1 页（波形 + 4 指标 + 声明）；`detailed` 2 页（全部测量、分类比例、质量/警告、模型卡）；`doctor` 2 页（完整测量表 + 参数/模型版本/预处理/引擎 + 局限）。分享卡固定版式，始终不含姓名/备注。
- 脱敏：默认开启；内容模型把成员名替换为「匿名」、notes 置空，只显示文件名哈希；PDF 加「非诊断 · 仅供健康参考」水印。关闭后显示成员姓名与备注。
- `db/report_repo.py`：复用 `reports` 表，存 id/recordId/analysisId/format/template/path/sha256/size/createdAt/redacted。
- API：`POST /records/{id}/reports`（201）、`GET /records/{id}/reports`、`GET /reports/{id}`、`GET /reports/{id}/download`（sha256 校验 + 正确 Content-Type/Disposition）、`DELETE /reports/{id}`（记录+文件）；无完成分析 409 `analysis_required`，未知格式/模板 422。
- 前端：`src/pages/reports.tsx` + `src/features/reports/**`。记录选择（最近 50 条、日期/设备/标签搜索、分析状态徽标）、PDF/PNG 切换、模板选择、脱敏开关、生成进度/错误、成功卡（下载/打开 PDF/PNG 预览）、历史（时间/格式/模板/大小/脱敏/下载/打开/删除确认）、空/加载/错误状态；feature-local zh-CN/en-US bundle，未改共享 i18n/API。

## 验证

- `backend\.venv\Scripts\python.exe -m ruff check`（本任务文件）→ All checks passed。
- `pytest backend/tests/reports -q` → 18 passed；`pytest backend/tests/reports backend/tests/api -q` → 52 passed。
- `npm run build` → pass（tsc + vite 1.09s，1,175 kB / gzip 365 kB，仅沿用的 >500 kB 提示）。
- 实测（合成/MIT-BIH 波形，临时 `EH_DATA_DIR`）：simple 1 页 105,615 B；detailed 2 页 126,027 B；doctor 2 页 145,841 B；PNG 1080×1350 / 155,735 B；均 `%PDF`/PNG 头、>20KB、sha256 下载一致。
- 字体：`Microsoft YaHei`，`C:/Windows/Fonts/msyh.ttc`；`font_supports_cjk("心")` 通过；缺字体抛 `report_font_missing`，不输出方块。
- 脱敏：内容快照中无「本人」/备注/原始文件名；未脱敏时包含；分享卡与 PNG 始终匿名。
- 空波形：无信号但有完成分析时仍生成 PDF（绘制「无波形数据」）。
- UI（真实后端 + MIT-BIH 100）：1440×1100 亮/暗、1080×700 无横向溢出（doc/body/main 均为 0）；生成 PNG 后图片自然尺寸 1080×1350；删除确认弹窗正常；console 无 error（favicon 404 已在预览入口修复）。
- 截图：`reports/screenshots/B3-03-reports-light.png`、`B3-03-reports-dark.png`、`B3-03-report-preview.png`、`B3-03-delete-dialog.png`。

## 未做 / 偏离

- 未使用 Jinja2/Pillow 参与渲染（matplotlib 直接生成 PDF/PNG，Pillow 仅测试校验）；未新增依赖。
- 生成是同步请求（本地单用户，约 0.3–0.6s/份），未做后台任务/进度百分比。
- PNG 时模板选择禁用；后端仍接受 template 并记录。
- 前端记录选择只取最近 50 条（搜索在这 50 条内）；更多分页留 B4。
- 未接 Tauri 文件保存插件、打印预览、邮件/云分享、电子签名、FHIR、12 导联报告、独立波形 PNG。
- 截图使用 `src/features/reports/preview.html` 独立入口（同 AppShell/Providers，未进入生产路由），因 `App.tsx` 不在本任务所有权内。

## 跨区需求（需要别的 Agent 或指挥官处理）

- **路由接线**：`src/App.tsx` 仍从 `@/pages/coming-soon` 导入 `ReportsPage`；需改为 `import { ReportsPage } from "@/pages/reports"`（一行）。B3-04 的 `AssistantPage` 同样未接线。
- `api/__init__.py` 增加了 `_mount_reports_router`（无其他挂载点；B3-02 的 trends、B3-04 的 assistant 也在此文件，当前共存）。
- `backend/pyproject.toml` 未声明 matplotlib/Pillow/Jinja2（venv 已装）；打包时需补依赖声明。
- 全量 `ruff check backend` 仍被其他 B3 Agent 文件阻断（`db/assistant_repo.py`、`llm/tools.py`、`tests/trends`），本批未动。

## 需要指挥官决策

- 是否保留 `src/features/reports/preview.html|tsx` 作为开发预览入口（不影响生产构建），或在接线后删除。
- 报告页是否对 `/reports` 做 `React.lazy` 分包（首包已 1.17MB，共享层决策）。

## 建议下一批

- 接线 `App.tsx` 后回归 `/reports`；B4 增加批量生成、报告模板自定义（字号/配色）、Tauri 保存/打印与 PDF 预览缩略图。
