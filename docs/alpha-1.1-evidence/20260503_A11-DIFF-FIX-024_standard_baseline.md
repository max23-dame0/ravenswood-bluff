# 20260503_A11-DIFF-FIX-024_standard_baseline

## 任务

- 任务 ID：A11-DIFF-FIX-024
- 任务名称：Standard 显式基线合同
- 改动范围：`src/agents/difficulty_presets.py`, `tests/test_difficulty.py`, `scripts/difficulty_acceptance.py`

## 基线

- 基线版本：Alpha 1.1 pre-fix（Standard 所有策略 prompt 为空字符串）
- 基线命令：`.\.venv\Scripts\python.exe scripts\difficulty_acceptance.py`
- 基线问题：Standard 为空白配置，无法定义和测试"标准体验"

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
.\.venv\Scripts\python.exe scripts\difficulty_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_agent_reasoning.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `test_difficulty.py`: 42 passed
  - `difficulty_acceptance.py`: 100/100 passed
  - `test_agent_reasoning.py`: 48 passed
- 关键观察：
  - Standard 现在有显式 `evil_strategy_prompt`（适度误导，不过度激进）
  - Standard 现在有显式 `good_strategy_prompt`（逻辑推理，关注矛盾点）
  - Standard 现在有显式 `speech_style_prompt`（自然有条理）
  - `prompt_modifier` 保持空（Standard 是基线，不需要修饰）
  - 接受脚本检查"基线合同存在"而非"standard 为空白"

## 回归保护

- 已覆盖的 Alpha 1.0 流程：agent reasoning tests (48), difficulty tests (42)
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Standard 基线 prompt 较温和，可能在实际对局中与 Casual 差异不够明显。需 A11-DIFF-FIX-027 行为级验收确认差异。
- 后续任务：A11-DIFF-FIX-025, A11-DIFF-FIX-026, A11-DIFF-FIX-027
