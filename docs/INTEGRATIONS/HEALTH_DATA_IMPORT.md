# 多源健康数据「直接导入 eclipse health」（S1 研究）

> 日期：2026-10-30 · 范围：只做研究，不写解析器。
> 终点始终是「官方导出的文件直接交给我们的应用」，**不经过三星健康中转**；三星仅作兜底。
> 结论状态：✅ 有官方依据 · ⚠ 有路径但格式待样本验证 · ❌ 公开能力不可得。

## 一页结论

**推荐顺序（与用户确认一致）**：Apple Health → 华为 → 小米 / Zepp → Samsung Health → Health Connect（暂不做）。

| 源 | 用户最少步骤（含传到电脑并上传） | 文件形态 | S2 判断 |
|---|---|---|---|
| Apple Health | 4 步 | `export.zip` → `export.xml` + `electrocardiograms/*.csv` | **首批实现** |
| 小米 Mi Fitness | 6 步（含邮件验证、解密） | AES 加密 ZIP → CSV | **首批实现** |
| 华为运动健康 | 5–6 步（数据副本，需等待） | 加密 ZIP → CSV（待验证） | 次批 |
| Zepp / Zepp Life | 4 步 + 邮件 | 邮件附导出包（格式待验证） | 次批 |
| Samsung Health | 4 步 | 手机 Downloads 下的 `Samsung Health/` 文件夹，JSON/CSV | 兜底 |
| Health Connect | 无官方文件导出 | 需第三方 App 走 API 导出 | 暂不排期 |

**S2 建议先实现 1–2 个解析器**：

1. **Apple Health `export.xml`（+ ECG CSV）**：唯一同时覆盖步数、心率、睡眠、体重、血压、ECG 六类、且官方明确提供 XML 导出的源；Python 标准库 `zipfile` + `xml.etree.ElementTree.iterparse` 即可流式解析，无需新依赖。
2. **小米 `hlth_center_fitness_data.csv`**：字段结构清晰（`Key`/`Time`/`Value`），覆盖步数、心率、睡眠等；CSV + JSON 标准库可解析。华为/Samsung 等拿到真实样本后再加映射，避免猜列名。

---

## 1. Apple Health（首选）

**导出路径（官方）**
iPhone「健康」→ 右上角头像 →「导出所有健康数据」→ 选择分享方式（存到“文件”/AirDrop/邮件）。官方说明只承诺 XML，不承诺目录细节。

**实际文件格式**
`export.zip` 解压后常见：

```
apple_health_export/
├─ export.xml            # 主数据，可达数百 MB～数 GB
├─ export_cda.xml        # CDA 副本，可忽略
├─ electrocardiograms/   # 每次 ECG 一个 CSV（社区样本可见）
└─ workout-routes/       # GPX
```

- `export.xml` 是扁平的 `<Record type="HKQuantityTypeIdentifier…" startDate endDate value unit/>`；
  睡眠是 `HKCategoryTypeIdentifierSleepAnalysis`，`value` 为 `HKCategoryValueSleepAnalysisAsleepCore/Deep/REM/InBed/Awake` 等。
- 常用类型：`StepCount`、`HeartRate`（count/min）、`BodyMass`（kg）、`BloodPressureSystolic/Diastolic`（mmHg）、`SleepAnalysis`。
- ECG 在 `electrocardiograms/*.csv`；Apple 官方只描述 HealthKit 字段（采样频率、电压、分类），**导出 CSV 的列名与单位仍需用户样本核验**，参考 `docs/FORMATS/apple.md` 的推断布局。

**转换/解析可行性**
- 标准库即可；必须用 `iterparse` 流式读取，不能 `read()` 整个文件。
- 单位在 `unit` 属性里，需做白名单换算（count/min、kg、mmHg 等）。
- 版本差异：iOS 版本会影响字段与导出目录；解析器应“按 type 取值、缺字段跳过”，不要假设固定顺序。

**用户步骤（4 步）**
1. 健康 App → 头像 → 导出所有健康数据 → 存到“文件”。
2. 把 `export.zip` 传到电脑（数据线 / 隔空投送 / 网盘，用户自选）。
3. 打开 eclipse health → 导入 → 选择 `export.zip`（无需手动解压）。
4. 等待解析完成，核对记录数与时间范围。

**合规 / 样本**
仅使用 Apple 官方导出、用户自有数据；不调用私有 API。公开去标识样本存在但需核对许可证；ECG 列结构建议向用户要一份**脱敏**导出包验证，不落地仓库。

---

## 2. 华为运动健康

**导出路径 A：数据副本（全量，官方）**
手机「设置」→ 华为账号 → 隐私中心 → 管理您的数据 → 获取您的数据副本；或电脑登录 [华为隐私中心](https://privacy.consumer.huawei.com/tool?lang=zh-cn&themeName=blue) → 获取您的数据副本。在线工具默认给近一年数据，更早需在“隐私问题”页面申请；数据保留 **21 天**。

**导出路径 B：App 内单项导出（官方）**
- 血压卡片 → 选择时间范围 → 导出 CSV（运动健康 16.0.12.300+）。
- 运动轨迹：运动记录 → 轨迹 → 导出路线文件（GPX/KML/TCX，仅户外跑/骑/走）。

**实际文件格式**
- 数据副本为**加密压缩包，密码单独发送**（社区经验），内部为按数据类别的 CSV；具体目录/列名**未找到官方说明，需用户样本**。
- 血压 CSV 的列名与单位同样未公开，需样本确认。

**转换/解析可行性**
- ZIP + CSV 标准库可解；**AES 加密 ZIP 标准库 `zipfile` 不支持**，建议让用户自行解压后上传 CSV，或后续评估只读未加密包。
- 不要求用户提供华为账号密码；我们只接收文件。

**用户步骤（5–6 步）**
1. 隐私中心 → 获取您的数据副本 → 选择“运动健康”。
2. 完成身份验证，提交申请。
3. 等待生成（官方口径：一年内在线工具；更久需人工配置）。
4. 在 21 天内下载压缩包，按邮件/页面提示解压。
5. 把 CSV 传到电脑并导入（可整包或单文件）。

**ECG**：华为公开能力只到“心电分析”结果页与 PDF/图片分享；未找到原始波形导出，**当前不可导入**，需要用户提供新样本才能重新评估。

---

## 3. 小米 Mi Fitness / Zepp

### 3.1 小米 Mi Fitness（次批首选）

**导出路径（官方支持页）**
登录 [account.xiaomi.com](https://account.xiaomi.com/) → 隐私 → 管理您的数据 → MI Fitness → Download，按提示绑定邮箱；随后收到下载链接与**独立密码**。

**实际文件格式**
- **AES 加密 ZIP**（链接 7 天有效，准备时间从几分钟到 15 个工作日），解密后为 CSV。
- 主文件 `hlth_center_fitness_data.csv`：`Key` 列区分指标（`heart_rate`、`spo2`、`sleep`、`steps`、`calories` 等），`Time` 为 Unix 时间戳，`Value` 为 JSON。
- 另有 `hlth_center_sport_record.csv` 等运动记录文件。

**解析可行性**：CSV + `json.loads(Value)` 即可；AES ZIP 由用户自行解压（或后续引入解密步骤，S2 不做）。

**用户步骤（6 步）**：登录账号 → 隐私 → 管理您的数据 → MI Fitness 下载 → 邮箱验证 → 收邮件下载并解密 → 上传 CSV。

### 3.2 Zepp / Zepp Life

**导出路径**
App：我的 → 设置 → 账号与安全 → 注销账号 → **导出数据** → 勾选数据 → 确定（不注销也可在流程中导出）。网页端亦有 GDPR 导出入口（`user.huami.com/privacy2`，社区工具引用）。

**实际文件格式**：官方未公开目录/列名；社区反馈为邮件发送的导出包，运动记录细节有限。**需用户样本验证**。

**用户步骤（4 步 + 邮件）**：App 内导出 → 选择数据类型 → 确认 → 收邮件下载 → 上传。

**ECG（小米 / Zepp）**：未找到公开的原始波形导出；按现有资料**不可导入**。

---

## 4. Samsung Health（仅兜底）

**导出路径（官方）**
Samsung Health → 右上角 ⋮ → 设置 → 滑到 **Download personal data** → Download → 授予权限 → 登录三星账号 → 等待 → 文件在「我的文件 → Download → Samsung Health」文件夹。

**实际文件格式（第三方整理，官方未列格式）**
文件夹内为 JSON/CSV/ZIP；常见 `com.samsung.health.activity.json`、`sleep.json`、`heart_rate.json`、`body_composition.json`、`blood_pressure.json` 等，字段按数据类型组织。

**解析可行性**：JSON/CSV 标准库可解；文件命名以 `com.samsung.health.*` 为稳定线索，但字段随版本变化，需样本。

**用户步骤（4 步）**：设置 → Download personal data → 登录并等待 → 传电脑 → 上传文件夹/压缩包。

**ECG**：Samsung Health Monitor 只提供 **PDF 报告**分享，原始波形不在公开导出范围；**不可导入**。

---

## 5. Health Connect（结论：暂不做）

- 没有面向用户的“导出为文件”功能；Android 15+ 提供的是系统级 **备份/恢复**（备份到 Google 账号），不是可交给桌面应用的 CSV/JSON。
- 数据只能由 Android App 通过 Health Connect API 读取后再导出；已有第三方 App（如 Health Data Export）做 CSV/Sheets 导出，但引入手机端依赖。
- 结论：不作为 S2 路径；若后续需要，按“第三方 App 导出 CSV → 我们解析”处理，且只作为补充源。

---

## 6. 酷安 / 应用商店那类工具（只作线索）

- **Health Sync（Android）**：平台间同步枢纽，可读 HUAWEI Health、Samsung Health 等，可写 Samsung Health；iOS 版仅以 Apple Health 等为源，写入目标不含三星健康。**它解决的是“App 到 App 同步”，不是“文件直接给我们”**。
- **运动健康转换工具（fitconverter 等网页工具）**：主打运动记录导出/转换（TCX/GPX），不是步数/心率/睡眠/血压全量解析。
- **Health Data Export 类 App**：依赖 Health Connect / Apple Health 权限读数据后导出 CSV，可作为备用路径，但要求手机端安装。
- **酷安帖子**：多为三星健康开发者模式、插件授权、步数同步技巧（如 `Download/SamsungHealth/FeatureManagerOn` 目录），不是通用数据导入器。

**结论**：现成工具没有“任意导出文件 → 我们的应用”的通用解析器；它们要么是平台间同步、要么只做运动轨迹。我们直接解析官方导出文件，路径更短、依赖更少。

---

## 7. 能力矩阵（能否直接导入）

| 数据类 | Apple | 华为 | 小米 | Zepp | Samsung | Health Connect |
|---|---|---|---|---|---|---|
| 步数 | ✅ XML | ⚠ 数据副本 | ✅ CSV | ⚠ 导出包 | ✅ JSON | ⚠ 需 App |
| 心率 | ✅ XML | ⚠ 数据副本 | ✅ CSV | ⚠ 导出包 | ✅ JSON | ⚠ 需 App |
| 睡眠 | ✅ XML | ⚠ 数据副本 | ✅ CSV | ⚠ 导出包 | ✅ JSON | ⚠ 需 App |
| 体重 | ✅ XML | ⚠ 数据副本 | ⚠ 字段待样本 | ⚠ 导出包 | ✅ JSON | ⚠ 需 App |
| 血压 | ✅ XML | ✅ App 内 CSV | ⚠ 待样本 | ⚠ 待样本 | ✅ JSON | ⚠ 需 App |
| ECG | ✅ ECG CSV | ❌ 仅 PDF | ❌ | ❌ | ❌ 仅 PDF | ❌ 公开能力不含波形 |

说明：✅ = 有官方导出且路径明确；⚠ = 有官方导出但格式/字段需样本验证；❌ = 公开能力不可得。

---

## 8. 合规声明

- 只使用厂商**官方公开**的导出/数据副本能力，或用户自有数据。
- 不逆向私有 API、不破解加密、不代下载、不绕过付费授权、不要求用户交出账号密码。
- 加密压缩包由用户自行解密后上传；应用不保存、不上传任何健康数据到网络。
- 公开样本只记录 URL 与许可证，不把受限数据集落地到仓库。

## 9. 来源

1. Apple Support — Share your data in Health on iPhone（XML 导出）：<https://support.apple.com/guide/iphone/share-your-health-data-iph5ede58c3d/ios>
2. Apple Developer — HKQuantityTypeIdentifier：<https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier>
3. Apple Developer — HKCategoryValueSleepAnalysis：<https://developer.apple.com/documentation/healthkit/hkcategoryvaluesleepanalysis>
4. MyDataHelps — Apple HealthKitV2 ECG 导出字段：<https://support.mydatahelps.org/apple-healthkitv2-electrocardiogram-export-format>
5. 华为 — 如何获取个人数据副本：<https://consumer.huawei.com/cn/support/content/zh-cn16044986/>
6. 华为 — 获取与您帐号相关的数据拷贝（21 天保留）：<https://consumer.huawei.com/cn/support/content/zh-cn15775110/>
7. 华为隐私中心：<https://privacy.consumer.huawei.com/tool?lang=zh-cn&themeName=blue>
8. 华为 — 运动轨迹导出/导入（GPX/KML/TCX）：<https://consumer.huawei.com/cn/support/content/zh-cn15893332/>
9. 华为 — 血压数据导出 CSV：<https://consumer.huawei.com/cn/support/content/zh-cn16081042/>
10. Xiaomi — How to download/export data from Mi Fitness App：<https://www.mi.com/global/support/article/KA-11566/>
11. Xiaomi 隐私白皮书（数据副本）：<https://trust.mi.com/docs/iot-privacy-white-paper-global/5/1>
12. Xiaomi 导出工具 README（AES ZIP、CSV 结构）：<https://github.com/WElArfaoui/xiaomi-health-exporter>
13. Zepp — Privacy protection Support（Export data）：<https://www.zepp.com/privacy-support>
14. Zepp GDPR 导出入口（社区引用）：<https://user.huami.com/privacy2/index.html?loginPlatform=web&platform_app=com.xiaomi.hm.health>
15. 百度经验 — Zepp 导出数据步骤：<https://jingyan.baidu.com/article/e52e361522500f01c70c5173.html>
16. Samsung — Download or erase your personal data from Samsung Health：<https://www.samsung.com/us/support/answer/ANS10001379/>
17. Samsung — Samsung Health Monitor 保存/恢复（PDF 导出）：<https://www.samsung.com/ae/support/apps-services/learn-how-to-save-or-restore-samsung-health-monitor/>
18. takeoutday — Samsung Health 导出目录与 JSON 结构：<https://takeoutday.org/guides/how-to-export-samsung-health-data>
19. Samsung Developer — Samsung Health 与 Health Connect：<https://developer.samsung.com/health/blog/en/accessing-samsung-health-data-through-health-connect>
20. Android Developers — Health Connect：<https://developer.android.com/health-and-fitness/health-connect>
21. Android Authority — Health Connect 备份/恢复：<https://www.androidauthority.com/health-connect-data-backup-3498985/>
22. Health Sync — 支持的数据源/目标：<https://healthsync.app/about-cn/>
23. fitconverter — Zepp Life 导出说明：<https://www.fitconverter.com/convert/export/zepp_life.html>
24. Health Data Export（Health Connect 导出 App）：<https://healthdataexport.com/instructions.html>
25. 酷安 — 三星健康开发者模式/目录帖子（线索）：<https://www.coolapk.com/feed/44392293>

---

## 10. S2 实现状态（2026-10-30）

**已实现**（`backend/src/eclipse_health_backend/importers/`）：

| 源 | 适配器 | 输入 | 已映射类型 |
|---|---|---|---|
| Apple Health | `org.eclipsehealth.apple-health` | `export.zip`（内含 `export.xml` + `electrocardiograms/*.csv`）或单独 `export.xml` | 步数、心率、睡眠、体重、血压（Correlation）、心电图 CSV |
| 小米 Mi Fitness | `org.eclipsehealth.xiaomi` | 解压后的 `hlth_center_fitness_data.csv`（`Key,Time,Value`） | 步数、心率、睡眠、体重 |

**记录形态**

- 非波形记录：`recordType = org.eclipsehealth.health.<kind>`（`steps` / `heart-rate` / `sleep` / `body-mass` / `blood-pressure`）；`payload = {value, unit, startAt, endAt, sourceApp?}`；`source.kind="import"`；`metadata.importSource = "apple-health" | "xiaomi-mi-fitness"`。
- 单位：步数 `count`；心率 `count/min`；体重 `kg`；血压 `mm[Hg]`；睡眠 `1`（`value` 为阶段名，`durationSec` 保存时长）。
- ECG：Apple CSV 的 `time,voltage`（秒/伏特）→ 单导联 I、mV；采样率按时间步长推断，失败时按 512 Hz 并告警。

**去重**

1. 整包：`provenance.fileHash`（文件 sha256）已存在 → 全部跳过。
2. 逐条：`metadata.externalId`。Apple 优先使用 `uuid` 属性；导出未提供 UUID 时用类型/起止时间/值/来源的指纹。ECG 用 CSV 内容 sha256。

**错误码**：`encrypted_export`（加密 ZIP）、`unsupported_xiaomi_export`（不是 Key/Time/Value）、`apple_export_missing`、`apple_export_empty`、`invalid_apple_export`、`invalid_ecg_csv`、`import_too_many_records`（默认 20,000 条 / 200 段 ECG）。

**字段限制 / 未验证**

- 未用真实 Apple / 小米导出包验证（当前用合成夹具）；ECG CSV 列名按 `time,voltage` 解析，并兼容带 `Date:` 元数据行。
- 睡眠按单条阶段记录导入，不合并为睡眠会话；Apple `InBed/Awake/Core/Deep/REM` 映射为 kebab 值。
- 未映射类型（如活动能量、站立）跳过并计数，不猜测。
- 小米 `Value` 为列表的行跳过；未知 Key 与坏 JSON 逐行计入警告。
- 不做 AES 解密、不做 Health Connect、不做 Huawei/Zepp/Samsung 健康数据。
