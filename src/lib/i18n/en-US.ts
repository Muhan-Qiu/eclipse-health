import type zhCN from "./zh-CN";

const enUS: typeof zhCN = {
  app: {
    name: "eclipse health",
    tagline: "The health you overlooked",
    skipToContent: "Skip to main content",
  },
  nav: {
    primary: "Primary navigation",
    dashboard: "Dashboard",
    records: "Records",
    trends: "Trends",
    reports: "Reports",
    assistant: "Assistant",
    modules: "Modules",
    settings: "Settings",
    about: "About",
    collapse: "Collapse navigation",
    expand: "Expand navigation",
  },
  topbar: {
    search: "Search or jump to",
    themeToggle: "Toggle light / dark theme",
    settings: "Open settings",
  },
  common: {
    demo: "Demo",
    demoNote: "Synthetic data for interface preview only",
    view: "View",
    back: "Back",
    all: "All",
    comingSoon: "Coming soon",
    planned: "Planned",
    close: "Close",
    minutes: "{{value}} min",
    seconds: "{{value}} s",
    version: "Version {{version}}",
    localOnly: "Stored on this device",
    loading: "Loading",
    loadError: "Failed to load",
  },
  greeting: {
    morning: "Good morning",
    afternoon: "Good afternoon",
    evening: "Good evening",
    night: "Still up",
  },
  dashboard: {
    eyebrow: "Overview",
    description:
      "Take a moment for your heart. Records and analysis stay on this device.",
    guide: {
      importTitle: "Import an ECG",
      importDesc: "Choose or drop a record to start a full analysis.",
      importAction: "Import ECG",
      exampleTitle: "Explore demo records",
      exampleDesc:
        "Three synthetic records to familiarise yourself with the interface. No real data.",
      exampleAction: "Open demo",
      formatsTitle: "See supported formats",
      formatsDesc:
        "Standard ECG files, wearable exports and hospital formats.",
      formatsAction: "View formats",
      importPending: "Import arrives in B2 — this is the interface shell for now.",
    },
    recent: {
      title: "Recent records",
      description: "ECG records stored on this device",
      emptyTitle: "No records yet",
      emptyDesc:
        "Once you import a record, its latest analysis and timestamp will appear here.",
      emptyAction: "Import ECG",
    },
    metrics: {
      title: "Metrics overview",
      note: "Synthetic data · not a diagnosis",
      heartRate: "Average heart rate",
      hrv: "HRV · RMSSD",
      abnormal: "Abnormal beat ratio",
      bpm: "bpm",
      ms: "ms",
      percent: "%",
      range: "Last 7 days",
    },
    waveform: {
      title: "ECG waveform",
      subtitle: "Lead II · 25 mm/s · synthetic",
      aria: "Synthetic ECG waveform example",
    },
    formats: {
      title: "Supported formats",
      description:
        "The first release ships adapters as modules. This is the planned list.",
      note: "Formats not listed here may arrive as community modules.",
      groups: {
        standard: "Standard files",
        wearable: "Wearables",
        hospital: "Hospital",
      },
      items: {
        wfdb: "WFDB (.hea / .dat / .atr)",
        csv: "CSV and raw float32",
        float32: "Raw float32, multi-lead",
        apple: "Apple Health export",
        samsung: "Samsung Health export",
        huawei: "Huawei Health export",
        scp: "SCP-ECG",
      },
    },
  },
  records: {
    eyebrow: "Records",
    title: "All records",
    description: "ECG records are stored on this device and can be exported.",
    filters: {
      time: "Time",
      device: "Device",
      tag: "Tag",
      allTime: "All time",
      last7: "Last 7 days",
      last30: "Last 30 days",
      allDevices: "All devices",
      allTags: "All tags",
    },
    emptyTitle: "No records yet",
    emptyDesc: "Import your first ECG and it will show up here.",
    emptyAction: "Import ECG",
    noMatchTitle: "No matching records",
    noMatchDesc: "Try widening the filters.",
    clearFilters: "Clear filters",
    duration: "Duration",
    leads: "Leads",
    sampleRate: "Sample rate",
    tagLabels: {
      morning: "Morning",
      resting: "Resting",
      postExercise: "Post-exercise",
      evening: "Evening",
    },
    status: {
      ready: "Ready",
      processing: "Processing",
      failed: "Failed",
    },
  },
  recordDetail: {
    eyebrow: "Record",
    notFound: "Record not found",
    notFoundDesc: "It may have been deleted, or the link is incomplete.",
    pendingTitle: "Analysis details arrive in B2",
    pendingDesc:
      "Waveform interaction, features and the result summary land in the next batch.",
    backToRecords: "Back to records",
    summaryTitle: "Result summary",
  },
  trends: {
    eyebrow: "Trends",
    title: "Long-term trends",
    description: "Heart rate, HRV and abnormal beats over time.",
    emptyTitle: "Trends are coming soon",
    emptyDesc:
      "With two or more records, daily aggregates and comparisons will appear here.",
  },
  reports: {
    eyebrow: "Reports",
    title: "Reports",
    description: "Turn an analysis into a shareable PDF or image.",
    emptyTitle: "Report generation is coming soon",
    emptyDesc:
      "Pick records, add notes and export PDF / PNG with a local copy kept.",
  },
  assistant: {
    eyebrow: "Assistant",
    title: "Analysis assistant",
    description:
      "Ask about metrics and waveforms in plain language, with visible tool calls.",
    emptyTitle: "Assistant is coming soon",
    emptyDesc:
      "Connect local Ollama or your own API key to ask about metrics and compare records.",
    note: "Health data is not sent over the network by default; online calls require your explicit permission.",
  },
  settings: {
    eyebrow: "Settings",
    title: "Settings",
    description: "Appearance, language and version. Choices are stored locally.",
    appearance: {
      title: "Appearance",
      description: "Follows the system by default, falling back to light.",
      mode: "Theme",
      light: "Light",
      dark: "Dark",
      system: "System",
      palette: "Palette",
    },
    language: {
      title: "Language",
      description:
        "Interface language. Dates and numbers follow the selected locale.",
      zh: "中文",
      en: "English",
    },
    about: {
      title: "About",
      version: "Version",
      license: "License",
      storage: "Storage",
      storageValue: "Local first · no telemetry",
    },
  },
  modules: {
    eyebrow: "Modules",
    title: "Modules",
    description:
      "Importers, analysis models, themes and UI components are all modules.",
    intro: "The module system is coming soon",
    introDesc:
      "Official modules ship with the installer; community modules can be installed, removed and replaced later.",
    cards: {
      importer: {
        title: "Importers",
        description:
          "WFDB, Samsung, Huawei, Apple Health and SCP-ECG arrive as adapter modules.",
      },
      model: {
        title: "Analysis models",
        description:
          "Cardia 2.0 is bundled; ONNX / safetensors model modules can be installed.",
      },
      theme: {
        title: "Themes & UI",
        description:
          "Monet palettes and declarative components; custom UI runs in a sandbox.",
      },
    },
    status: {
      preset: "Bundled",
      comingSoon: "Coming soon",
    },
    install: "Install",
  },
  about: {
    eyebrow: "About",
    title: "eclipse health",
    description:
      "A local-first ECG record and analysis tool. The health you overlooked.",
    sections: {
      what: {
        title: "What this is",
        body: "Import ECGs, inspect waveforms and analysis summaries, and follow changes over time. The first release focuses on ECG; other health domains arrive as modules.",
      },
      privacy: {
        title: "Privacy",
        body: "Records are stored on this device; no telemetry is sent; exported files are de-identified by default. Network access requires your explicit permission.",
      },
      stack: {
        title: "Stack",
        body: "Tauri 2 · React 19 · TypeScript · FastAPI · ONNX",
      },
      license: {
        title: "License",
        body: "The core is open source under GPL-3.0; modules declare their own licenses.",
      },
    },
  },
  palette: {
    title: "Palette",
    a: {
      name: "Water Lilies",
      description: "Deep teal and warm white — quiet and aqueous.",
    },
    b: {
      name: "Impression, Sunrise",
      description: "Deep blue and paper white — a warm morning light.",
    },
    c: {
      name: "The Japanese Footbridge",
      description: "Moss green and ivory — a calm, green stillness.",
    },
  },
  themeMode: {
    light: "Light",
    dark: "Dark",
    system: "System",
  },
  command: {
    title: "Command palette",
    description: "Search pages or run actions",
    placeholder: "Search pages or commands…",
    noResults: "No matching results",
    groups: {
      navigation: "Pages",
      appearance: "Appearance",
      palette: "Palette",
      help: "Help",
    },
  },
  notFound: {
    title: "Page not found",
    description: "The address may be wrong, or the page has moved.",
    action: "Back to dashboard",
  },
  a11y: {
    expandNav: "Expand navigation",
    collapseNav: "Collapse navigation",
    demoData: "Demo data badge",
    tagFilter: "Filter by tag",
    paletteOption: "Choose the {{name}} palette",
    themeOption: "Use the {{name}} theme",
    openCommand: "Open command palette",
    searchShortcut: "Ctrl K",
    status: "Status: {{status}}",
  },
};

export default enUS;
