# V4.1 问题清单（BUGS）

状态图例：`NEW` 待确认 / `REPRO` 已复现 / `ROOT CAUSE` 根因已定位 / `FIXING` 修复中 / `FIXED` 已修复待验证 / `DONE` 已验证

---

## BUG-101 助手回复的 Markdown 未渲染

- **状态**：`FIXED`（类型检查与构建通过；待界面实机验收）
- **优先级**：P1
- **用户描述**（2026-11-06）：
  > Agent 内部与 LLM 对话的显示有问题：模型输出的是 Markdown，但界面不是按 Markdown 显示，
  > 星号、井号、列表符号直接露出来，看起来很难受。

### 根因

助手消息气泡直接把 `message.content` 放进 `<p className="whitespace-pre-wrap">`：

- `src/features/assistant/chat-panel.tsx:219`（V4 基线）

模型按系统提示输出 Markdown（标题、加粗、有序列表、表格），但前端没有任何 Markdown 渲染层，
于是 `**`、`##`、`-` 等标记原样显示。

### 修复

| 文件 | 变更 |
|---|---|
| `package.json` / `package-lock.json` | 新增 `react-markdown`、`remark-gfm` |
| `src/components/common/markdown.tsx`（新增） | 统一 Markdown 渲染组件：标题、段落、列表、加粗/斜体/删除线、链接、引用、分隔线、行内代码、代码块、GFM 表格；原始 HTML 不渲染；远程图片不加载（只显示替代文字）；站内链接走 `react-router` |
| `src/features/assistant/chat-panel.tsx` | 助手气泡改用 `<MarkdownText>`，流式状态传入 `streaming` |
| `src/index.css` | `.eh-markdown` 代码块样式与流式末尾光标 |

### 验收

- [x] `npx tsc --noEmit` 通过；
- [x] `npm run build` 通过；
- [ ] 界面实机：发送包含标题/列表/表格/代码块的问题，确认按格式渲染且流式光标正常。

---

## BUG-102 助手防御性过高，过度免责、缺少建议

- **状态**：`FIXED`（提示词与 mock 回复已改；待真实模型实机验收）
- **优先级**：P1
- **用户描述**（2026-11-06）：
  > Agent 防御性太高，太急于撇清关系，不能及时给建议，什么都说「我不知道」。
  > 内部写了「仅供参考」就行了，没必要每条信息都按照这个展开，不然可用性很差。

### 根因

1. `backend/src/eclipse_health_backend/llm/agent.py:59`（V4 基线）系统提示第 8 条强制
   「回答末尾用一句话提醒：以上为数据解读，不构成医学诊断。」——每轮回答都被追加固定免责尾注。
2. `agent.py:52` 第 1 条把「不做诊断」放在最前，且没有给出「在边界内可以给什么建议」的正向指引，
   模型倾向于先声明不能做什么，再给出很少的可用信息。
3. `agent.py:53` 第 2 条只有「没有数据就明确说没有」，缺少「说明缺什么、如何补齐、在现有信息下能说什么」。
4. Coach 提示同样强制末尾免责（`agent.py:71`），且「缺失的数据就明说没有」缺少后续动作。
5. Mock provider 在 4 处回复里硬编码追加免责句（`agent.py:558/563/586/1132`），即便换成真实模型，
   演示与测试链路仍表现出「每轮免责」。

### 修复

- 重写 `SYSTEM_PROMPT` 与 `COACH_SYSTEM_PROMPT`：
  - 第 1 条改为**先给结论和可执行建议**，明确「不要用免责声明或『我不知道』代替回答」；
  - 保留「不诊断、不开处方、不给用药剂量」的边界，但改为正向表述：可以解释数值、趋势、常见含义，
    可以给一般性生活方式建议；
  - 只有涉及诊断、用药、剂量或急症症状时才用一句话建议就医；
  - 缺数据时要求说明「缺哪项、如何补齐、现有信息下能判断什么」；
  - 免责声明由界面统一展示（「仅供参考，不构成医学诊断」），提示词明确要求回答中不要重复；
  - 红旗症状立即建议就医的规则原样保留。
- 删除 Mock provider 与工具上限兜底中的固定免责尾注。
- 更新 `backend/tests/assistant/test_live_providers.py`：联调断言从「回复必须包含免责句」
  改为「回复不得以固定免责句结尾」。
- 新增 `backend/tests/assistant/test_agent_prompt.py`：锁定新提示词与 mock 回复行为。

### 验收

- [x] 新增/更新的提示词单测通过；
- [x] `pytest tests/assistant tests/coach` 通过；
- [ ] 真实模型实机：连续提问 3–5 轮，确认回复以结论/建议开头、末尾无固定免责句；
      询问诊断/用药时仍会提示就医；描述红旗症状时立即建议急诊。

---

## 待补充

后续 bug 按同样格式追加：现象、复现、根因（file:line）、修复、验证、回滚点。
