# 个性化记忆（Memory）

健康档案页的「个人记忆」允许用户写下希望助手长期记住的信息（心情、近期事件、生活习惯等）。
内容只保存在本机，不写入日志、不做遥测。

## 存储

- 路径：`<EH_DATA_DIR>/memory.json`（默认 `backend/.data/memory.json`）。
- 结构：

```json
{
  "content": "纯文本 / Markdown",
  "enabled": true,
  "updatedAt": "2026-10-31T09:00:00+00:00"
}
```

- 写入使用临时文件 + `os.replace` 原子替换；文件不存在、JSON 损坏或字段类型不符时
  一律回退为 `{content: "", enabled: false, updatedAt: null}`，不会拖垮档案页或助手。

## 限制

| 字段 | 规则 |
|---|---|
| `content` | 字符串，最多 20000 字；空内容允许 |
| `enabled` | 布尔；关闭后助手不会读取内容 |
| `updatedAt` | 服务端生成，ISO 8601 带时区 |

## API

- `GET /api/v1/memory` → `{content, enabled, updatedAt}`
- `PUT /api/v1/memory`，请求体 `{content, enabled}`；整体替换，返回保存后的文档。
- 超出长度返回 422 `validation_error`。

## 助手如何注入

G4 / 助手在组装上下文时调用：

```python
from eclipse_health_backend.memory import memory_context

context = memory_context()  # enabled=false 或内容为空时返回 ""
```

`memory_context()` 每次读取本机文件，只返回已启用内容；调用方自行决定是否拼进提示词。
记忆内容不得写入应用日志。

## 隐私

- 仅本机文件，不上传、不发遥测。
- 只在用户使用助手时随请求提供给用户配置的模型；关闭开关后不读取。
- 删除记忆即清空文本框并保存（或删除 `memory.json`）。
