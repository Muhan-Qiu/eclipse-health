# Samsung Health 导入 + AI 优先导入（用户实测修复）

日期：2026-11-02

## 问题

用户选择 Samsung Health 导出目录
`C:\Users\qiumuhan\Downloads\samsunghealth_8618208229485_20261101221958` 无法导入；
希望未知厂商数据优先交给 AI Agent 解析。

## 根因

1. Samsung 导出是 31 个 CSV（每个 CSV 第一行是 `com.samsung.*,device,version` 元数据，
   第二行才是表头）+ 862 个 JSON 旁路文件。原有 Samsung 适配器只按「波形 CSV」找
   time/voltage 列，完全不适配健康数据；目录内多个 CSV 还会触发
   VendorImportAdapter 的“只能保留一个文件”错误。
2. AI Agent 的 `propose_records` 工具说明没有给出精确记录形状，DeepSeek 反复试错
   `source.kind`/时区/多余字段，12 次工具调用在提交前耗尽，最终 0 条。

## 修复

- 新增 `importers/samsung_health_adapter.py`（`org.eclipsehealth.samsung-health`）：
  - 识别 `samsunghealth_*` 目录 / ZIP / 单个 Samsung CSV；
  - 步数按本地日汇总；心率逐小时；压力、睡眠、运动、体重、呼吸率逐条；
  - 真实导出实测 **360 条**（步数 14、心率 161、压力 149、运动 33、睡眠 1、体重 1、呼吸率 1）；
  - 未映射文件只给警告，不猜测。
- 导入弹窗改为 AI 优先：新增主按钮「用 AI 解析文件」，选中后直接建 Agent 会话；
  「自动识别导入」保留给 ECG/WFDB 等已知格式。
- Agent 改进：
  - 系统提示与 `propose_records` 工具描述加入精确 JSON 模板、`source.kind` 白名单、
    时区要求，并建议先提交 1 条验证；
  - 工具预算 12 → **24** 次，整轮 180 → **300 秒**。
- 健康数据计数新增 压力 / 运动 / 呼吸率 三类。

## 验证

- Samsung 真实导出：API 预览 200 → 提交 201，360 条全部写入；
  UI 用同名 ZIP 走「自动识别导入」：预览显示 360 条、提交成功 360、健康数据页刷新为 360。
- AI 导入：用用户已配置的 DeepSeek 跑 `qa-pulse.csv`，Agent 用脚本解析并提交
  **2 条心率**（62/68 bpm，带文件+行号证据），`accepted=2, rejected=0`。
- `pytest backend/tests/imports backend/tests/import_agent`：全部通过（含新增 Samsung 用例）。
- `ruff check backend`：通过。
- `npm run build`：通过。

## 已知限制

- Samsung 的 HRV/楼层/身高/睡眠分期等文件暂未映射，只提示跳过；睡眠时长与评分已导入。
- AI 解析仍受模型能力与 token 成本影响；Samsung、Apple、小米等已知格式优先走原生适配器。
