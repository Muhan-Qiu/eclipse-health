# Samsung Health 心电图（ECG）格式要点

来源：Samsung Developers Health <https://developer.samsung.com/health>（Health Data / Sensor /
Accessory / Research 各套 SDK 总览）；Samsung Health Monitor 的 ECG 功能文档只描述产品能力。

**结论：未找到公开、可再分发的 ECG 原始波形导出格式，也没有公开样本。需要用户提供。**

## 已知事实（有来源）

- Galaxy Watch 的 ECG 由 **Samsung Health Monitor** 应用采集，记录为单导联、约 30 s（产品层面）。
- 第三方接入走 **Samsung Privileged Health SDK**（合作方需申请权限），提供的是设备端传感器 API，
  不是文件格式；没有公开的 CSV/JSON 导出规范。
- Samsung Health 的「个人数据下载 / 导出」面向 Health 数据（步数、心率等），
  是否包含 ECG 原始波形**未公开说明**——按现有资料推断为不包含（依据：公开导出的字段说明中没有 ECG 波形项）。

## 适配器需要的字段（用户提供样本后确认）

| 项 | 说明 |
|---|---|
| 文件容器 | CSV / JSON / ZIP / 其他；若只有 PDF，当前任务不做 PDF 导入 |
| 时间列 | 绝对时间（时区）还是相对秒；字符串格式 |
| 电压列 | 单位 V / mV / µV；是否整数 ADC 值、增益/基线偏移 |
| 采样率 | 字段名或从时间步长推导 |
| 导联 | 是否固定 Lead I，字段里怎么写 |
| 记录元数据 | 设备型号、采集时间、是否含诊断结论 |

## 已知坑

- 不要按「Samsung Health CSV 都有统一列名」假设：不同 App 版本/导出渠道的列名会变，
  必须先看样本再写映射。
- 不要把 Samsung Health Monitor 的 PDF 当波形格式解析（本批明确不做 PDF）。
- 若用户给的是 JSON，注意时间可能是 epoch 毫秒或本地时间字符串，单位判断错误会导致时间轴全错。

## 样本能力

| 样本 | 能力 | 限制 |
|---|---|---|
| 无 | — | 需用户提供；见 `uploads/samples/index.json` 的 `missing.samsung` |

给 B4-03 的建议：在没有样本前**不要写字段映射**，只保留占位并返回 `requires: ["Samsung ECG export sample"]`；
拿到样本后再实现 `experimental → verified`。
