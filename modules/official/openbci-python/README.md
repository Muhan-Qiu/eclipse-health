# OpenBCI Serial Capture · io.github.openbci-archive.openbci

OpenBCI 板卡串口采集适配，适配自
<https://github.com/openbci-archive/OpenBCI_Python>。
上游仓库已归档（2022 年后停更），本模块只做薄封装并明确标注风险。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `devices.list`：支持的板型与默认通道数（纯函数）。
- `ports.check`：校验串口名（COMx / /dev/tty*）。
- `stream.start` / `stream.stop`：连接/断开板卡（需要硬件与上游库）。
- `import`：解析 OpenBCI raw text（离线），输出会话摘要与通道质量。
- `stats` / `channels.list`：声明式 UI 页面/组件数据。

## 文本格式

OpenBCI GUI 导出的文本：`%` 开头为头注释；数据行为
`Sample Index,Channel 1..N[,Accel X..Z,Other]`。只读取前 `channelCount` 个通道，
额外加速度/辅助列被忽略。

## 依赖与隐私

`pyserial` 只装进本模块独立 venv；无网络权限。原始 EEG 不写日志、不返回大数组。
非医疗器械，不用于诊断。

## 许可

适配层 GPL-3.0-only；上游 MIT，见 `NOTICE`。
