# 20260504_A11-VERIFY-035_final_fixes

## 任务

- 任务 ID：A11-VERIFY-035
- 任务名称：发布证据索引 — 最终修复
- 改动范围：`src/agents/ai_agent.py`, `tests/test_orchestrator/test_api_server.py`

## 问题

聚合验收脚本 `alpha1.1_acceptance.py` 返回 6/7 PASS，两个测试失败：

1. `test_ai_persona_nomination_fires_when_signal_is_strong` — BrokenBackend 返回非 JSON 时，兜底决策未能根据高怀疑度（trust=-0.9）产生提名动作
2. `test_metrics_expose_backend_and_nomination_flow` — 投票和执行事件尚未产生时就断言 `vote_count >= 1`

## 修复

### 修复 1：提升怀疑度信号权重

- 文件：`src/agents/ai_agent.py:2112`
- 改动：`_target_signal_score` 中 trust_score < 0 的贡献系数从 `min(0.20, abs * 0.25)` 提升到 `min(0.35, abs * 0.40)`
- 原因：trust=-0.9 时旧系数仅贡献 0.20，总分 0.54 低于阈值 ~0.57，导致 `_select_nomination_target` 返回 None
- 修复后：trust=-0.9 贡献 0.35，总分 0.69，超过阈值，提名正确触发

### 修复 2：延长 API 测试轮询窗口

- 文件：`tests/test_orchestrator/test_api_server.py:76-81`
- 改动：轮询条件从仅检查 `nomination_prompt_count > 0` 改为同时等待 `vote_count >= 1` 和 `execution_count >= 1`，轮询次数从 20 增加到 50
- 原因：mock 后端速度极快，提名提示出现时投票和执行可能尚未完成

## 验证

- 验证日期：2026-05-04
- 验证命令：

```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - 7/7 passed, 0 failed, 0 skipped
  - existing tests regression: 250 passed (2m 44.6s)
  - agent reasoning: passed (5.5s)
  - difficulty acceptance: passed (1.5s)
  - difficulty comparison: passed (1.5s)
  - difficulty behavior acceptance: passed (2.3s)
  - ai speed acceptance: 16/16 passed (53.6s)
  - alpha1 backward compatibility: passed (3.9s)

## 结论

- 是否满足 Done：是
- 残留风险：trust_score 系数调整可能影响其他提名场景的敏感度，已通过全部 250+ 测试回归验证
- 后续任务：无
