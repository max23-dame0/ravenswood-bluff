---
description: AI 玩家与说书人智能体模块规则
globs: src/agents/**/*.py
alwaysApply: false
---
# 智能体规则 (agents)

> 适用于 `src/agents/**`。`ai_agent.py`(~1100) / `storyteller_agent.py`(~1500) 是 facade。

## 核心约束

- **改 Agent 行为进子模块**：`ai_agent.py` 委托 decision/ prompt/ speech/ observation/ strategy/ memory/ reasoning/ dialogue/ persona/ deception 共 9 子模块。勿在 facade 堆逻辑。**why**：可维护。**when_remove**：子模块合并时。
- **BaseAgent 接口**：所有 Agent 实现 `act / observe_event / archive_phase_memory / synchronize_role`。HumanAgent 经 WebSocket 代理但接口一致。**why**：orchestrator 互换 AI/真人。
- **难度系统**：`DifficultyPreset` 五轴（competence/deception/volatility/expressiveness/information_openness）× 4 预设。**why**：多维度难度。新增轴须为 4 预设全设值并经 `difficulty_behavior_acceptance.py` 验证。
- **Good AI 不得吃 evil 策略**：注入 strategy 前先查 `player.team`。**why**：破坏公平。
- **兜底模式**：`_timed_act` 包 `agent.act` 硬超时 → 合法兜底；公众 `speak`/`defense_speech` 兜底属应急路径，live 局公开发言兜底率 >20% 即发布 blocker。

## 代码风格

- 记忆四层：working / episodic / vector / social_graph（`memory/` 下）。
- persona 9 archetype（`persona_registry.py`）。

## 禁止模式

- 在 `ai_agent.py` facade 内直接写决策/提示词逻辑（应下沉 decision/ prompt/）。
- 给 Good 阵营 Agent 注入 evil strategy 提示。
- 把 `_extract_claims_via_llm` 做成同步阻塞（须异步、限流、非阻塞）。

## 推荐模式

- 调试决策：用 `scripts/debug/dump_ai_prompt.py` 抽取发给 LLM 的 prompt；`data/exports/` 看 trace。
