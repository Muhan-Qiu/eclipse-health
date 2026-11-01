# BLE Health · eclipse health 模块

官方 `device-adapter` 模块，适配自 [hbldh/bleak](https://github.com/hbldh/bleak)。
在 Windows 11 上通过 WinRT 连接 BLE 心率带（0x2A37）与体重秤（0x2A9C），读取并解析 GATT 特征。
**非医疗器械，不用于诊断。**

## RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` / `warmup` / `health` | 握手；`health` 报告 `bleak` 是否安装 |
| `readHeartRate` | `{address, timeoutS?}` → `hr.sample`（设备地址不回显） |
| `readWeight` | `{address, timeoutS?}` → `weight` |
| `parseCapture` | `{kind: "heartRate"|"weight", dataHex}` → 离线回放 GATT 字节 |
| `latestSample` | 本进程最近一次采样，供首页 widget |
| `deactivate` | 退出 |

## 采集 JSON（importFormats）

```json
{ "kind": "heartRate", "dataHex": "0048", "measuredAt": "2026-01-01T10:00:00Z" }
```

当前核心的导入桥接尚未实现；该格式先用于 `parseCapture` 与后续批次。

## 适配说明

- 心率按 Bluetooth SIG 规范处理 uint8/uint16、接触状态、能量消耗与 RR 间期；
- 体成分按 flags 顺序跳过可选字段，SI/英制分别换算为 kg / m；
- 蓝牙配对、系统权限与地址格式由 Windows 负责；模块不保存地址、不写日志；
- `src/adapter.py` 纯函数覆盖全部字节解析，无硬件也可单测。

## 许可与署名

- 本适配层：GPL-3.0-only；上游 MIT，署名见 `NOTICE`；
- 上游 LICENSE 需在发布前放入 `LICENSES/bleak-upstream.txt`。
