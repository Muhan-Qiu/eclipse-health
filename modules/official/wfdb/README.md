# wfdb · ECG 记录读写

适配自 [MIT-LCP/wfdb-python](https://github.com/MIT-LCP/wfdb-python)（MIT）。
`wfdb` 已在核心 venv（E 类），本模块通过 `import wfdb` 调用，不复制源码。

## 方法

| RPC | 说明 |
|---|---|
| `initialize` / `warmup` / `health` / `deactivate` | 生命周期 |
| `export.wfdb` | `wfdb.wrsamp` 写出 `.hea` + `.dat`；需 `outputDir` |
| `export.csv` | 通道写成 CSV（`time_s` + 各通道） |
| `import.wfdb` | `wfdb.rdrecord` 读取并返回摘要；可返回前 5 万样本 |

`export.*` 只写调用方提供的 `outputDir`；`import.wfdb` 的 `path` 接受 `.hea`
文件或记录前缀。

## 贡献点

- `importFormats`：`wfdb-record`（`.hea` / `.dat`）
- `exporters`：`wfdb-csv`（CSV；原生 WFDB 走 RPC）
- 已知限制：schema 的 exporter `format` 枚举没有 `wfdb`，因此原生 WFDB 导出只能经 RPC 暴露。

## 权限与依赖

- 权限：`files:user-selected`、`files:export`、`records:read`
- pip 依赖：无（核心 venv 已含 `wfdb` 与 `numpy`）

## 测试

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_wfdb.py -q
```

## 声明

非医疗器械，不用于诊断。本适配层为 GPL-3.0-only；上游许可与署名见 `NOTICE`。
