import i18n from "@/lib/i18n";

/**
 * 波形增强（B4-05）自带的 i18n bundle。
 *
 * 只做增量合并，不修改共享 `src/lib/i18n/*`；记录详情加载时把
 * 心搏列表、节律条、多导联、PNG 与快捷键的文案挂到现有命名空间下。
 */
const zh = {
  waveform: {
    controls: {
      layout: "波形布局",
      single: "单导联",
      grid: "多导联网格",
      export: "导出 PNG",
      exportView: "导出当前视图",
      exportFull: "导出整段记录",
      exporting: "正在生成 PNG…",
      exported: "PNG 已下载",
      exportFailed: "PNG 导出失败",
    },
    overview: {
      label: "节律条",
      aria: "整段记录节律条，总时长 {{duration}}，当前视窗 {{start}} 至 {{end}}",
      hint: "点击或拖动跳转",
      panHint: "方向键平移，Home / End 到首尾",
    },
    multiLead: {
      note: "分析仅使用 {{lead}} 导联（Cardia 单导联模型）；其余导联仅供展示，不代表 12 导联分析。",
      note_one:
        "分析仅使用 {{lead}} 导联（Cardia 单导联模型）；其余导联仅供展示，不代表 12 导联分析。",
      note_other:
        "分析仅使用 {{lead}} 导联（Cardia 单导联模型）；其余 {{count}} 个导联仅供展示，不代表 12 导联分析。",
      count: "{{count}} 个导联",
      loading: "正在加载导联…",
      partial: "{{loaded}} / {{total}} 个导联已加载",
    },
    scale: {
      mv: "{{value}} mV",
      seconds: "0.2 s",
    },
    png: {
      title: "心电波形",
      watermark: "非诊断用途 · NOT FOR DIAGNOSIS",
      meta: "{{lead}} · {{fs}} Hz · {{start}} – {{end}}",
      date: "记录时间 {{date}}",
      duration: "总时长 {{duration}}",
      layout: "布局",
      layouts: {
        single: "单导联",
        grid: "多导联（仅展示）",
      },
    },
    beatsTotal: "{{count}} 个心搏",
  },
  beatList: {
    title: "心搏列表",
    count: "{{shown}} / {{total}}",
    classFilter: "类别",
    allClasses: "全部类别",
    abnormalOnly: "只看异常",
    sort: "排序",
    sortAbnormal: "异常优先",
    sortTime: "按时间",
    timeRange: "时间（秒）",
    timeFrom: "起",
    timeTo: "止",
    columns: {
      index: "#",
      time: "时间",
      label: "类别",
      confidence: "置信度",
      rr: "RR",
    },
    select: "定位到第 {{index}} 搏",
    aria: "心搏列表，共 {{count}} 条",
    empty: "没有符合条件的心搏",
    emptyNoAnalysis: "完成一次分析后显示心搏列表",
    truncated: "列表仅显示前 {{limit}} 条（共 {{total}} 条）",
    current: "当前选中",
    normal: "N",
    abnormal: "异常",
    loading: "心搏加载中…",
  },
  qualityLegend: {
    title: "信号质量",
    legend: "图例",
    levels: {
      good: "良好",
      fair: "一般",
      poor: "较差",
      unknown: "未知",
    },
    columns: {
      time: "时间段",
      level: "等级",
      score: "质量",
      reason: "原因",
    },
    empty: "该记录没有质量区段",
    count: "{{count}} 个区段",
    thresholds: "良好 ≥ 82% · 一般 70–82% · 较差 < 70%",
    focus: "定位到 {{start}} – {{end}}",
    reasonUnknown: "未提供原因",
    footer: "底色 = 质量较低区段；点击区段可定位到波形。",
    more: "还有 {{count}} 个区段未列出",
  },
  shortcuts: {
    title: "快捷键",
    hint: "+ / - 缩放 · ← / → 平移 · 0 重置 · [ / ] 上/下一条 · Esc 取消选中",
    zoom: "+ / - 缩放",
    pan: "← / → 平移",
    reset: "0 重置",
    records: "[ / ] 上一条 / 下一条记录",
    beats: "[ / ] 上/下一搏（选中心搏后）",
    escape: "Esc 取消选中",
  },
};

const en: typeof zh = {
  waveform: {
    controls: {
      layout: "Waveform layout",
      single: "Single lead",
      grid: "Multi-lead grid",
      export: "Export PNG",
      exportView: "Export current view",
      exportFull: "Export full record",
      exporting: "Rendering PNG…",
      exported: "PNG downloaded",
      exportFailed: "PNG export failed",
    },
    overview: {
      label: "Rhythm strip",
      aria: "Whole-record rhythm strip, {{duration}}, current window {{start}} to {{end}}",
      hint: "Click or drag to jump",
      panHint: "Arrow keys pan, Home / End jump to edges",
    },
    multiLead: {
      note: "Analysis uses the {{lead}} lead only (Cardia is a single-lead model); the other leads are displayed for review only and do not constitute 12-lead analysis.",
      note_one:
        "Analysis uses the {{lead}} lead only (Cardia is a single-lead model); the other lead is displayed for review only and does not constitute 12-lead analysis.",
      note_other:
        "Analysis uses the {{lead}} lead only (Cardia is a single-lead model); the other {{count}} leads are displayed for review only and do not constitute 12-lead analysis.",
      count: "{{count}} leads",
      loading: "Loading leads…",
      partial: "{{loaded}} / {{total}} leads loaded",
    },
    scale: {
      mv: "{{value}} mV",
      seconds: "0.2 s",
    },
    png: {
      title: "ECG waveform",
      watermark: "NOT FOR DIAGNOSIS · 非诊断用途",
      meta: "{{lead}} · {{fs}} Hz · {{start}} – {{end}}",
      date: "Recorded {{date}}",
      duration: "Total {{duration}}",
      layout: "Layout",
      layouts: {
        single: "Single lead",
        grid: "Multi-lead (display only)",
      },
    },
    beatsTotal: "{{count}} beats",
  },
  beatList: {
    title: "Beat list",
    count: "{{shown}} / {{total}}",
    classFilter: "Class",
    allClasses: "All classes",
    abnormalOnly: "Abnormal only",
    sort: "Sort",
    sortAbnormal: "Abnormal first",
    sortTime: "By time",
    timeRange: "Time (s)",
    timeFrom: "From",
    timeTo: "To",
    columns: {
      index: "#",
      time: "Time",
      label: "Class",
      confidence: "Confidence",
      rr: "RR",
    },
    select: "Go to beat {{index}}",
    aria: "Beat list, {{count}} rows",
    empty: "No beats match the filters",
    emptyNoAnalysis: "Run an analysis to see the beat list",
    truncated: "Showing the first {{limit}} of {{total}} beats",
    current: "Selected",
    normal: "N",
    abnormal: "Abnormal",
    loading: "Loading beats…",
  },
  qualityLegend: {
    title: "Signal quality",
    legend: "Legend",
    levels: {
      good: "Good",
      fair: "Fair",
      poor: "Poor",
      unknown: "Unknown",
    },
    columns: {
      time: "Window",
      level: "Level",
      score: "Quality",
      reason: "Reason",
    },
    empty: "This record has no quality segments",
    count: "{{count}} segments",
    thresholds: "Good ≥ 82% · Fair 70–82% · Poor < 70%",
    focus: "Go to {{start}} – {{end}}",
    reasonUnknown: "No reason provided",
    footer: "Shaded bands mark lower-quality segments; click a segment to locate it.",
    more: "{{count}} more segments not listed",
  },
  shortcuts: {
    title: "Shortcuts",
    hint: "+ / - zoom · ← / → pan · 0 reset · [ / ] previous/next · Esc clear selection",
    zoom: "+ / - zoom",
    pan: "← / → pan",
    reset: "0 reset",
    records: "[ / ] previous / next record",
    beats: "[ / ] previous / next beat (when a beat is selected)",
    escape: "Esc clear selection",
  },
};

i18n.addResourceBundle("zh-CN", "translation", zh, true, true);
i18n.addResourceBundle("en-US", "translation", en, true, true);

export {};
