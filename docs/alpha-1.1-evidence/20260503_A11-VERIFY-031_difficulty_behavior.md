# 20260503_A11-VERIFY-031_difficulty_behavior

## 任务

- 任务 ID：A11-VERIFY-031
- 任务名称：补齐难度行为验收
- 改动范围：`scripts/difficulty_behavior_acceptance.py` (new), `scripts/alpha1.1_acceptance.py`

## 基线

- 基线版本：无（新建脚本）
- 基线命令：N/A
- 基线结果：N/A（之前无行为级验收）

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe scripts\difficulty_behavior_acceptance.py
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `difficulty_behavior_acceptance.py`: 50/50 passed
  - `alpha1.1_acceptance.py`: 6 PASS, 0 FAIL, 1 SKIP
- 关键观察：
  - 覆盖 4 档难度 (casual/standard/master/chaos)
  - 验证 prompt block 差异：不同难度注入不同策略 prompt
  - 验证 team 边界：good 不见 evil 策略，evil 不见 good 策略
  - 验证 temperature 差异：4 个难度 4 个不同温度
  - 验证 decision noise 差异：chaos magnitude > casual > standard > master
  - 验证 persona override 差异：casual 被动，master/chaos 主动
  - 验证 multi-axis 参数排序：competence/deception/volatility/information_openness
  - 验证 latency budget 差异：casual 比 master 更宽松

## 回归保护

- 已覆盖的 Alpha 1.0 流程：aggregate acceptance includes alpha1 backward compatibility
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：行为验收当前基于配置差异和 prompt 结构差异，未包含实际 LLM 调用的 action 输出对比（需要 mock LLM 返回不同结果）。后续可扩展为端到端行为对比。
- 后续任务：A11-VERIFY-032 (AI speed acceptance)
