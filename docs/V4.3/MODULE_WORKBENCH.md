# V4.3 模块工作台与 Agent 模块选择
> 本文描述 V4.3 的模块改版目标、工作台区块、Agent 请求契约与校验脚本。
> 契约事实源仍是 `schemas/module.schema.json`；本文只解释前端/后端如何消费它。

## 1. 改版目标
V4.3 把「模块中心」从安装管理页扩展为**每个模块独立的工作台**：

1. **独立工作台**：每个已启用模块拥有自己的入口页，集中展示身份、声明式页面、
   仪表盘卡片、工具试运行、权限与审计，而不是只能回到模块列表里操作。
2. **侧栏直达**：侧栏展示已安装模块（最多 12 个，超出引导到模块中心），点击即可
   进入该模块；模块状态用颜色点表示（运行中/已启用/崩溃/已禁用）。
3. **Agent「+」选模块**：助手输入框旁的「+」打开模块选择器。用户勾选的模块成为
   **本轮优先模块**：它们的工具排在工具目录前面，并在系统提示词中显式列出；
   **其他已安装且启用的模块工具仍然可用**，不是白名单过滤。
4. **会话记忆**：所选 `moduleIds` 随会话保存；切换会话时恢复，消息气泡显示本轮
   选择的模块，透明面板展示 `selectedModules` / `selectedModuleTools`。

## 2. 模块工作台区块与数据来源

| 区块 | 内容 | 数据来源 |
|---|---|---|
| 身份摘要 | 名称、id、版本、类型、作者、许可证、描述 | `GET /modules`、`GET /modules/{id}/manifest` |
| 声明式页面 | `contributes.ui.pages[]` 的 `text/list/table/detail/form` 块 | `GET /modules/contributions?type=pages` |
| 页面数据 | 每个块的 `source.method` 经模块自身 RPC 执行 | `POST /modules/{id}/rpc` `{method, params}` |
| 仪表盘卡片 | `contributes.ui.widgets[]` 的 stat/list/sparkline/bar/progress/text | `GET /modules/contributions?type=widgets` + 同一 RPC |
| 工具试运行 | `contributes.tools[]` 按 `inputSchema` 生成受控表单 | `GET /modules/contributions?type=tools` + RPC（`method = tool.id`） |
| 权限 | 模块请求/已授予的 scope，支持授予与撤销 | `GET/POST/DELETE /modules/{id}/permissions[/{scope}]` |
| 生命周期 | 启用/禁用/启动/停止/卸载 | `POST /modules/{id}/enable`、`/disable`、`/start`、`/stop`；`DELETE /modules/{id}` |
| 审计 | 安装、启用、权限变更等事件 | `GET /modules/audit?moduleId=...` |
| 安装/更新 | 上传 `.ehmod`、预览、安装、市场更新 | `POST /modules/preview-upload`、`POST /modules/install-upload` |

工作台只渲染 JSON 声明，不执行模块提供的任意前端代码；所有数据调用都限定在
`moduleId` 自己的 RPC 上，单个卡片失败只降级该卡片。

## 3. Agent 选择模块的请求契约
### 3.1 请求字段
`moduleIds?: string[]`，出现在：

- `POST /assistant/sessions`（新建会话时保存选择）
- `POST /assistant/sessions/{session_id}/messages`（每轮对话的选择）

约束：

- 最多 32 个；后端会 trim、去重、保持用户顺序（`normalize_module_ids`）。
- 省略或空数组表示**不指定优先模块**，使用全量模块工具。
- 每个 id 必须是已安装模块；未知 id 返回 `422 module_not_found`，已禁用模块返回
  `422 module_disabled`。
- 模块系统整体不可用时后端降级为空列表并继续对话，不让整轮请求 500。

### 3.2 后端行为
1. `_resolve_module_ids` 校验并规范化；会话表与消息 `data.moduleIds` 持久化。
2. `_selected_module_briefs` 汇总所选模块的 id、名称、类型、描述、工具和页面。
3. 系统提示词追加一段（`llm/agent.py::_render_selected_modules`）：

   > 本轮用户选择的模块（优先调用它们的工具；其他已安装模块的工具仍可用）：
   > - 模块名 (module.id) · 类型
   >   说明：...
   >   工具：工具名 (tool.id)、...
   >   页面：页面标题 (page.id)、...

   没有暴露工具的模块会提示「该模块没有向 Agent 暴露工具，可在模块工作台使用」。
   名称/描述/工具列表都有字符上限，避免第三方文案撑大提示词。
4. `ToolBox(preferred_module_ids=...)` 只对模块工具做**稳定排序**，把优先模块排前；
   不缩小可用工具集合。工具别名冲突时宁可少一个工具，也不让调用落到别的模块。
5. 透明面板返回 `selectedModules` 与 `selectedModuleTools`，便于用户核对本轮实际
   优先级；消息级 `moduleIds` 回显在用户消息上。

### 3.3 提示词语义
- 「优先」不是「只能」：模型仍可调用其他已启用模块的工具和内置工具。
- 选择模块不会自动读取模块数据，也不会绕过权限；工具调用仍受模块 scope 约束。
- 若用户没有选择模块，提示词不追加该段，行为与旧版一致。

## 4. 校验脚本
三个脚本均为 Node ESM，只依赖内置模块，从项目根目录运行。

### 4.1 `scripts/validate-modules.mjs`
```powershell
node scripts/validate-modules.mjs
node scripts/validate-modules.mjs --json
```

- 扫描 `modules/` 下所有 `module.json`，跳过 `node_modules`、`.venv`、`dist`、
  `releases`、`packaging` 等目录。
- 检查：UTF-8 BOM、U+FFFD、非法控制字符、JSON 可解析、必填字段、id 格式与长度、
  `ui.pages[]` 的块/列/表单字段、`tools[]`、`ui.widgets[]`。
- 输出 `[ERROR] 相对路径: 原因`、`[WARN] ...`，末尾
  `checked N manifests, M errors, K warnings`；有错误退出码 1。
- `--json` 输出 `{checked, errors, warnings, manifests}`，适合 CI 或编辑器插件。

### 4.2 `scripts/check-encoding.mjs`
```powershell
node scripts/check-encoding.mjs
node scripts/check-encoding.mjs --fix-bom
```

- 扫描 `src/`、`backend/src/`、`backend/tests/`、`modules/`、`schemas/`、`docs/`、
  `scripts/` 下的文本扩展名；排除构建产物、虚拟环境与缓存目录。
- 检查 UTF-8 BOM、UTF-16 BOM、非法 UTF-8 字节、U+FFFD（列出前 3 个行号）。
- 输出 `[ERROR] 路径:行号: 原因`，末尾 `scanned N files, M errors`；有错误退出码 1。
- `--fix-bom` 只删除文件开头的 UTF-8 BOM，不改变其余字节；修复后打印
  `[FIXED] ...`，其余编码错误仍然报错。

### 4.3 `scripts/check-module-package.mjs`
```powershell
node scripts/check-module-package.mjs dist/modules/example.ehmod
node scripts/check-module-package.mjs dist/modules
node scripts/check-module-package.mjs   # 默认扫描 dist/modules 与 releases
```

- 自实现最小 ZIP reader：解析 EOCD、中央目录与本地文件头，支持 stored/deflate
  （`node:zlib.inflateRawSync`）和基本 ZIP64；不处理加密 ZIP。
- 校验 PK 签名、能列出 `module.json`；校验其 UTF-8、无 BOM、无 U+FFFD、JSON 可解析。
- 若存在 `checksums.json`，按 `{algorithm, files: {相对路径: sha256}}` 逐文件比对
  `node:crypto` 计算的 sha256；缺失、格式错误、哈希不一致都报错。
- 输出 `[OK]/[FAIL]`、`[ERROR]`、`[WARN]`，末尾
  `checked N packages, M errors, K warnings`；有错误退出码 1。

### 4.4 常见错误处理

| 输出 | 处理 |
|---|---|
| `UTF-8 BOM` | 用 `check-encoding.mjs --fix-bom` 或编辑器「UTF-8 无 BOM」另存 |
| `U+FFFD` | 不要手工替换；从 git/原始包恢复，确认源文件本身是 UTF-8 |
| `JSON parse failed at line X` | 按行列和 `near:` 片段修复 JSON；注意尾逗号与中文引号 |
| `sha256 mismatch` | 重新打包 `.ehmod`，不要只改 `checksums.json` 掩盖内容变化 |
| `module not found/disabled` | 在模块中心安装并启用该模块，或从 `moduleIds` 移除 |

## 5. 编码规范
- 所有 `module.json`、源码、文档必须 **UTF-8 无 BOM**；禁止 U+FFFD 与裸控制字符。
- `.ehmod` 内的 `module.json`、`checksums.json`、源码同样必须 UTF-8 无 BOM。
- `checksums.json` 的 sha256 基于**文件原始字节**；任何重新编码（包括去 BOM）都会
  改变哈希，改完必须重新生成校验和并重新打包。
- Windows 编辑器保存时选择「UTF-8」而不是「UTF-8 with BOM」；PowerShell 输出重定向
  默认可能带 BOM，生成文件后跑一次 `check-encoding.mjs`。

## 6. 已知限制
- 声明式页面只支持 `text/list/table/detail/form` 五种块，复杂交互需模块提供 RPC，
  前端不执行模块代码。
- `moduleIds` 最多 32 个；只接受已启用模块；选择只影响工具排序与提示词，不改变
  权限与可用范围。
- 模块工具排序是「优先」而非「独占」；提示词中的模块描述有长度截断。
- `.ehmod` 校验器不支持加密 ZIP，ZIP64 仅覆盖常见字段；不校验 CRC，只校验
  `checksums.json` 列出的文件，未列出的文件只给 warning。
- `validate-modules.mjs` 只扫描仓库 `modules/`，不扫描 `backend/packaging`、
  `src-tauri/target` 下的安装副本；发布前应对实际 `.ehmod` 再跑包校验。
- `check-encoding.mjs` 只覆盖列出的目录与扩展名，不检查图片/模型等二进制资源；
  文件中若故意包含 U+FFFD 也会被报错。
- 侧栏直接展示所有已安装模块（保留 64 个的异常保护上限）；模块很多时侧栏需要滚动。
- 没有 `contributes.ui.pages` 的模块也有独立工作台（`/modules/:moduleId`），可查看状态、模型卡、工具、权限与审计；只是没有额外的声明式子页面。
- 工作台路由 `/modules/:moduleId` 已与声明式页面路由 `/modules/:moduleId/pages/:pageId` 一起注册；侧栏、模块中心「打开」按钮和详情面板都指向工作台。
