# 20260503_A11-DIFF-FIX-022_team_boundary

## 任务

- 任务 ID：A11-DIFF-FIX-022
- 任务名称：阵营策略 prompt 边界修复
- 改动范围：`src/agents/ai_agent.py`, `src/agents/difficulty_presets.py`, `tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 / Alpha 1.1 pre-fix
- 基线命令：`.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q`
- 基线问题：`_build_persona_prompt_block` 在 line 896 无条件注入 `evil_strategy_prompt`，所有阵营 AI 均可见邪恶策略

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_agent_reasoning.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `test_difficulty.py`: 40 passed
  - `test_agent_reasoning.py`: 48 passed
- 关键观察：
  - Good agent 在 casual/master/chaos 难度下均不接收 `【邪恶策略】`
  - Evil agent 在 casual/master/chaos 难度下均不接收 `【正义策略】`
  - Standard 难度无策略 prompt 注入（空白基线）
  - 新增 `good_strategy_prompt` 字段，四个 preset 均具备

## 回归保护

- 已覆盖的 Alpha 1.0 流程：agent reasoning tests (48 tests), difficulty tests (40 tests)
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：`good_strategy_prompt` 为空字符串时 `elif` 短路，无副作用。Standard 的空白策略 prompt 在 A11-DIFF-FIX-024 中补基线合同。
- 后续任务：A11-DIFF-FIX-024 (Standard baseline contract)
