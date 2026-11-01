# 报告 · G4 教练（Coach）+ 天气 + 记忆注入 + 助手预设

状态：完成（Agent 在写报告前被暂停，指挥官续跑验收并补记）

## 交付
- 后端 `coach/`：`context.py`（评分/健康数据/运动/记忆聚合，缺失项跳过）、`weather.py`（Open-Meteo 地理编码 + 3 日预报，30 分钟缓存，失败返回 null）、`api.py`（`GET /coach/context`、`GET /coach/weather`）。
- `llm/agent.py`：coach 模式系统提示注入评分、健康摘要、运动、记忆、天气；非 coach 行为不变；记忆 `enabled=false` 不注入。
- 助手页：Coach 模式切换、5 个预设（睡眠/心脏/运动/压力呼吸/体重）、城市与天气卡、`?prompt=` 预填。
- i18n `assistant.coach.*` 中英双语；截图 `G4-coach-*.png`。

## 验证
- 后端：`pytest backend/tests/coach` 全绿；全量 `pytest backend/tests` **710 passed / 11 skipped**。
- ruff：All checks passed。
- `npm run build`：通过。
- 天气：mock 成功/失败/无城市；失败不阻塞教练回答。
- 记忆注入：开/关两种；关闭时系统提示不含记忆内容。
- 助手：教练切换、预设填词、首页 prompt 预填、天气不可用降级；控制台无 error。

## 未做 / 偏离
- 天气只支持中文城市名地理编码；英文城市可后续补。
- 教练建议仍依赖用户已配置的 LLM；无 provider 时助手按既有 503/提示处理。
- 未做自动发送、语音、结构化运动计划卡（当前为对话文本）。

## 跨区需求
- 指挥官已统一挂载 `coach` router；G2/G3 服务用延迟导入，缺失时自动跳过。
