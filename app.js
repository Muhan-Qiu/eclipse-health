/* eclipse health marketplace · static site behavior
   No dependencies, no telemetry. Index data and module copy are treated as untrusted text. */

(function () {
  "use strict";

  var root = document.documentElement;
  var LANG = (root.lang || "zh").toLowerCase().indexOf("en") === 0 ? "en" : "zh";
  var DEPTH = Number(document.body.dataset.depth || "1") === 2 ? 2 : 1;

  var STRINGS = {
    zh: {
      themeToLight: "切换到亮色主题",
      themeToDark: "切换到暗色主题",
      copied: "已复制",
      copyFailed: "复制失败",
      copy: "复制",
      moduleCount: function (n) { return n + " 个模块"; },
      indexMeta: function (date, signed, key) {
        return "索引生成于 " + date + " · " + (signed ? "索引已签名" : "索引未签名（开发模式）") +
          (key ? " · " + key : "") + " · 签名由应用安装器校验";
      },
      loadingTitle: "正在读取索引…",
      loadingText: "首次加载会同时读取官方与社区索引。",
      errorPublished: "索引尚未发布",
      errorUnavailable: "索引暂时不可用",
      retry: "重试",
      clearFilters: "清除筛选",
      emptyIndex: "索引里还没有模块",
      emptyOfficial: "官方索引尚未发布模块。开发者可以从提交 PR 开始。",
      emptyCommunity: "社区索引尚未收录模块。开发者可以通过 GitHub PR 提交。",
      noMatch: "没有匹配的模块",
      noMatchText: "试试其他关键词，或切换到另一索引。",
      verified: "已验证",
      unverified: "未审核",
      yanked: "已撤回",
      officialIndex: "官方索引",
      communityIndex: "社区索引 · 未审核",
      authorYanked: "作者已撤回",
      firstParty: "官方自研",
      details: "查看详情",
      download: "下载",
      downloadEhmod: "下载 .ehmod",
      basicInfo: "基本信息",
      author: "作者",
      version: "版本",
      license: "许可证",
      type: "类型",
      size: "大小",
      source: "来源",
      category: "分类",
      price: "价格",
      pricePaid: "付费（核心不处理支付）",
      priceSponsor: "赞助",
      permissionsTitle: "权限",
      noPermissions: "未申请额外权限。",
      unknownPermission: "未识别的权限，请谨慎评估",
      dependencies: "依赖",
      dependencyNote: "首次安装会为模块创建独立 venv 并联网安装这些依赖。",
      scan: "扫描结果",
      scanStatus: "状态",
      scanRisk: "风险",
      viewReport: "查看完整扫描报告",
      repo: "仓库与源码",
      homepage: "主页",
      sha: "SHA-256",
      nonDiagnostic: "非诊断声明",
      nonDiagnosticText: "模块输出不构成医疗建议，不是医疗器械，不用于诊断、治疗或替代专业医疗判断。",
      close: "关闭",
      yankedNotice: "该版本已被作者撤回，不建议新安装；已安装用户请考虑回滚。",
      communityNotice: "社区模块未经人工审核，仅经过自动扫描。安装前请自行评估来源与代码。",
      features: "能做什么",
      usage: "怎么用",
      inputs: "输入",
      outputs: "输出",
      goodFor: "适合",
      limits: "限制与边界",
      techNote: "技术说明",
      featureCount: function (n) { return n + " 项能力"; },
      errFetch: "无法读取索引文件。请确认已通过本地静态服务器打开本站（直接双击 HTML 文件时浏览器会阻止 fetch）。",
      err404: "索引尚未发布：对应目录下没有 index.json。",
      errJson: "索引文件不是合法 JSON。",
      errGeneric: "读取索引失败",
      types: {
        "device-adapter": "设备适配",
        "signal-engine": "信号引擎",
        "analysis-model": "分析模型",
        "health-domain": "健康领域",
        "dashboard-widget": "界面组件",
        exporter: "导出器",
        "ai-tool": "AI 工具",
        theme: "主题",
        locale: "语言包",
        "data-source": "数据源"
      },
      permissions: {
        "records:read": "读取记录、测量与分析结果",
        "records:write": "创建或更新记录",
        "records:delete": "删除记录（高风险，默认不授予）",
        "files:user-selected": "读取你主动选择的文件",
        "files:export": "写入你确认的导出目录",
        network: "访问网络（仅限 allowedHosts 列出的主机）",
        llm: "调用你配置的 LLM",
        "models:download": "下载模型权重",
        "ui:custom": "在沙箱中提供自定义界面",
        "system:notify": "发送系统通知",
        "system:background": "最小化后继续在后台运行"
      },
      risks: { green: "低风险", yellow: "中风险", orange: "高风险", red: "拒绝安装" },
      categories: {
        devices: "设备", signal: "信号", analysis: "分析", health: "健康", ui: "界面",
        export: "导出", ai: "AI", theme: "主题", locale: "语言", data: "数据", other: "其他"
      },
      unknownType: "未知类型",
      uncategorized: "未分类"
    },
    en: {
      themeToLight: "Switch to light theme",
      themeToDark: "Switch to dark theme",
      copied: "Copied",
      copyFailed: "Copy failed",
      copy: "Copy",
      moduleCount: function (n) { return n + (n === 1 ? " module" : " modules"); },
      indexMeta: function (date, signed, key) {
        return "Index generated " + date + " · " + (signed ? "signed index" : "unsigned index (development)") +
          (key ? " · " + key : "") + " · signature verified by the app installer";
      },
      loadingTitle: "Loading index…",
      loadingText: "The first load reads both the official and community indexes.",
      errorPublished: "Index not published yet",
      errorUnavailable: "Index temporarily unavailable",
      retry: "Retry",
      clearFilters: "Clear filters",
      emptyIndex: "No modules in this index yet",
      emptyOfficial: "The official index has no modules yet. Developers can start with a pull request.",
      emptyCommunity: "The community index has no modules yet. Developers can submit one via GitHub PR.",
      noMatch: "No matching modules",
      noMatchText: "Try another keyword, or switch to the other index.",
      verified: "Verified",
      unverified: "Unreviewed",
      yanked: "Withdrawn",
      officialIndex: "Official index",
      communityIndex: "Community index · unreviewed",
      authorYanked: "Withdrawn by author",
      firstParty: "First-party",
      details: "Details",
      download: "Download",
      downloadEhmod: "Download .ehmod",
      basicInfo: "Basic info",
      author: "Author",
      version: "Version",
      license: "License",
      type: "Type",
      size: "Size",
      source: "Source",
      category: "Category",
      price: "Price",
      pricePaid: "Paid (the core does not handle payments)",
      priceSponsor: "Sponsorship",
      permissionsTitle: "Permissions",
      noPermissions: "Requests no extra permissions.",
      unknownPermission: "Unrecognised permission — evaluate carefully",
      dependencies: "Dependencies",
      dependencyNote: "The first install creates a dedicated venv for the module and fetches these dependencies.",
      scan: "Scan result",
      scanStatus: "Status",
      scanRisk: "Risk",
      viewReport: "Open full scan report",
      repo: "Repository and source",
      homepage: "Homepage",
      sha: "SHA-256",
      nonDiagnostic: "Non-diagnostic notice",
      nonDiagnosticText: "Module output is not medical advice. It is not a medical device and must not be used for diagnosis, treatment, or as a substitute for professional judgement.",
      close: "Close",
      yankedNotice: "This version was withdrawn by the author. Do not install it for new use; existing users should consider rolling back.",
      communityNotice: "Community modules are not manually reviewed, only automatically scanned. Assess the source and code before installing.",
      features: "What it does",
      usage: "How to use it",
      inputs: "Inputs",
      outputs: "Outputs",
      goodFor: "Good for",
      limits: "Limits",
      techNote: "Technical note",
      featureCount: function (n) { return n + (n === 1 ? " capability" : " capabilities"); },
      errFetch: "Could not read the index. Open this site through a local static server — browsers block fetch() when an HTML file is opened directly.",
      err404: "Index not published: index.json is missing from that directory.",
      errJson: "The index file is not valid JSON.",
      errGeneric: "Could not read the index",
      types: {
        "device-adapter": "Device adapter",
        "signal-engine": "Signal engine",
        "analysis-model": "Analysis model",
        "health-domain": "Health domain",
        "dashboard-widget": "Dashboard widget",
        exporter: "Exporter",
        "ai-tool": "AI tool",
        theme: "Theme",
        locale: "Locale pack",
        "data-source": "Data source"
      },
      permissions: {
        "records:read": "Read records, measurements and analysis results",
        "records:write": "Create or update records",
        "records:delete": "Delete records (high risk, never granted by default)",
        "files:user-selected": "Read files you explicitly choose",
        "files:export": "Write to an export directory you confirm",
        network: "Access the network (only hosts listed in allowedHosts)",
        llm: "Call the LLM you configured",
        "models:download": "Download model weights",
        "ui:custom": "Provide custom UI inside a sandbox",
        "system:notify": "Send system notifications",
        "system:background": "Keep running in the background when minimised"
      },
      risks: { green: "Low risk", yellow: "Medium risk", orange: "High risk", red: "Install refused" },
      categories: {
        devices: "Devices", signal: "Signal", analysis: "Analysis", health: "Health", ui: "UI",
        export: "Export", ai: "AI", theme: "Theme", locale: "Locale", data: "Data", other: "Other"
      },
      unknownType: "Unknown type",
      uncategorized: "Uncategorised"
    }
  };

  var T = STRINGS[LANG];
  var LOCALE = LANG === "en" ? "en-US" : "zh-CN";

  /* ------------------------------------------------------------ theme */
  function currentTheme() {
    if (root.dataset.theme === "light" || root.dataset.theme === "dark") {
      return root.dataset.theme;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function syncThemeButton() {
    var button = document.getElementById("theme-toggle");
    if (!button) return;
    var isDark = currentTheme() === "dark";
    button.setAttribute("aria-pressed", String(isDark));
    button.setAttribute("aria-label", isDark ? T.themeToLight : T.themeToDark);
  }

  function setupTheme() {
    var button = document.getElementById("theme-toggle");
    syncThemeButton();
    if (!button) return;
    button.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem("eh-theme", next);
      } catch (error) {
        /* storage may be unavailable; theme still applies for this page */
      }
      syncThemeButton();
    });
    var media = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function () {
      if (!root.dataset.theme) syncThemeButton();
    };
    if (typeof media.addEventListener === "function") media.addEventListener("change", onChange);
    else if (typeof media.addListener === "function") media.addListener(onChange);
  }

  /* ------------------------------------------------------------ nav */
  function setupNav() {
    var page = document.body.dataset.page;
    var links = document.querySelectorAll(".site-nav a[data-nav]");
    links.forEach(function (link) {
      if (link.dataset.nav === page) link.setAttribute("aria-current", "page");
    });
  }

  /* ------------------------------------------------------------ clipboard */
  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      try {
        var area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        var ok = document.execCommand("copy");
        document.body.removeChild(area);
        if (ok) resolve();
        else reject(new Error("copy failed"));
      } catch (error) {
        reject(error);
      }
    });
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text).catch(function () {
        return legacyCopy(text);
      });
    }
    return legacyCopy(text);
  }

  function setupCopyButtons() {
    document.querySelectorAll("[data-copy-target]").forEach(function (button) {
      button.addEventListener("click", function () {
        var target = document.getElementById(button.dataset.copyTarget);
        if (!target) return;
        var label = button.textContent;
        copyText(target.textContent.trim())
          .then(function () {
            button.textContent = T.copied;
            window.setTimeout(function () {
              button.textContent = label;
            }, 1600);
          })
          .catch(function () {
            button.textContent = T.copyFailed;
            window.setTimeout(function () {
              button.textContent = label;
            }, 1600);
          });
      });
    });
  }

  /* ------------------------------------------------------------ helpers */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeHttpUrl(value) {
    if (typeof value !== "string") return null;
    var trimmed = value.trim();
    if (!/^https?:\/\//i.test(trimmed)) return null;
    try {
      var parsed = new URL(trimmed);
      return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
    } catch (error) {
      return null;
    }
  }

  function formatBytes(value) {
    var bytes = Number(value);
    if (!Number.isFinite(bytes) || bytes <= 0) return "—";
    var units = ["B", "KB", "MB", "GB"];
    var index = 0;
    var size = bytes;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return size.toFixed(index === 0 ? 0 : 1) + " " + units[index];
  }

  function formatDate(value) {
    if (typeof value !== "string" || !value) return "";
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    try {
      return date.toLocaleString(LOCALE, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (error) {
      return value;
    }
  }

  function categoryLabel(value) {
    return T.categories[value] || value;
  }

  function typeLabel(type) {
    return T.types[type] || type || T.unknownType;
  }

  function permissionText(value) {
    return T.permissions[value] || T.unknownPermission;
  }

  function riskLabel(value) {
    return T.risks[value] || value || "";
  }

  /* ------------------------------------------------------------ paths */
  function indexPath(source) {
    return (DEPTH === 2 ? "../.." : "..") + "/" + source + "/index.json";
  }

  function copyPath() {
    return (DEPTH === 2 ? ".." : ".") + "/module-copy." + LANG + ".json";
  }

  /* ------------------------------------------------------------ index loading */
  var state = {
    source: "official",
    query: "",
    category: "all",
    copy: {},
    sources: {
      official: { status: "idle", modules: [], error: "", meta: null },
      community: { status: "idle", modules: [], error: "", meta: null },
    },
    modules: [],
  };

  var lastOpener = null;

  function pickVersionEntry(raw) {
    if (!Array.isArray(raw.versions) || raw.versions.length === 0) return null;
    if (raw.latest) {
      var match = raw.versions.find(function (item) {
        return item && item.version === raw.latest;
      });
      if (match) return match;
    }
    return raw.versions[0] || null;
  }

  function normalizeEntries(raw, source) {
    var list = Array.isArray(raw.modules) ? raw.modules : [];
    return list
      .filter(function (item) {
        return item && typeof item.id === "string" && item.id;
      })
      .map(function (item) {
        var versionEntry = pickVersionEntry(item);
        var author = item.author;
        if (author && typeof author === "object") author = author.name;
        var categories = [];
        [item.categories, item.tags].forEach(function (group) {
          if (Array.isArray(group)) {
            group.forEach(function (tag) {
              if (typeof tag === "string" && tag && categories.indexOf(tag) === -1) {
                categories.push(tag);
              }
            });
          }
        });
        var permissions = versionEntry && Array.isArray(versionEntry.permissions)
          ? versionEntry.permissions
          : Array.isArray(item.permissions)
            ? item.permissions
            : [];
        var download = versionEntry && versionEntry.download ? versionEntry.download : null;
        return {
          id: item.id,
          name: typeof item.name === "string" && item.name ? item.name : item.id,
          version: (versionEntry && versionEntry.version) || item.latest || item.version || "",
          type: item.type || "",
          description:
            (typeof item.summary === "string" && item.summary) ||
            (typeof item.description === "string" && item.description) ||
            "",
          author: typeof author === "string" ? author : "",
          license: typeof item.license === "string" ? item.license : "",
          homepage: item.homepage || "",
          repository: item.repository || "",
          permissions: permissions,
          dependencies: Array.isArray(item.dependencies) ? item.dependencies : [],
          categories: categories,
          verified:
            source === "official"
              ? item.verified !== false && !(item.author && item.author.verified === false)
              : false,
          file: (download && download.url) || item.file || "",
          downloadUrl: download && download.url ? download.url : "",
          size: (download && download.size) || item.size,
          sha256: (download && download.sha256) || item.sha256 || "",
          scan: (versionEntry && versionEntry.scan) || item.scan || null,
          yanked: Boolean(versionEntry && versionEntry.yanked),
          pricing: item.pricing || null,
          source: source,
        };
      });
  }

  function loadIndex(source) {
    var slot = state.sources[source];
    if (slot.status !== "idle") return Promise.resolve();
    slot.status = "loading";
    return fetch(indexPath(source), { cache: "no-store", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (raw) {
        var modules = normalizeEntries(raw, source);
        slot.modules = modules;
        slot.meta = {
          generatedAt: raw.generatedAt || "",
          keyId: raw.keyId || "",
          signed: typeof raw.signature === "string" && raw.signature.length > 0,
          schemaVersion: raw.schemaVersion || "",
        };
        slot.status = modules.length === 0 ? "empty" : "ready";
      })
      .catch(function (error) {
        slot.status = "error";
        slot.error = friendlyLoadError(error);
      });
  }

  function loadCopy() {
    return fetch(copyPath(), { cache: "no-store", credentials: "same-origin" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (raw) {
        state.copy = raw && typeof raw.modules === "object" && raw.modules ? raw.modules : {};
      })
      .catch(function () {
        state.copy = {};
      });
  }

  function friendlyLoadError(error) {
    var message = error && error.message ? error.message : "";
    if (/Failed to fetch|NetworkError|Load failed/i.test(message)) {
      return T.errFetch;
    }
    if (/HTTP 404/.test(message)) {
      return T.err404;
    }
    if (/JSON|Unexpected token|parse/i.test(message)) {
      return T.errJson;
    }
    return T.errGeneric + (message ? ": " + message : ".");
  }

  function activeSlot() {
    return state.sources[state.source];
  }

  function withCopy(item) {
    var copy = state.copy[item.id] || {};
    var merged = {
      id: item.id,
      version: item.version,
      type: item.type,
      description: item.description,
      author: item.author,
      license: item.license,
      homepage: item.homepage,
      repository: item.repository,
      permissions: item.permissions,
      dependencies: item.dependencies,
      categories: item.categories,
      verified: item.verified,
      file: item.file,
      downloadUrl: item.downloadUrl,
      size: item.size,
      sha256: item.sha256,
      scan: item.scan,
      yanked: item.yanked,
      pricing: item.pricing,
      source: item.source,
      name: typeof copy.name === "string" && copy.name ? copy.name : item.name,
      tagline: typeof copy.tagline === "string" ? copy.tagline : "",
      summary: typeof copy.summary === "string" && copy.summary ? copy.summary : item.description,
      features: Array.isArray(copy.features) ? copy.features : [],
      usage: Array.isArray(copy.usage) ? copy.usage : [],
      inputs: Array.isArray(copy.inputs) ? copy.inputs : [],
      outputs: Array.isArray(copy.outputs) ? copy.outputs : [],
      goodFor: typeof copy.goodFor === "string" ? copy.goodFor : "",
      limits: Array.isArray(copy.limits) ? copy.limits : [],
      techNote: typeof copy.techNote === "string" ? copy.techNote : "",
      firstParty: item.id.indexOf("org.eclipsehealth.") === 0,
    };
    return merged;
  }

  function allModules() {
    return state.sources.official.modules
      .concat(state.sources.community.modules)
      .map(withCopy);
  }

  var FIRST_PARTY_ORDER = {
    "org.eclipsehealth.relay-ecg": 0,
    "org.eclipsehealth.relay-sleep": 1,
  };

  function currentModules() {
    var slot = activeSlot();
    var query = state.query.trim().toLowerCase();
    return slot.modules
      .map(withCopy)
      .filter(function (item) {
        if (state.category !== "all") {
          var haystackCategories = item.categories.concat([item.type]);
          if (haystackCategories.indexOf(state.category) === -1) return false;
        }
        if (!query) return true;
        var featureText = item.features.map(function (feature) {
          return (feature.title || "") + " " + (feature.text || "");
        });
        var haystack = [
          item.id,
          item.name,
          item.tagline,
          item.summary,
          item.author,
          item.type,
          typeLabel(item.type),
          item.license,
        ]
          .concat(item.categories)
          .concat(item.categories.map(categoryLabel))
          .concat(featureText)
          .join(" ")
          .toLowerCase();
        return haystack.indexOf(query) !== -1;
      })
      .sort(function (a, b) {
        if (a.firstParty !== b.firstParty) return a.firstParty ? -1 : 1;
        if (a.firstParty) {
          var orderA = FIRST_PARTY_ORDER[a.id];
          var orderB = FIRST_PARTY_ORDER[b.id];
          if (orderA !== undefined || orderB !== undefined) {
            return (orderA === undefined ? 99 : orderA) - (orderB === undefined ? 99 : orderB);
          }
        }
        if (a.verified !== b.verified) return a.verified ? -1 : 1;
        return a.name.localeCompare(b.name, LANG === "en" ? "en" : "zh-CN");
      });
  }

  function buildCategoryChips() {
    var container = document.getElementById("category-chips");
    if (!container) return;
    var slot = activeSlot();
    var counts = new Map();
    slot.modules.forEach(function (item) {
      var labels = item.categories.length ? item.categories : [item.type || "other"];
      labels.forEach(function (label) {
        counts.set(label, (counts.get(label) || 0) + 1);
      });
    });
    var labels = Array.from(counts.keys()).sort(function (a, b) {
      return counts.get(b) - counts.get(a) || String(a).localeCompare(String(b), LANG === "en" ? "en" : "zh-CN");
    });

    container.textContent = "";
    if (labels.length === 0) return;

    function addChip(value, text) {
      var button = el("button", "chip", text);
      button.type = "button";
      button.dataset.category = value;
      button.setAttribute("aria-pressed", String(state.category === value));
      button.addEventListener("click", function () {
        state.category = value;
        buildCategoryChips();
        renderModules();
      });
      container.appendChild(button);
    }

    addChip("all", LANG === "en" ? "All" : "全部");
    labels.slice(0, 12).forEach(function (label) {
      addChip(label, categoryLabel(label));
    });
    if (state.category !== "all" && labels.indexOf(state.category) === -1) {
      addChip(state.category, categoryLabel(state.category));
    }
  }

  function renderModules() {
    var grid = document.getElementById("module-results");
    var count = document.getElementById("result-count");
    var meta = document.getElementById("index-meta");
    if (!grid) return;

    var slot = activeSlot();
    var modules = currentModules();
    grid.textContent = "";

    if (count) {
      if (slot.status === "ready" || slot.status === "empty") {
        count.textContent = T.moduleCount(modules.length);
      } else {
        count.textContent = "";
      }
    }

    if (meta) {
      if (slot.meta && slot.meta.generatedAt) {
        meta.textContent = T.indexMeta(
          formatDate(slot.meta.generatedAt),
          slot.meta.signed,
          slot.meta.keyId
        );
      } else {
        meta.textContent = "";
      }
    }

    if (slot.status === "idle" || slot.status === "loading") {
      var loading = el("div", "state-box");
      loading.appendChild(el("h2", null, T.loadingTitle));
      loading.appendChild(el("p", null, T.loadingText));
      grid.appendChild(loading);
      return;
    }

    if (slot.status === "error") {
      var failed = el("div", "state-box");
      var failedTitle = slot.error.indexOf(T.err404) === 0 || slot.error === T.err404
        ? T.errorPublished
        : T.errorUnavailable;
      failed.appendChild(el("h2", null, failedTitle));
      failed.appendChild(el("p", null, slot.error));
      var retry = el("button", "btn btn-ghost btn-small", T.retry);
      retry.type = "button";
      retry.style.marginTop = "1rem";
      retry.addEventListener("click", function () {
        slot.status = "idle";
        slot.error = "";
        loadIndex(state.source).then(function () {
          buildCategoryChips();
          renderModules();
        });
      });
      failed.appendChild(retry);
      grid.appendChild(failed);
      return;
    }

    if (slot.status === "empty" && state.query.trim() === "") {
      var emptyIndex = el("div", "state-box");
      emptyIndex.appendChild(el("h2", null, T.emptyIndex));
      emptyIndex.appendChild(
        el("p", null, state.source === "official" ? T.emptyOfficial : T.emptyCommunity)
      );
      grid.appendChild(emptyIndex);
      return;
    }

    if (modules.length === 0) {
      var noMatch = el("div", "state-box");
      noMatch.appendChild(el("h2", null, T.noMatch));
      noMatch.appendChild(el("p", null, T.noMatchText));
      var clear = el("button", "btn btn-ghost btn-small", T.clearFilters);
      clear.type = "button";
      clear.style.marginTop = "1rem";
      clear.addEventListener("click", function () {
        state.query = "";
        state.category = "all";
        var input = document.getElementById("module-search");
        if (input) input.value = "";
        buildCategoryChips();
        renderModules();
      });
      noMatch.appendChild(clear);
      grid.appendChild(noMatch);
      return;
    }

    var fragment = document.createDocumentFragment();
    modules.forEach(function (item) {
      fragment.appendChild(buildModuleCard(item));
    });
    grid.appendChild(fragment);
  }

  function buildModuleCard(item) {
    var card = el("article", "module-card");

    var top = el("div", "module-card-top");
    var heading = el("div");
    heading.appendChild(el("h2", null, item.name));
    heading.appendChild(el("div", "module-id", item.id));
    top.appendChild(heading);
    var badgeGroup = el("div", "module-card-badges");
    if (item.firstParty) badgeGroup.appendChild(el("span", "badge badge-accent", T.firstParty));
    else if (item.verified) badgeGroup.appendChild(el("span", "badge badge-ok", T.verified));
    if (item.source === "community") badgeGroup.appendChild(el("span", "badge badge-warn", T.unverified));
    if (item.yanked) badgeGroup.appendChild(el("span", "badge badge-danger", T.yanked));
    top.appendChild(badgeGroup);
    card.appendChild(top);

    if (item.tagline) card.appendChild(el("p", "module-tagline", item.tagline));

    if (item.features.length) {
      var points = el("ul", "module-points");
      item.features.slice(0, 3).forEach(function (feature) {
        if (feature && feature.title) points.appendChild(el("li", null, feature.title));
      });
      if (points.childNodes.length) card.appendChild(points);
    } else if (item.description) {
      card.appendChild(el("p", "module-desc", item.description));
    }

    var meta = el("div", "module-meta");
    if (item.version) meta.appendChild(el("span", "badge", "v" + item.version));
    meta.appendChild(el("span", "badge badge-accent", typeLabel(item.type)));
    if (item.license) meta.appendChild(el("span", "badge", item.license));
    if (item.features.length) {
      meta.appendChild(el("span", "module-count", T.featureCount(item.features.length)));
    }
    card.appendChild(meta);

    var actions = el("div", "module-actions");
    var detail = el("button", "btn btn-ghost btn-small", T.details);
    detail.type = "button";
    detail.addEventListener("click", function () {
      lastOpener = detail;
      openDialog(item);
    });
    actions.appendChild(detail);

    var download = resolveDownload(item);
    if (download) {
      var link = el("a", "btn btn-primary btn-small", T.download);
      link.href = download;
      link.rel = "noopener";
      link.setAttribute("download", "");
      actions.appendChild(link);
    }
    card.appendChild(actions);
    return card;
  }

  function resolveDownload(item) {
    var direct = safeHttpUrl(item.downloadUrl);
    if (direct) return direct;
    if (!item.file) return null;
    var fileUrl = safeHttpUrl(item.file);
    if (fileUrl) return fileUrl;
    var baseName = item.file.split(/[\\/]/).pop();
    if (!baseName || baseName === ".." || baseName === ".") return null;
    var repository = safeHttpUrl(item.repository);
    if (repository && item.version) {
      var trimmed = repository.replace(/\/+$/, "").replace(/\.git$/i, "");
      if (/^https:\/\/github\.com\/[^/]+\/[^/]+$/i.test(trimmed)) {
        return trimmed + "/releases/download/v" + encodeURIComponent(item.version) + "/" +
          encodeURIComponent(baseName);
      }
    }
    if (/^\.\.\/|^[A-Za-z0-9._/-]+$/.test(item.file) && item.file.indexOf("..") === -1) {
      try {
        var resolved = new URL("../" + item.file.replace(/^\/+/, ""), window.location.href);
        if (resolved.protocol === "http:" || resolved.protocol === "https:") return resolved.href;
      } catch (error) {
        return null;
      }
    }
    return null;
  }

  function appendList(parent, className, values) {
    if (!values.length) return false;
    var list = el("ul", className || null);
    values.forEach(function (value) {
      if (value !== undefined && value !== null && String(value).trim()) {
        list.appendChild(el("li", null, value));
      }
    });
    if (!list.childNodes.length) return false;
    parent.appendChild(list);
    return true;
  }

  function openDialog(item) {
    var dialog = document.getElementById("module-dialog");
    if (!dialog || typeof dialog.showModal !== "function") return;

    document.getElementById("dialog-id").textContent = item.id;
    document.getElementById("dialog-title").textContent = item.name;

    var badges = document.getElementById("dialog-badges");
    badges.textContent = "";
    badges.appendChild(el("span", "badge badge-accent", typeLabel(item.type)));
    badges.appendChild(el(
      "span",
      "badge " + (item.source === "official" ? "badge-ok" : "badge-warn"),
      item.source === "official" ? T.officialIndex : T.communityIndex
    ));
    if (item.firstParty) badges.appendChild(el("span", "badge badge-accent", T.firstParty));
    if (item.version) badges.appendChild(el("span", "badge", "v" + item.version));
    if (item.yanked) badges.appendChild(el("span", "badge badge-danger", T.authorYanked));

    var body = document.getElementById("dialog-body");
    body.textContent = "";

    if (item.tagline) body.appendChild(el("p", "dialog-tagline", item.tagline));
    if (item.summary) body.appendChild(el("p", null, item.summary));

    if (item.yanked) {
      body.appendChild(el("p", "notice-inline", T.yankedNotice));
    }

    if (item.source === "community") {
      body.appendChild(el("p", "notice-inline", T.communityNotice));
    }

    if (item.features.length) {
      body.appendChild(el("h3", null, T.features));
      var featureList = el("ul", "feature-list");
      item.features.forEach(function (feature) {
        if (!feature) return;
        var row = el("li");
        if (feature.title) row.appendChild(el("strong", null, feature.title));
        if (feature.text) row.appendChild(el("span", null, feature.text));
        featureList.appendChild(row);
      });
      body.appendChild(featureList);
    }

    if (item.usage.length) {
      body.appendChild(el("h3", null, T.usage));
      var steps = el("ol", "steps");
      item.usage.forEach(function (step) {
        steps.appendChild(el("li", null, step));
      });
      body.appendChild(steps);
    }

    if (item.inputs.length || item.outputs.length) {
      var spec = el("div", "spec-grid");
      if (item.inputs.length) {
        var inBlock = el("div", "spec-block");
        inBlock.appendChild(el("h4", null, T.inputs));
        appendList(inBlock, null, item.inputs);
        spec.appendChild(inBlock);
      }
      if (item.outputs.length) {
        var outBlock = el("div", "spec-block");
        outBlock.appendChild(el("h4", null, T.outputs));
        appendList(outBlock, null, item.outputs);
        spec.appendChild(outBlock);
      }
      body.appendChild(spec);
    }

    if (item.goodFor) {
      body.appendChild(el("h3", null, T.goodFor));
      body.appendChild(el("p", null, item.goodFor));
    }

    if (item.limits.length) {
      body.appendChild(el("h3", null, T.limits));
      appendList(body, "limit-list", item.limits);
    }

    body.appendChild(el("h3", null, T.basicInfo));
    var dl = el("dl", "detail-list");
    function addPair(label, value) {
      if (!value) return;
      dl.appendChild(el("dt", null, label));
      dl.appendChild(el("dd", null, value));
    }
    addPair(T.author, item.author);
    addPair(T.version, item.version);
    addPair(T.license, item.license);
    addPair(T.type, typeLabel(item.type));
    addPair(T.size, item.size ? formatBytes(item.size) : "");
    addPair(T.source, item.source === "official" ? T.officialIndex : T.communityIndex);
    if (item.categories.length) addPair(T.category, item.categories.map(categoryLabel).join(" · "));
    if (item.pricing && item.pricing.model && item.pricing.model !== "free") {
      addPair(T.price, item.pricing.model === "paid" ? T.pricePaid : T.priceSponsor);
    }
    body.appendChild(dl);

    body.appendChild(el("h3", null, T.permissionsTitle + " (" + item.permissions.length + ")"));
    if (item.permissions.length === 0) {
      body.appendChild(el("p", null, T.noPermissions));
    } else {
      var list = el("ul", "permission-list");
      item.permissions.forEach(function (permission) {
        var row = el("li");
        row.appendChild(el("code", null, permission));
        row.appendChild(el("span", null, permissionText(permission)));
        list.appendChild(row);
      });
      body.appendChild(list);
    }

    if (item.dependencies.length) {
      body.appendChild(el("h3", null, T.dependencies));
      var deps = el("div");
      item.dependencies.forEach(function (dep) {
        deps.appendChild(el("span", "tag", dep));
        deps.appendChild(document.createTextNode(" "));
      });
      body.appendChild(deps);
      body.appendChild(el("p", "fine-print", T.dependencyNote));
    }

    if (item.scan && (item.scan.status || item.scan.risk)) {
      body.appendChild(el("h3", null, T.scan));
      var line = el("p", null,
        T.scanStatus + ": " + (item.scan.status || "—") +
        " · " + T.scanRisk + ": " + riskLabel(item.scan.risk) +
        (item.scan.scannedAt ? " · " + formatDate(item.scan.scannedAt) : ""));
      body.appendChild(line);
      var report = safeHttpUrl(item.scan.reportUrl);
      if (report) {
        var reportLink = el("a", "btn btn-ghost btn-small", T.viewReport);
        reportLink.href = report;
        reportLink.rel = "noopener";
        body.appendChild(reportLink);
      }
    }

    if (item.techNote) {
      var details = el("details", "tech-details");
      details.appendChild(el("summary", null, T.techNote));
      details.appendChild(el("p", null, item.techNote));
      body.appendChild(details);
    }

    var links = el("div");
    links.style.marginTop = "1rem";
    var repo = safeHttpUrl(item.repository);
    if (repo) {
      var repoLink = el("a", null, T.repo);
      repoLink.href = repo;
      repoLink.rel = "noopener";
      links.appendChild(repoLink);
    }
    var homepage = safeHttpUrl(item.homepage);
    if (homepage) {
      if (repo) links.appendChild(document.createTextNode(" · "));
      var homeLink = el("a", null, T.homepage);
      homeLink.href = homepage;
      homeLink.rel = "noopener";
      links.appendChild(homeLink);
    }
    if (links.childNodes.length) body.appendChild(links);

    if (item.sha256) {
      body.appendChild(el("h3", null, T.sha));
      var mono = el("div", "mono-line");
      mono.appendChild(el("code", null, item.sha256));
      var copyButton = el("button", "copy-btn", T.copy);
      copyButton.type = "button";
      copyButton.addEventListener("click", function () {
        copyText(item.sha256).then(function () {
          copyButton.textContent = T.copied;
          window.setTimeout(function () { copyButton.textContent = T.copy; }, 1600);
        }).catch(function () {
          copyButton.textContent = T.copyFailed;
          window.setTimeout(function () { copyButton.textContent = T.copy; }, 1600);
        });
      });
      mono.appendChild(copyButton);
      body.appendChild(mono);
    }

    body.appendChild(el("h3", null, T.nonDiagnostic));
    body.appendChild(el("p", null, T.nonDiagnosticText));

    var foot = document.getElementById("dialog-foot");
    foot.textContent = "";
    var close = el("button", "btn btn-ghost btn-small", T.close);
    close.type = "button";
    close.addEventListener("click", function () {
      dialog.close();
    });
    foot.appendChild(close);
    var download = resolveDownload(item);
    if (download) {
      var downloadLink = el("a", "btn btn-primary btn-small", T.downloadEhmod);
      downloadLink.href = download;
      downloadLink.rel = "noopener";
      downloadLink.setAttribute("download", "");
      foot.appendChild(downloadLink);
    }

    dialog.showModal();
    var closeButton = document.getElementById("dialog-close");
    if (closeButton) closeButton.focus();
  }

  function findModule(id) {
    var match = null;
    ["official", "community"].forEach(function (source) {
      state.sources[source].modules.forEach(function (item) {
        if (!match && item.id === id) match = withCopy(item);
      });
    });
    return match;
  }

  function setupModulesPage() {
    var grid = document.getElementById("module-results");
    if (!grid) return;

    var params = new URLSearchParams(window.location.search);
    var requested = params.get("source");
    if (requested === "community") state.source = "community";

    var search = document.getElementById("module-search");
    var tabs = document.querySelectorAll(".tab[data-source]");

    function syncTabs() {
      tabs.forEach(function (tab) {
        var selected = tab.dataset.source === state.source;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
        var panel = document.getElementById("module-results");
        if (panel) panel.setAttribute("aria-labelledby", "tab-" + state.source);
      });
      window.setTimeout(function () {
        renderModules();
      }, 0);
    }

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        if (state.source === tab.dataset.source) return;
        state.source = tab.dataset.source;
        state.category = "all";
        syncTabs();
        loadIndex(state.source).then(function () {
          buildCategoryChips();
          renderModules();
        });
      });
      tab.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        var index = Array.prototype.indexOf.call(tabs, tab);
        var next = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
        tabs[next].focus();
        tabs[next].click();
      });
    });

    if (search) {
      search.addEventListener("input", function () {
        state.query = search.value || "";
        renderModules();
      });
    }

    var dialog = document.getElementById("module-dialog");
    if (dialog) {
      dialog.addEventListener("click", function (event) {
        if (event.target === dialog) dialog.close();
      });
      dialog.addEventListener("close", function () {
        if (lastOpener && document.contains(lastOpener)) lastOpener.focus();
      });
      var closeButton = document.getElementById("dialog-close");
      if (closeButton) {
        closeButton.addEventListener("click", function () {
          dialog.close();
        });
      }
    }

    syncTabs();
    Promise.all([loadIndex("official"), loadIndex("community"), loadCopy()]).then(function () {
      buildCategoryChips();
      renderModules();

      var requestedModule = params.get("module");
      if (requestedModule) {
        var module = findModule(requestedModule);
        if (module) {
          if (module.source !== state.source) {
            state.source = module.source;
            syncTabs();
            buildCategoryChips();
            renderModules();
          }
          lastOpener = null;
          openDialog(module);
        }
      }
    });
  }

  /* ------------------------------------------------------------ boot */
  setupTheme();
  setupNav();
  setupCopyButtons();
  setupModulesPage();
})();
