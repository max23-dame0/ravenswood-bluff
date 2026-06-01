# 20260503_A11-DIFF-FIX-025_deception_budget

## 任务

- 任务 ID：A11-DIFF-FIX-025
- 任务名称：Master 欺诈预算与一致性
- 改动范围：`src/agents/ai_agent.py`, `tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 无欺诈预算机制
- 基线命令：N/A
- 基线结果：N/A（之前无 claim tracking 或 fabrication budget）

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 62/62 tests passed (was 47 before this task)
  - TestDeceptionTracker: 10/10 passed
  - TestAgentDeceptionBudgetPrompt: 5/5 passed
- 关键观察：
  - `DeceptionTracker` class: budget scales with deception level (deception=0.7 → max 2 fabrications/day)
  - `record_self_claim`: tracks what role the evil agent publicly claimed
  - `can_fabricate`: enforces per-day budget, resets each day
  - `get_consistency_guidance`: returns guidance to maintain narrative consistency
  - `_deception_budget_prompt`: injected into evil agent's system prompt, warns at 1 remaining, blocks when exhausted
  - `_track_own_claims_from_decision`: auto-tracks extracted_claims from LLM responses
  - `_build_persona_prompt_block`: appends 【叙事一致性】 block for evil agents with active claims
  - Good agents are unaffected (empty budget prompt, no consistency block)

## 回归保护

- 已覆盖的 Alpha 1.0 流程：All 47 pre-existing difficulty tests still pass alongside new deception tests
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Budget is enforced via prompt guidance, not hard blocking. LLM may still fabricate despite the warning. Runtime claim tracking depends on LLM returning extracted_claims in JSON response.
- 后续任务：A11-DIFF-FIX-026 (Chaos bounded random guardrails)
