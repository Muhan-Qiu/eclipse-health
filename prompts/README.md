# 提示词索引 · B3 已验收，B4 收口（两波 8 个 Agent）

> 指挥官文件。Agent 只读自己的提示词 + `00-COMMON.md`，不要读别人的。
> B3 结果：357 项后端测试通过、ruff/build 通过；趋势/对比/PDF/PNG/LLM mock/启动 1.2s 全部落地。

## 为什么分两波

本机 16GB 内存，B3 四个 Agent 并行时已出现 OOM；8 个同时跑会互相拖慢/抢端口。
**Wave 1（4 个）→ 验收/让路 → Wave 2（4 个）**，仍然是「一次性收口」，不是多轮迭代。

## Wave 1（现在开）

| 提示词 | 任务 | 难度 | 思考强度 | 端口 |
|---|---|---|---|---|
| `31-packaging.md` | PyInstaller sidecar + Tauri 安装包 + 桌面增强 | 困难 3/4 | **high** | — |
| `32-data-acquisition.md` | 公开样本下载 + 格式资料（EDF/SCP-ECG/Apple/Samsung/华为） | 中等 2/4 | **medium** | — |
| `33-device-adapters.md` | 设备/医院格式适配器 | 困难 3/4 | **high** | 8783 |
| `34-export-privacy.md` | 导出/备份 + 隐私中心 + 诊断日志 + 设置 | 困难 3/4 | **high** | 8784 / 1420 |

## Wave 2（Wave 1 完成/报告出来后再开）

| 提示词 | 任务 | 难度 | 思考强度 | 端口 |
|---|---|---|---|---|
| `35-waveform-extras.md` | 心搏列表 / 节律条 / 12 导联展示 / PNG / 快捷键 | 困难 3/4 | **high** | 1425 |
| `36-module-ui.md` | 模块安装 / 权限 / 审计 UI | 中等偏难 3/4 | **high** | 8786 / 1426 |
| `37-profile-metrics.md` | 健康档案 + 手动指标 + 通知 | 中等偏难 3/4 | **high** | 8787 / 1427 |
| `38-llm-live.md` | LLM 真实联调 + 助手收尾 | 困难 3/4 | **high** | 8788 / 1428 |

## 启动句

```
阅读 prompts/00-COMMON.md 和 prompts/31-packaging.md，严格按照其中的范围执行。
只修改「文件所有权」列出的路径；完成后写 reports/B4-01-report.md。
```

替换文件名/报告名即可。Wave 1 四个可同时开；Wave 2 等 Wave 1 报告齐了再开。

## 依赖与共享文件

- **B4-04** 是后端路由接线所有者：`api/__init__.py`、`app.py`；挂载 B4-07 的 `metrics.api.router`。
- **B4-01** 拥有 `src-tauri/**`；B4-04/B4-07 通过 `invoke` 调它暴露的设置/通知命令。
- **B4-02** 是唯一允许写 `uploads/` 的 Agent；B4-03 只读样本。
- **B4-05** 拥有记录详情与波形；**B4-06** 拥有模块页；**B4-07** 拥有档案页/App 路由；**B4-08** 拥有助手。互不改页面。
- `src/lib/api/*` 与 `src/lib/i18n/*`：Wave 2 中 B4-05/06/07/08 都用 feature-local bundle/fetch，不改共享；B4-04 可改 settings 相关 i18n。

## 必须提前知道的限制

1. **12 导联只能展示，不能分析。** Cardia 2.0 是单导联模型；B4-05 的 12 导联网格是显示/复查，分析仍用 MLII/第一导联。
2. **自动更新需要签名私钥 + 更新服务器。** B4-01 只做插件配置/占位与本地验证；没有这两样不能真正上线更新。
3. **外部 LLM 需要 API Key。** B4-08 优先用本机 Ollama；没有 Ollama/Key 时用 mock 交付，并报告缺什么。不会系统级安装 Ollama。
4. **华为样本可能找不到。** B4-02 会尽力下载公开样本；华为/部分 Samsung 导出可能只有文档没有样本，B4-03 会标 `experimental`，真实设备兼容性需你后续提供样本验证。
5. **下载物**放 `uploads/`（已 gitignore），不提交受限数据集；每个样本记录来源/许可证/sha256。

## 启动前检查

- 基线：`pytest backend\tests -q` 357 项通过；`npm run build` 通过。
- 后端命令：`backend\.venv\Scripts\python.exe -m ...`（`uv` 不在 PATH）。
- 事实源：`docs/INTERNAL_API_V1.md`、`docs/V3_BUILD_PLAN.md`。

## 收尾

Wave 1/2 报告齐后，指挥官统一做：接线检查、全量测试/build、真机冒烟、路由懒加载、依赖声明、README、git checkpoint。
