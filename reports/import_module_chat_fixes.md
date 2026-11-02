# 模块安装 / ECG AI 导入 / 会话隔离（用户实测修复）

日期：2026-11-02

## 1. 安装模块卡死

**原因**：`/api/v1/marketplace/install` 是同步请求，首次安装会创建 venv 并 `pip install`
依赖，可能持续几分钟；前端 300 秒后断开，界面看起来像卡死。

**修复**：
- 新增异步任务：`POST /marketplace/install?async=1` 立即返回 `jobId`，
  `GET /marketplace/install/{jobId}` 返回 `running/done/error` 与结果/错误。
- 前端改为轮询（1.5 s/次，最长 30 分钟），安装中提示
  「首次安装依赖可能需要几分钟，请保持窗口打开」。
- 同步接口保留，现有 API/测试不受影响。

**验证**：`gpxpy`（含依赖）异步安装 15 秒完成；无依赖的 `activity-calendar` 3 秒完成。

## 2. ECG 也支持 Agent 解析

- Agent 系统提示与 `propose_records` 工具说明加入 ECG 采样规则：
  CSV/HTML/XLSX/JSON 中的 time+voltage、sample+value 等成对列，写入
  `output/ecg.csv` 后提供 `waveform`（file/column/timeColumn/samplingRate/unit/lead）。
- PDF/图片仍不伪造波形，只提取数值。
- 验证：合成 HTML（500 点、500 Hz、time_ms+voltage_mv）交给 DeepSeek Agent，
  产出 **1 条 ecg 候选**，`waveform.file=output/ecg.csv`、`samplingRate=500`、`lead=I`。

## 3. 对话窗口隔离

- 仪表盘建议卡、评分建议、自定义卡片「让助手创建」等入口现在带 `new=1`。
- 助手页检测到 `new=1` 时清空当前会话；用户发送后自动新建会话，
  不再把不同功能的上下文混到同一个会话里。
- 会话列表仍可自由选择、重命名、删除、导出。

## 验证

- `pytest backend/tests/marketplace backend/tests/import_agent backend/tests/imports`：全部通过。
- `ruff check backend`：通过。
- `npm run build`：通过。

## 安装包

390,693,242 字节，SHA-256
`6E00105D8191C93A84AEE43B478771FD9A89C6A515762EF107ABC019C9F39D85`。
