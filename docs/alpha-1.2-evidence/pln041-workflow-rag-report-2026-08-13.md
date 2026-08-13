---
doc_id: "RPT-017"
title: "PLN-041 工作流 + RAG 融入实施与验证报告"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-13"
author: "Ravenswood Bluff"
---

# PLN-041 工作流 + RAG 融入实施与验证报告

> 覆盖：2026-08-12 至 2026-08-13，PLN-041（`docs/plans/血染钟楼_工作流与RAG融入计划_2026-08-12.md`）全量实施 + D017 验收 flaky 修复。
> 关联决策：DECISIONS D016（工作流 + RAG 融入落地）、D017（persona_vote_bias 纳入 archetype 维度）。

---

## 1. 背景与目标

用户诉求（2026-08-12）：把每次 agent 玩家的**决策/发言**都包装为一个工作流，并引入 RAG 检索**规则书 / 对局经验 / 网络玩家分析经验**，减少大模型不按照规则乱发言的幻觉。实施要求：按 SpecForge TDD 工作流逐项完成、全部功能过单元测试与实测、完成后做 harness 治理与文档治理。

## 2. 可行性核查结论（先行）

对照代码库逐条核实计划文档断言（详见 PLN-041 §5），两处关键纠偏：

1. **Faiss 稠密检索运行时实际不可用**：`vector_memory.py` 存在但 `.venv` 未装 faiss/numpy，`search()` 空转返回 `[]`——"RAG 雏形已有"是纸面断言。
2. **玩家侧已有防幻觉防线**：`normalize_decision` 合法性校验 / `fallback_decision` 兜底 / `local_low_value_decision` 本地启发式 / `_sanitize_public_speech_content` 净化——残余幻觉集中在**发言内容层面**（角色能力描述/规则引用错误），正是规则知识注入最有价值之处。

结论：落地顺序按用户诉求重排为 **规则静态注入 > 检索注入 > 工作流化**；工作流化必须"包装非重写"（`act()` 是深度优化热路径，重写会击穿 token 预算/草稿复用/前缀缓存/既有测试）。

## 3. 实施内容

### 3.1 检索基础设施（Phase 1-2，T1-T7）

| 模块 | 文件 | 说明 |
|---|---|---|
| 规则知识库导出器 | `src/content/rule_knowledge.py` | 从 `trouble_brewing_terms.py` + `night_order` + `RoleDefinition` 导出 22 角色结构化条目（name/team/role_type/ability/desc/order） |
| 分块器 | `src/agents/memory/retrieval/chunker.py` | 规则按角色条目分块；历史对局按轮次+事件分块（元数据 round/phase/type） |
| BM25 稀疏检索 | `src/agents/memory/retrieval/bm25_retriever.py` | `rank_bm25`，纯本地零模型依赖，embeddings 降级兜底（**必装**） |
| 双路混合检索 | `src/agents/memory/retrieval/hybrid_retriever.py` | BM25 + Faiss 稠密（可选，缺依赖自动降级）+ RRF 融合 |
| 持久化 | `src/agents/memory/retrieval/retrieval_store.py` | 索引 + metadata 落盘 `data/agents/_retrieval/`，启动重建 |
| 统一注入管线 | `src/agents/memory/retrieval/retrieval_pipeline.py` | `retrieve → 敏感过滤 → 相关性门控 → 注入`，收敛 vector_memory/shared_pool/player_profile 三套检索 |

依赖变更：`pyproject.toml` 新增 `rank-bm25>=0.2`（必装）；numpy/faiss-cpu 可选（本地已装 faiss-cpu 1.15.0 + numpy 2.5.2）。

### 3.2 规则书静态注入（Phase 3，T9，防幻觉核心）

- `AIAgent.load_player_profile` setup 期调用 `build_role_rulebook_context`，注入 stable_context **首段**（同局逐 token 稳定、零缓存破坏，遵守 D013/D014）。
- 内容：角色能力边界（如洗衣妇"仅首夜一次"、贞洁者"首次被提名"）、阵营红线、动作时机——直接约束发言中的规则引用幻觉。
- 敏感过滤：管线对 `type=rule` 白名单放行（`is_sensitive` 含裸词「恶魔」会误杀规则文本，见 §5 踩坑②）。

### 3.3 工作流引擎（Phase 4，T11-T15）

| 模块 | 文件 | 说明 |
|---|---|---|
| Workflow DSL | `src/agents/workflow/workflow.py` | `ToolCallNode`（超时/重试）/ `ConditionNode`（分支）/ `ParallelNode`（并行）声明式定义 |
| 执行器 | `src/agents/workflow/engine.py` | 调度 + 状态跟踪 + 超时重试 + `WorkflowTrace` 落盘 JSON 可回放 |
| 说书人裁决试点 | `src/agents/workflow/storyteller_workflows.py` | 6 工具编排为显式工作流（包装非重写，handler 复用 `invoke_tool`）；LLM 仅保留 `choose_distortion` 节点（`BOTC_ST_LLM_STRATEGY` 默认 off，确定性红线验证：默认路径零 LLM 调用） |
| 玩家行动轨迹 | `src/agents/workflow/action_trace.py` | 每次决策/发言落盘 `data/agents/{player_id}/games/{game_id}/action_trace.jsonl`；**仅 live 落盘**（`BOTC_BACKEND=mock` 关闭），mock 测试零污染 |

### 3.4 评测与门禁（Phase 3/5，T10/T16-T17）

- `scripts/benchmark/retrieval_quality_benchmark.py`：规则评测集 22 条（每角色 1 条）+ 混合评测集（`storyteller_eval_samples/full_game_nodes` 采样）+ Recall@k/MRR + 阈值门禁（默认 0.85/0.80）。
- `scripts/acceptance/retrieval_workflow_acceptance.py`：检索质量 gate + 工作流轨迹完整性 gate（start/node/finish 事件齐全、节点完整、结果正确、落盘可回放）。
- 已登记进 `scripts/alpha1.1_acceptance.py` 聚合门禁（10 gate）。

### 3.5 D017：验收 flaky 根因修复（2026-08-13）

**现象**：全量 slow 模式 6 项验收失败（wave3 / a3_memory / alpha3 / long_game_ai / ai_evaluation）。

**根因**（非 mock 噪声，是生产行为缺陷）：
- vote 走本地判定路径，suspicion 常落 `threshold ± margin(0.06)` 模糊带 → `DecisionEngine.persona_vote_bias` 兜底；
- 该函数只看**随机 pick 的 `decision_style` 文案**（`refresh_persona_profile` 用 `_pick_stable` 从 6 模板 pick，与 archetype 弱相关）→ aggressive/silent 投票行为趋同：
  - `aggressive_vote_push_rate 1.0 <= 1.0`（4 项）
  - `persona_diversity_score 0.2`（5 个 archetype 仅 1 个独特签名，2 项）

**修复**：`persona_vote_bias` good 阵营分支先按 `archetype.assertiveness`（稳定人格锚点）定倾向：`high`（aggressive/paranoid/strategist）→ yes；`low`（silent/cooperative/protector/outsider_vibe）→ no；`neutral`/无 archetype 回退原文案。evil 分支不动。诊断脚本：`tmp_work/diag_vote.py`。

## 4. 验证结果（全部实测）

| 检查项 | 结果 |
|---|---|
| `pytest tests -q`（全量含 slow） | ✅ **676 passed / 0 failed / 0 errors**（254s；快速单测 657） |
| `ruff check src tests scripts` | ✅ 0 告警 |
| `ruff format --check src tests scripts` | ✅ 0 未归一（含 ruff 0.16.1 存量格式归一，用户确认保留） |
| `python scripts/check_doc_health.py` | ✅ PASSED（82+ 文件，仅 1 个历史遗留 GEMINI 绝对路径 warning） |
| `python scripts/alpha1.1_acceptance.py` | ✅ **10/10 全绿**（含新增 retrieval+workflow gate） |
| 检索质量实测（BM25-only） | ✅ Recall@5=**1.0** / MRR=**1.0**（22 条规则评测集） |
| mock 8 人局端到端 | ✅ 完整 game_over，action_trace 零污染 |
| D017 修复后 slow 验收 | ✅ 此前 6 项失败全部恢复通过 |

新增测试统计：检索 4 文件（BM25/hybrid/store/pipeline）+ 规则知识库 + 评测脚本指标 + 工作流 17 项 + 说书人试点 7 项 + 行动轨迹 7 项 + gate 包装 ≈ **+95 测试**。

## 5. 关键踩坑（已固化 MEMORY.md）

1. **rank_bm25 高频词 IDF=0**：词在 ≥50% 文档出现则 IDF=0，小语料测试必然 miss——测试改用真实 22 条规则语料。
2. **`is_sensitive` 误杀规则文本**：含裸词「恶魔」，规则书文本会被敏感过滤拒绝——管线对 `type=rule` 白名单放行。
3. **mock embeddings 污染 RRF**：mock 返回长度向量无语义，会打乱融合排序——评测默认 BM25-only（`--dense` 需真实 embeddings）。
4. **trace 类名黑名单不可靠**：`PassiveBackend` 等自定义替身漏网导致测试污染——改为按 `BOTC_BACKEND` 环境变量判定（mock 关闭）。
5. **dataclass 继承默认值**：`Node` 有默认值字段后，子类非默认字段报 `TypeError`——全字段给默认值 + `__post_init__` 校验。

## 6. 提交与仓库状态

- 提交策略：按逻辑分组原子提交（检索基础设施 / 规则注入 / 工作流引擎 / gate 评测 / 引擎修复 / 文档治理 / 格式归一），详见 git log。
- 分支：main → origin/main（push 已完成）。

## 7. 后续建议（非本计划范围）

1. **live 检索抽查**：`retrieval_quality_benchmark.py --dense` 需真实 embeddings 后端，验证 Faiss 稠密路质量。
2. **网络玩家分析经验知识源**：人工整理为"角色 × 套路 × 适用场景"结构化条目后，复用规则索引管线注入（注意来源合规）。
3. **动态案例检索**：历史对局案例只进 user 动态段（烧 token），作为 live 可选项，需评估收益。
4. **行动轨迹可视化**：`action_trace.jsonl` 已具备回放数据，可做对局分析仪表盘。
