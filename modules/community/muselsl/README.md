# Muse LSL Stream · io.github.alexandrebarachant.muselsl

Muse 头环 EEG 设备适配，适配自 <https://github.com/alexandrebarachant/muse-lsl>。
通过上游 CLI 启动 LSL 流，并解析 `muselsl record` 生成的 CSV。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `devices.list`：支持的 preset 与通道名（纯函数）。
- `stream.start`：在子进程启动 `muselsl stream`（需要 Muse 头环与蓝牙）。
- `stream.stop`：终止本模块启动的流进程。
- `import`：解析 MuseLSL CSV（离线），返回会话摘要与通道质量。
- `stats` / `channels.list`：声明式 UI 页面/组件数据。

## 依赖

`muselsl`、`pylsl`、`bleak`，只装进本模块独立 venv。缺依赖时 `health` 返回
`dependency.available=false`，`stream.start` 返回 `MODULE_DEPENDENCY_MISSING`；
`import` 与纯解析仍可用。

## 隐私与边界

- 原始 EEG 不写日志、不返回大数组；只输出会话摘要与通道质量。
- 连接需要蓝牙配对与 LSL 运行时；LSL 流可能被本机其他程序订阅。
- 非医疗器械，不用于诊断。

## 许可

适配层 GPL-3.0-only；上游 BSD-3-Clause，见 `NOTICE`。
