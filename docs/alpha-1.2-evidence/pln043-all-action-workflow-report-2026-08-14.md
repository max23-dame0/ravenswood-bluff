---
doc_id: "RPT-019"
title: "PLN-043 全动作声明式工作流实施与 live 实测报告"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-14"
author: "Ravenswood Bluff"
---

# PLN-043 全动作声明式工作流实施与 live 实测报告

> 覆盖：2026-08-14，PLN-043（`docs/plans/pln043-all-action-workflow-plan.md`）T1-T6 全量实施 + live 实测验收。
> 关联决策：DECISIONS D019（全动作声明式工作流落地）。

---

## 1. 目标

用户诉求（2026-08-14）：把认知工作流推广到**全部动作**，把 agent 玩家所有决策统一为**声明式工作流**——每个动作都是 recall→decide→validate→record 的显式编排（对齐 PLN-042 的 speak 认知工作流）。

## 2. 实施内容（T1-T5，SpecForge TDD）

| 任务 | 交付 | 测试 |
|:--:|------|:--:|
| T1 | **决策原语化重构**：`act()` 提取 4 个原语 `_decide_local_low_value` / `_decide_slayer_shot` / `_draft_reuse_decision` / `_decide_via_llm`（纯提取，行为零变更，`act()` 按原顺序调用） | 696 既有测试零回归（重构门禁） |
| T2 | **动作工作流工厂**：`src/agents/workflow/action_workflows.py`，8 种动作类型声明 Workflow（recall→decide→validate→record），decide 节点复用决策原语（包装非重写） | 14 |
| T3 | **执行器路由**：`act()` 开头 `BOTC_WORKFLOW_ACTIONS=1` 路由（默认 off）；失败回退原路径 | 3 |
| T4 | **观点演化闭环**：record 节点决策→观点库回写（有激活观点则 update/supersede；无则**创建软印象观点**作为演化起点，不 gate 不注入发言） | 3 |
| T5 | **严格回归**：全量 pytest + ruff + format + doc health + 10/10 gate + mock 8 人局 | **710 全绿**（含新增 14 测试） |

**关键设计**：
- **包装非重写**：decide 节点复用既有决策原语（本地启发式/猎手/草稿/LLM），不重新实现决策逻辑——`act()` 默认路径逐行等价；
- **token 分级**：vote/nomination_intent 零 LLM（本地启发式确定性）；reason 全确定性零 LLM；
- **信息隔离**：recall 用 `build_memory_snapshot`（排除阵营私密）；观点回写证据只取 reasoning 文本；
- **前缀缓存**：观点摘要只进 user 段（D013/D014）；system 稳定。

## 3. 验证结果（全部实测）

| 检查项 | 结果 |
|------|------|
| `pytest tests -q -m "not slow"` | ✅ **710 passed / 0 failed / 0 errors** |
| ruff check / format | ✅ 0 / 0 |
| `check_doc_health.py` | ✅ PASSED |
| `alpha1.1_acceptance.py` | ✅ **10/10 全绿** |
| mock 8 人局（开关 off） | ✅ game_over，**零新增** workflow trace（95 个存量均为历史测试产物） |
| mock 5 人局（开关 on） | ✅ 26 个新 trace 覆盖 4 种动作工作流（speak/vote/defense/nomination_intent） |

## 4. live 实测验收（T6，真实 DeepSeek 5 人局 day_1）

| 验收项 | 结果 |
|------|------|
| ① 全部动作走工作流 | ✅ 52 个 trace 覆盖 action_speak/action_vote/action_defense/action_nomination_intent |
| ② 观点演化闭环 | ✅ 5 玩家 viewpoints 落盘；**11 条观点全部由决策创建（decision_feedback），6 条被后续决策更新**（updated_at > created_at） |
| ③ fallback=0 | ✅ 全部动作 fallback=0 |
| ④ 决策合法 | ✅ validate 无 invalid 拦截（workflow_invalid_decision 零触发） |
| ⑤ 节点完整性 | ✅ 采样 action_vote trace：recall/decide/validate/record 四节点全 |
| ⑥ 开关关闭对照 | ✅ mock 8 人局开关 off 零 trace 新增（行为与现状一致） |

## 5. 关键踩坑（已固化 MEMORY.md）

1. **record 只回写不创建**：初版 `_feedback_decision_to_viewpoints` 无激活观点时直接跳过 → live 局（无认知 speak 开关）观点库恒空，演化闭环无源。修复：无激活观点时从决策**创建软印象观点**（不 gate 不注入发言，仅作演化起点）。
2. **测试环境陷阱**：DummyBackend 返回 `{"foo":"bar"}` 会先被 `_normalize_decision` 兜底（empty_speech）而非留给 validate 节点——validate 单测需 monkeypatch `_decide_via_llm` 直接返回无 action 决策；nominate 的 legal_targets 约束（phase/状态）使构造合法提名场景复杂，改用 vote 场景测试。
3. **act() 原语化风险**：大段提取（378 行内联 → 原语方法）必须逐行等价——696 既有测试为硬门禁，实测零回归。

## 6. 后续建议

1. **speak 认知工作流并入动作工作流**：当前 speak 有两条路径（BOTC_COGNITIVE_SPEAK 认知 + BOTC_WORKFLOW_ACTIONS 动作），可统一为动作工作流的 reason 节点。
2. **观点注入发言**：观点库已含"关注对象+置信度"，可在 speak 的 stable user 段注入观点摘要（已实现 build_summary，接入时机待评估 token 成本）。
3. **动态 RAG 进 recall 节点**：检索本局内前人发言作为 soft 证据源。
