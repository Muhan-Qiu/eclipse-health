# 报告 · G2 规则健康评分 + 建议后端

状态：完成（路由已交付；`/api/v1` 挂载按约定由指挥官统一完成）

## 交付

- `backend/src/eclipse_health_backend/scoring/models.py`：`ScoreCategory` / `ScoreReport` / `Suggestion` / `SuggestionList`、分级与免责声明。
- `scoring/service.py`：30 天窗口的规则评分；heart/sleep/weight/activity/blood_pressure；缺失项不参与，可用子项重新归一化。
- `scoring/suggestions.py`：1–3 条规则建议，attention 优先，不调用 LLM。
- `scoring/api.py`：`GET /scores`、`GET /suggestions`（支持 `memberId`，未知成员返回空报告）。
- `docs/SCORING.md`：全部阈值、权重、API 形状与公开区间来源说明。
- `backend/tests/scoring/`：9 个用例，覆盖空数据、只有心率、睡眠+体重、血压偏高、步数不足、总分平均、缺失项、建议排序、免责声明、非法 payload。

## 评分规则摘要

- heart：静息心率 0.40（健康数据 resting 均值或 10% 分位，否则 ECG `heart_rate_mean`）；RMSSD 0.25；异常搏动占比 0.20；信号质量 0.15。
- sleep：近 7 天平均睡眠 0.70；深睡+REM 占比 0.30（需浅睡分期同时存在）。
- weight：档案身高 + 最近体重 → BMI（中国成人公开区间 18.5–23.9 为满分）。
- activity：近 7 天日均步数 / 8000，封顶 100。
- blood_pressure：最近 30 天最新血压，按公开分级给分（<120/80 满分，≥160/100 为 30）。
- 分级：≥85 excellent、≥70 good、≥55 fair、<55 attention、无数据 unknown；总分只平均可用分类。

## 验证

- `backend\.venv\Scripts\python.exe -m ruff check backend\src\eclipse_health_backend\scoring backend\tests\scoring`
  - 结果：pass（All checks passed）
- `backend\.venv\Scripts\python.exe -m pytest backend\tests\scoring -q -o addopts=""`
  - 结果：**9 passed in 1.13s**
- `backend\.venv\Scripts\python.exe -m ruff check backend`
  - 结果：fail，14 个错误全部位于并行批次的 `coach/context.py`、`coach/weather.py`；scoring 路径 0 错误。

## API 形状

- `GET /api/v1/scores` → `{overall, grade, categories[{id,label,score,grade,factors,missing,evidenceCount}], missing[], disclaimer, generatedAt, memberId, windowDays}`。
- `GET /api/v1/suggestions` → `{items:[{id,text,category,severity,prompt}]}`。
- 空库/未知成员：`overall=null`、`grade=unknown`、`categories=[]`、`missing` 全列出，HTTP 200。
- 不返回 notes、波形或文件路径。

## 未做 / 偏离

- 按 00-COMMON 与总控第 697 行要求，**未修改** `api/__init__.py`；测试通过临时 app 挂载 router 验证真实路径。
- 未接 LLM、未做诊断、未改前端、未新增依赖、未 commit。

## 跨区需求（需要别的 Agent 或指挥官处理）

- 指挥官挂载：在 `api/__init__.py` 增加
  `from ..scoring.api import router as scoring_router`，再 `api_router.include_router(scoring_router)`（路由自带 `/scores`、`/suggestions`，`api_router` 已挂 `/api/v1`）。
- G4：`coach/context.py` 10 处、`coach/weather.py` 4 处 ruff 错误导致全量 `ruff check backend` 失败；本轮未触碰。
- G1：前端可直接消费上述字段；`missing` 是分类中文名，`categories` 只含已有数据的项。

## 需要指挥官决策

- 是否在挂载后补一条端到端 smoke（`GET /api/v1/scores` 空库返回 200）并纳入全量测试。

## 建议下一批

- 挂载路由后做一次真实 app 的 200/JSON 冒烟；后续可在建议中加入 LLM 改写，但本次规则模板已可独立工作。
