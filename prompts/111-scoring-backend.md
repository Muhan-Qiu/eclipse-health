# G2 · 健康评分 + 建议后端（规则、可解释、非诊断）

> 先读 `prompts/00-COMMON.md`、`docs/DATA_SCHEMA_V1.md`、`src` 无关（本任务只后端）、现有 `records`/`metrics`/`analyses` API。
> **思考强度：low。** 规则清晰即可，不要接入 LLM 打分。

## 目标

用已有 ECG/健康导入/手动指标/档案数据，产出 0–100 的规则评分与一句话建议。缺数据的项不显示；总分只平均可用项。

## 交付

### 1. 评分服务

- 新建 `backend/src/eclipse_health_backend/scoring/`：
  - `models.py`：`ScoreCategory`（id/label/score/grade/factors/missing/evidenceCount）、`ScoreReport`、`Suggestion`。
  - `service.py`：读取最近 30 天数据，按规则计算：
    - `heart`：静息心率（优先健康数据 `heart-rate` 的静息/最低分位，否则最近 ECG 平均心率）、HRV（ECG analysis 的 RMSSD）、异常搏动占比、信号质量；可用项加权平均。
    - `sleep`：最近 7 天睡眠总时长、深睡/REM 占比（Apple/小米 sleep 记录）；无睡眠记录 → None。
    - `weight`：档案身高 + 最近体重 → BMI 区间；无身高或体重 → None。
    - `activity`：最近 7 天日均步数 vs 目标（如 8000）；无步数 → None。
    - `blood_pressure`：最近血压（手动或导入）区间；无 → None。
  - 分级：`excellent ≥85`、`good ≥70`、`fair ≥55`、`attention <55`；无数据 `unknown` 且不参与总分。
  - 每项 `factors` 用中文短句说明依据（如「静息心率 62 bpm」「近 7 天平均睡眠 7.2 h」）；`missing` 说明缺什么。
  - 全部附 `disclaimer`：「基于公开区间规则的参考评分，不是医学诊断」。
- 阈值与区间写进 `docs/SCORING.md`（新建），注明来源为公开健康建议区间，非临床标准。

### 2. 建议

- `suggestions.py`：按最低分项/缺失项生成 1–3 条一句话建议；每条带：
  - `id`、`text`、`category`、`severity`（info/attention）、`prompt`（给助手的预置问题，如「观察我最近的睡眠数据，分析可以改善的点」）。
- 不做 LLM 调用；建议是规则模板。

### 3. API

- `GET /api/v1/scores` → 上面 ScoreReport；无数据时 `overall=null`、categories 为空、missing 列出全部。
- `GET /api/v1/suggestions` → `{items:[...]}`；无数据时返回「先导入健康数据/完成一次分析」的建议。
- 挂在现有 API（`api/__init__.py` 或新 router），本地无需额外认证；不返回 notes/波形。
- 错误：数据库空/成员不存在按空数据返回，不要 500。

### 4. 测试

- `backend/tests/scoring/`：无数据、只有心率、有睡眠+体重、血压偏高、步数不足、总分平均、缺失项不参与、建议排序、免责声明。
- 用临时 DB 构造 records/analyses/metrics；不要依赖真实数据。

## 文件所有权（只改这些）

- `backend/src/eclipse_health_backend/scoring/**`（新建）
- `backend/src/eclipse_health_backend/api/__init__.py`（挂 router）
- `backend/tests/scoring/**`（新建）
- `docs/SCORING.md`（新建）
- `reports/G2-*.md`

## 明确不做

- 不接 LLM、不做诊断、不改前端（G1）、不改 profile/assistant（G3/G4）。
- 不新增依赖；不改 `prompts/`、`uploads/`；不 commit。

## 验收

```powershell
backend\.venv\Scripts\python.exe -m ruff check backend
backend\.venv\Scripts\python.exe -m pytest backend\tests\scoring -q
```

报告 `reports/G2-scoring-report.md`，≤80 行：每项规则/阈值、API 形状、测试输出、未做项。
