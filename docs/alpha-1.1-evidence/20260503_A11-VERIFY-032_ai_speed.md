# 20260503_A11-VERIFY-032_ai_speed

## 任务

- 任务 ID：A11-VERIFY-032
- 任务名称：补齐 AI 速度验收
- 改动范围：`scripts/ai_speed_acceptance.py` (new), `scripts/alpha1.1_acceptance.py`

## 基线

- 基线版本：无（新建脚本）
- 基线命令：N/A
- 基线结果：N/A（之前无速度验收）

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `ai_speed_acceptance.py`: 11/11 passed
  - 5-player game: 16 actions, 0 fallbacks
  - 10-player game: 33 actions, 1 fallback
  - All action types P95 within targets (mock backend)
- 关键观察：
  - 覆盖 speak/nomination_intent/vote/night_action/defense_speech 五种 action type
  - 输出 P50/P95/max 和 fallback count
  - Mock backend 延迟极低 (0-1ms)，实际 live 延迟需单独基准测试
  - 1 fallback in 10p game (illegal_night_target — expected in mock mode)
  - 聚合验收自动接入，SKIP 逻辑消失

## 回归保护

- 已覆盖的 Alpha 1.0 流程：aggregate acceptance includes alpha1 backward compatibility
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：Mock backend 延迟不反映真实 LLM 延迟。Live 模式需要单独运行 `parallel_benchmark.py` 并记录实际 P50/P95。速度验收脚本的基线是"功能可用+指标可采集"，不是"延迟达标"。
- 后续任务：A11-SPEED-015/016/017 (actual speed engineering)
