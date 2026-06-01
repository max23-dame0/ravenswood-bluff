# 20260503_A11-SPEED-015-016_latency_metrics_and_budget

## 任务

- 任务 ID：A11-SPEED-015 / A11-SPEED-016
- 任务名称：AI action latency 度量 + 硬时间预算
- 改动范围：`src/orchestrator/game_loop.py`, `src/engine/data_collector.py`

## 基线

- 基线版本：Alpha 1.0 + Alpha 1.1 M1-M4
- 基线命令：`.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_game_loop.py -q`
- 基线问题：AI action 没有 latency 追踪，没有硬超时，单个 AI 卡住会阻塞整个对局流程。

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_game_loop.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py tests\test_agents\test_agent_reasoning.py tests\test_decision_noise.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `test_game_loop.py`: 25 passed
  - `test_difficulty.py + test_agent_reasoning.py + test_decision_noise.py`: 121 passed
- 关键观察：
  - `_timed_act` 包装了所有 `agent.act()` 调用（speak, vote, nomination_intent, defense_speech, night_action, death_trigger）
  - 每次 AI action 记录 `player_id/action_type/phase/latency_ms/fallback_used/fallback_reason`
  - 硬超时使用 `asyncio.wait_for`，超时后返回合法 fallback action
  - Fallback actions: vote→False, nomination→not_nominating, speak→"我还在想", defense→"我没有要补充的", night_action→none
  - `GameDataCollector.record_action_latency` 持久化到 JSONL
  - `get_action_latency_summary` 计算 P50/P95/max/timeout 统计
  - 默认 latency budgets: vote 800ms, nomination_intent 1000ms, night_action 1500ms, speak 2000ms, defense_speech 2500ms

## 回归保护

- 已覆盖的 Alpha 1.0 流程：游戏循环全流程（first_night → day_discussion → nomination → voting → execution → settlement）
- 已覆盖的 Alpha 1.1 流程：difficulty presets、team boundary、decision noise

## 结论

- 是否满足 Done：是（SPEED-015 完全完成，SPEED-016 完全完成）
- 残留风险：
  - Fallback action 质量较低（vote always False, speak 固定文本），后续 A11-SPEED-017 FastDecisionPolicy 应提升 fallback 质量
  - 未在真实多人局中验证 P50/P95 指标，需要 A11-VERIFY-032 速度验收脚本
- 后续任务：A11-SPEED-017（FastDecisionPolicy）、A11-SPEED-018（发言预生成）、A11-VERIFY-032（速度验收）
