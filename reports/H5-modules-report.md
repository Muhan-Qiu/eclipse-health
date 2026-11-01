# 报告 · H5 模块适配包（候选 13–18）
状态：完成

## 交付
- `modules/official/python-fitbit` · `io.github.orcasgit.fitbit` · data-source：活动/睡眠/心率/体重导入（fitbit、requests、requests-oauthlib；network + records:write）。
- `modules/official/python-myfitnesspal` · `io.github.coddingtonbear.myfitnesspal` · data-source：饮食日记导入（myfitnesspal、lxml、cloudscraper；network + records:write）。
- `modules/official/python-withings-api` · `io.github.vangorra.withings` · data-source：体重/体脂/血压测量（requests、requests-oauthlib；network + records:write）。
- `modules/official/brainflow` · `io.github.brainflow-dev.brainflow` · device-adapter：EEG/EMG 采集与通道质量（brainflow；无网络）。
- `modules/official/muselsl` · `io.github.alexandrebarachant.muselsl` · device-adapter：Muse LSL 流 + CSV 导入（muselsl、pylsl、bleak）。
- `modules/official/openbci-python` · `io.github.openbci-archive.openbci` · device-adapter：OpenBCI 串口 + raw text 导入（pyserial）。
- 每模块含 `module.json`、`README.md`、`LICENSE`（适配层 GPL-3.0-only）、`NOTICE`、`src/main.py`、`src/adapter.py`；myfitnesspal 另含 `LICENSES/python-myfitnesspal-upstream.txt`。
- 6 个模块均实现 `initialize/warmup/health/deactivate` + 各自 import/fetch/stats/页面数据方法；adapter 全部纯标准库，便于离线单测。
- UI 只用受控类型：stat / list / progress + table 页面，未使用新类型。

## 验证
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\modules\test_official_python_fitbit.py ...（6 个文件）`
- 结果：**34 passed, 5 skipped in 0.77s**（5 skip 为上游库未装入核心 venv：fitbit / myfitnesspal / brainflow / muselsl / openbci）。
- manifest：6/6 通过 `schemas/module.schema.json`（Draft 2020-12）与 `load_manifest_file`（含 dependencies 校验）。
- `ruff check`（6 个模块目录）：All checks passed。
- worker 测试用真实 stdio 子进程覆盖 initialize/health/import/deactivate 与非法输入（`data.code=INVALID_INPUT`、`METHOD_NOT_FOUND`）。
- 边界覆盖：非法日期/日期区间、负体重、未知 kind/board/preset、平线信号质量=0、坏 CSV/JSONL/文本行。

## 未做 / 偏离
- 网络与硬件主路径未实测（无 API key、无设备、核心 venv 不装依赖）：fitbit/MyFitnessPal/Withings 的 OAuth 与 fetch、BrainFlow/Muse/OpenBCI 的实时采集仅实现并做了错误兜底，未连真机验证。
- 上游 LICENSE 仅 MyFitnessPal 成功 curl（网络受限）；其余 5 个在 NOTICE 写 URL 并标记「build 时未取到」，未伪造版权文本。
- withings 适配层直接调用 Withings 公共 REST（候选表标注 requests/oauth），未 import `withings_api`，避免依赖其不稳定的对象结构；模块 ID/署名仍对应上游。
- OpenBCI 依赖只写 `pyserial`（候选表口径）；`stream.start` 需要 `import openbci`，该包在 PyPI 的可获得性未验证，health 会如实返回 `available=false`。
- 未生成 `checksums.json`、未打包 `.ehmod`、未安装到核心。
- 大波形不返回：EEG 模块只回质量摘要；data-source 单次上限 2000–5000 条，低于 1MB 目标。

## 跨区需求（需要别的 Agent 或指挥官处理）
- 核心/manifest 已接受 `dependencies`（本批实测通过），无需再改 schema。
- 需要核心 glue 才能让 data-source 真正落库：`records:write` 授权、OAuth token 安全存储、把 `records` 传入 `stats/*.list` 的参数通道；否则组件/页面在真实运行时拿不到数据。
- device-adapter 无蓝牙/串口权限枚举；建议评估新增权限 scope（bleak/pyserial 访问硬件）。
- H1 模块 venv 需联网安装；依赖版本已给区间，建议后续加哈希锁定与索引白名单。
- 需要核心在拉起 worker 时透传 `ECLIPSE_MODULE_ID/API_VERSION/PERMISSIONS`（当前已有；本批 worker 兼容缺省）。

## 需要指挥官决策
- 非官方 API（Fitbit/MyFitnessPal/Withings）是否进入官方索引，并显著标注 ToS/稳定性风险（候选表 §3.5-3 未决）。
- 是否允许 device-adapter 用 `system:background` 权限从子进程/线程持续采集。

## 建议下一批
- 用真实 API key 与硬件各跑一次 fitbit/withings、brainflow/openbci，补齐 live 测试。
- 补抓 5 个上游 LICENSE 到 `LICENSES/`，并登记 upstream commit SHA。
- 按 H1 流程打包 6 个 `.ehmod`，跑 preview/install/start/rpc/audit/uninstall 闭环。
