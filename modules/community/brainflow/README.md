# BrainFlow EEG/EMG Capture · io.github.brainflow-dev.brainflow

多板卡 EEG/EMG/ECG 采集适配，适配自 <https://github.com/brainflow-dev/brainflow>。
通过 BrainFlow 公共 API 连接板卡、读取缓冲并计算纯本地信号质量摘要。

## 方法（stdio JSON-RPC 2.0）

- `initialize` / `warmup` / `health` / `deactivate`：生命周期。
- `boards.list`：支持的板卡别名与 BoardShim ID（纯函数，无需依赖）。
- `connect`：按板卡别名/串口连接（需要硬件与 `brainflow`）。
- `snapshot`：读取当前缓冲并返回每通道质量摘要（不返回原始波形）。
- `disconnect`：释放板卡。
- `import`：解析调用方提供的 BrainFlow JSONL（离线）。
- `stats` / `channels.list`：声明式 UI 页面/组件数据。

## 信号质量

每通道计算 RMS、平线比例、削顶比例，输出 0–100 质量分与 `ok` 标志。
质量只用于提示采集是否可用，不构成诊断或异常判断。

## 依赖与隐私

`brainflow`（二进制 wheel）只装进模块 venv；无网络权限。
原始 EEG/EMG 数据不写日志、不默认返回；超出单次返回上限时由核心改为文件句柄。
非医疗器械，不用于诊断。

## 许可

适配层 GPL-3.0-only；上游 MIT，见 `NOTICE`。
