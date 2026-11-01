/* eclipse health marketplace · static site behavior
   No dependencies, no telemetry. Index data is treated as untrusted text. */

(function () {
  "use strict";

  var root = document.documentElement;

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
    button.setAttribute("aria-label", isDark ? "切换到亮色主题" : "切换到暗色主题");
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
            button.textContent = "已复制";
            window.setTimeout(function () {
              button.textContent = label;
            }, 1600);
          })
          .catch(function () {
            button.textContent = "复制失败";
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
      return date.toLocaleString("zh-CN", {
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

  var TYPE_LABELS = {
    "device-adapter": "设备适配",
    "signal-engine": "信号引擎",
    "analysis-model": "分析模型",
    "health-domain": "健康领域",
    "dashboard-widget": "界面组件",
    exporter: "导出器",
    "ai-tool": "AI 工具",
    theme: "主题",
    locale: "语言包",
    "data-source": "数据源",
  };

  var PERMISSION_TEXT = {
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
    "system:background": "最小化后继续在后台运行",
  };

  var RISK_LABELS = {
    green: "低风险",
    yellow: "中风险",
    orange: "高风险",
    red: "拒绝安装",
  };

  var CATEGORY_LABELS = {
    devices: "设备",
    signal: "信号",
    analysis: "分析",
    health: "健康",
    ui: "界面",
    export: "导出",
    ai: "AI",
    theme: "主题",
    locale: "语言",
    data: "数据",
    other: "其他",
  };

  function categoryLabel(value) {
    return CATEGORY_LABELS[value] || value;
  }

  function typeLabel(type) {
    return TYPE_LABELS[type] || type || "未知类型";
  }

  /* ------------------------------------------------------------ index loading */
  var INDEX_PATHS = {
    official: "official/index.json",
    community: "community/index.json",
  };

  var state = {
    source: "official",
    query: "",
    category: "all",
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
    var url = INDEX_PATHS[source];
    return fetch(url, { cache: "no-store", credentials: "same-origin" })
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

  function friendlyLoadError(error) {
    var message = error && error.message ? error.message : "";
    if (/Failed to fetch|NetworkError|Load failed/i.test(message)) {
      return "无法读取索引文件。请确认已通过本地静态服务器打开本站（直接双击 HTML 文件时浏览器会阻止 fetch）。";
    }
    if (/HTTP 404/.test(message)) {
      return "索引尚未发布：对应目录下没有 index.json。";
    }
    if (/JSON|Unexpected token|parse/i.test(message)) {
      return "索引文件不是合法 JSON。";
    }
    return "读取索引失败" + (message ? "：" + message : "。");
  }

  function activeSlot() {
    return state.sources[state.source];
  }

  function currentModules() {
    var slot = activeSlot();
    var query = state.query.trim().toLowerCase();
    return slot.modules
      .filter(function (item) {
        if (state.category !== "all") {
          var haystackCategories = item.categories.concat([item.type]);
          if (haystackCategories.indexOf(state.category) === -1) return false;
        }
        if (!query) return true;
        var haystack = [
          item.id,
          item.name,
          item.description,
          item.author,
          item.type,
          typeLabel(item.type),
          item.license,
        ]
          .concat(item.categories)
          .concat(item.categories.map(categoryLabel))
          .join(" ")
          .toLowerCase();
        return haystack.indexOf(query) !== -1;
      })
      .sort(function (a, b) {
        if (a.verified !== b.verified) return a.verified ? -1 : 1;
        return a.name.localeCompare(b.name, "zh-CN");
      });
  }

  function buildCategoryChips() {
    var container = document.getElementById("category-chips");
    if (!container) return;
    var slot = activeSlot();
    var counts = new Map();
    slot.modules.forEach(function (item) {
      var labels = item.categories.length ? item.categories : [item.type || "未分类"];
      labels.forEach(function (label) {
        counts.set(label, (counts.get(label) || 0) + 1);
      });
    });
    var labels = Array.from(counts.keys()).sort(function (a, b) {
      return counts.get(b) - counts.get(a) || String(a).localeCompare(String(b), "zh-CN");
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

    addChip("all", "全部");
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
        count.textContent = modules.length + " 个模块";
      } else {
        count.textContent = "";
      }
    }

    if (meta) {
      if (slot.meta && slot.meta.generatedAt) {
        var signatureText = slot.meta.signed ? "索引已签名" : "索引未签名（开发模式）";
        var keyText = slot.meta.keyId ? " · " + slot.meta.keyId : "";
        meta.textContent =
          "索引生成于 " + formatDate(slot.meta.generatedAt) + " · " + signatureText + keyText +
          " · 签名由应用安装器校验";
      } else {
        meta.textContent = "";
      }
    }

    if (slot.status === "idle" || slot.status === "loading") {
      var loading = el("div", "state-box");
      loading.appendChild(el("h2", null, "正在读取索引…"));
      loading.appendChild(el("p", null, "首次加载会同时读取官方与社区索引。"));
      grid.appendChild(loading);
      return;
    }

    if (slot.status === "error") {
      var failed = el("div", "state-box");
      var failedTitle = slot.error.indexOf("索引尚未发布") === 0 ? "索引尚未发布" : "索引暂时不可用";
      failed.appendChild(el("h2", null, failedTitle));
      failed.appendChild(el("p", null, slot.error));
      var retry = el("button", "btn btn-ghost btn-small", "重试");
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
      emptyIndex.appendChild(el("h2", null, "索引里还没有模块"));
      emptyIndex.appendChild(
        el("p", null, state.source === "official"
          ? "官方索引尚未发布模块。开发者可以从提交 PR 开始。"
          : "社区索引尚未收录模块。开发者可以通过 GitHub PR 提交。")
      );
      grid.appendChild(emptyIndex);
      return;
    }

    if (modules.length === 0) {
      var noMatch = el("div", "state-box");
      noMatch.appendChild(el("h2", null, "没有匹配的模块"));
      noMatch.appendChild(el("p", null, "试试其他关键词，或切换到另一索引。"));
      var clear = el("button", "btn btn-ghost btn-small", "清除筛选");
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
    if (item.verified) top.appendChild(el("span", "badge badge-ok", "已验证"));
    else if (item.source === "community") top.appendChild(el("span", "badge badge-warn", "未审核"));
    card.appendChild(top);

    if (item.description) card.appendChild(el("p", "module-desc", item.description));

    var meta = el("div", "module-meta");
    if (item.version) meta.appendChild(el("span", "badge", "v" + item.version));
    meta.appendChild(el("span", "badge badge-accent", typeLabel(item.type)));
    if (item.license) meta.appendChild(el("span", "badge", item.license));
    if (item.yanked) meta.appendChild(el("span", "badge badge-danger", "已撤回"));
    card.appendChild(meta);

    var actions = el("div", "module-actions");
    var detail = el("button", "btn btn-ghost btn-small", "查看详情");
    detail.type = "button";
    detail.addEventListener("click", function () {
      lastOpener = detail;
      openDialog(item);
    });
    actions.appendChild(detail);

    var download = resolveDownload(item);
    if (download) {
      var link = el("a", "btn btn-primary btn-small", "下载");
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
      item.source === "official" ? "官方索引" : "社区索引 · 未审核"
    ));
    if (item.version) badges.appendChild(el("span", "badge", "v" + item.version));
    if (item.yanked) badges.appendChild(el("span", "badge badge-danger", "作者已撤回"));

    var body = document.getElementById("dialog-body");
    body.textContent = "";

    if (item.description) {
      body.appendChild(el("p", null, item.description));
    }

    if (item.yanked) {
      body.appendChild(el("p", "notice-inline", "该版本已被作者撤回，不建议新安装；已安装用户请考虑回滚。"));
    }

    if (item.source === "community") {
      body.appendChild(el("p", "notice-inline", "社区模块未经人工审核，仅经过自动扫描。安装前请自行评估来源与代码。"));
    }

    body.appendChild(el("h3", null, "基本信息"));
    var dl = el("dl", "detail-list");
    function addPair(label, value) {
      if (!value) return;
      dl.appendChild(el("dt", null, label));
      dl.appendChild(el("dd", null, value));
    }
    addPair("作者", item.author);
    addPair("版本", item.version);
    addPair("许可证", item.license);
    addPair("类型", typeLabel(item.type));
    addPair("大小", item.size ? formatBytes(item.size) : "");
    addPair("来源", item.source === "official" ? "官方索引" : "社区索引");
    if (item.categories.length) addPair("分类", item.categories.map(categoryLabel).join(" · "));
    if (item.pricing && item.pricing.model && item.pricing.model !== "free") {
      addPair("价格", item.pricing.model === "paid" ? "付费（核心不处理支付）" : "赞助");
    }
    body.appendChild(dl);

    body.appendChild(el("h3", null, "权限（" + item.permissions.length + "）"));
    if (item.permissions.length === 0) {
      body.appendChild(el("p", null, "未申请额外权限。"));
    } else {
      var list = el("ul", "permission-list");
      item.permissions.forEach(function (permission) {
        var row = el("li");
        row.appendChild(el("code", null, permission));
        row.appendChild(el("span", null, PERMISSION_TEXT[permission] || "未识别的权限，请谨慎评估"));
        list.appendChild(row);
      });
      body.appendChild(list);
    }

    if (item.dependencies.length) {
      body.appendChild(el("h3", null, "依赖"));
      var deps = el("div");
      item.dependencies.forEach(function (dep) {
        deps.appendChild(el("span", "tag", dep));
        deps.appendChild(document.createTextNode(" "));
      });
      body.appendChild(deps);
      body.appendChild(el("p", "fine-print", "首次安装会为模块创建独立 venv 并联网安装这些依赖。"));
    }

    if (item.scan && (item.scan.status || item.scan.risk)) {
      body.appendChild(el("h3", null, "扫描结果"));
      var risk = item.scan.risk && RISK_LABELS[item.scan.risk] ? RISK_LABELS[item.scan.risk] : (item.scan.risk || "未知");
      var scanLine = el("p", null,
        "状态：" + (item.scan.status || "未知") + " · 风险：" + risk +
        (item.scan.scannedAt ? " · " + formatDate(item.scan.scannedAt) : ""));
      body.appendChild(scanLine);
      var report = safeHttpUrl(item.scan.reportUrl);
      if (report) {
        var reportLink = el("a", "btn btn-ghost btn-small", "查看完整扫描报告");
        reportLink.href = report;
        reportLink.rel = "noopener";
        body.appendChild(reportLink);
      }
    }

    var links = el("div");
    links.style.marginTop = "1rem";
    var repo = safeHttpUrl(item.repository);
    if (repo) {
      var repoLink = el("a", null, "仓库与源码");
      repoLink.href = repo;
      repoLink.rel = "noopener";
      links.appendChild(repoLink);
    }
    var homepage = safeHttpUrl(item.homepage);
    if (homepage) {
      if (repo) links.appendChild(document.createTextNode(" · "));
      var homeLink = el("a", null, "主页");
      homeLink.href = homepage;
      homeLink.rel = "noopener";
      links.appendChild(homeLink);
    }
    if (links.childNodes.length) body.appendChild(links);

    if (item.sha256) {
      body.appendChild(el("h3", null, "SHA-256"));
      var mono = el("div", "mono-line");
      mono.appendChild(el("code", null, item.sha256));
      var copyButton = el("button", "copy-btn", "复制");
      copyButton.type = "button";
      copyButton.addEventListener("click", function () {
        copyText(item.sha256).then(function () {
          copyButton.textContent = "已复制";
          window.setTimeout(function () { copyButton.textContent = "复制"; }, 1600);
        }).catch(function () {
          copyButton.textContent = "复制失败";
          window.setTimeout(function () { copyButton.textContent = "复制"; }, 1600);
        });
      });
      mono.appendChild(copyButton);
      body.appendChild(mono);
    }

    body.appendChild(el("h3", null, "非诊断声明"));
    body.appendChild(el(
      "p",
      null,
      "模块输出不构成医疗建议，不是医疗器械，不用于诊断、治疗或替代专业医疗判断。"
    ));

    var foot = document.getElementById("dialog-foot");
    foot.textContent = "";
    var close = el("button", "btn btn-ghost btn-small", "关闭");
    close.type = "button";
    close.addEventListener("click", function () {
      dialog.close();
    });
    foot.appendChild(close);
    var download = resolveDownload(item);
    if (download) {
      var downloadLink = el("a", "btn btn-primary btn-small", "下载 .ehmod");
      downloadLink.href = download;
      downloadLink.rel = "noopener";
      downloadLink.setAttribute("download", "");
      foot.appendChild(downloadLink);
    }

    dialog.showModal();
    var closeButton = document.getElementById("dialog-close");
    if (closeButton) closeButton.focus();
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
    Promise.all([loadIndex("official"), loadIndex("community")]).then(function () {
      buildCategoryChips();
      renderModules();
    });
  }

  /* ------------------------------------------------------------ boot */
  setupTheme();
  setupNav();
  setupCopyButtons();
  setupModulesPage();
})();
