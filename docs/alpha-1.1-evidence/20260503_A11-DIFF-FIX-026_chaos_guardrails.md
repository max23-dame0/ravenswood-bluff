# 20260503_A11-DIFF-FIX-026_chaos_guardrails

## 任务

- 任务 ID：A11-DIFF-FIX-026
- 任务名称：Chaos 有界随机护栏
- 改动范围：`src/agents/decision_noise.py`, `src/agents/ai_agent.py`, `tests/test_decision_noise.py`

## 基线

- 基线版本：Alpha 1.0 `should_bold_move` 返回 bool，无社交理由标签
- 基线命令：`.\.venv\Scripts\python.exe -m pytest tests\test_decision_noise.py -q`
- 基线结果：原有测试全部通过

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_decision_noise.py tests\test_difficulty.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 102/102 tests passed (40 decision_noise + 62 difficulty)
  - TestBoldMoveReasonLabels: 3/3 passed
  - TestLegalTargetFiltering: 3/3 passed
  - TestGameIdSeedBinding: 3/3 passed
- 关键观察：
  - `BoldMoveResult` dataclass: `triggered: bool`, `reason: str`
  - Social reason labels: `retaliation`, `pressure_test`, `intuition`, `story_hook`
  - `should_bold_move` now returns `BoldMoveResult` with deterministic reason assignment
  - `pick_noisy_target` accepts optional `legal_targets` parameter to filter candidates
  - `DecisionNoise` now accepts `game_id` parameter for cross-game seed isolation
  - `_seed` binds to `game_id:player_id:context_key` for deterministic but varied results
  - `AIAgent.act()` syncs `game_id` from `visible_state` to `decision_noise` on first call
  - Reason labels are deterministic per context_key (same key → same reason)

## 回归保护

- 已覆盖的 Alpha 1.0 流程：All existing decision_noise and difficulty tests pass with updated API
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Reason labels are hash-distributed, not context-aware (a "retaliation" label doesn't mean the agent was actually provoked). Labels serve as social hooks for prompt injection, not semantic analysis.
- 后续任务：A11-VERIFY-035 (release evidence index)
