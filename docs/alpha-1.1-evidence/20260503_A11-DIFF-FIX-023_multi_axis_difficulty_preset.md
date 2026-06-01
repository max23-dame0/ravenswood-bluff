# 20260503_A11-DIFF-FIX-023_multi_axis_difficulty_preset

## 任务

- 任务 ID：A11-DIFF-FIX-023
- 任务名称：难度多轴配置模型
- 改动范围：`src/agents/difficulty_presets.py`, `tests/test_difficulty.py`

## 基线

- 基线版本：Alpha 1.0 + Alpha 1.1 M1-M4
- 基线命令：`.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q`
- 基线问题：DifficultyPreset 只有单一 `temperature` 字段表达难度，混杂了噪声、欺诈、叙事、推理等维度，难以独立调参。

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py -q
```

## 结果

- 通过状态：PASS
- 关键指标：
  - `test_difficulty.py`: 40 passed (新增 8 个多轴测试)
  - 所有轴值在 [0,1] 范围内
  - Master competence >= 其他难度
  - Chaos volatility >= 其他难度
  - Master deception >= 其他难度
  - Casual information_openness >= 其他难度
  - 所有难度 latency_budget 包含 5 个必需 action type
  - Master latency_budget 最紧
- 关键观察：
  - 新增 5 个体验轴：competence, deception, volatility, expressiveness, information_openness
  - 新增 latency_budget 按 action type 配置速度预算
  - 新增 temperature_by_action 按动作类型覆盖温度
  - Standard 不再是空白配置，有显式基线值 (competence=0.5, deception=0.3 等)
  - 四种难度的轴值形成差异化梯度

## 回归保护

- 已覆盖的 Alpha 1.0 流程：difficulty acceptance、preset 结构测试
- 已覆盖的 Alpha 1.1 流程：team boundary 测试、temperature 范围测试

## 结论

- 是否满足 Done：是
- 残留风险：多轴值尚未在 agent 实际决策中使用，需要后续任务 (A11-DIFF-FIX-024/025/026) 将轴值接入 prompt 和决策逻辑。
- 后续任务：A11-DIFF-FIX-024（Standard 基线合同）、A11-DIFF-FIX-025（Master 欺诈预算）、A11-DIFF-FIX-027（行为级验收）
