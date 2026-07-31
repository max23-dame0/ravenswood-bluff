---
description: 对局编排与事件分发模块规则
globs: src/orchestrator/**/*.py
alwaysApply: false
---
# 编排规则 (orchestrator)

> 适用于 `src/orchestrator/**`。`game_loop.py`(~766) 是 facade。

## 核心约束

- **facade 仅路由**：`game_loop.py` 委托 phases/ agents/ claims/ grimoire/ info/ metrics/ settlement 等子模块。改编排行为进子模块。**why**：可维护。**when_remove**：子模块合并。
- **EventBus + Broker**：所有状态变更经 `EventBus.publish`；orchestrator 订阅 `"*"` 转发到日志与 broker；`InformationBroker` 按 `Visibility` 过滤产出 `AgentVisibleState`。**why**：信息隔离与可重放。
- **顺序白天发言**：`day_discussion.py` 逐次处理 AI 发言，禁 `asyncio.gather` 最终发言。**why**：上下文依赖。
- **双超时预算**：orchestrator 的 `_timed_act` 超时须大于 agent 内部 `latency_budget_ms`（`_action_latency_budgets`）。**why**：避免 agent 兜底先于 orchestrator 触发。**when_remove**：统一超时机制时。
- **claim 提取非阻塞**：`_extract_claims_via_llm` 失败（空/非 JSON）须异步、限流、非阻塞，不在 live 讨论中加可见等待或告警噪声。

## 代码风格

- 阶段处理器：`night_phase.py`(574) / `day_discussion.py`(274) / `nomination_voting.py`(756)。
- `replay_parser.py` 支持日志重放调试。

## 禁止模式

- 在 `game_loop.py` facade 内堆阶段逻辑。
- 并行 `asyncio.gather` 生成白天最终发言。
- 让 claim 提取阻塞讨论主流程。

## 推荐模式

- 调试用 `SnapshotManager` 重放快照；metrics 经 `GET /api/game/metrics` 实时查看。
