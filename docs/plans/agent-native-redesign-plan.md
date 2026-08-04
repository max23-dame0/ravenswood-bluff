---
doc_id: "PLN-038"
title: "AI 玩家与说书人 Agent 原生重构方案：从「集中式提示词调用」到「受控自主 Agent」"
category: "planning"
role: "[Delta]"
status: "published"
date: "2026-08-03"
author: "Ravenswood Bluff"
---

# AI 玩家与说书人 Agent 原生重构方案

> 核心论断：当前 AI 玩家与说书人**都不是 agent**，而是"集中式调度 + 单次无状态 LLM 调用"（玩家）与"规则密集型确定性方法集合 + 零星 LLM 点缀"（说书人），本质是上下文工程、提示词工程与硬编码裁量逻辑的产物。本方案将两者重构为**事件驱动的受控自主 Agent**：每个实体有独立决策循环、有明确的"目标"（玩家=赢下本局；说书人=对局平衡与戏剧性）、通过标准化的工具/技能与世界交互、自主维护记忆与判决记录。
>
> 配套文档：`docs/plans/token-budget-optimization-plan.md`（PLN-037）。两方案同属一个版本节奏（Alpha 1.3），Agent 原生化天然提升 token 缓存命中（稳定 tool schema 前缀）。

---

## 1. 现状诊断：为什么当前不是 Agent

### 1.1 接口层面：Agent 是被动函数，无 loop、无目标、无工具

`BaseAgent` 仅暴露三个被动方法（`src/agents/base_agent.py`）：

| 方法 | 触发方 | 性质 |
|---|---|---|
| `act(visible_state, action_type, legal_context)` | orchestrator `_timed_act` | 引擎规定动作类型，agent 返回 JSON 决策 |
| `observe_event(event, visible_state)` | `InformationBroker.broadcast_event`（并行 gather） | 引擎推事件，agent 被动吸收 |
| `think(prompt, visible_state)` | 引擎阶段钩子 | 强制思考，返回文本 |

**证据**：`act()` 不接受"目标/策略"，只接受引擎指定的 `action_type`；返回值是 JSON 动作体而非工具调用；agent 没有任何自己的循环或主动触发逻辑。

### 1.2 认知层面：记忆维护完全被引擎硬调度

- 反思时机由硬编码阈值决定：`working_memory.observations > self._reflection_threshold` 才触发 `_reflect`（`src/agents/ai_agent.py`）。
- 阶段归档由 orchestrator 在阶段边界统一调用 `_archive_agent_phase_memories()`（`src/orchestrator/game_loop.py`）。
- 记忆结构（observation/fact/impression/social graph）是内存对象，由引擎写入、agent 无自主读写工具。

**结论**：记忆的"何时写、写什么、何时反思"由代码写死，不是 agent 自己判断。

### 1.3 世界感知层面：上下文全是"喂"，不是"取"

`act()` 每次把以下内容硬拼进 system prompt（`src/agents/ai_agent.py` + `src/agents/prompt/prompt_factory.py`）：

- 人格块、记忆档案、社交图谱、局势摘要、行动上下文、分层记忆、JSON schema……

agent 没有"按需查询世界"的工具，只能被动消费引擎塞给它的全部信息。这既是架构缺陷，也是 PLN-037 诊断的缓存命中率低（16.9%）的直接根因——大而逐轮变化的 prompt 前缀在每个变化点断裂。

### 1.4 结论

当前实现 = **集中式状态机 + 硬编码上下文组装 + 无状态单次 LLM 调用**。它"像"多 agent，实为多 prompt。玩家没有自主性，无法在需要时主动思考（如死亡后布局、静默观察、撒谎策略演进）。

### 1.5 说书人现状诊断：规则密集，但同样不是 Agent

说书人（`src/agents/storyteller_agent.py` + `storyteller_delegation.py`）比玩家更"功能化"，但同样**没有自主 loop 与目标驱动**：

- **职责**：夜信息裁定（`decide_night_info`）、平衡样本（`build_balance_sample`）、夜间编排（`build_night_order`）、初始设置（`decide_initial_setup_info` / `decide_drunk_role` / `decide_misregistration`）、判决账本（`record_judgement` / `decision_ledger`）、阶段报幕（`narrate_phase`）、局势独白（`analyze_game_situation`）。
- **LLM 介入极稀薄**：除 `analyze_game_situation`（内心独白）外，几乎所有裁决都是确定性规则或启发式随机（`_distort_fixed_info` / `_distort_storyteller_info` 等）。`_apply_suppression_to_info_async` 中已留注释"暂未实现全量 LLM 虚假信息生成，先走启发式"。
- **信息全知但被动**：`build_decision_context` 构造 `truth_view`（全量真实身份/抑制/魔典）供裁量，但说书人从不"主动查询"，只能被 orchestrator 阶段钩子调用。

**结论**：说书人是"被调用的裁决函数库"，不是 agent。它缺少：① 基于对局演绎的自主决策循环（如"当前优势过大，应主动加强干扰"）；② 把扭曲/干扰策略作为**可审计工具**的选择面（现为散落启发式）；③ 对局级记忆（判决账本已有，但未升级为说书人的自主认知）。

---

## 2. 目标架构：事件驱动的受控自主 Agent

### 2.1 设计原则

1. **规则裁判留在引擎**：回合顺序、合法性、胜负判定是不可协商的硬编码（这是游戏正确性来源）。Agent 的自主 loop 只能发生在"轮到它行动的窗口"内。
2. **信息隔离是红线**：任何 Agent 获取的世界状态必须经过 `InformationBroker.get_visible_state()` 过滤；Agent 自主写入的记忆也必须过隔离层，防止 evil 私密信息泄漏到可检索存储。
3. **自主必须按需、受控、可测**：每次 loop 的 LLM 调用受预算与策略表约束（对接 PLN-037 P0），不破坏 447 个测试基线的可预期性。

### 2.2 四层改造目标

| 层 | 现状 | 目标 |
|---|---|---|
| 决策 | 引擎逐动作调 `agent.act()`，一次调用一个动作 | 引擎守回合与合法性；轮到 agent 时**唤醒其决策 loop**（observe → deliberate → act → remember） |
| 行动 | 引擎规定 `action_type`，agent 返回 JSON | 行动标准化为 **Tool/Skill 注册表**（speak / vote / nominate / night_action / defense_speech / private_message），agent 通过 tool calling 发起 |
| 世界感知 | 每轮全量塞 `AgentVisibleState` | 提供只读工具（`observe_state` / `query_public_log` / `query_players` / `query_legal_context`），agent 按需取用（仍过隔离层） |
| 记忆 | 引擎硬编码时机/阈值，内存对象 | 提供记忆工具（`append_memory` / `read_memory` / `reflect` / `archive_phase`），**agent 自己决定何时写、何时反思**；存储落盘到 agent 自己的目录/文件 |

### 2.3 Agent 决策循环（示意）

```text
[引擎：轮到 p1，唤醒 loop]
   │
   ▼
┌─ observe ──────────┐  通过只读工具获取当前可见世界（增量，而非全量）
│  deliberate         │  可选 1 次"策略先行"LLM 调用（think / 内心独白）
│  act                │  通过工具发起动作（speak/vote/nominate/night_action...）
│  remember           │  自主调用记忆工具沉淀本轮认知/印象
└─────────────────────┘
   │
   ▼
[引擎：校验合法性 → 应用状态迁移 → 发布事件]
```

引擎仍负责：合法性校验（`RuleEngine` / `AgentActionLegalContext`）、状态迁移（`GameState.with_*`）、事件分发（`EventBus` + `InformationBroker`）。Agent 负责：**怎么想、怎么行动、记什么**。

### 2.4 说书人 Agent 目标架构

说书人重构为**第二个受控自主 Agent**，与玩家 Agent 平行但目标不同：

| 维度 | 玩家 Agent | 说书人 Agent |
|---|---|---|
| 目标 | 赢下本局（自己阵营） | 对局平衡 + 戏剧性（维持悬念） |
| 世界感知 | 受限 `AgentVisibleState`（经隔离层） | **全知** `truth_view`（真实身份/抑制/魔典/平衡态） |
| 决策循环 | observe → deliberate → act → remember | 平衡评估 → 策略选择 → 裁决/干扰 → 记账 |
| 工具 | 行动工具（speak/vote/...）+ 只读查询 + 记忆 | 裁决工具（夜信息/编排/扭曲策略）+ 平衡评估 + 记账 |
| 记忆 | 自主维护个人认知 | **判决账本**（已有 `decision_ledger`）升级为说书人认知 + 对局平衡档案 |
| LLM 介入面 | 行动/策略/发言全部 | **只在"策略选择面"介入**（扭曲策略、报幕润色、独白），确定性裁量不被 LLM 替代 |

**说书人工具注册表（新增）**：

| 工具 | 现形态 | 目标形态 |
|---|---|---|
| `assess_balance` | `_evaluate_team_advantage`（私有方法） | 只读工具：返回平衡分值/风险标记（hard_lock/early_end） |
| `choose_distortion` | 散落 `_distort_fixed_info` / `_distort_storyteller_info` | **策略选择工具**：把"扭曲策略"标准化为枚举，`distortion_strategy` 成为可审计的输入而非输出 |
| `adjudicate_night_info` | `decide_night_info` | 裁决工具：真实信息计算仍走规则引擎（确定性）；**是否扭曲/选哪条扭曲策略**由说书人 loop 决策 |
| `compose_narration` | `narrate_phase` | 报幕工具：LLM 润色可选，模板兜底 |
| `deliver_verdict` | `record_judgement` | 记账工具：所有裁决/扭曲写入判决账本（已有，保留） |
| `review_balance` | — | **新增记忆查询**：基于判决账本 + 对局平衡档案，说书人自主复盘"我上轮干扰是否过度" |

**说书人决策循环（示意）**：

```text
[引擎：夜信息 / 阶段边界，唤醒说书人 loop]
   │
   ▼
┌─ assess_balance ──────┐  查询平衡分值 + 风险标记（只读）
│  choose_strategy       │  从合法扭曲策略集中选择（LLM 可选、启发式兜底）
│  adjudicate            │  确定性计算真实信息（规则引擎）
│  deliver_verdict       │  记录判决（策略名 + 理由 + 结果）→ decision_ledger
└───────────────────────┘
```

**核心边界**：说书人的**真实信息计算永远保持确定性**（谁是真恶魔、占卜师是否命中），LLM 只能影响"**是否扭曲 + 扭曲成什么**"的选择面，且每个选择都留 `distortion_strategy` 审计痕迹。

---

## 3. 硬约束与红线（不可妥协）

| # | 约束 | 原因 |
|---|---|---|
| 1 | 回合顺序、合法性、胜负判定留在引擎 | 游戏正确性来源；自由 loop 会导致死锁/越权/顺序混乱 |
| 2 | 所有世界信息经 `InformationBroker` 过滤 | 信息隔离；evil 私密信息（TEAM_EVIL/PRIVATE）不得泄漏 |
| 3 | Agent 记忆落盘须过隔离层 | 防私密信息进入可检索文件（文件级也需要 `Visibility` 感知） |
| 4 | 白天发言顺序处理，禁 `asyncio.gather` 最终发言 | 后发言者需先发言者事件上下文（全局规则） |
| 5 | 决策 loop 受时间预算与 token 策略表约束 | 兼容 PLN-037；防止无限 loop 拖垮对局延迟 |
| 6 | `GameState` 不可变原则不变 | Agent 只能通过动作/工具提案，不得直接改状态 |
| 7 | **说书人真实信息计算保持确定性** | 谁是真恶魔/占卜师命中/夜信息真值只能来自规则引擎，LLM 不得改写真值 |
| 8 | **说书人 LLM 介入面 = 策略选择** | LLM 只能选择扭曲策略/报幕润色/独白，且必须经 `deliver_verdict` 留审计痕迹；禁止 LLM 直接产出私密信息本体 |
| 9 | **说书人干扰受平衡约束** | 扭曲策略选择以 `assess_balance` 分值为输入，禁止无依据的随机干扰；人类说书人模式（`mode=human`）完全不走 LLM 策略层 |

---

## 4. 渐进落地路径（阶段 A→D，避免大爆炸重构）

### 阶段 A：行动工具化（最小改动，立即见效）

- 将 `act()` 从"返回 JSON"重构为"返回 tool_calls"：定义 `GameActionToolRegistry`，注册 `speak` / `vote` / `nominate` / `night_action` / `defense_speech` / `private_message` 等 ToolDef。
- 复用 `src/agents/dialogue/dialogue_manager.py` 已演示的 ToolDef 范式。
- 保留 JSON 解析作 fallback（`_parse_llm_decision_json` 仍可用）。
- 产出：agent 开始"调用工具"而非"填表单"，为后续自主 loop 打基础。

### 阶段 B：策略先行小 loop（决策与行动分离）

- 在 `act()` 内引入可选前置一步：`think`（内心独白，1 次 LLM，低预算）→ `act`（基于独白发起工具调用）。
- 通过 `cached_speech_draft` / `refinement_mode` 现有机制串联，避免重复生成。
- 产出：agent 具备"先定策略再行动"的能力，更接近真人玩家的思考节奏。

### 阶段 C：记忆工具化（agent 自主维护认知）

- 新增记忆工具集：`append_memory` / `read_memory` / `reflect` / `archive_phase`。
- 把 `_reflection_threshold` 硬阈值、引擎阶段钩子触发的归档，逐步替换为 agent 自主调用（保留引擎兜底钩子）。
- 存储落盘：每 agent 一个目录（如 `data/agents/{player_id}/memory.md` + 结构化子文件），写入内容经隔离层校验。
- 产出：记忆的"时机与原则"由 agent 决定，而非代码写死。

### 阶段 D：世界感知查询化（prompt 瘦身 + 缓存命中）

- 新增只读工具：`observe_state` / `query_public_log` / `query_players` / `query_legal_context`。
- system prompt 瘦身为「稳定规则层 + 工具 schema + 人格锚点」，局势信息从工具按需获取。
- 产出：prompt 前缀稳定 → 缓存命中率大幅提升（对接 PLN-037 P1）；上下文按需取，降低输入 token。

### 阶段 S：说书人工具化（可与 A/B 并行，独立性强）

- 把 `_evaluate_team_advantage` / `_distort_*` / `narrate_phase` / `decide_night_info` 拆包为注册表工具（§2.4），接口先保持行为一致。
- 新增 `choose_distortion` 策略选择层：把现有散落 if/else 启发式收敛为「扭曲策略集」（含 `distortion_strategy` 枚举），LLM 可选介入（`BOTC_ST_LLM_STRATEGY=off|low|on`），启发式兜底。
- 新增 `review_balance` 记忆查询：说书人基于判决账本 + 平衡档案自主复盘，写入对局平衡档案（`data/storyteller/{game_id}/`）。
- 产出：说书人具备"评估 → 选策略 → 裁决 → 记账 → 复盘"的自主闭环，且每步可审计。

> 每个阶段保持：orchestrator 裁决 + `AgentVisibleState` 隔离 + `pytest tests -q` 基线不变。阶段 S（说书人）与 A/B 无耦合，可并行；建议顺序 A → B → S → C → D。

---

## 5. 与 Token 优化方案的协同

| 维度 | Agent 原生化收益 |
|---|---|
| 缓存命中 | 工具 schema 是稳定字符串，可作公共缓存前缀；对比现状大而逐轮变化的 system prompt，命中率预计从 16.9% → 60%+ |
| 输入 token | 世界状态查询化后，不再每轮全量塞局势/记忆，输入显著下降 |
| 输出 token | 行动工具化后，agent 输出的是短工具调用（结构化参数）而非长篇 JSON + reasoning；配合 PLN-037 的 thinking 分级，输出削减叠加 |
| 延迟 | 查询工具按需、策略先行小 loop 有预算约束，不会劣化对局节奏 |

**说书人专项收益**：说书人现有 LLM 介入几乎为零（仅独白），重构后 LLM 仅在策略选择面介入（`BOTC_ST_LLM_STRATEGY` 可关），增量 token 受控；同时 `distortion_strategy` 稳定枚举可作为公共前缀的一部分，进一步助益缓存。

两个方案应作为 **Alpha 1.3 同一版本** 统筹实施：先做 PLN-037 的 P0（输出削减 + 度量），再做本文档的阶段 A/B（行动工具化 + 策略先行），阶段 S（说书人工具化）与 A/B 并行，最后阶段 C/D（记忆/感知工具化）自然复用前者的稳定前缀收益。

---

## 6. 风险与权衡

| 风险 | 缓解 |
|---|---|
| 行动工具化后模型偶发不调工具/乱调参数 | 保留 JSON fallback + `MAX_AGENT_RETRIES` + 兜底决策；工具 schema 描述写严格 |
| agent 自主记忆导致遗忘关键事实/重复写入 | 记忆工具加上限与去重（复用现有 `_cap_memory_section` / dedup 逻辑）；保留引擎兜底归档 |
| 私密信息经记忆工具泄漏 | 记忆写入过 `Visibility` 校验层；`TEAM_EVIL` 内容禁止写入可被他人读取的文件 |
| 自由 loop 拖长对局 | 决策 loop 次数上限 + 时间预算（对接 PLN-037 策略表） |
| 重构影响现有测试 | 阶段 A 保持 `act()` 返回结构兼容；每阶段全量回归 `pytest tests -q` + `ruff check src tests` |
| 工具调用可能触发 reasoning_content 空 content | 参考 2026-08-03 live 验收残留风险，工具参数从 `arguments` 解析而非 content |
| 说书人 LLM 介入导致扭曲策略失真/失衡 | 真实信息计算保持确定性（约束 7）；LLM 仅选策略（约束 8）；`BOTC_ST_LLM_STRATEGY` 分级开关；启发式兜底 |
| 说书人自主复盘引入状态或副作用 | `review_balance` 只读账本 + 写平衡档案（`data/storyteller/`），不触碰 `GameState`；人类模式全关 |
| 策略枚举化改变既有启发式行为 | 阶段 S 先保持行为一致再收敛枚举；`distortion_strategy` 输出兼容旧字段 |

---

## 7. 验收标准

- [x] `act()` 以工具调用为主导路径，JSON 为 fallback；全动作类型（speak/vote/nominate/night_action/defense_speech）工具化。
- [x] Agent 具备策略先行 loop：`think` → `act`，且不重复生成发言草稿。
- [x] 记忆工具可用，Agent 可在对局中自主 `append_memory`/`reflect`；存储落盘至 `data/agents/{player_id}/`。
- [x] 世界状态查询工具可用，system prompt 瘦身；缓存命中率 ≥ 50%（对局实测，对齐 PLN-037）。
- [x] 信息隔离回归通过：evil 私密信息不出现在任何可见事件/可检索文件。
- [x] 说书人工具注册表就位：`assess_balance` / `choose_distortion` / `adjudicate_night_info` / `compose_narration` / `deliver_verdict` / `review_balance` 均可调且行为兼容。
- [x] 说书人确定性红线验证：同一对局状态下真实信息计算（恶魔/命中/真值）与重构前逐 token 一致；LLM 介入不影响真值。
- [x] 说书人策略选择可审计：每个 `choose_distortion` 均以 `distortion_strategy` 枚举写入 `decision_ledger`；`BOTC_ST_LLM_STRATEGY=off` 时行为与重构前完全一致。
- [x] 说书人对局级记忆：`review_balance` 可基于判决账本输出复盘，平衡档案落盘 `data/storyteller/{game_id}/`。
- [x] `pytest tests -q` 全绿；`ruff check src tests` 零告警；2 局 5 人 live 对局质量不低于现状。

---

## 8. 落地记录（2026-08-03）

已按本计划实现并全量验证通过，审查报告见
`docs/reviews/agent-native-redesign-cr-review-2026-08-03.md`。

- **实现文件**：`src/agents/tools/`（action_tool_registry / memory_tools / world_tools）、
  `src/agents/storyteller_tools.py`、`src/agents/prompt/common_rules.py`、
  `src/agents/ai_agent.py`、`src/agents/memory/memory_controller.py`、
  `src/llm/{base,openai,mock}_backend.py`、`src/orchestrator/claims/__init__.py`。
- **测试**：新增 `tests/test_agents/test_agent_tools.py`（19）、
  `tests/test_agents/test_storyteller_tools.py`（9）、`tests/test_llm/test_llm_strategy.py`（5），
  全量 `pytest tests -q` = 476 passed。
- **Token 控制**：`scripts/benchmark/token_budget_benchmark.py` RESULT=PASS
  （草稿复用 LLM 调用 0 次 / system 前缀逐 token 稳定 / 公共前缀跨 agent 共享）。
- **协同 PLN-037**：策略表（简单动作关思考、发言降 effort）、usage 扩展解析、
  claim 关闭思考均已落地。
- **端到端**：`simulate_game.py --backend mock --stop-after day_1` 完整白天流程通过；
  `alpha1.1_acceptance.py` 9/9 exit=0。
- **遗留**：`BOTC_ST_LLM_STRATEGY=low|on` 的 LLM 策略介入需 live 真人验收；
  记忆/世界工具能力已就位，agent 自主调用依赖真实 LLM 行为（引擎钩子兜底保留）。

---

## 9. 阶段 E 落地记录：对局隔离 + 玩家进化机制（2026-08-04）

### 9.1 记忆对局隔离（每局独立目录）

原 `MemoryTools` 固定落盘 `data/agents/{player_id}/`，跨局串味。现改为：

```
data/agents/{player_id}/
    profile/                     # 跨局玩家档案（进化，独立于对局）
        profile.json             # 战绩统计（局数/胜率/角色/阵营）
        long_term_memory.jsonl   # 跨局经验教训（局末提炼追加）
    games/{game_id}/             # 单局记忆（对局隔离）
        memory.jsonl             # 本局观察/印象/工具事件
```

- `MemoryTools.game_dir(player_id, game_id)` 新增；无 `game_id` 时回退玩家根目录（向后兼容单测）。
- `AIAgent.game_id` 属性：`set_game_context(game_id)` 在 setup 时绑定，`act()` 兜底同步。
- `MemoryTools.append_memory/read_memory/reflect/archive_phase` 统一以 `agent.game_id` 定位本局记忆文件。

### 9.2 玩家进化机制（跨局长期记忆）

- **新模块** `src/agents/memory/player_profile.py`：`PlayerProfileStore`
  - `record_game_result(won, role_id, team)`：更新战绩统计（玩家画像）；
  - `append_lesson()` / `read_lessons()`：跨局经验教训持久化；
  - `build_long_term_summary()`：生成供 prompt 注入的『跨局玩家记忆』，**敏感内容（恶魔/队友名单）过滤**。
- **AIAgent 进化闭环**：
  - `load_player_profile()`（setup 时调用）→ 生成 `_long_term_summary`；
  - `finalize_game_lesson(won, role_id, team, lesson)`（局末调用）→ 记战绩 + 追加教训；
  - `build_long_term_context()` → 注入 `act()` 的 stable_context 首段（同局内稳定，不破坏前缀缓存）。
- **orchestrator 钩子**：
  - `game_loop._bind_agent_game_context()`（setup 后）：绑定 game_id + 加载档案；
  - `game_loop._finalize_agent_player_profiles()`（GAME_OVER 结算后）：为每个 AI 玩家提炼本局经验，
    经验为规则模板（角色/阵营/胜负 + 本局记忆亮点摘要），私密内容经 `_player_lesson_sensitive` 过滤。

### 9.3 说书人进化机制

- **新模块** `StorytellerProfileStore`（`src/agents/storyteller_tools.py`）：
  `data/storyteller/profile/` 记录主持局数、累计裁决、扭曲率；`long_term_memory.jsonl` 追加主持经验。
- **StorytellerAgent**：`finalize_game_profile(game_id, lesson)` 局末统计决策账本（判决数/扭曲数）并落盘；
  game_loop 局末钩子统一触发。
- 对局隔离（`data/storyteller/{game_id}/balance_archive.json`）此前已实现，未改动。

### 9.4 验证

| 检查项 | 结果 |
|------|:--:|
| `pytest tests -q -m "not slow"`（含新增 10 个进化测试） | ✅ RC=0 |
| `ruff check src tests` / `ruff format --check` | ✅ 0 告警 |
| `simulate_game.py --backend mock --stop-after day_1` | ✅ 完整白天流程，进化绑定不破坏对局 |
| 局末进化落盘端到端 | ✅ 5 玩家各记录战绩 + 说书人记录主持局数 |

### 9.5 拟人化进化增强（局中反思 / 局后复盘 / 学习他人 / 调整策略）

参考人类玩家游戏水平增长的机制，将玩家进化细化为四个拟人化维度（2026-08-04 落地）：

| 维度 | 人类机制 | 实现 |
|------|---------|------|
| **局中反思** | 对局中不断自我校正 | `PlayerProfileStore.add_reflection()`（`reflections.jsonl`），沉淀"刚才这个决定做得对不对"；AIAgent 暴露 `add_in_game_reflection()` |
| **局后复盘** | 赢/输后复盘总结 | `add_game_review()`（`game_reviews.jsonl`），记录"赢在哪/败在哪/下次怎么改"；`finalize_game_review()` 局末自动触发 |
| **学习他人经验** | 观察高手打法并模仿 | `learn_from_others()`（`lessons_learned.jsonl`）；game_loop 局末从**胜方表现最好的玩家**提炼打法，写入所有 AI 玩家 |
| **调整策略** | 基于战绩调整自我认知与打法 | `evolve_strategies()`（`strategies.jsonl`）+ `tendency` 画像（aggression/risk_taking/talkativeness/caution），基于胜负/阵营微调（规则驱动 + 轻微随机扰动），`build_evolved_tendency_summary()` 生成可注入的"打法倾向" |

**注入链路**：`build_long_term_summary()` 综合 战绩 + 打法倾向 + 最近复盘 + 学到的打法 + 经验教训 → 新局 setup 时 `load_player_profile()` 载入 → 注入 `act()` 的 stable_context 首段（同局内稳定，不破坏前缀缓存）。

**默认倾向微调规则**（`_derive_tendency_delta`，确定性 + 轻微随机）：
- 赢 evil（恶魔胜）→ 强化 caution（保护信息）+ aggression；
- 赢 good（正义胜）→ 强化 talkativeness + aggression；
- 输 evil → 强化 caution、降低 risk_taking（避免暴露）；
- 输 good → 强化 talkativeness + aggression（更早梳理信息位）。

**局末钩子**（`game_loop._finalize_agent_player_profiles`）：① `finalize_game_review()`（复盘+战绩+倾向调整）；② `finalize_game_lesson()`（经验教训兼容）；③ `_learn_from_strong_players()`（学习胜方打法）；④ 说书人 `finalize_game_profile()`。

**验证**：新增 6 个拟人化单测（`test_player_evolution.py`）；端到端 mock 对局 5 玩家局末自动触发 `reviews_done/lessons_learned/strategy_adjustments` 各 +1，`tendency` 随胜负演化；全量 `pytest -m "not slow"` = 477 passed（全量含 slow 共 495）；ruff check + format 0 告警。

### 9.6 设计要点与约束

- **对局隔离与跨局档案分离**：本局记忆（`games/{game_id}/`）不跨局；跨局档案（`profile/`）只存"可复用经验"，不含单局私密信息。
- **信息隔离红线不变**：跨局经验注入前经 `MemoryToolsLike.is_sensitive` 过滤（恶魔/队友名单等）；`PlayerProfileStore` 自带过滤。
- **进化注入不破坏前缀缓存**：跨局摘要放入 user 首条 stable_context，同局内逐 token 稳定。
- **确定性**：战绩/胜负/角色来自 `settlement_report`（规则引擎）；倾向微调为规则驱动 + 轻微随机，LLM 不参与局末提炼（可后续演进为 LLM 蒸馏）。
- **学习他人经验的信息隔离**：从胜方提炼的打法是**角色通用战术**（非该玩家私密信息），写入所有 AI 玩家的 lessons_learned，不泄露任何玩家真实身份。
- **后续可演进**：① 局末 LLM 蒸馏"高质量经验"（默认规则模板兜底）；② 进化影响人格参数
  （如胜率低→更谨慎）；③ 说书人 LLM 策略介入时参考跨局档案；④ 局中反思的引擎级自动触发钩子
  （当前为工具能力，agent 自主调用）。
