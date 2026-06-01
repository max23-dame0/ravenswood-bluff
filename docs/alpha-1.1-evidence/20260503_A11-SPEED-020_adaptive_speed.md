# 20260503_A11-SPEED-020_adaptive_speed

## 任务

- 任务 ID：A11-SPEED-020
- 任务名称：人数自适应加速模式
- 改动范围：`src/agents/ai_agent.py`, `tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 fixed action budgets regardless of player count
- 基线命令：N/A
- 基线结果：N/A

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 69/69 difficulty tests passed
  - TestSpeedProfile: 7/7 passed
  - ai_speed_acceptance: 11/11 passed
- 关键观察：
  - `_speed_profile` property: standard (< 8), aggressive (8-9), extreme (10+)
  - Standard profile: base budgets unchanged (vote=0.8s, speak=2.0s)
  - Aggressive profile (8-9 players): budgets scaled by 0.85x, min 0.6s
  - Extreme profile (10+ players): budgets scaled by 0.7x, min 0.5s
  - Env override (`AI_ACTION_TIMEOUT_SECONDS`) still takes precedence
  - `action_metrics` records `fallback_used` and `fallback_reason` for timeout tracking
  - Fallback reason format: `latency_budget_exceeded:<action_type>`

## 回归保护

- 已覆盖的 Alpha 1.0 流程：All existing tests pass
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Tighter budgets for large games may increase fallback rate with slow LLM backends. Live mode testing needed to validate.
- 后续任务：A11-SPEED-018 (pre-gen cache, deferred)
