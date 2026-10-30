# Apple Health 心电图（ECG）格式要点

来源：Apple HealthKit 文档
<https://developer.apple.com/documentation/healthkit/hkelectrocardiogram>、
采样频率 <https://developer.apple.com/documentation/healthkit/hkelectrocardiogram/samplingfrequency>、
电压单位 <https://developer.apple.com/documentation/healthkit/hkelectrocardiogram/voltagemeasurement/quantity(for:)>；
Apple 支持「共享健康数据」<https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios>。

**重要：本任务没有找到可再分发的公开真实导出样例。** 下列 CSV 布局中标注「推断」的部分，
依据是 HealthKit 字段语义与社区工具对该目录的引用，未经真实文件验证；适配器一律先按
`experimental` 处理，等用户提供导出包后再升级为 verified。

## 导出包结构（推断，依据：社区工具 / 导出 zip 常见布局）

```
export.zip
└─ apple_health_export/
   ├─ export.xml              # 主数据（HKQuantitySample 等）
   ├─ export_cda.xml          # CDA 格式副本
   ├─ electrocardiograms/     # 每次 ECG 一个 CSV
   │  └─ <记录标识>.csv
   ├─ workout-routes/         # GPX
   └─ electrocardiograms.csv  # 有的导出/第三方工具会合并成一个文件
```

- 真实导出是否包含 `electrocardiograms/` 与文件名规则未验证；适配器应同时接受：
  单个 `*.csv`、导出 zip、以及目录。
- 若给的是 zip，解压后按文件名/目录名探测，不要依赖固定 UUID。

## 波形数据（HealthKit 语义）

- 单导联 **Lead I**（Apple Watch）。
- 采样频率：`HKElectrocardiogram.samplingFrequency`，单位 **Hz**；Apple Watch 记录通常为 **512 Hz**
  （该值是实现细节，文档未固定，适配器应读取字段，读不到再默认 512 并记 `requires`）。
- 电压：`VoltageMeasurement.quantity(for:)` 返回 **volt** 单位的 `HKQuantity`。
- 典型记录时长 30 s；也可能更短（设备/电量原因），不要硬编码样本数。
- 元数据：classification（`sinusRhythm` / `atrialFibrillation` / `highHeartRate` / `lowHeartRate` /
  `inconclusive` / `unreadable`）、平均心率、症状、算法版本、设备信息。

## CSV 布局（推断）

```
time,voltage
0.000000,0.000145
0.001953,-0.000121
...
```

- 第一行表头 `time,voltage`（也可能大写或带 BOM）。
- `time` 为从 0 开始的秒数，步长 1/512 ≈ 0.001953125 s。
- `voltage` 单位按 HealthKit 为 **V**；但社区导出/第三方 App 常写成 **mV**。
  适配器应做量级判断：`median(|voltage|) < 0.02` 视为 V 并 ×1000；在 0.1–5 之间视为 mV；
  两者都不像时要求用户确认，不要默认相乘。
- 有的文件在表头前有 1–3 行元数据（设备、日期、classification），需跳过非数字行。
- 时区：时间列是相对秒数，无时区；采集绝对时间只能来自文件名或 `export.xml`，
  需要时从 `export.xml` 的 `HKDataTypeIdentifierElectrocardiogram` 记录里取 `startDate`（含时区）。
- 编码：UTF-8（可能带 BOM）、CRLF；用 `utf-8-sig` 读、`csv` 模块解析，不要按字节切。

## 已知坑

- 单导联：入库时导联名固定为 `Lead I` / `I`，不要生成 12 导联。
- 采样率必须来自数据步长或 metadata；步长与声称的 512 Hz 不一致时以数据为准并记录 `requires`。
- 患者姓名/生日可能出现在 `export.xml`，入库前必须脱敏（只存哈希），CSV 本身一般不含身份信息。
- 同一次 ECG 可能在 `export.xml` 有元数据、CSV 有波形，需要按时间/设备关联；本适配器只负责波形。
- 不要按「文件里一定有 30 s」假设；Apple Watch 的 30 s 是产品约束，不是格式约束。

## 样本能力

| 样本 | 能力 | 限制 |
|---|---|---|
| `backend/tests/fixtures/imports/apple/electrocardiograms.csv` | **合成**夹具：`time,voltage`、512 Hz、10 s、伏特、Lead I | 非真实 Apple 导出；仅验证解析路径 |
| 真实导出 | **未找到** | 需用户提供，见 `uploads/samples/index.json` 的 `missing.apple` |

给 B4-03 的建议：先按上述 CSV 实现 `detect`（表头 + 两列数字 + 512 Hz 步长）与量级判单位，
把真实导出缺失写进 preview 的 `requires`，标 `experimental`；用户提供样例后再加回归测试。
