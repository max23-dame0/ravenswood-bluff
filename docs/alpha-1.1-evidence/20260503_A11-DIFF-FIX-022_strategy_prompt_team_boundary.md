# 20260503_A11-DIFF-FIX-022_strategy_prompt_team_boundary

## 任务

- 任务 ID：A11-DIFF-FIX-022
- 任务名称：阵营策略 prompt 边界修复
- 改动范围：`src/agents/ai_agent.py`, `src/agents/difficulty_presets.py`, `tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 + Alpha 1.1 M1-M4
- 基线命令：`.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py tests\test_agents\test_agent_reasoning.py -q`
- 基线问题：`_build_persona_prompt_block` 第 896 行无条件注入 `evil_strategy_prompt`，不检查 `self.team`。好人 AI 可能收到邪恶策略指导。

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
  - `test_difficulty.py`: 40 passed (新增 7 个 team boundary 测试)
  - `test_agent_reasoning.py`: 48 passed (无回归)
- 关键观察：
  - `evil_strategy_prompt` 现在只在 `self.team == "evil"` 时注入
  - 新增 `good_strategy_prompt` 字段，只在 `self.team == "good"` 时注入
  - 好人 prompt 中永远不出现 `【邪恶策略】`
  - 邪恶方 prompt 中永远不出现 `【正义策略】`
  - Standard 难度两种策略 prompt 均为空，不注入任何策略指导

## 回归保护

- 已覆盖的 Alpha 1.0 流程：信息隔离测试、agent reasoning 测试
- 已覆盖的 Alpha 1.1 流程：difficulty acceptance、persona prompt 构建

## 结论

- 是否满足 Done：是
- 残留风险：无。策略 prompt 分支逻辑清晰，Team 枚举已导入。
- 后续任务：A11-DIFF-FIX-023（多轴配置）、A11-VERIFY-034（阵营信息边界测试）
