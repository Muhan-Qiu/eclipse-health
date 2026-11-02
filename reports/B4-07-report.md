# 报告 · B4-07 健康档案 + 手动指标 + 通知
状态：完成

## 交付
- 后端 `metrics/`（models/service/api）：`POST /api/v1/metrics`、`GET /api/v1/metrics?kind=&from=&to=&limit=&offset=`、`PATCH/DELETE /api/v1/metrics/{id}`；软删除。
- 存储复用 `records`：`recordType="org.eclipsehealth.metric"`、`payload={kind,values}`、`moduleId=null`、无信号；`source.kind="manual"`。
- 单位/硬边界：血压 mmHg（收缩 50–300 / 舒张 20–200）、体重 kg（2–500）、血氧 %（50–100）、血糖 mmol/L（0.5–50）；临床异常（如 190/100、SpO₂ 96）只返回 `warnings`，不拒绝写入。
- 健康档案：复用 `GET/PATCH /members/{id}`，出生年/性别/身高/体重/病史/用药/备注均可编辑与清空；上限沿用模型（32 项、单项 64 字、备注 4000 字）并补测试。
- 前端 `/profile`：基本信息表单（校验/保存/放弃）、四类快捷录入（共享测量时间与备注）、历史列表（类型 + 7/30/90 天过滤、两段式删除）、隐私说明与设置页链接；左侧导航新增「健康档案」。
- 通知 watcher：15s 轮询最近 20 条记录，仅在窗口可见时检测 `queued/running → completed`；Tauri 通知插件 → 浏览器 `Notification` → 静默降级；文案含记录日期与「非诊断」，默认不含心率数值。
- feature-local i18n `src/features/profile/i18n.ts`（zh-CN / en-US），未改共享 i18n；`nav.profile` 随 bundle 注册。

## 验证
- `backend\.venv\Scripts\python.exe -m ruff check backend`：All checks passed。
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\metrics -q`：**16 passed in 0.53s**（四类 CRUD、时间/类型/分页、软删除、硬边界、仅警告、recordType 过滤、档案上限、非法时区）。
- 相邻回归：`pytest backend/tests/{api,trends}` 通过（56 passed in 1.87s）。
- `npm run build`：通过，2.44s，2831 modules。
- 手工（独立后端 8766 + dev 1437）：保存档案成功；录入四类指标成功；190/100 出现「收缩压偏高 · 舒张压偏高」toast 与历史徽标；类型过滤只留体重 1 条；时间过滤可用。
- 通知：生产构建（vite preview）中拦截 `/records`，首轮 running、次轮 completed，浏览器通知构造被调用，标题「分析完成」，正文「记录 2026年10月30日 09:15 的分析已完成。仅为数据解读，非诊断。」
- 控制台：profile 页 0 error；截图 `reports/screenshots/B4-07-light.png`、`B4-07-dark.png`（1600×1500，亮/暗各一张）。

## 未做 / 偏离
- 未做指标趋势图（B4 可选）。
- 指标编辑 UI 未做（PATCH 已实现并有测试，历史列表只提供删除）。
- 删除确认用两段式按钮，未用弹窗组件。
- Tauri 原生通知只在代码路径上接通，未在桌面壳内实测；浏览器降级路径已自动化验证。
- 前端仅对 `values` 做基础数字校验，范围/单位最终以后端 422 为准。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 设置页缺少通知开关：B4-04 的 `/settings` 只有 closeToTray/splash/telemetry/locale。当前 watcher 读取 `localStorage["eh-notify-analysis-complete"]`（默认开启），需要设置页补开关或扩展设置 API。
- `api/__init__.py` 已由 B4-04 预挂 `metrics.api.router`，无需改动。
- 记录页固定查询 `recordType="org.eclipsehealth.ecg"`，手动指标不会混入；若要做统一时间线需另开任务。

## 需要指挥官决策
- 通知开关放设置页（建议）还是档案页。
- 是否把四类手动指标接入趋势图（B4 可选项）。

## 建议下一批
- 手动指标趋势与区间统计；历史条目编辑（复用已就绪的 PATCH）。
