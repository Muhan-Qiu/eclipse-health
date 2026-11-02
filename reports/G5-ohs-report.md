# 报告 · G5 可选 Open Health Sync 连接器
状态：完成（真实 OHS 未联调，按要求不安装 Docker）

## 交付
- `backend/src/eclipse_health_backend/ohs/client.py`：httpx 客户端；仅允许 http/https，默认 `http://127.0.0.1:8080`；Bearer 认证；10s 超时；`GET /v1/users`、`GET /v1/users/{id}/daily?from=&to=`。
- `ohs/store.py`：`<EH_DATA_DIR>/ohs.json`；token 用 Windows DPAPI（`win32crypt`）加密后 base64 落盘；DPAPI 不可用/加密失败明确报错并拒绝明文；读取接口永不返回 token。
- `ohs/sync.py`：最近 30 天 daily → `org.eclipsehealth.health.*`；步数、静息心率、睡眠时长、体重、血压；`externalId=ohs:<user>:<date>:<kind>` 去重；逐条提交，失败只计数不回滚。
- `ohs/api.py`：`GET/PUT /api/v1/ohs/settings`、`POST /api/v1/ohs/test`、`POST /api/v1/ohs/sync`；router 自带 `/ohs` 前缀。
- `src/pages/settings.tsx`：新增「Open Health Sync（可选）」卡片（外部访问旁）；地址/token/user id、保存、测试、同步、最近结果与 warnings；未配置隐藏同步按钮；启动不连接 OHS。
- `src/lib/i18n/{zh-CN,en-US}.ts`：新增 `settings.ohs.*`。
- `docs/INTEGRATIONS/OPEN_HEALTH_SYNC.md`：启动/建 token/配置/字段映射/限制/AGPL；`HEALTH_DATA_IMPORT.md` 末尾加一行链接。
- 截图：`reports/screenshots/G5-ohs-light.png`、`G5-ohs-dark.png`。

## 配置与加密
- 首保存必须提供 token（`ohs_token_required` 422）；后续留空沿用旧密文。
- 文件含 `baseUrl`、`token:{scheme:"dpapi",data}`、`userId`、`lastSync`；无健康数据。
- 解密失败 → `ohs_token_unreadable`；DPAPI 缺失 → `ohs_dpapi_unavailable`，不会写明文。

## 测试连接
- 200：返回 `authType`（多用户/单用户 tenant）、`userCount`、`users[{id,name}]`。
- 401 → `ohs_auth_failed`（HTTP 401）；403 → 视为只读 user token，成功并警告需手填 user id。
- 网络/超时 → `ohs_unreachable` / `ohs_timeout`（502）；404 → `ohs_endpoint_missing`。

## 同步字段与去重
- daily 响应兼容数组及 `{daily|days|items|data|...}` 包装。
- 识别别名：`steps/stepCount/totalSteps`；`restingHeartRate/rhr`；`sleepMinutes/sleepHours/sleepSeconds`；`weightKg/weightLbs`；`bloodPressure{systolic,diastolic}` 或平铺。
- 单位：步数 `count`；心率 `count/min`；睡眠 `durationSec` + `value="asleep"`；体重 `kg`；血压 `mm[Hg]`（kPa 换算）。
- 不确定单位/字段只写 warnings 并跳过：`ohs_unknown_daily_fields`、`ohs_sleep_unit_unknown`、`ohs_blood_pressure_incomplete`、`ohs_bp_unit_unknown`。
- 返回 `{created,skipped,failed,warnings,userId,days}`；重复同步幂等（第二次全部 skipped）。

## 验证（真实输出）
- `backend\.venv\Scripts\python.exe -m ruff check backend` → `All checks passed!`
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\ohs -q` → `37 passed in 0.60s`（37 dots，0 fail）
- `npm run build` → `✓ built in 3.43s`，2860 modules；仅有既存 >500kB chunk 警告，无错误。
- UI：临时以 18765 端口挂载 ohs router + Vite 1422 截图，控制台无业务 error；亮/暗两图均正常渲染。

## 未做 / 偏离
- 未启动真实 OHS（按要求不装 Docker），所有 HTTP 行为用 `httpx.MockTransport` 验证。
- 仓库内没有 OHS `docs/api.md`/`docs/mcp.md`，daily 字段名按公开接口摘要与容错别名实现；真实字段差异会以 warnings 暴露，不猜测写入。
- 未拉取 `/samples`、`/sleep`、`/workouts` 原始明细，只做 daily 汇总。
- `/api/v1/ohs` 尚未真正挂载：按要求未改 `api/__init__.py`；截图时用临时进程内挂载验证。

## 跨区需求
- 指挥官挂载：在 `backend/src/eclipse_health_backend/api/__init__.py` 增加
  `from ..ohs.api import router as ohs_router` 并 `api_router.include_router(ohs_router)`（router 已自带 `/ohs`）。
- 挂载后设置页无需改动；未挂载时 UI 显示「后端未提供 OHS 接口」降级提示。

## 需要指挥官决策
- OHS 真实版本/镜像与 daily JSON 字段需一次实机核对；若字段不同，只需扩展 `sync.py` 别名表。
- 是否允许 UI 未来增加「同步天数」选择（后端已支持 1–90，UI 固定 30）。

## 建议下一批
- 用真实 OHS 实例跑一次 `/v1/users` + daily，记录字段与警告；必要时补充 samples/sleep/workouts 映射。
- 若要双向写入或 MCP 代理，单独开任务（本期明确不做）。
