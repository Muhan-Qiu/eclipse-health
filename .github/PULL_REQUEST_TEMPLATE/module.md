# 模块提交 / Module submission

> 使用方式：在 PR 描述中保留本模板；删除不适用的提示行。CI `validate-module` 失败会阻止合并。

## 模块信息

- **模块 ID**：`io.github.<owner>.<name>`
- **名称**：
- **版本**：`x.y.z`
- **类型**：`device-adapter` / `signal-engine` / `analysis-model` / `health-domain` / `dashboard-widget` / `exporter` / `ai-tool` / `theme` / `locale` / `data-source`
- **作者（适配层维护者）**：
- **许可证（SPDX）**：
- **上游仓库 / 版权人**（如有）：
- **主页 / 仓库**：

## 权限

逐项写出 `module.json` 中的权限，并解释用途；没有则写“无”。

| 权限 | 用途 | 是否新增（升级时） |
| --- | --- | --- |
|  |  |  |

- [ ] 未声明 `network`，或已提供非空 `allowedHosts` 且不含通配符
- [ ] 未申请 `records:delete` / `system:background` / `ui:custom`（如申请，已说明理由）
- [ ] 升级时新增权限会在安装页重新请求用户确认

## 依赖与数据

- **依赖**（PEP 508，无 URL / 本地路径 / editable）：
- **模型权重**（onnx / safetensors；来源、许可证、sha256）：
- **数据来源与许可证**（如 Open Food Facts ODbL）：
- [ ] 不包含 API Key、私钥、令牌或任何用户健康数据
- [ ] 日志不记录波形、备注与原始文件名

## 测试

- [ ] `module.json` 通过 `schemas/module.schema.json`
- [ ] 主路径在干净临时目录运行通过
- [ ] 空输入 / 非法参数 / 未知方法返回结构化错误且不崩溃
- [ ] 断网或超时有明确错误
- [ ] 打包后的 `.ehmod` 可解包，`checksums.json` 一致
- 测试命令与结果：

```text
（粘贴关键命令与通过数量）
```

## 截图 / 录屏（UI 模块）

<!-- 亮色与暗色各一张；没有 UI 可写“不适用” -->

## 许可证与署名

- [ ] 已随包保留上游 `LICENSE`（Apache-2.0 另附 `NOTICE`）
- [ ] 未删除版权头；fork 修改处已在 README 说明
- [ ] 未暗示上游或 eclipse health 为本模块背书
- [ ] 非诊断声明已写入模块描述

## 非诊断声明

> 我确认：本模块不是医疗器械，输出不用于诊断、治疗或替代专业医疗判断；描述中没有任何诊断或治愈宣称。

## 提交清单

- [ ] 文件位于 `marketplace/submissions/<module-id>/`
- [ ] 包含 `module.json`、`src/`、`LICENSE`、`README.md`
- [ ] 未提交 `venv/`、`__pycache__/`、`.git/` 或任何密钥
- [ ] 已阅读 `marketplace/CONTRIBUTING.md`

## 备注

<!-- 给维护者的额外说明 -->
