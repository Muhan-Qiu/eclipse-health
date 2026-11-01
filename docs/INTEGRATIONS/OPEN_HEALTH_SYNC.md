# 可选连接：Open Health Sync（OHS）

> 状态：已实现连接、测试与日汇总同步（G5，2026-10-31）。
> OHS 是**独立第三方服务**（Go + Postgres + Docker，AGPL-3.0）；本项目只通过 HTTP 读取数据，
> 不安装、不打包、不复制其代码。普通用户无需 Docker，内置 Apple / 小米导入照常可用。

## 1. OHS 快速启动（示例）

OHS 的官方镜像名、环境变量与控制台入口以其发布文档为准；下面是本地单机的最小结构，
**部署前请把占位符替换为 OHS 官方发布说明中的实际值**：

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ohs
      POSTGRES_USER: ohs
      POSTGRES_PASSWORD: change-me
    volumes:
      - ohs_pgdata:/var/lib/postgresql/data
  ohs:
    image: <OHS 官方镜像>        # 按 OHS Release 填写，不要使用来源不明的镜像
    environment:
      DATABASE_URL: postgres://ohs:change-me@postgres:5432/ohs?sslmode=disable
      # 其他必填项以 OHS 发布说明为准
    ports:
      - "8080:8080"
    depends_on:
      - postgres
volumes:
  ohs_pgdata:
```

启动后 REST base 默认是 `http://127.0.0.1:8080`。验证：

```bash
curl -s http://127.0.0.1:8080/v1/users -H "Authorization: Bearer <token>"
```

## 2. 创建 token

- **tenant key**：可访问整个 tenant，通常能列出 `/v1/users` 的所有用户。
- **user token**：只读、最长 30 天，适合只同步一个用户；部分部署下不能列出用户，
  此时需要在本应用里手填 `user id`。

在 OHS 控制台或 CLI 中创建 token（具体命令以 OHS 版本为准），权限只需读取。
本应用不会把 token 写入日志或界面，也不会代用户申请 token。

## 3. 在本应用配置

设置页 →「Open Health Sync（可选）」：

1. 填 **OHS 地址**（仅 `http://` / `https://`，默认 `http://127.0.0.1:8080`）。
2. 填 **Token**（密码框）。
3. 可选填 **OHS user id**；tenant key 下留空会自动取 `/v1/users` 的第一个用户。
4. 保存 →「测试连接」 →「同步最近 30 天」。

只有点击测试/同步才会访问 OHS，启动时不自动连接。未保存配置时不显示同步按钮。

**Token 存储**：`<EH_DATA_DIR>/ohs.json`，token 使用 Windows DPAPI 加密（当前用户范围）。
DPAPI 不可用时保存会明确失败，绝不落明文。文件里只有连接参数和最近一次同步摘要。

## 4. 同步范围与字段映射

- 时间范围：最近 30 天（接口支持 1–90 天，UI 固定 30）。
- 接口：`GET /v1/users/{id}/daily?from=YYYY-MM-DD&to=YYYY-MM-DD`。
- 响应可以是数组，也可以是 `{"daily": [...]}` / `{"data": {"days": [...]}}` 等包装。

写入本应用的健康记录沿用 B4 的 `org.eclipsehealth.health.*` 格式：

| OHS 字段（可识别别名） | 记录类型 | 单位 / payload |
|---|---|---|
| `steps` / `stepCount` / `totalSteps` | `...health.steps` | `count`，整数 |
| `restingHeartRate` / `restingHeartRateBpm` / `rhr` | `...health.heart-rate` | `count/min` |
| `sleepMinutes` / `sleepDurationMinutes` / `sleepHours` / `sleepSeconds` | `...health.sleep` | `durationSec`，`value="asleep"` |
| `weightKg` / `bodyMassKg` / `weightLbs`（换算为 kg） | `...health.body-mass` | `kg` |
| `bloodPressure: {systolic, diastolic}`，或 `systolic`/`diastolic` 平铺 | `...health.blood-pressure` | `mm[Hg]`，kPa 自动换算 |

字段名可能随 OHS 版本变化。本应用只转换**能明确识别**的字段：

- 未知字段或整条无法识别 → `warnings` 中记录 `ohs_unknown_daily_fields`，不猜测；
- 睡眠没有明确单位 → `ohs_sleep_unit_unknown`，跳过睡眠；
- 血压只有一侧或单位未知 → `ohs_blood_pressure_incomplete` / `ohs_bp_unit_unknown`，跳过血压；
- 单条写入失败只计入 `failed`，不撤销已经写入的记录。

**去重**：`externalId = ohs:<user_id>:<YYYY-MM-DD>:<kind>`，日期与类型相同即跳过。
OHS 不返回稳定的记录 id 时以日期为准，重复同步是幂等的。

返回结构：`{created, skipped, failed, warnings[]}`，并额外带 `userId`、`days`。

## 5. 限制与已知风险

- **OHS 未运行**：测试/同步返回 502 `ohs_unreachable` / `ohs_timeout`；token 错误返回 401。
- **字段变化**：OHS 升级后 daily 字段可能改名；本应用会通过 warnings 暴露，不会静默写错。
- **user token**：可能无法列出用户，需要手填 `user id`；权限不足返回 403。
- **仅日汇总**：不拉取逐条 samples、睡眠分段、运动轨迹或 ECG；不做双向写入。
- **不管理 Docker/Postgres**：不提供安装、升级、容器控制；OHS 的可用性由用户负责。
- **网络范围**：允许 `http://` 是为了本机/局域网自建；不要把 OHS 暴露到公网后仍使用明文 HTTP。

## 6. 许可证与合规

OHS 采用 **AGPL-3.0**。本项目仅通过公开 HTTP 接口调用，不复制、不修改、不打包其代码，
因此不产生 OHS 代码的衍生分发。健康数据只在本机与用户指定的 OHS 之间传输，
不发送遥测，不经过本项目服务器。

## 7. 相关代码

- `backend/src/eclipse_health_backend/ohs/client.py`：URL 校验、认证、`/v1/users` 与 daily 读取。
- `backend/src/eclipse_health_backend/ohs/store.py`：DPAPI 加密设置存储。
- `backend/src/eclipse_health_backend/ohs/sync.py`：字段映射、去重、失败计数。
- `backend/src/eclipse_health_backend/ohs/api.py`：`/api/v1/ohs/*` 路由。
- `backend/tests/ohs/`：mock httpx 的单元与路由测试。
