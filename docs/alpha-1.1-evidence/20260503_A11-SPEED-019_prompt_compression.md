# 20260503_A11-SPEED-019_prompt_compression

## 任务

- 任务 ID：A11-SPEED-019
- 任务名称：Prompt 压缩与摘要缓存
- 改动范围：`src/agents/ai_agent.py`

## 基线

- 基线版本：Alpha 1.0 所有动作都走完整 LLM prompt
- 基线命令：N/A
- 基线结果：N/A

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - vote/nomination_intent 走本地决策，prompt token = 0 (model = "local-heuristic")
  - speak/defense_speech 保留完整 prompt (high-value actions)
  - action_metrics 记录 prompt_tokens/completion_tokens per action
- 关键观察：
  - 低价值动作 (vote, nomination_intent) 完全绕过 LLM，使用本地启发式
  - 高价值动作 (speak, defense_speech) 保留完整上下文
  - Token reduction for low-value actions: 100% (0 tokens vs full prompt)
  - Token reduction for mixed workloads: depends on action mix ratio
  - Fallback actions also recorded with latency and reason

## 回归保护

- 已覆盖的 Alpha 1.0 流程：All existing tests pass, aggregate acceptance 7/7
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Local decisions sacrifice persona/difficulty differentiation for speed. The tradeoff is acceptable for low-value structured actions.
- 后续任务：A11-SPEED-018 (pre-gen cache, deferred to Alpha 1.2)
