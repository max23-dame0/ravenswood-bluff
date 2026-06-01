# Alpha 1.1 证据索引

这里用于保存 Alpha 1.1 改进项的验证证据。每个证据文件应能独立说明：改了什么、怎么验证、和什么基线比较、结果是什么、还有哪些风险。

## 命名规范

```text
YYYYMMDD_<task_id>_<short_slug>.md
```

示例：

```text
20260503_A11-VERIFY-032_ai_speed_acceptance.md
```

## 收录范围

- 自动化验收结果摘要。
- benchmark 结果摘要。
- 固定场景行为对比。
- 人工试玩记录。
- 发布前证据汇总。

## 不收录

- `data/sessions/` 运行时 session。
- 本地数据库、journal、临时 JSON fallback。
- 一次性调试日志。
- 机器相关绝对路径或密钥。

## 模板

复制 [template.md](template.md) 作为新证据文件的起点。

## 已收录证据

| 日期 | 任务 ID | 文件 | 类型 |
|---|---|---|---|
| 2026-05-03 | A11-VERIFY-029 | [20260503_A11-VERIFY-029_verification_policy.md](20260503_A11-VERIFY-029_verification_policy.md) | 文档 |
| 2026-05-03 | A11-VERIFY-033 | [20260503_A11-VERIFY-033_evidence_template.md](20260503_A11-VERIFY-033_evidence_template.md) | 文档 |
| 2026-05-03 | A11-DIFF-FIX-022 | [20260503_A11-DIFF-FIX-022_team_boundary.md](20260503_A11-DIFF-FIX-022_team_boundary.md) | 代码+测试 |
| 2026-05-03 | A11-DIFF-FIX-023 | [20260503_A11-DIFF-FIX-023_multi_axis.md](20260503_A11-DIFF-FIX-023_multi_axis.md) | 代码+测试 |
| 2026-05-03 | A11-DIFF-FIX-024 | [20260503_A11-DIFF-FIX-024_standard_baseline.md](20260503_A11-DIFF-FIX-024_standard_baseline.md) | 代码+测试 |
| 2026-05-03 | A11-VERIFY-030 | [20260503_A11-VERIFY-030_aggregate_acceptance.md](20260503_A11-VERIFY-030_aggregate_acceptance.md) | 脚本 |
| 2026-05-03 | A11-VERIFY-031 | [20260503_A11-VERIFY-031_difficulty_behavior.md](20260503_A11-VERIFY-031_difficulty_behavior.md) | 脚本 |
| 2026-05-03 | A11-VERIFY-032 | [20260503_A11-VERIFY-032_ai_speed.md](20260503_A11-VERIFY-032_ai_speed.md) | 脚本 |
| 2026-05-03 | A11-VERIFY-034 | [20260503_A11-VERIFY-034_faction_boundary.md](20260503_A11-VERIFY-034_faction_boundary.md) | 测试 |
| 2026-05-03 | A11-DIFF-FIX-025 | [20260503_A11-DIFF-FIX-025_deception_budget.md](20260503_A11-DIFF-FIX-025_deception_budget.md) | 代码+测试 |
| 2026-05-03 | A11-DIFF-FIX-026 | [20260503_A11-DIFF-FIX-026_chaos_guardrails.md](20260503_A11-DIFF-FIX-026_chaos_guardrails.md) | 代码+测试 |
| 2026-05-03 | A11-SPEED-019 | [20260503_A11-SPEED-019_prompt_compression.md](20260503_A11-SPEED-019_prompt_compression.md) | 代码+测试 |
| 2026-05-03 | A11-SPEED-020 | [20260503_A11-SPEED-020_adaptive_speed.md](20260503_A11-SPEED-020_adaptive_speed.md) | 代码+测试 |
| 2026-05-03 | A11-VERIFY-035 | [20260503_A11-VERIFY-035_release_index.md](20260503_A11-VERIFY-035_release_index.md) | 发布证据 |
| 2026-05-04 | A11-SPEED-022 | [20260504_A11-SPEED-022_speed_acceptance.md](20260504_A11-SPEED-022_speed_acceptance.md) | 脚本 |
| 2026-05-04 | A11-VERIFY-035 | [20260504_A11-VERIFY-035_final_fixes.md](20260504_A11-VERIFY-035_final_fixes.md) | 修复+验收 |
| 2026-05-05 | A11-SPEED-FIX | [20260505_A11-SPEED-FIX_m5r_regression.md](20260505_A11-SPEED-FIX_m5r_regression.md) | 回归修复+验收 |
