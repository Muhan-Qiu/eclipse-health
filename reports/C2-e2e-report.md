# 报告 · C2 Stage C 端到端验收（真实安装 → 卡片/工具/页面 → 卸载）
状态：完成

## 交付
- `backend/tests/fixtures/modules/e2e/module.json`：`health-domain` 测试模块，声明 2 个 widget（`e2e-stat` stat / `e2e-list` list）、1 个 tool（`e2e.echo`）、1 个页面（`text` + `form` + `table`），权限 `records:read`、`llm`。
- `backend/tests/fixtures/modules/e2e/src/main.py`：stdio JSON-RPC worker，固定测试数据；页面表单只写进程内列表，不读写真实健康记录。
- `scripts/e2e_stage_c.py`：临时 `EH_DATA_DIR` + 端口 8790 启动真实后端，`pack_directory` 打包 `.ehmod`，全程走 REST；`--hold-seconds` 供截图，结束清理进程/数据目录，失败打印步骤并以 1 退出。
- 截图：`reports/screenshots/C2-dashboard-{light,dark}.png`、`C2-module-page-{light,dark}.png`。

## 验证
- 命令：`backend\.venv\Scripts\python.exe scripts\e2e_stage_c.py`
- 结果：**三次独立运行均 43 项 PASS、exit 0**（每次约 25s，含后端启动）；后续两次证明可重复（8790 空闲、临时目录已清理）。
- `backend\.venv\Scripts\python.exe -m ruff check backend/tests/fixtures/modules/e2e scripts/e2e_stage_c.py` → `All checks passed!`
- 未改生产代码；工作树里 `backend/src/**`、`src/**`、`schemas/**` 的改动均来自并行 Agent。

## 真实步骤与返回（节选）
| 步骤 | 实测 |
|---|---|
| 启动 | `/api/v1/health` 200；初始 contributions `{widgets:0,pages:0,tools:0}` |
| 安装（enable=false） | `state=installed`，默认授权 `llm,records:read`；贡献仍为 0 |
| 显式授权 + enable + start | 三个 `POST` 均 200；`state=running`；contributions `widgets=2 pages=1 tools=1`，每项带 `moduleName=Stage C E2E Fixture`、`moduleVersion=0.1.0` |
| widget RPC | `widget.stats` → `latest.bpm=72`；`widget.list` → 3 项（深睡/浅睡/心率） |
| page RPC | `page.form` → `note=seed-note`；`page.list` → 2 行；`page.submit` → `saved=true,count=3`；再查 `page.list` → 3 行含 `c2-submit` |
| tool RPC | `e2e.echo{text:"stage-c"}` → `{text:"stage-c",length:7,calls:7}` |
| 助手工具表 | 真实 `ToolBox.tool_specs()` 含 `m_cd643419_e2e_echo`，`parameters.additionalProperties=false`；`ToolBox.execute()` 返回 `text=assistant` |
| 边界 | 缺参 → 422 `INVALID_INPUT`；未知方法 → 404 `METHOD_NOT_FOUND`；`?type=bogus` → 422；禁用后 RPC → 409 `MODULE_DISABLED` |
| 撤销/重授 llm | 撤销后 `tools=0`、widgets/pages 不变；重新授予后 `tools=1` |
| disable | 三处同时消失，模块目录仍在 |
| 重新 enable + start | 三处恢复，worker 重启后 RPC 正常 |
| uninstall `keepData=false` | `uninstalled=true`；`modules/{id}` 目录消失；详情 404；contributions 清空且无残留 |

## 真实前端（可选项已做）
- 用 Vite dev（`VITE_API_BASE=http://127.0.0.1:8790/api/v1`）+ Playwright 打开真实前端：
  首页出现 2 张模块卡片（「E2E 心率」72 bpm、「E2E 列表」3 行）；模块页表单回填、表格渲染；
  在 UI 填备注 `c2-ui-submit` 点「提交」后 toast + 表格自动刷新出现新行（见 light 截图）。
- 有效会话内 `console.error` = 0；截图里的 4 条 `ERR_CONNECTION_REFUSED` 出现在杀掉后端后的 teardown 轮询，不是运行期错误。
- 助手页需 provider/会话才会显示工具痕迹，无 Key 无法截图；工具表已用助手实际消费的 `ToolBox` 目录+执行路径验证。

## 未做 / 偏离
- 未提交 `.ehmod`、未写 `uploads/`、未改 `prompts/`、未 commit。
- 截图模式为 `--hold-seconds` 人工停留；脚本正常模式不做浏览器截图（后端 venv 未装 Playwright）。

## 跨区问题（未修）
- `backend/src/eclipse_health_backend/modules/manager.py:uninstall`：`keepData=true`（前端卸载对话框默认值）会在卸载后**重建空的 `modules/{id}/` 目录**；E2E 用 `keepData=false` 才满足「目录消失」。无数据残留，但文件系统上看起来像残留，建议确认 UI 默认值。
- `src/features/modules/widgets/widget-card.tsx`：模块来源名在卡片头部被截断（`Stage C E2E Fix…`），布局限制，非错误。
- 前端卸载/启停后的 contributions 刷新依赖 `["modules"]` 前缀；本次 API 层验证通过，UI 层刷新由 C1 负责。

## 需要指挥官决策
- 卸载默认是否改为 `keepData=false`（或仅当模块确有 `data/` 时才保留目录），避免空目录。
