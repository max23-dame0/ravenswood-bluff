# 20260503_A11-VERIFY-034_faction_boundary

## 任务

- 任务 ID：A11-VERIFY-034
- 任务名称：补齐阵营信息边界测试
- 改动范围：`tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 无阵营边界测试
- 基线命令：N/A
- 基线结果：N/A（之前无专门的阵营信息隔离测试）

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 47/47 tests passed
  - TestFactionInfoBoundary: 5/5 passed
- 关键观察：
  - `test_strategy_prompts_are_static_text`: 4 presets × 3 fields = 12 checks, no template vars found
  - `test_prompt_block_no_player_id_leakage`: 4 difficulties × 2 teams = 8 blocks, no unexpected player IDs
  - `test_evil_block_does_not_leak_good_strategy`: 3 non-standard difficulties checked, evil never sees good strategy
  - `test_good_block_does_not_leak_evil_strategy`: 4 difficulties checked, good never sees evil strategy
  - `test_difficulty_preserves_team_assignment`: 4 difficulties × 2 teams verified
  - Standard baseline strategy prompts correctly gated by team
  - Prompt blocks contain only difficulty-appropriate strategy markers (【邪恶策略】 or 【正义策略】, never both)

## 回归保护

- 已覆盖的 Alpha 1.0 流程：All 42 pre-existing difficulty tests still pass alongside new faction boundary tests
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Static text checks cover template variable leakage; runtime prompt construction verified through prompt block inspection. Dynamic information leakage (e.g., AI inferring hidden info from context) requires behavioral tests beyond prompt-level checks.
- 后续任务：A11-VERIFY-035 (release evidence index)
