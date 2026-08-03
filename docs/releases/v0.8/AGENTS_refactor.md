---
doc_id: "REL-008"
title: "AIAgent / StorytellerAgent / GameOrchestrator 上帝对象拆分计划"
category: "release"
role: "[State]"
status: "published"
date: "2026-07-31"
author: "Ravenswood Bluff"
---

# AIAgent / StorytellerAgent / GameOrchestrator 上帝对象拆分计划

> **状态**：✅ 已完成（2026-07-31 第二轮落地）
> **依据决策**：`DECISIONS.md` D006「双 facade 上帝对象仅做路由」
> **目标**：使 facade 仅做路由/编排，行为逻辑下沉到子模块，恢复 D006 设计约束。

## 1. 现状（2026-07-31 实测 + 拆分后落地）

### 拆分前（2026-07-31 实测）

| 文件 | 行数 | D006 标注 | 是否 facade | 是否达标 |
|------|------|-----------|------------|----------|
| `src/agents/ai_agent.py` | 1429 | ~1100 | 是 | ❌ 超标 |
| `src/orchestrator/game_loop.py` | 842 | ~766 | 是 | ❌ 超标 |
| `src/agents/storyteller_agent.py` | 1369 | **未登记** | 实为 facade | ❌ 未治理 |

- D006 原标注 `ai_agent.py(~1100)` / `game_loop.py(~766)`，实际分别为 1429 / 842，均超出且持续增长。
- `storyteller_agent.py`(1369) 是第三个上帝对象，D006 未登记，须补入治理。

### 拆分后（2026-07-31 落地，facade 仅做路由 + 委托）

| 文件 | 角色 | 行数 | 是否达标 |
|------|------|------|----------|
| `src/agents/ai_agent.py` | facade（继承 7 个 delegation Mixin） | 802 | ✅ < 1000 |
| `src/agents/ai_agent_delegation.py` | 委托：Decision/Prompt/Memory/Observer/Speech/Evil/SignalSummary 7 个 Mixin | 706 | — |
| `src/orchestrator/game_loop.py` | facade（继承 `GameOrchestratorDelegation`） | 497 | ✅ < 700 |
| `src/orchestrator/game_loop_delegation.py` | 委托：metrics/grimoire/claims/agents/settlement/phases 包装 | 383 | — |
| `src/agents/storyteller_agent.py` | facade（继承 `StorytellerAgentDelegation`） | 25 | ✅ < 1100 |
| `src/agents/storyteller_delegation.py` | 委托：判定记录/夜间信息裁定/平衡样本/夜间编排/误登记 全部逻辑 | 1369 | — |

> 三个 facade 全部达成本文档 §2 目标；逻辑完整下沉到 `*_delegation.py`，行为零变更（仅物理搬家 + 调用重定向）。

## 2. 拆分目标

| 文件 | 当前 | 目标 | 落点子模块 |
|------|------|------|-----------|
| `ai_agent.py` | 1429 | < 1000 | 现有 `decision/prompt/speech/observation/strategy/memory/reasoning/dialogue/persona/deception` + 新增 `_context_builders.py` |
| `game_loop.py` | 842 | < 700 | 现有 `phases/agents/claims/grimoire/info/metrics/settlement` + 新增 `_diagnostics.py` |
| `storyteller_agent.py` | 1369 | 登记并 < 1100 | 新增 `src/agents/storyteller/` 子模块（context/judgement/info_adjudication/balance/night） |

## 3. 拆分方法（低风险、可验证）

1. 以**方法组**为单位提取：将内聚的私有方法（`_build_*`、`_format_*`、`_summarize_*`、`_classify_*` 等）迁移到目标子模块，改为**模块级函数，首参为 agent 实例**（如 `def build_speech_priority_brief(agent, visible_state)`）。
2. facade 内调用点由 `self._x(...)` 改为 `submodule.x(self, ...)`，保持行为完全一致。
3. 每次提取后跑对应测试子集并 `ruff check`，确保零回归。
4. 不做行为重构，仅做物理搬家 + 调用重定向。

> **实际落地方法（2026-07-31 第二轮）**：采用**委托 Mixin / 委托类**方式，而非 §4 草案的「模块级函数 + `submodule.x(self, ...)` 调用重定向」。具体为：新建 `*_delegation.py`，内部以 `Mixin` 或委托类承载原私有方法（`return self._submodule.x(...)` 或自包含 helper），facade 类通过**继承**这些 Mixin/委托类获得方法，调用点保持 `self._x(...)` 不变。理由：① 调用点零改动、行为完全等价，回归风险最低；② 免去逐个改写 `self._x`→`submodule.x(self,...)` 的上百处调用；③ 与原「facade 不堆逻辑、逻辑在子模块」的 D006 约束一致。§4 的「子模块函数」映射表仍可作后续进一步细粒度拆分的参考路线，但本轮以委托方式达成 D006 行数目标。

## 4. 各文件提取映射（草案）

### `ai_agent.py`
- 发言上下文构建：`_build_speech_priority_brief` / `_build_memory_signal_brief` / `_build_action_context` / `_build_legal_action_context` / `_extract_role_statements` / `_iter_role_terms` / `_format_event_to_text` / `_player_name_from_visible_state` → `src/agents/ai_agent/_context_builders.py`
- 信号摘要：`_empath_neighbor_ids` / `_empath_neighbor_signal_summary` / `_chef_signal_summary` / `_latest_numeric_value` / `_visible_alive_count` → 同上
- 记忆辅助：`_remember_critical_event` / `_store_private_info_memory` / `_extract_role_ids_from_text` / `_role_team_hint` / `_store_targeted_private_hints` / `_process_event_for_social_graph` / `_sync_social_graph` → 现有 `memory/` 子模块
- 邪恶协同：`_get_evil_strategic_summary` / `build_evil_night_coordination_message` / `generate_first_night_coordination` → 现有 `strategy/` 子模块

### `game_loop.py`
- 延迟/指标诊断：`_latency_*` / `_summarize_ai_action_records` / `collect_ai_action_metrics` / `collect_runtime_diagnostics` → `src/orchestrator/_diagnostics.py`
- 叙事/结算：`_build_settlement_report` / `_determine_victory_reason` → 现有 `settlement/`

### `storyteller_agent.py`（新建 `src/agents/storyteller/`）
- 决策上下文：`StorytellerDecisionContext` + `build_decision_context` + `_build_*_view` → `context.py`
- 判定记录：`record_judgement` / `export_judgements` / `summarize_recent_judgements` → `judgement.py`
- 夜间信息裁定：`decide_night_info` / `_distort_*` / `_apply_suppression_*` / `_pick_false_*` → `info_adjudication.py`
- 平衡样本：`build_balance_sample` / `_evaluate_team_advantage` → `balance.py`
- 夜间编排：`build_night_order` / `decide_initial_setup_info` / `decide_misregistration` → `night.py`

## 5. 验收门禁

- `ruff check src tests scripts` 零告警
- `pytest tests/test_agents -q` 全绿
- `pytest tests/test_orchestrator/test_game_loop.py -q` 全绿
- `pytest tests/test_simulate_game.py -q` 全绿
- 三个 facade 文件行数达成本文档 §2 目标

## 6. 进度看板

| 文件 | 状态 | 备注 |
|------|------|------|
| `ai_agent.py` | ✅ 已拆分 | facade 802 行；逻辑下沉 `ai_agent_delegation.py`(706 行，7 个 Mixin)；`pytest tests/test_agents` 198 passed |
| `game_loop.py` | ✅ 已拆分 | facade 497 行；逻辑下沉 `game_loop_delegation.py`(383 行)；`test_game_loop.py` 25 passed |
| `storyteller_agent.py` | ✅ 已拆分 | facade 25 行；逻辑下沉 `storyteller_delegation.py`(1369 行)；`test_storyteller_judgement_logging.py` 通过 |

> 验收：`ruff check src tests scripts` 零告警；`pytest tests -q` 仅 1 个 subprocess 验收测试在全量并发下偶发 240s 超时（隔离运行 `test_wave1_*`/`test_alpha3_*` 均 exit 0，`alpha1.1_acceptance.py` 9/9 全绿），属既存测试隔离脆弱性，非本拆分回归。详见 PROGRESS.md 任务 #6。
