# 20260504_A11-SPEED-022_speed_acceptance

## 任务

- 任务 ID：A11-SPEED-022
- 任务名称：速度专项验收脚本
- 改动范围：`scripts/ai_speed_acceptance.py`

## 基线

- 基线版本：无（新建脚本）
- 基线命令：N/A
- 基线结果：N/A

## 验证

- 验证日期：2026-05-04
- 验证命令：

```powershell
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 16/16 passed
  - 5-player mock game: 17 actions, 0 fallbacks
  - 10-player mock game: 31 actions, 0 fallbacks
  - Slow backend timeout test: 26 actions, 6 timeout fallbacks
  - Event ordering: speak events in order, nominations after discussion
- 关键观察：
  - 覆盖 speak/nomination_intent/vote/night_action/defense_speech 五种 action type
  - 输出 P50/P95/max 和 fallback count
  - SlowBackend (3s delay) 正确触发 timeout fallback (speak budget=2s)
  - timeout_fallbacks=6 验证了超时降级机制正常工作
  - 事件顺序验证：speak 事件按序、提名在讨论之后

## 回归保护

- 已覆盖的 Alpha 1.0 流程：聚合验收包含速度门禁
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Mock backend 延迟不反映真实 LLM 延迟。Live 模式需单独基准测试。
- 后续任务：N/A
