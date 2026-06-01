# 20260503_A11-DIFF-FIX-023_multi_axis

## 任务

- 任务 ID：A11-DIFF-FIX-023
- 任务名称：难度多轴配置模型
- 改动范围：`src/agents/difficulty_presets.py`, `tests/test_difficulty.py`, `scripts/difficulty_acceptance.py`

## 基线

- 基线版本：Alpha 1.1 pre-fix（单一 temperature + prompt_modifier 表达难度）
- 基线命令：`.\.venv\Scripts\python.exe scripts\difficulty_acceptance.py`
- 基线问题：难度维度混杂，temperature/噪声/欺诈/叙事/阈值散落在不同结构，难以调参

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
.\.venv\Scripts\python.exe scripts\difficulty_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `test_difficulty.py`: 40 passed（含多轴范围、排序、latency_budget 结构测试）
  - `difficulty_acceptance.py`: 97/97 passed
- 关键观察：
  - 四个 preset 均具备 `competence/deception/volatility/expressiveness/information_openness` 轴，范围 [0,1]
  - 每个 preset 具备 `latency_budget`（5 种 action type）和 `temperature_by_action`
  - Master competence >= all others (0.85)
  - Chaos volatility >= all others (0.85)
  - Master deception >= all others (0.7)
  - Casual information_openness >= all others (0.7)
  - Standard 使用显式基线值（competence=0.5, deception=0.3, volatility=0.2）

## 回归保护

- 已覆盖的 Alpha 1.0 流程：difficulty acceptance script, difficulty unit tests
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：多轴参数当前仅用于结构定义和验收，尚未接入 ai_agent.py 的实际决策流程（temperature_by_action 未在 LLM 调用中使用）。后续 A11-DIFF-FIX-025/026 将把 deception/volatility 接入行为逻辑。
- 后续任务：A11-DIFF-FIX-024, A11-DIFF-FIX-025, A11-DIFF-FIX-026
