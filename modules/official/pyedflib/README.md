# pyedflib · EDF/BDF 读写

适配自 [holgern/pyedflib](https://github.com/holgern/pyedflib)（BSD-3-Clause）。
本模块是**薄适配层**：不复制上游源码，`import pyedflib` 调用；依赖装进模块独立 venv（B 类）。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `export.edf` | `EdfWriter` 写 EDF+（`outputDir` 必填） |
| `export.csv` | 通道写成 CSV |
| `import.edf` | `EdfReader` 读 EDF/BDF 摘要；可返回前 5 万样本 |

通道标签在进入上游前会被截断/清洗为 EDF 规范允许的 ≤16 个 ASCII 字符。

## 贡献点

- `importFormats`：`edf-bdf`（`.edf` / `.bdf`）
- `exporters`：`edf-csv`（CSV；原生 EDF+ 走 RPC）
- 已知限制：schema 的 exporter `format` 枚举没有 `edf`，原生 EDF 导出只能经 RPC 暴露。

## 权限与依赖

- 权限：`files:user-selected`、`files:export`、`records:read`
- pip 依赖：`pyedflib>=0.1.38,<1`（含 numpy）

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_pyedflib.py -q
```

未安装 pyedflib 时，往返测试自动 skip；适配层与 manifest 测试仍会执行。

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。
