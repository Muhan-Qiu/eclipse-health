# GPX Track · eclipse health 模块

官方 `device-adapter` 模块，适配自 [tkrajina/gpxpy](https://github.com/tkrajina/gpxpy)。
导入 GPX 轨迹并生成摘要（距离、爬升、时长、平均/最大心率）；也可把轨迹导出为 GPX 1.1。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` | 握手与 `gpxpy` 可用性 |
| `summary` | `{path}` → `{summary, record, parser}` |
| `importFile` | 同上并返回轨迹点（≤100000） |
| `exportGpx` | `{points, name?, outputPath?}` → GPX 文本或写入用户选择的 `.gpx` |
| `latestSummary` | 本进程最近一次导入摘要 |
| `deactivate` | 退出 |

## 适配说明

- 有 `gpxpy` 时优先用它解析；缺失时回退到 `adapter.parse_gpx_xml`（stdlib，未压缩 GPX）；
- 心率读取 Garmin `TrackPointExtension` 的 `hr` 字段，缺失不影响距离/时长；
- 距离使用 haversine（球面近似），爬升按相邻点正/负高程差累加；
- `exporters` 贡献点未声明：当前 `schemas/module.schema.json` 的 `exporter.format` 枚举不含 `gpx`，导出只经 RPC 暴露。

## 许可与署名

- 本适配层：GPL-3.0-only；上游 Apache-2.0，全文见 `LICENSES/gpxpy-upstream.txt`；
- 署名与修改说明见 `NOTICE`。
