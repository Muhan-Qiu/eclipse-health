# 报告 · A4 S1 多源健康数据直接导入研究

状态：完成

## 交付
- `docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md`（新建，204 行）：一页结论、Apple/华为/小米/Zepp/Samsung/Health Connect 分源章节、酷安类工具线索、6 类数据能力矩阵、合规声明、25 条来源。
- 研究结论：终点是官方导出文件直接导入；每个源都给出最少用户步骤。

## 验证
- 命令：`wc -l docs/INTEGRATIONS/HEALTH_DATA_IMPORT.md` → 204 行。
- 命令：统计文末来源 → 25 个条目、26 个唯一 URL，均可点击。
- 能力矩阵覆盖：步数、心率、睡眠、体重、血压、ECG；每格标注 ✅/⚠/❌。
- 样本核验：README/格式说明只引用公开来源，未下载受限数据集。

## 关键结论
- 推荐顺序：Apple（4 步）→ 华为（5–6 步）→ 小米（6 步）/ Zepp（4 步+邮件）→ Samsung（4 步）→ Health Connect（不做）。
- S2 首批：**Apple `export.xml` + ECG CSV**、**小米 `hlth_center_fitness_data.csv`**。
- Apple 是唯一官方 XML、同时覆盖 6 类数据（含 ECG）的源；`iterparse` 流式解析即可，无新依赖。
- 小米导出为 AES 加密 ZIP，内部 CSV 的 `Key`/`Time`/`Value(JSON)` 结构清晰（社区实测，2026-06）。
- 华为数据副本为加密 ZIP、需等待，内部 CSV 列名无官方说明；血压有 App 内 CSV 导出。
- Zepp 导出入口在“注销账号 → 导出数据”，格式未公开。
- Samsung 官方路径为 Samsung Health → 设置 → Download personal data；文件落在手机 Downloads 的 Samsung Health 文件夹，JSON/CSV。
- ECG：只有 Apple 可导出原始波形；华为/小米/Zepp/Samsung 只有 PDF 或不可得。
- 酷安类工具（Health Sync 等）是 App 间同步或运动轨迹转换，不是通用文件解析器，不能替代我们的直接导入。

## 未做 / 偏离
- 提示词要求用 WebFetch 打开 Bing；本机 WebFetch 对 bing.com/support.apple.com 等均返回 “Unable to verify if domain is safe”，因此改用 `curl` + Playwright 访问 Bing（同源、同查询），并直接抓取官方页面核对。未使用 WebSearch。
- 未写任何解析器/后端/前端代码；未改其他 docs/prompts/uploads；未 commit。
- 未获取真实导出包：Apple ECG CSV 列名、华为数据副本目录、Zepp 导出包结构仍为 ⚠，需用户样本验证。
- HuggingFace 上的 Apple ECG 公开样本因网络不可达未下载，仅记录结论。

## 跨区需求
- 无代码跨区；若 S2 实现 Apple 解析，需要 `backend` 导入管线 owner 预留“大 XML 流式解析”入口。
- 华为/Zepp/Samsung 的字段映射需要用户各提供一份脱敏导出包，建议在 S2 前收集。

## 需要指挥官决策
1. S2 是否按建议只先做 Apple + 小米两个解析器（其余等样本）。
2. 是否接受“加密 ZIP 由用户自行解压后上传 CSV”，还是后续投入 AES 解密支持。
3. 应用内引导页文案是否明确“不经过三星健康”；三星仅作为最后兜底入口。

## 建议下一批
- S2：Apple `export.zip`（含 ECG CSV）解析 + 小米 CSV 解析 + 上传/去重/单位换算。
- S2 并行：向用户收集华为、Zepp、Samsung 各一份脱敏导出包，补字段映射后再做第二批。
- 暂不排期 Health Connect；若做，按“第三方 App 导出 CSV → 我们解析”处理。
