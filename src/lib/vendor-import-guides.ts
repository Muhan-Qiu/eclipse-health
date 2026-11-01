/**
 * 厂商健康数据导出教程（中英文）。
 *
 * 入口文案与步骤按各厂商官方客户端的通用路径整理；官方链接在文件末尾给出。
 * 客户端界面会随版本调整，UI 里统一提示「界面可能随版本变化」。
 */

export type VendorGuideId =
  | "apple-health"
  | "samsung-health"
  | "xiaomi"
  | "huawei-health"
  | "zepp"
  | "oppo-health"
  | "garmin-connect"
  | "fitbit"
  | "withings"
  | "google-fit";

export interface VendorGuide {
  id: VendorGuideId;
  name: { zh: string; en: string };
  /** 导出步骤；每一步都是可独立阅读的动作。 */
  steps: { zh: string[]; en: string[] };
  /** 导出文件格式。 */
  formats: string;
  /** 一般包含哪些数据。 */
  includes: { zh: string; en: string };
  /** 版本差异提示（可选，未单独列出时使用通用提示）。 */
  versionNote?: { zh: string; en: string };
  /** 官方帮助页；已验证可访问或为厂商官方帮助中心入口。 */
  helpUrl: string;
}

export const VENDOR_GUIDES: readonly VendorGuide[] = [
  {
    id: "apple-health",
    name: { zh: "Apple 健康", en: "Apple Health" },
    steps: {
      zh: [
        "在 iPhone 打开「健康」App，点右上角头像。",
        "滑到最下方，点「导出所有健康数据」。",
        "选择保存到「文件」或隔空投送到电脑。",
        "把生成的 export.zip 直接拖进本应用（无需解压）。",
      ],
      en: [
        "Open the Health app on iPhone and tap your profile picture (top right).",
        "Scroll to the bottom and tap Export All Health Data.",
        "Save it to Files or AirDrop the archive to your computer.",
        "Drag the resulting export.zip into this app (no need to unzip).",
      ],
    },
    formats: "ZIP（内含 export.xml）",
    includes: {
      zh: "步数、心率、静息心率、睡眠、体重、血压、血氧、体温、血糖、HRV、运动记录，以及心电图（如设备支持）。",
      en: "Steps, heart rate, resting heart rate, sleep, body mass, blood pressure, SpO2, body temperature, blood glucose, HRV, workouts, and ECG when the device supports it.",
    },
    versionNote: {
      zh: "iOS 16 起入口在「健康」→ 头像 → 底部；更早版本在「隐私」中。导出包可能很大，生成需要几分钟。",
      en: "On iOS 16+ the entry is Health → profile → bottom. Older versions list it under Privacy. Exports can be large and take a few minutes to generate.",
    },
    helpUrl: "https://www.apple.com/health/",
  },
  {
    id: "samsung-health",
    name: { zh: "Samsung Health", en: "Samsung Health" },
    steps: {
      zh: [
        "打开 Samsung Health，点右上角「更多」（⋮）或「设置」。",
        "进入「隐私」→「下载个人数据」。",
        "勾选需要的数据类型，选择时间范围后导出。",
        "在「我的文件」里找到导出的 ZIP/CSV，拖进本应用。",
      ],
      en: [
        "Open Samsung Health and tap More (⋮) or Settings.",
        "Go to Privacy → Download personal data.",
        "Select the data types and date range, then export.",
        "Find the exported ZIP/CSV in My Files and drag it into this app.",
      ],
    },
    formats: "ZIP（CSV / JSON）",
    includes: {
      zh: "步数、心率、睡眠、体重、血压、血氧、压力、运动记录。",
      en: "Steps, heart rate, sleep, body mass, blood pressure, SpO2, stress, and workouts.",
    },
    versionNote: {
      zh: "不同 One UI 版本入口可能是「设置 → 隐私」或「三星账号 → 隐私 → 下载数据」；没有「下载个人数据」时请先更新 Samsung Health。",
      en: "Depending on One UI it may be Settings → Privacy or Samsung account → Privacy → Download your data. Update Samsung Health if the option is missing.",
    },
    helpUrl: "https://www.samsung.com/us/support/",
  },
  {
    id: "xiaomi",
    name: { zh: "小米运动健康 / Zepp Life", en: "Mi Fitness / Zepp Life" },
    steps: {
      zh: [
        "打开「小米运动健康」（或 Zepp Life），进入「我的」。",
        "点「设置」→「隐私」→「导出数据 / 下载个人数据」。",
        "选择时间范围并提交，导出文件会发送到绑定邮箱或保存在手机。",
        "把下载到的 CSV/JSON/ZIP 拖进本应用。",
      ],
      en: [
        "Open Mi Fitness (or Zepp Life) and go to Profile.",
        "Open Settings → Privacy → Export data / Download personal data.",
        "Choose a date range and submit; the export is emailed or saved on the phone.",
        "Drag the downloaded CSV/JSON/ZIP into this app.",
      ],
    },
    formats: "CSV / JSON / ZIP",
    includes: {
      zh: "步数、心率、睡眠、体重、血氧、压力、运动记录。",
      en: "Steps, heart rate, sleep, body mass, SpO2, stress, and workouts.",
    },
    versionNote: {
      zh: "Zepp Life 与小米运动健康是两个客户端，入口名称略有差异；部分账号只支持邮件发送导出文件。",
      en: "Zepp Life and Mi Fitness are separate apps with slightly different labels; some accounts only deliver exports by email.",
    },
    helpUrl: "https://www.mi.com/global/support/",
  },
  {
    id: "huawei-health",
    name: { zh: "华为运动健康", en: "Huawei Health" },
    steps: {
      zh: [
        "打开「华为运动健康」，进入「我的」。",
        "点「隐私」→「下载个人数据」。",
        "选择数据类型与时间范围，提交申请。",
        "收到下载链接后导出 ZIP，拖进本应用。",
      ],
      en: [
        "Open Huawei Health and go to Me.",
        "Go to Privacy → Download personal data.",
        "Select data types and a date range, then submit the request.",
        "Open the download link you receive and drag the ZIP into this app.",
      ],
    },
    formats: "ZIP（CSV / JSON）",
    includes: {
      zh: "步数、心率、静息心率、睡眠、血氧、压力、体温、运动记录。",
      en: "Steps, heart rate, resting heart rate, sleep, SpO2, stress, body temperature, and workouts.",
    },
    versionNote: {
      zh: "部分版本需要登录华为账号后等待数分钟生成；运动健康与「荣耀运动健康」入口名称不同。",
      en: "Some versions require a few minutes to prepare the archive. Honor Health uses different labels.",
    },
    helpUrl: "https://consumer.huawei.com/en/support/",
  },
  {
    id: "zepp",
    name: { zh: "Zepp / 华米", en: "Zepp / Amazfit" },
    steps: {
      zh: [
        "打开 Zepp App，进入「我的」。",
        "点「设置」→「隐私」→「导出数据」。",
        "选择时间范围，确认后下载导出包。",
        "把 ZIP/CSV 拖进本应用。",
      ],
      en: [
        "Open the Zepp app and go to Profile.",
        "Open Settings → Privacy → Export data.",
        "Choose a date range and download the export archive.",
        "Drag the ZIP/CSV into this app.",
      ],
    },
    formats: "ZIP（CSV / JSON）",
    includes: {
      zh: "步数、心率、睡眠、血氧、压力、运动记录。",
      en: "Steps, heart rate, sleep, SpO2, stress, and workouts.",
    },
    versionNote: {
      zh: "Zepp 与 Zepp Life 为不同客户端，导出入口可能分别位于「隐私」或「账号」下。",
      en: "Zepp and Zepp Life are separate apps; the export entry may live under Privacy or Account.",
    },
    helpUrl: "https://support.zepp.com/en/",
  },
  {
    id: "oppo-health",
    name: { zh: "OPPO 健康", en: "OPPO Health" },
    steps: {
      zh: [
        "打开「OPPO 健康」，进入「我的」。",
        "点「设置」→「隐私」→「导出我的数据」。",
        "选择数据范围并提交，导出文件会保存到手机或发送到邮箱。",
        "把 ZIP/CSV 拖进本应用。",
      ],
      en: [
        "Open OPPO Health and go to Me.",
        "Open Settings → Privacy → Export my data.",
        "Choose a range and submit; the export is saved on the phone or emailed.",
        "Drag the ZIP/CSV into this app.",
      ],
    },
    formats: "ZIP / CSV",
    includes: {
      zh: "步数、心率、睡眠、血氧、压力、运动记录。",
      en: "Steps, heart rate, sleep, SpO2, stress, and workouts.",
    },
    versionNote: {
      zh: "ColorOS 版本不同，入口可能在「隐私」或「账号与安全」下。",
      en: "Depending on ColorOS it may be under Privacy or Account & Security.",
    },
    helpUrl: "https://www.oppo.com/en/support/",
  },
  {
    id: "garmin-connect",
    name: { zh: "Garmin Connect", en: "Garmin Connect" },
    steps: {
      zh: [
        "在电脑浏览器打开 Garmin Connect，登录账号。",
        "进入「账户设置」→「数据管理」→「导出你的数据」。",
        "确认后下载 ZIP，内含 FIT/CSV/JSON 文件。",
        "把 ZIP 直接拖进本应用（无需解压）。",
      ],
      en: [
        "Open Garmin Connect in a desktop browser and sign in.",
        "Go to Account Settings → Data Management → Export Your Data.",
        "Confirm and download the ZIP containing FIT/CSV/JSON files.",
        "Drag the ZIP into this app (no need to unzip).",
      ],
    },
    formats: "ZIP（FIT / CSV / JSON）",
    includes: {
      zh: "步数、心率、睡眠、压力、血氧、体重、运动记录（含距离、时长、热量、平均心率）。",
      en: "Steps, heart rate, sleep, stress, SpO2, body mass, and workouts (distance, duration, calories, average heart rate).",
    },
    versionNote: {
      zh: "Garmin Connect 手机端通常不提供完整导出，请使用网页版；导出请求可能需要几分钟到数小时。",
      en: "The mobile app usually cannot export everything; use the web version. The request may take minutes to hours.",
    },
    helpUrl: "https://support.garmin.com/en-US/",
  },
  {
    id: "fitbit",
    name: { zh: "Fitbit", en: "Fitbit" },
    steps: {
      zh: [
        "在浏览器打开 fitbit.com 并登录。",
        "进入「设置」→「数据与隐私」→「导出数据」。",
        "选择「全部数据」或指定日期范围，确认后下载。",
        "把下载的 ZIP 拖进本应用。",
      ],
      en: [
        "Sign in at fitbit.com in a browser.",
        "Go to Settings → Data & Privacy → Export Data.",
        "Choose All Data or a date range and download.",
        "Drag the downloaded ZIP into this app.",
      ],
    },
    formats: "ZIP（CSV / JSON）",
    includes: {
      zh: "步数、心率、静息心率、睡眠、体重、血氧、呼吸率、运动记录。",
      en: "Steps, heart rate, resting heart rate, sleep, body mass, SpO2, respiratory rate, and workouts.",
    },
    versionNote: {
      zh: "Fitbit 账号迁移到 Google 后，导出也可能通过 Google Takeout 完成；邮件里的下载链接有时效。",
      en: "After migrating to a Google account, exports may also be handled through Google Takeout; email links expire.",
    },
    helpUrl: "https://support.google.com/fitbit/",
  },
  {
    id: "withings",
    name: { zh: "Withings", en: "Withings" },
    steps: {
      zh: [
        "打开 Withings App，进入「设置」。",
        "点「隐私」→「导出我的数据」。",
        "选择时间范围并确认，导出文件会发送到账号邮箱。",
        "把邮件里的 CSV/ZIP 拖进本应用。",
      ],
      en: [
        "Open the Withings app and go to Settings.",
        "Tap Privacy → Export my data.",
        "Choose a range and confirm; the export is emailed to your account address.",
        "Drag the CSV/ZIP from the email into this app.",
      ],
    },
    formats: "CSV / ZIP",
    includes: {
      zh: "体重、体脂、血压、心率、睡眠、步数、运动记录。",
      en: "Body mass, body fat, blood pressure, heart rate, sleep, steps, and workouts.",
    },
    versionNote: {
      zh: "也可以在 Withings 网页版「Dashboard → Settings → Export my data」导出。",
      en: "You can also export from the Withings web dashboard under Settings → Export my data.",
    },
    helpUrl:
      "https://support.withings.com/hc/en-us/articles/31647944317201-Withings-App-Exporting-your-data",
  },
  {
    id: "google-fit",
    name: { zh: "Google Fit", en: "Google Fit" },
    steps: {
      zh: [
        "在浏览器打开 Google Takeout（takeout.google.com）并登录。",
        "点「取消全选」，只勾选「Fit」。",
        "选择导出格式与频率，创建导出。",
        "下载 ZIP 后拖进本应用。",
      ],
      en: [
        "Open Google Takeout (takeout.google.com) in a browser and sign in.",
        "Choose Deselect all, then select only Fit.",
        "Pick a format and frequency, then create the export.",
        "Download the ZIP and drag it into this app.",
      ],
    },
    formats: "ZIP（JSON / TCX）",
    includes: {
      zh: "步数、心率、睡眠、体重、运动记录（TCX）。",
      en: "Steps, heart rate, sleep, body mass, and workouts (TCX).",
    },
    versionNote: {
      zh: "Google Fit 已并入 Health Connect，历史数据仍可从 Takeout 导出；导出准备可能需要数小时。",
      en: "Google Fit has been folded into Health Connect; historical data is still available through Takeout, which can take hours to prepare.",
    },
    helpUrl: "https://support.google.com/fit/",
  },
] as const;

export const VENDOR_GUIDES_VERSION_NOTE = {
  zh: "厂商界面可能随 App 版本变化；如果找不到上述入口，请在应用内搜索「导出数据 / Download my data」。",
  en: "Vendor menus change between app versions. If you cannot find the entry, search the app for “export data” or “download my data”.",
};
