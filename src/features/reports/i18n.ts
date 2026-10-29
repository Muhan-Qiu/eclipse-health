import i18n from "@/lib/i18n";

/**
 * 报告功能自带的 i18n bundle。
 *
 * 只做「增量合并」：深合并、同名键覆盖。B3-02 拥有的 `src/lib/i18n/*` 不修改，
 * 页面加载时把本模块的键挂到现有 translation 命名空间下。
 */
const zh = {
  reports: {
    composer: {
      title: "新建报告",
      pageEyebrow: "分享与归档",
      description:
        "选择一条记录，生成 PDF 报告或 PNG 分享卡。渲染与文件都留在本机。",
      record: "选择记录",
      searchPlaceholder: "搜索日期、设备或标签",
      recent: "最近 {{count}} 条记录",
      settings: "输出设置",
      noRecords: "还没有可生成报告的记录",
      noRecordsDesc: "先在记录页导入一份 ECG，并完成一次分析。",
      noMatch: "没有匹配的记录",
      noMatchDesc: "换个关键词，或清空搜索。",
      clearSearch: "清空搜索",
      goRecords: "打开记录库",
      current: "当前记录",
      openRecord: "查看记录",
      analysisStatus: {
        completed: "已分析",
        queued: "排队中",
        running: "分析中",
        failed: "分析失败",
        none: "未分析",
      },
      format: "格式",
      formats: {
        pdf: "PDF 报告",
        png: "PNG 分享卡",
      },
      template: "模板",
      templates: {
        simple: "简洁版",
        detailed: "详细版",
        doctor: "医生版",
      },
      templateHints: {
        simple: "1 页：波形 + 4 个关键指标",
        detailed: "2 页：全部测量、分类比例、质量与警告",
        doctor: "2 页：完整测量表与技术细节",
      },
      pngHint:
        "分享卡固定版式（1080×1350），适合微信 / 小红书；始终不含姓名与备注。",
      redact: "脱敏",
      redactHint: "隐藏成员姓名、备注与原始文件名，并在报告上加水印。",
      redactWarning: "关闭脱敏后，报告会包含成员姓名与备注，分享前请确认。",
      generate: "生成报告",
      generating: "正在生成…",
      generatingPdf: "正在渲染 PDF…",
      generatingPng: "正在渲染分享卡…",
      needsAnalysis: "这条记录还没有完成的分析，先打开记录发起一次分析。",
      failedAnalysis:
        "最近一次分析失败；如更早有完成的分析，仍可尝试生成。",
      successTitle: "报告已生成",
      successDesc: "{{fileName}} · {{size}} · {{template}}",
      download: "下载",
      openPdf: "打开 PDF",
      previewAlt: "PNG 分享卡预览",
      errorTitle: "报告生成失败",
      errorUnknown: "生成失败，请稍后重试。",
    },
    history: {
      title: "报告历史",
      description: "{{date}} 的记录，共 {{count}} 份报告。",
      selectRecord: "选择一条记录后显示报告历史。",
      emptyTitle: "还没有报告",
      emptyDesc: "生成的报告会保存在本机，可随时下载或删除。",
      redacted: "脱敏",
      unredacted: "含个人信息",
      createdAt: "{{date}} 生成",
      download: "下载",
      open: "打开",
      delete: "删除",
      deleteTitle: "删除这份报告？",
      deleteDesc: "报告文件与元数据会从本机删除，无法恢复。",
      deleting: "正在删除…",
      deleteFailed: "删除失败",
      loadError: "报告历史加载失败",
      retry: "重试",
    },
    errors: {
      analysisRequired: "这条记录还没有完成的分析，请先分析后再生成报告。",
      unknownTemplate: "未知的报告模板。",
      unsupportedFormat: "不支持的报告格式。",
      fontMissing:
        "本机缺少中文字体，无法生成报告。请安装微软雅黑/黑体，或设置 EH_REPORT_FONT。",
      network: "无法连接到本地后端，请确认服务已启动。",
      timeout: "生成超时，请稍后重试。",
      validation: "请求参数无效。",
    },
  },
};

const en = {
  reports: {
    composer: {
      title: "New report",
      pageEyebrow: "Share & archive",
      description:
        "Pick a record to create a PDF report or a PNG share card. Rendering and files stay on this device.",
      record: "Record",
      searchPlaceholder: "Search date, device or tag",
      recent: "{{count}} recent records",
      settings: "Output settings",
      noRecords: "No records to report on yet",
      noRecordsDesc:
        "Import an ECG on the records page and finish an analysis first.",
      noMatch: "No matching records",
      noMatchDesc: "Try another keyword or clear the search.",
      clearSearch: "Clear search",
      goRecords: "Open records",
      current: "Selected record",
      openRecord: "View record",
      analysisStatus: {
        completed: "Analysed",
        queued: "Queued",
        running: "Analysing",
        failed: "Analysis failed",
        none: "Not analysed",
      },
      format: "Format",
      formats: {
        pdf: "PDF report",
        png: "PNG share card",
      },
      template: "Template",
      templates: {
        simple: "Simple",
        detailed: "Detailed",
        doctor: "Doctor",
      },
      templateHints: {
        simple: "1 page: waveform + 4 key metrics",
        detailed: "2 pages: all measurements, class ratios, quality and warnings",
        doctor: "2 pages: full measurement table and technical details",
      },
      pngHint:
        "The share card uses a fixed 1080×1350 layout for social sharing and never includes names or notes.",
      redact: "Redact",
      redactHint:
        "Hide the member name, notes and original file name, and add a watermark.",
      redactWarning:
        "With redaction off, the report includes the member name and notes. Check before sharing.",
      generate: "Generate report",
      generating: "Generating…",
      generatingPdf: "Rendering PDF…",
      generatingPng: "Rendering share card…",
      needsAnalysis:
        "This record has no completed analysis. Open the record and run one first.",
      failedAnalysis:
        "The latest analysis failed; an earlier completed analysis may still work.",
      successTitle: "Report generated",
      successDesc: "{{fileName}} · {{size}} · {{template}}",
      download: "Download",
      openPdf: "Open PDF",
      previewAlt: "PNG share card preview",
      errorTitle: "Report generation failed",
      errorUnknown: "Could not generate the report. Try again.",
    },
    history: {
      title: "Report history",
      description: "{{date}} · {{count}} report(s).",
      selectRecord: "Select a record to see its report history.",
      emptyTitle: "No reports yet",
      emptyDesc:
        "Generated reports are stored on this device and can be downloaded or deleted at any time.",
      redacted: "Redacted",
      unredacted: "Personal info",
      createdAt: "Generated {{date}}",
      download: "Download",
      open: "Open",
      delete: "Delete",
      deleteTitle: "Delete this report?",
      deleteDesc:
        "The report file and metadata are removed from this device and cannot be restored.",
      deleting: "Deleting…",
      deleteFailed: "Delete failed",
      loadError: "Could not load report history",
      retry: "Retry",
    },
    errors: {
      analysisRequired:
        "This record has no completed analysis. Analyse it before generating a report.",
      unknownTemplate: "Unknown report template.",
      unsupportedFormat: "Unsupported report format.",
      fontMissing:
        "No Chinese font is available on this device. Install Microsoft YaHei / SimHei or set EH_REPORT_FONT.",
      network: "Could not reach the local backend. Make sure it is running.",
      timeout: "Generation timed out. Try again.",
      validation: "Invalid request parameters.",
    },
  },
};

i18n.addResourceBundle("zh-CN", "translation", zh, true, true);
i18n.addResourceBundle("en-US", "translation", en, true, true);
