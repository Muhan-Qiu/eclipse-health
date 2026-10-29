# B4-07 · 健康档案 + 手动指标 + 通知

> 难度：中等偏难 3/4 · 建议思考强度：**high** · 批次：B4 收口（Wave 2）
> 你是四个并行 Agent 之一。先读 `prompts/00-COMMON.md`。
> 目标：补齐 I3 健康档案、I2 手动指标、H1 通知；不碰波形/报告/模块。

## 1. 必读

- `docs/DATA_SCHEMA_V1.md`：§3 Member、§4 HealthRecord、§10 模块自定义记录、§15 隐私。
- `docs/V3_FEATURE_BACKLOG.md`：I2、I3、H1。
- `docs/INTERNAL_API_V1.md`：§0/§1。
- `reports/B1-01-report.md`（Member/Record API）、`reports/B4-04-report.md`（设置页；如未完成则按契约）。
- 代码：`backend/src/.../domain/models.py`、`db/repositories.py`、`api/members.py`、`api/records.py`、`src/App.tsx`、`src/lib/nav.ts`、`src/pages/profile.tsx`（可能不存在）。

## 2. 你必须交付

### 后端

1. **健康档案**
   - 复用 `GET/PATCH /members/{id}`；确保 `birthYear/sex/heightCm/weightKg/conditions/medications/notes` 可编辑；不做完整生日。
   - 校验上限（conditions/medications ≤32、notes ≤4000）；不记录 PII 到日志。
2. **手动指标**
   - `backend/src/.../metrics/` + `api/metrics.py`：
     - `POST /metrics`：`{kind:"blood_pressure"|"weight"|"spo2"|"glucose", measuredAt, values:{...}, notes?}`；
     - `GET /metrics?kind=&from=&to=&limit=&offset=`；
     - `PATCH /metrics/{id}`、`DELETE /metrics/{id}`（软删除）。
   - 存储：写入 `records`，`recordType="org.eclipsehealth.metric"`，`payload` 存 kind/values；无信号、`moduleId=null`；标签/备注沿用记录。
   - 单位：血压 mmHg、体重 kg、血氧 %、血糖 mmol/L（可扩展）；校验范围，异常值只警告不拒绝。
   - 路由：提供 `metrics/api.py` 的 `router`；B4-04 负责在 `api/__init__.py` 挂载（若它未完成，你可在测试中用临时 app 挂载，不要改 `api/__init__.py`）。
3. **测试**：档案更新、四类指标 CRUD、时间过滤、软删除、单位/范围、记录列表按 recordType 过滤。

### 前端

4. **档案页**（`src/pages/profile.tsx` + `src/features/profile/**`）
   - 基本信息：出生年、性别、身高、体重、病史、用药、备注；保存/取消/校验。
   - 手动指标：四类快捷录入卡（血压双值、体重、血氧、血糖）+ 历史列表（时间/值/备注/删除）；按时间过滤。
   - 隐私说明：仅本机、可随时清除；链接到设置页隐私中心。
   - 路由 `/profile` + 左侧导航（你拥有 `src/App.tsx`、`src/lib/nav.ts`）。
5. **通知**
   - 分析完成通知：轻量 watcher（轮询最近记录状态，running→completed 时通知一次），只在窗口可见/托盘时提示。
   - 优先 Tauri 通知插件（`@tauri-apps/plugin-notification`，若 B4-01 已装）；不可用时用浏览器 `Notification` API；再不可用则静默并在报告说明。
   - 设置页开关由 B4-04 提供；你只读 localStorage/设置 API，不修改 `src/pages/settings.tsx`。
   - 通知文案含记录日期与「非诊断」；不包含心率等敏感数值（或可配置，默认不含）。
6. **i18n/边界**：feature-local bundle（`src/features/profile/i18n.ts`），不改共享 i18n；截图 `reports/screenshots/B4-07-*.png`。

## 3. 文件所有权（只能改这些）

```
backend/src/eclipse_health_backend/metrics/**
backend/src/eclipse_health_backend/api/metrics.py
backend/tests/metrics/**
src/pages/profile.tsx
src/features/profile/**
src/App.tsx                 # 仅加 /profile 路由与 watcher
src/lib/nav.ts              # 仅加档案入口
reports/screenshots/B4-07-*.png
```

只读：`api/members.py`、`api/records.py`、`db/repositories.py`、`src/lib/api/**`、`src/pages/settings.tsx`。
不要动：`api/__init__.py`（B4-04）、`src/lib/i18n/**`、`src/pages/{record-detail,modules,...}.tsx`、`src/features/{waveform,modules,export,privacy}/**`、`src-tauri/**`、`docs/**`、`prompts/**`、`uploads/**`。

## 4. 契约

- B4-04 挂载 `metrics.api.router`；若它未完成，报告注明，指挥官验收时接线。
- 通知插件由 B4-01 安装；你动态 import + 失败降级。
- 不改 `RecordSummary` 形状；手动指标用 `recordType` 过滤。

## 5. 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\metrics -q
npm run build
# 手工：编辑档案 → 录入四类指标 → 记录列表按类型过滤 → 分析完成后收到通知
```

报告写：API、指标单位/范围、通知降级路径、截图、未做项。

## 6. 明确不做

完整病历、FHIR/Apple Health 导入（I4）、多成员切换（D7 架构预留）、指标趋势图（B4 可选）、用药提醒、云同步。
