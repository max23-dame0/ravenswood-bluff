---
doc_id: "PLN-042"
title: "认知工作流：观点-证据层 + 人类式决策/发言工作流"
category: "planning"
role: "[Delta]"
status: "published"
date: "2026-08-13"
updated: "2026-08-13"
author: "Ravenswood Bluff"
---

# 认知工作流：观点-证据层 + 人类式决策/发言工作流（PLN-042）

> 日期：2026-08-13
> 状态：**published**——2026-08-13 T1-T6 全量完成：692 快速单测全绿 + ruff 0 + 10/10 gate + live 实测（观点落盘/分级/fallback=0/A-B 论证式发言），报告见 RPT-018。
> 愿景来源（用户 2026-08-13）：agent 玩家的决策/发言/行动应形成**完整工作流**——像人类一样，先根据之前的印象和前人的发言去思考，**建立观点和逻辑链**，再推导决策/发言/行动；RAG 作为**真实可信信息来源的保证**。

---

## 1. 背景与动机

### 1.1 用户愿景

当前 agent 是"**直接说话，理由后补**"（发言由 LLM 一次生成，reasoning 只是事后标注）。用户要的是"**先形成论点，再说话**"——人类式认知过程：

```
之前的印象 + 前人的发言 → 思考（建立观点与逻辑链）→ 推导 → 决策/发言/行动
```

其中 RAG 负责**真实可信信息来源**（检索本局内前人发言/事件，防止"无依据断言"的推理幻觉）。

### 1.2 现状差距（PLN-038/040/041 之后）

| 愿景维度 | 现状 | 差距 |
|---|---|---|
| 基于印象思考 | `MemoryController.think` 是 ≤80 字低预算内心独白 | 是速记不是思考，不产出结构化观点 |
| 建立观点和逻辑链 | 印象（impressions）是 reflect 随机触发产物；reasoning 是事后拼接证据 | 逻辑链不显式，无"断言+证据+置信度"结构 |
| 再推导决策/发言 | 发言一次生成，reasoning 标注 | 无"论点树→语言"推导过程，幻觉无法在生成前拦截 |
| RAG 保证真实来源 | 规则静态注入（PLN-041 T9）；检索管线就绪但动态检索未启用 | "前人说过什么"靠 working_memory 摘要，细节丢失 |

### 1.3 已有基础（全部复用，不重复造轮子）

- `Workflow` DSL/执行器/trace（PLN-041 T11-T15，`src/agents/workflow/`）
- 检索管线（BM25/Faiss/RRF/门控/敏感过滤，`src/agents/memory/retrieval/`）
- 证据候选 `reasoning_evidence_candidates`（决策引擎已有硬/软证据来源）
- 行动轨迹 ActionTrace（`action_trace.jsonl`，仅 live 落盘约定）
- 规则书静态注入（`rule_knowledge.py`）

---

## 2. 核心设计

### 2.1 观点-证据模型（Viewpoint/Evidence）

```python
Evidence:
  kind: "hard" | "soft"        # 硬证据=说书人信息/公开行为；软印象=他人发言观感
  source: str                  # 来源描述（如 "fortune_teller_info" / "public_claim"）
  detail: str
  day_number / round_number

Viewpoint:
  viewpoint_id
  subject_player_id / subject_name   # 观点对象
  claim: str                         # 断言，如 "P2 可能是恶魔"
  evidence: list[Evidence]
  confidence: float                  # 0-1，随证据增减演化
  status: "active" | "superseded"
  source_action: str                 # 产生该观点的动作（speak/nominate/...）
```

落盘：`data/agents/{player_id}/games/{game_id}/viewpoints.jsonl`（追加式，**仅 live**，对齐 thoughts.jsonl/action_trace.jsonl 约定）。

### 2.2 认知工作流（复用 Workflow 引擎）

```
recall  : 加载当前激活观点摘要 + 检索本局内前人发言/事件（RAG 进 user 段）
reason  : 基于证据构建/更新论点（LLM 低预算），产出结构化 Claim（断言+证据+置信度）
decide  : 从逻辑链推导动作（合法性仍由现有决策引擎约束）
speak   : 将逻辑链压缩为自然发言（LLM 只做表达，不做论证）
record  : 观点 + 轨迹落盘
```

**防幻觉核心机制**：发言的**论证来自 reason 节点的输出**；speak 只做语言化。无证据支持的断言在 reason 阶段被降置信度或拦截（证据分级门控），幻觉在**生成前**被拦截（质变于当前的"生成后 sanitize"）。

### 2.3 试点范围

- **白天发言（speak）**：核心表达场景，逐次处理天然串行，`reasoning_evidence_candidates` 可直接升级为证据源。
- 其余动作（vote/nominate/night_action）保持既有路径（token 分级，防止预算爆炸）。
- 环境开关 `BOTC_COGNITIVE_SPEAK`：**默认 off**（行为与现状完全兼容，mock 全量测试零回归）；live 验收时开启验证真实效果。

---

## 3. 任务板

| # | 任务 | 验收标准 |
|:--:|------|------|
| T1 | 观点-证据模型 + ViewpointStore：`src/agents/reasoning/viewpoint.py`（Evidence/Viewpoint 数据类 + JSONL 落盘 + 激活观点查询 + 摘要构建） | ✅ 单测 9 个：数据类字段/落盘往返/激活与废弃/仅 live 落盘（mock 零污染） |
| T2 | 证据提取与置信度引擎：从 working_memory + `reasoning_evidence_candidates` 提取证据并分级（hard/soft），置信度计算（硬证据高权重、软证据低权重、封顶 0.95），门控要求 hard_count ≥ 1（纯软印象一律拦截），观点演化（新证据升级/冲突废弃） | ✅ 单测 12 个：hard/soft 分级精确（一条文本一条证据，CR P1-1 修复）、置信度单调性与封顶、冲突废弃、门控按 hard_count 判定（≥2 条软印象数值越阈值仍拦截，CR P1-2 修复） |
| T3 | 认知工作流组装：`src/agents/workflow/cognitive_workflow.py`（recall→reason→speak→record 节点，复用 Workflow/WorkflowTrace） | ✅ 单测 6 个：节点声明完整、执行产出 Claim 与发言、trace 落盘可回放、无证据拦截生效 |
| T4 | 试点接入：AIAgent 挂接（`BOTC_COGNITIVE_SPEAK` 开关 + speak 路径分流 + 向后兼容），观点摘要注入 user 段（同轮稳定） | ✅ 单测 10 个：开关关闭时行为与现状一致（零回归）；开启时观点链注入 LLM user 段；草稿复用也落盘观点；敏感过滤生效 |
| T5 | 严格回归：全量 pytest（含新增 ~35 测试）+ ruff 0 + format 0 + doc health + 10/10 gate + mock 8 人局 game_over | ✅ 快速单测 692 全绿 + ruff 0 + format 0 + doc health PASS + mock 8 人局 game_over（viewpoints 零污染） |
| T6 | **live 实测验收**：真实 LLM（DeepSeek）5 人局 day_1，`BOTC_COGNITIVE_SPEAK=1` | ✅ ① viewpoints.jsonl 5 玩家全落盘（含 hard/soft 证据 24/23）；② 观点链注入 user 段驱动发言（单测+live 验证）；③ fallback=0；④ 无证据断言拦截（强断言降级单测 + 无证据玩家不产生观点）；⑤ A/B 对比：开启=论证式（依据+前人说辞+隐藏底牌）vs 关闭=断言式（直接亮牌） |

## 4. DoD（完成定义，全部满足才算完成）

1. 全量 `pytest tests -q` 全绿（含 slow，新增测试全过，基线无回归）
2. `ruff check src tests scripts` = 0 告警；`ruff format --check` = 0 未归一
3. `check_doc_health.py` PASSED
4. `alpha1.1_acceptance.py` 10/10 全绿
5. mock 8 人局完整 game_over，viewpoints 零污染（mock 不落盘）
6. **live 5 人局 day_1 实测通过**（§3 T6 五条验收全过，证据落盘）
7. 文档收尾：DECISIONS D018 + PROGRESS 任务板 + PLN-042 published + RPT-018 实测报告

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 认知工作流烧 token（多节点 LLM 调用） | 只试点 speak；reason 低预算（max_tokens 受限）；vote/低价值动作不走认知路径 |
| 前缀缓存破坏（动态注入） | 观点摘要/检索结果只进 **user 段**；system 保持逐 token 稳定（D013/D014） |
| mock 行为回归 | `BOTC_COGNITIVE_SPEAK` 默认 off，mock 全量测试走原路径零回归 |
| 信息泄露（证据含恶魔/队友） | 证据提取过 `is_sensitive` 过滤；hard 证据白名单（fortune_teller_info 等既有分类） |
| live 成本/超时 | 5 人局 day_1 小规模；沿用既有双超时预算（orchestrator > agent） |

## 6. 红线约束

1. **包装非重写**：`act()` 主路径不动；认知工作流是新入口 + 开关分流，关闭即完全回退
2. **token 分级**：认知工作流只用于白天发言，其余动作保持本地启发式/既有路径
3. **证据分级**：hard/soft 显式标注，门控要求 hard_count ≥ 1——纯软印象（他人发言观感）即使置信度数值达标也一律拦截（CR P1-2 修复后的语义）
4. **信息隔离**：所有证据/检索注入前过敏感过滤
5. **仅 live 落盘**：viewpoints.jsonl 对齐 thoughts.jsonl 约定，mock 测试/模拟零污染

---

## 7. 相关文档

- `docs/plans/血染钟楼_工作流与RAG融入计划_2026-08-12.md`（PLN-041，基础设施）
- `DECISIONS.md` D016/D017
- `docs/alpha-1.2-evidence/pln041-workflow-rag-report-2026-08-13.md`（RPT-017）
