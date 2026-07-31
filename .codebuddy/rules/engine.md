---
description: 规则引擎与角色能力模块规则
globs: src/engine/**/*.py
alwaysApply: false
---
# 规则引擎规则 (engine)

> 适用于 `src/engine/**`：阶段机、规则校验、角色能力、剧本分发、数据采集。

## 核心约束

- **角色注册**：角色类继承 `BaseRole`，用 `@register_role("role_id")` 装饰，实现 `get_definition / execute_ability / can_act_at_phase / needs_night_target`。**why**：统一角色注册表 `_ROLE_REGISTRY`。**when_remove**：注册机制重构时。
- **阶段机**：`PhaseManager` 驱动 `SETUP→FIRST_NIGHT→DAY_DISCUSSION→NOMINATION→VOTING→EXECUTION→NIGHT→GAME_OVER`。**why**：单一状态流转来源。
- **规则校验**：`RuleEngine` 校验 `can_nominate / can_vote / votes_required` 等合法性。
- **剧本分发**：`scripts.py` 含 Trouble Brewing 分发表；新角色须加入分发表。
- **数据采集**：`data_collector.py` 捕快照供分析，不得影响主流程时序。

## 代码风格

- 角色按 team 分文件：townsfolk / outsiders / minions / demons。
- 高价值/边界角色（如 Imp 星传）须在 `docs/reference/rule_matrix.md` 追踪。

## 禁止模式

- 在角色实现里直接改 `GameState`（应返回经 orchestrator 应用的迁移）。
- 绕过 `PhaseManager` 手动切阶段。

## 推荐模式

- 新角色：建类 → `@register_role` → 实现能力 → 加分发表 → 在 `tests/test_engine/` 补测。
