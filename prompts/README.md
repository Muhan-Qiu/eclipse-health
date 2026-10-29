# 提示词索引 · B2 已验收，B3 启动

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> B2 结果：275 个后端测试通过、ruff/build 通过；导入→分析→详情→重启持久化全链路成立；桌面壳/托盘/启动动画完成。

## B3 启动表（建议 4 个并行）

| 顺序 | 提示词 | 任务 | 难度 | 思考强度 | 备注 |
|---|---|---|---|---|---|
| 1 | `21-carda-simplify.md` | 简化 ONNX + 模块自带权重 + 启动 ≤3s | 中等偏难 3/4 | **high** | 先做，其他任务都受益 |
| 2 | `22-trends-compare.md` | 趋势 + 记录状态 + 两条记录对比 | 困难 3/4 | **high** | 前端共享层所有者 |
| 3 | `23-reports.md` | 报告 PDF/PNG + 模板 + 历史 | 困难 3/4 | **high** | 不加 Python 依赖 |
| 4 | `24-llm-assistant.md` | LLM 助手 + 工具调用可视化 | 极难 4/4 | **max** | 先 mock，再 Ollama/API |

## 每个会话粘贴这一句

```
阅读 prompts/00-COMMON.md 和 prompts/21-carda-simplify.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/21-carda-simplify-report.md。
```

编号换成对应文件名即可。

## B3 并行注意事项

- **端口**：不要抢同一个 uvicorn / Vite。建议：
  - B3-01：`--port 8781`（后端）
  - B3-02：后端 8782、Vite 默认 1420
  - B3-03：后端 8783、`npm run dev -- --port 1423`
  - B3-04：后端 8784、`npm run dev -- --port 1424`
- **共享前端层**：B3-02 独占 `src/App.tsx`、`src/lib/api/*`、`src/lib/i18n/*`；B3-03/04 只加 `src/features/<x>/**` 与页面文件，i18n 用 feature-local bundle。
- **共享后端**：B3-02 改 `api/records.py` 加列表状态；其他人不要动。B3-01 只管 `modules/official/cardia` 与 `analysis/model.py`。
- **引擎预热**：B3-01 完成前仍是 ~150s；B3-02/03/04 若需要真实分析，先等 B3-01，或用已有 completed 分析/构造 fixture，不要卡住。
- **依赖**：没有 pip/uv；不要新增 Python 依赖。PDF 用 matplotlib+Pillow，Key 存储用 DPAPI ctypes。
- **样本**：`uploads/` 仍为空；不做 Samsung/Apple/华为/SCP-ECG 真实解析。

## 启动前检查

- 当前目录：`C:\Users\qiumuhan\Documents\claude\心电智能体\v3`
- 基线：`pytest backend\tests -q` 275 passed；`npm run build` 通过。
- 事实源：`docs/INTERNAL_API_V1.md`、`docs/V3_BUILD_PLAN.md`。

## 跑完 B3 之后

1. 四个报告到 `reports/`；
2. 指挥官验收：趋势/对比、PDF/PNG、助手工具调用、启动 ≤3s；
3. 更新计划，决定 B4：打包/自动更新、更多设备格式（等样本）、模块安装 UI、波形增强、隐私/导出。

## B4 单任务（先跑这一个）

| 提示词 | 任务 | 难度 | 思考强度 |
|---|---|---|---|
| `31-packaging.md` | PyInstaller sidecar + Tauri 安装包 + 冒烟测试 | 困难 3/4 | **high** |

- 这个任务与 UI 反馈无关，可以并行于用户试用。
- 其余 B4 功能（导出/隐私中心/波形增强/模块 UI/设备格式/健康档案）等用户试用意见后再排。
- 启动句同上，替换文件名与报告名即可。
