import i18n from "@/lib/i18n";

/**
 * 模块声明式页面自带的 i18n bundle。
 * 只新增 `modulePage.*`，不修改共享 i18n 文件。
 */
const zh = {
  modulePage: {
    eyebrow: "模块页面",
    pagesTitle: "模块页面",
    openPage: "打开页面",
    refresh: "刷新",
    loading: "正在加载页面…",
    loadError: "无法加载模块页面",
    loadErrorDesc: "无法读取模块贡献点，请确认本地后端正在运行。",
    notFoundTitle: "页面不可用",
    notFoundDesc: "页面不存在，或模块已被卸载。",
    disabledTitle: "模块未启用",
    disabledDesc: "启用模块后即可打开此页面。",
    missingModuleTitle: "模块未安装",
    missingModuleDesc: "该模块未安装或已被卸载。",
    backToModules: "返回模块",
    blocks: {
      list: "列表",
      table: "表格",
      detail: "详情",
      form: "表单",
    },
    unsupportedBlock: "不支持的块",
    unsupportedBlockDesc: "当前版本不支持组件「{{component}}」。",
    invalidBlock: "块配置无效",
    invalidBlockDesc: "该块缺少必要的数据源或字段。",
    rpcError: "数据加载失败",
    rpcErrorDesc: "模块调用失败：{{message}}",
    emptyList: "列表为空",
    emptyTable: "表格为空",
    emptyDetail: "没有可显示的字段",
    submit: "提交",
    submitting: "正在提交…",
    submitSuccess: "已提交",
    submitFailed: "提交失败",
    noSubmitMethod: "该表单未声明提交方法",
    required: "必填",
    invalidNumber: "请输入数字",
    selectPlaceholder: "请选择",
    emptyValue: "—",
    yes: "是",
    no: "否",
  },
};

const en = {
  modulePage: {
    eyebrow: "Module page",
    pagesTitle: "Module pages",
    openPage: "Open page",
    refresh: "Refresh",
    loading: "Loading page…",
    loadError: "Cannot load module page",
    loadErrorDesc:
      "Could not read module contributions. Make sure the local backend is running.",
    notFoundTitle: "Page unavailable",
    notFoundDesc: "The page does not exist, or the module was uninstalled.",
    disabledTitle: "Module disabled",
    disabledDesc: "Enable the module to open this page.",
    missingModuleTitle: "Module not installed",
    missingModuleDesc: "This module is not installed or was removed.",
    backToModules: "Back to modules",
    blocks: {
      list: "List",
      table: "Table",
      detail: "Details",
      form: "Form",
    },
    unsupportedBlock: "Unsupported block",
    unsupportedBlockDesc: "Component “{{component}}” is not supported in this version.",
    invalidBlock: "Invalid block",
    invalidBlockDesc: "This block is missing its required data source or fields.",
    rpcError: "Cannot load data",
    rpcErrorDesc: "Module call failed: {{message}}",
    emptyList: "The list is empty",
    emptyTable: "The table is empty",
    emptyDetail: "No fields to show",
    submit: "Submit",
    submitting: "Submitting…",
    submitSuccess: "Submitted",
    submitFailed: "Submit failed",
    noSubmitMethod: "This form declares no submit method",
    required: "Required",
    invalidNumber: "Enter a number",
    selectPlaceholder: "Select…",
    emptyValue: "—",
    yes: "Yes",
    no: "No",
  },
};

i18n.addResourceBundle("zh-CN", "translation", zh, true, false);
i18n.addResourceBundle("en-US", "translation", en, true, false);

export default i18n;
