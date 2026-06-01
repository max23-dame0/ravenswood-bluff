# Alpha 1.1 发布证据索引

## 概述

本文档汇总 Alpha 1.1 所有 P0/P1 任务的验证证据。每项改进都能回答：改了什么、怎么验证、结果如何、残留风险。

## P0 任务证据

| ID | 任务 | 证据文件 | 状态 |
|---|---|---|---|
| A11-DIFF-001 | 难度数据模型与 GameConfig 集成 | [20260503_A11-DIFF-FIX-023_multi_axis.md](20260503_A11-DIFF-FIX-023_multi_axis.md) | PASS |
| A11-DIFF-002 | AIAgent 接入难度参数 | [20260503_A11-DIFF-FIX-023_multi_axis.md](20260503_A11-DIFF-FIX-023_multi_axis.md) | PASS |
| A11-DIFF-003 | 休闲模式可体验 | [20260503_A11-VERIFY-031_difficulty_behavior.md](20260503_A11-VERIFY-031_difficulty_behavior.md) | PASS |
| A11-DIFF-004 | 大师模式欺诈策略 | [20260503_A11-DIFF-FIX-025_deception_budget.md](20260503_A11-DIFF-FIX-025_deception_budget.md) | PASS |
| A11-UI-005 | 前端难度选择 | Alpha 1.0 已实现 | PASS |
| A11-ACC-006 | 难度验收脚本 | [20260503_A11-VERIFY-030_aggregate_acceptance.md](20260503_A11-VERIFY-030_aggregate_acceptance.md) | PASS |
| A11-SPEED-015 | AI action latency 度量 | [20260503_A11-VERIFY-032_ai_speed.md](20260503_A11-VERIFY-032_ai_speed.md) | PASS |
| A11-SPEED-016 | AI action 硬时间预算 | [20260503_A11-VERIFY-032_ai_speed.md](20260503_A11-VERIFY-032_ai_speed.md) | PASS |
| A11-SPEED-017 | 投票/提名本地优先 | [20260503_A11-VERIFY-032_ai_speed.md](20260503_A11-VERIFY-032_ai_speed.md) | PASS |
| A11-DIFF-FIX-022 | 阵营策略 prompt 边界修复 | [20260503_A11-DIFF-FIX-022_team_boundary.md](20260503_A11-DIFF-FIX-022_team_boundary.md) | PASS |
| A11-DIFF-FIX-023 | 难度多轴配置模型 | [20260503_A11-DIFF-FIX-023_multi_axis.md](20260503_A11-DIFF-FIX-023_multi_axis.md) | PASS |
| A11-VERIFY-029 | Alpha 1.1 验证规范 | [20260503_A11-VERIFY-029_verification_policy.md](20260503_A11-VERIFY-029_verification_policy.md) | PASS |
| A11-VERIFY-030 | 聚合验收入口升级 | [20260503_A11-VERIFY-030_aggregate_acceptance.md](20260503_A11-VERIFY-030_aggregate_acceptance.md) | PASS |
| A11-VERIFY-031 | 难度行为验收 | [20260503_A11-VERIFY-031_difficulty_behavior.md](20260503_A11-VERIFY-031_difficulty_behavior.md) | PASS |
| A11-VERIFY-032 | AI 速度验收 | [20260503_A11-VERIFY-032_ai_speed.md](20260503_A11-VERIFY-032_ai_speed.md) | PASS |
| A11-SPEED-022 | 速度专项验收脚本 | [20260504_A11-SPEED-022_speed_acceptance.md](20260504_A11-SPEED-022_speed_acceptance.md) | PASS |

## P1 任务证据

| ID | 任务 | 证据文件 | 状态 |
|---|---|---|---|
| A11-CHAOS-007 | 混沌模式与决策噪声 | [20260503_A11-DIFF-FIX-026_chaos_guardrails.md](20260503_A11-DIFF-FIX-026_chaos_guardrails.md) | PASS |
| A11-NARR-008 | 叙事驱动发言 | difficulty_behavior_acceptance 50/50 | PASS |
| A11-COMPARE-009 | 多难度对比验收 | difficulty_comparison 62/62 | PASS |
| A11-FEEDBACK-010 | 真人体验反馈收集 | 延期（需真人参与） | DEFERRED |
| A11-SPEED-018 | 发言预生成缓存 | 延期至 Alpha 1.2 | DEFERRED |
| A11-SPEED-019 | Prompt 压缩与摘要缓存 | [20260503_A11-SPEED-019_prompt_compression.md](20260503_A11-SPEED-019_prompt_compression.md) | PASS |
| A11-SPEED-020 | 人数自适应加速模式 | [20260503_A11-SPEED-020_adaptive_speed.md](20260503_A11-SPEED-020_adaptive_speed.md) | PASS |
| A11-DIFF-FIX-024 | Standard 显式基线合同 | [20260503_A11-DIFF-FIX-024_standard_baseline.md](20260503_A11-DIFF-FIX-024_standard_baseline.md) | PASS |
| A11-DIFF-FIX-025 | Master 欺诈预算与一致性 | [20260503_A11-DIFF-FIX-025_deception_budget.md](20260503_A11-DIFF-FIX-025_deception_budget.md) | PASS |
| A11-DIFF-FIX-026 | Chaos 有界随机护栏 | [20260503_A11-DIFF-FIX-026_chaos_guardrails.md](20260503_A11-DIFF-FIX-026_chaos_guardrails.md) | PASS |
| A11-DIFF-FIX-027 | 难度行为级验收 | [20260503_A11-VERIFY-031_difficulty_behavior.md](20260503_A11-VERIFY-031_difficulty_behavior.md) | PASS |
| A11-VERIFY-033 | 基线与证据模板 | [20260503_A11-VERIFY-033_evidence_template.md](20260503_A11-VERIFY-033_evidence_template.md) | PASS |
| A11-VERIFY-034 | 阵营信息边界测试 | [20260503_A11-VERIFY-034_faction_boundary.md](20260503_A11-VERIFY-034_faction_boundary.md) | PASS |
| A11-VERIFY-035 | 发布证据索引 | 本文档 | PASS |

## 延期项说明

| ID | 任务 | 延期原因 | 计划版本 |
|---|---|---|---|
| A11-SPEED-018 | 发言预生成缓存 | 需新建 planning cache 模块，复杂度高。P0 速度目标已通过本地优先达成。 | Alpha 1.2 |
| A11-FEEDBACK-010 | 真人体验反馈收集 | 需真人参与测试。 | Alpha 1.2 |
| A11-VERIFY-036 | 人工试玩记录流程 | 需真人参与试玩。 | Alpha 1.2 |

## 聚合验收结果

```text
alpha1.1 acceptance summary (2026-05-04 最终)
========================================================================
PASS existing tests regression       2m 44.6s
PASS agent reasoning tests               5.5s
PASS difficulty acceptance               1.5s
PASS difficulty comparison               1.5s
PASS difficulty behavior acceptance      2.3s
PASS ai speed acceptance                53.6s
PASS alpha1 backward compatibility       3.9s
========================================================================
passed: 7
failed: 0
skipped: 0
```

## 复现命令

```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py tests\test_decision_noise.py -q
.\.venv\Scripts\python.exe scripts\difficulty_behavior_acceptance.py
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
```
