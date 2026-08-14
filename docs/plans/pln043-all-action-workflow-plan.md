---
doc_id: "PLN-043"
title: "全动作声明式工作流：agent 决策统一工作流化（认知推广）"
category: "planning"
role: "[Delta]"
status: "published"
date: "2026-08-14"
updated: "2026-08-14"
author: "Ravenswood Bluff"
---

# 全动作声明式工作流：agent 决策统一工作流化（PLN-043）

> 日期：2026-08-14
> 状态：**published**——2026-08-14 T1-T6 全量完成：710 快速单测全绿 + ruff 0 + 10/10 gate + mock 双态验证 + live 实测（RPT-019，观点演化闭环生效）。
> 诉求（用户 2026-08-14）：把认知工作流推广到**全部动作**，把所有 agent 决策统一为**声明式工作流**——每个动作都是 recall→decide→validate→record 的显式编排，与 PLN-042 的 speak 认知工作流对齐。
> 前情：PLN-042 已实现 speak/defense_speech 的认知工作流试点（`cognitive_workflow.py`，`BOTC_COGNITIVE_SPEAK=1`）；PLN-041 已提供 Workflow DSL/引擎/trace。本计划把**全部动作**（vote / nomination_intent / nominate / night_action / death_trigger / slayer_shot / speak / defense_speech）统一为声明式工作流。

---

## 1. 现状盘点（2026-08-14）

| 动作 | 当前路径 | 认知/工作流状态 |
|------|---------|----------------|
| speak / defense_speech | 认知块（观点形成）→ 草稿复用 或 LLM 工具调用 → normalize → sanitize | ✅ 已有显式认知工作流（recall→reason→speak→record，开关 off 时走原路径） |
| vote / nomination_intent | `local_low_value_decision`（本地启发式）或 LLM → normalize → fallback | ❌ 隐式流程，无观点形成、无工作流实例 |
| nominate | LLM 工具调用 → normalize → fallback | ❌ 同上 |
| night_action / death_trigger | LLM 工具调用 → normalize → fallback | ❌ 同上 |
| slayer_shot | 本地判定（`_select_slayer_shot_target`） | ❌ 同上 |

**关键事实**：
- `act()` 是**隐式工作流**：草稿复用 → 本地启发式 → 猎手判定 → 记忆检索 → LLM 决策 → normalize/fallback → 记录。所有动作都经它，但无显式编排。
- 所有动作已有 `ActionTrace` 落盘（PLN-041 Phase 4，仅 live）——**可观测性已就绪**，缺的是"声明式编排 + 观点层参与"。
- 观点演化（`ViewpointEngine.update_with_new_evidence` / supersede）已实现但**未接入主循环**——动作决策结果没有回写观点库。

## 2. 目标架构

```
act() 入口（BOTC_WORKFLOW_ACTIONS=1 时路由）
  └─ run_action_workflow(action_type) → 声明式 Workflow 实例
       ├─ recall   : 记忆快照（hard/soft 分级）+ 激活观点摘要 + 局势要点   （零 LLM）
       ├─ reason   : 观点形成/更新（speak/defense/nominate/night 启用；vote 跳过）  （确定性，LLM 不参与数值）
       ├─ decide   : 复用决策原语（本地启发式 / LLM 工具调用 / slayer 判定）       （按动作类型选路）
       ├─ validate : normalize_decision 合法性校验 + fallback                       （复用）
       └─ record   : 决策结果 → 观点库回写（update_with_new_evidence 演化闭环）+ ActionTrace + workflow trace
```

**核心设计原则**：
1. **原语化重构（行为零变更）**：把 `act()` 内部各阶段提取为独立方法（`_decide_local_low_value` / `_decide_slayer_shot` / `_draft_reuse_decision` / `_decide_via_llm`），`act()` 默认路径调用顺序不变——696 测试即回归门禁。
2. **工作流 = 编排层，decide 复用原语**：工作流节点不重新实现决策逻辑，只是显式编排（包装非重写红线）。
3. **开关默认 off**：`BOTC_WORKFLOW_ACTIONS=1` 开启，默认走原 `act()` 路径——mock 全量零回归。
4. **观点演化闭环**：record 节点把本次决策的 reasoning/证据回写观点库，新证据更新置信度/冲突 supersede——补齐 PLN-042 预留的"观点演化接入主循环"。
5. **token 分级**：vote/低价值动作**不引入 LLM**（decide 走本地启发式，确定性零成本）；reason 只对 speak/nominate/night 等高价值动作启用（复用 PLN-042 确定性引擎，零 LLM）。

## 3. 任务板（SpecForge TDD，每项先 RED 后 GREEN）

| # | 任务 | 验收标准 |
|:--:|------|------|
| T1 | **决策原语化重构**：`act()` 提取 `_decide_local_low_value` / `_decide_slayer_shot` / `_draft_reuse_decision` / `_decide_via_llm` 四个原语，`act()` 默认路径调用顺序与行为完全一致 | ✅ 696 既有测试零回归 + ruff 0；原语可被工作流节点独立调用 |
| T2 | **动作工作流工厂**：`src/agents/workflow/action_workflows.py` 为 8 种动作声明 Workflow（recall→decide→validate→record；vote 走本地启发式；nominate/night 走 LLM；slayer 走本地判定） | ✅ 14 单测：节点声明完整、入口 recall、decide 复用原语 |
| T3 | **执行器路由**：`act()` 开头加 `BOTC_WORKFLOW_ACTIONS=1` 路由，关闭时原路径零差异；失败回退原路径 | ✅ 3 单测：开关开/关行为对比、trace 字段、回退 |
| T4 | **观点演化闭环**：record 节点把决策 reasoning 写入观点库（有激活观点 update/supersede；无则创建软印象观点作为演化起点，不 gate 不注入发言） | ✅ 3 单测：回写更新置信度、决策创建观点（演化起点） |
| T5 | **严格回归**：全量 pytest（新增 14）+ ruff 0 + format 0 + doc health + 10/10 gate + mock 8 人局 | ✅ 710 全绿 + ruff 0 + format 0 + doc health PASS + 10/10 gate + mock 开关 off 零 trace 新增 + 开关 on 26 trace 覆盖 4 动作 |
| T6 | **live 实测验收**：真实 LLM（DeepSeek）5 人局 day_1，`BOTC_WORKFLOW_ACTIONS=1` | ✅ ① 52 trace 覆盖 4 类动作工作流；② 观点演化闭环：11 条观点全由决策创建、6 条被后续决策更新；③ fallback=0；④ 决策全合法；⑤ 节点完整（recall/decide/validate/record） |

## 4. DoD（完成定义，全部满足才算完成）

1. 全量 `pytest tests -q` 全绿（含 slow，基线无回归）
2. `ruff check src tests scripts` = 0；`ruff format --check` = 0
3. `check_doc_health.py` PASSED
4. `alpha1.1_acceptance.py` 10/10 全绿
5. mock 8 人局 game_over + 开关 off 零污染（无新增 viewpoints/action_trace/trace）
6. **live 5 人局 day_1 实测通过**（§3 T6 五条验收全过）
7. 文档收尾：DECISIONS D019 + PROGRESS 任务板 + PLN-043 published + RPT-019 实测报告

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| act() 原语化重构破坏热路径（草稿复用/前缀缓存/双超时） | 原语只做"提取不重组"，默认路径调用顺序逐行保持；696 测试 + mock 8 人局为硬门禁 |
| 全动作工作流烧 token | token 分级：vote 零 LLM（本地启发式）；reason 确定性零 LLM；仅 decide(LLM 动作) 保持既有预算 |
| 前缀缓存破坏 | 观点摘要/检索只进 user 段；system 稳定（D013/D014） |
| 信息隔离 | 快照排除阵营私密（复用 build_memory_snapshot）；决策回写观点前过敏感过滤 |
| 开关语义混乱（三开关并存） | `BOTC_WORKFLOW_ACTIONS=1` 为总开关（含认知 speak）；`BOTC_COGNITIVE_SPEAK` 保持独立（只开 speak 认知）；`BOTC_VIEWPOINTS` 只控制观点库落盘 |

## 6. 相关文档

- PLN-042（认知工作流试点）、PLN-041（Workflow 引擎/RAG）、RPT-018（认知 live 实测）
- DECISIONS D018（认知工作流落地）、D016（工作流+RAG）
- `.codebuddy/rules/global.md`（GameState 不可变/信息隔离/前缀缓存）
