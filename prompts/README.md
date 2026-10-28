# 提示词索引 · B1 已验收，B2 启动

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> B1 结果：199 个后端测试通过、ruff 通过、前端构建通过、4 张 UI 截图达标。

## B2 启动表（建议 4 个并行）

| 顺序 | 提示词 | 任务 | 难度 | 思考强度 | 说明 |
|---|---|---|---|---|---|
| 1 | `11-analysis-module.md` | Cardia 模块化 + 分析 API + ONNX 启动性能 | 极难 4/4 | **max** | 后端接线所有者；先做 ORT spike |
| 2 | `12-import-pipeline.md` | 导入链路（WFDB/CSV）+ 参数校正 | 困难 3/4 | **high** | 为 Samsung 留接口，不猜格式 |
| 3 | `13-ui-vertical-slice.md` | UI 端到端：记录详情 + 波形 + 分析 | 困难 3/4 | **high** | 接真 API，保留 mock 降级 |
| 4 | `14-desktop-branding.md` | 桌面壳 + 日食启动动画 + logo | 中等 2/4 | **medium** | Tauri 卡住再升 high |

## 每个会话粘贴这一句

```
阅读 prompts/00-COMMON.md 和 prompts/11-analysis-module.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/11-analysis-module-report.md。
```

编号换成对应文件名即可。

## B2 并行注意事项

- **后端接线**：B2-01 拥有 `api/__init__.py`、`app.py`、`pyproject.toml`；B2-02 只提供 `importers/api.py` 的 `router`，由 B2-01 挂载。
- **前端**：B2-03 拥有 `src/**`（页面/组件/API 层）；B2-04 只拥有 `src/main.tsx`、`src/branding/**`、`public/brand/**`、`src-tauri/**`、`index.html`、Tauri 插件依赖。两者不要互改。
- **端口 1420**：B2-03 会占用 `npm run dev`；B2-04 的 `npm run tauri dev` 也会启动 Vite。**不要同时跑**：B2-04 先做 logo/动画/代码，最后再启动 Tauri；若 1420 被占，先让 B2-03 停 dev server，或在 Tauri 启动参数里复用已有 devUrl。
- **引擎冷启动**：Cardia ONNX 初始化当前约 150s；B2-03 的 E2E 要预留等待，B2-01 负责给 `GET /engine` 状态与后台预热。
- **样本**：`uploads/` 仍为空；B2 只用 MIT-BIH 与合成 CSV，Samsung/Apple/华为/SCP-ECG 不实现真实解析。

## 启动前检查

- 当前目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 基线：`pytest backend\tests -q` 199 passed；`npm run build` 通过。
- 事实源：`docs/INTERNAL_API_V1.md`、`docs/V3_BUILD_PLAN.md`。

## 跑完 B2 之后

1. 四个报告到 `reports/`；
2. 指挥官跑总验收并实测第一条端到端链路；
3. 更新 `docs/V3_BUILD_PLAN.md`，再决定 B3（趋势/报告/LLM/更多格式/打包）。
