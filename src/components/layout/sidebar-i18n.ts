import i18n from "@/lib/i18n";

/**
 * 侧栏模块导航自带的 i18n bundle。
 * 只新增 `nav.*` 键，不覆盖共享 i18n 中已有的同名文案。
 */
const zh = {
  nav: {
    moduleCenter: "模块中心",
    modulesEmpty: "暂无已安装模块",
    modulesUnavailable: "模块不可用",
    viewAllModules: "查看全部模块",
  },
};

const en = {
  nav: {
    moduleCenter: "Module center",
    modulesEmpty: "No modules installed",
    modulesUnavailable: "Modules unavailable",
    viewAllModules: "View all modules",
  },
};

i18n.addResourceBundle("zh-CN", "translation", zh, true, false);
i18n.addResourceBundle("en-US", "translation", en, true, false);

export default i18n;
