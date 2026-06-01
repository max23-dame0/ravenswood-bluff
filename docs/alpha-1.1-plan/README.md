# Alpha 1.1 开发入口

Alpha 1.1 的主计划见 [alpha-1.1-plan.md](../alpha-1.1-plan.md)。

## 核心文档

- [主计划：Gameplay & AI Difficulty](../alpha-1.1-plan.md)
- [验证规范：证明改进真实存在](verification_policy.md)
- [证据索引与模板](../alpha-1.1-evidence/README.md)

## 任务板

- [M5：AI 响应速度与流畅体验](task_m5_ai_speed_flow.md)
- [M5-R：AI 发言质量回归与并行机制纠偏](task_m5r_ai_speech_quality_repair.md)
- [M6：难度系统校准与架构补丁](task_m6_difficulty_system_refactor.md)
- [M7：验证规范与增量证据](task_m7_validation_evidence.md)

## 后续开发流程

1. 从主计划的 P0/P1/P2 任务板选择任务 ID。
2. 在对应 M 任务板中补齐实现范围、验收命令和证据等级。
3. 完成代码或文档改动。
4. 按 [verification_policy.md](verification_policy.md) 记录基线、命令、结果和残留风险。
5. 任务完成后再更新主计划和任务板状态。

## 当前重点

- M5 负责 AI 响应速度，重点证明多人局等待时间确实下降；M5-R 负责修复并行最终发言和低信息 fallback 带来的发言质量回归。
- M6 负责难度系统补丁，重点证明不同难度的 AI 行为确实不同。
- M7 负责测试、验收和证据留存，重点防止“实现存在但增量不可证”。

## 相关实现入口

- `scripts/alpha1.1_acceptance.py`：Alpha 1.1 聚合验收入口。
- `scripts/parallel_benchmark.py`：并行与速度基准工具。
- `scripts/difficulty_acceptance.py`：难度配置验收。
- `scripts/difficulty_comparison.py`：难度对比验收。
- `scripts/ai_speed_acceptance.py`：计划中的速度验收入口。
- `scripts/difficulty_behavior_acceptance.py`：计划中的难度行为验收入口。
