# B4-02 · 公开样本与格式资料采集

> 难度：中等 2/4 · 建议思考强度：**medium** · 批次：B4 收口（Wave 1）
> 你是唯一允许写 `uploads/` 的 Agent；也是唯一允许为「公开数据」联网下载的 Agent（见 `00-COMMON.md` 例外）。
> 目标：为 Samsung / 华为 / Apple / SCP-ECG / EDF 找到**可公开下载**的样本与格式说明，写成适配器能直接用的资料包；找不到就如实标注，不编造。

## 1. 目标格式

| 格式 | 需要什么 | 备注 |
|---|---|---|
| EDF / EDF+ | 1–3 个小样本（ECG，最好单导联/多导联各一）+ 规范要点 | PhysioNet / EDF+ 规范，公开概率高 |
| SCP-ECG | 1–3 个小样本 + 段结构/导联/采样率说明 | OpenECG / PhysioNet / GitHub，公开概率高 |
| Apple Health ECG | `electrocardiograms.csv` 样例或导出包样例 + 字段说明 | GitHub 上常见脱敏样例，注意隐私 |
| Samsung Health ECG | 导出 CSV/JSON 样例 + 字段说明 | 社区文档/GitHub，公开概率中等 |
| 华为运动健康 ECG | 导出样例 + 字段说明 | 公开概率最低；找不到就明确写「需用户提供」 |

## 2. 你必须交付

1. **样本目录** `uploads/samples/<vendor>/`
   - 每个格式 1–3 个小文件（单文件 ≤20MB，总量 ≤100MB）；保留原始文件名与目录结构。
   - 只下载**公开、可再分发用于测试**的样本；不碰登录/个人数据；不下载整库。
2. **索引** `uploads/samples/index.json`
   ```json
   {
     "samples": [
       {
         "id": "scp-ecg-example-1",
         "vendor": "scp-ecg",
         "path": "samples/scp-ecg/xxx.scp",
         "sourceUrl": "https://...",
         "license": "CC-BY-4.0 / public domain / unknown",
         "downloadedAt": "2026-10-29",
         "sha256": "...",
         "bytes": 12345,
         "leads": ["I", "II"],
         "samplingRate": 500,
         "durationSec": 10,
         "notes": "字段/单位/标注说明"
       }
     ],
     "missing": [{ "vendor": "huawei", "reason": "未找到公开样本", "needed": ["导出文件", "字段说明"] }]
   }
   ```
3. **格式说明** `docs/FORMATS/<vendor>.md`（≤80 行/篇）
   - 文件结构、必需字段、单位、采样率、导联命名、时间格式、标注（如有）、已知坑、示例片段。
   - 只写有来源的内容；推断必须标「推断」并给依据。
4. **测试夹具**
   - 许可证允许时，复制 1 个小样本到 `backend/tests/fixtures/imports/<vendor>/`；
   - 不允许/找不到时，基于文档造一个**合成夹具**，并在索引标 `synthetic: true`。
5. **验证**
   - 用 Python 标准库做最小校验：文件头/行数/时间列/采样率字段能读出来；不写生产解析器。
   - 记录 `sha256`、大小、能否被现有 `wfdb`/`csv` 工具打开（能则记录）。
6. **报告** `reports/B4-02-report.md`：每个格式「找到/没找到/合成」，来源 URL、许可证、样本能力矩阵、给 B4-03 的建议。

## 3. 下载方法

- 先用 WebFetch 打开 Bing/DuckDuckGo 结果页找来源，再下载：
  ```powershell
  curl.exe -L --fail --max-time 120 "<url>" -o "uploads\samples\<vendor>\<file>"
  ```
- 优先：PhysioNet、OpenECG、GitHub 公开仓库、厂商公开文档/示例。
- 每次下载记录 URL；失败换备用源；不要反复重试同一 403/404。
- 不要用 WebSearch（本机上游不支持）。
- 不安装新 Python 依赖。

## 4. 文件所有权

可写：`uploads/samples/**`、`uploads/SOURCES.md`、`docs/FORMATS/**`、`backend/tests/fixtures/imports/**`（仅小样本/合成）、`reports/B4-02-report.md`。
不要动：`uploads/models/**`（留给用户）、`backend/src/**`、`src/**`、`src-tauri/**`、其他 `docs/**`、`prompts/**`。

## 5. 明确不做

不写生产适配器（B4-03）、不做 UI、不下载付费/需登录数据、不抓取用户个人健康数据、不把大文件提交进 git（`uploads/` 已忽略）。

## 6. 交付判据

- 至少 EDF、SCP-ECG、Apple 有公开样本或明确「不可得」结论；
- Samsung/华为给出「可用样本 / 仅文档 / 需用户提供」三选一，并写清缺什么；
- B4-03 能只读 `docs/FORMATS/` + `uploads/samples/index.json` 开始写适配器。
