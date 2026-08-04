---
doc_id: "REF-006"
title: "AI 玩家输入提示词（Prompt）设计总览"
category: "reference"
role: "[Cold]"
status: "published"
date: "2026-08-04"
author: "Ravenswood Bluff"
---

# AI 玩家输入提示词（Prompt）设计总览

> 本文档系统性介绍《鸦木布拉夫小镇》中 AI 玩家 / 说书人 agent 的 LLM 输入提示词设计：三层前缀架构、各层内容、动作差异、工具调用、草稿复用、策略表，以及从真实对局提取的完整案例。基于 alpha1.2（Agent 原生重构）当前代码，并反映 2026-08-04 缓存命中优化后的结构。

## 1. 概述

### 1.1 定位

AI 玩家（`src/agents/ai_agent.py`）与说书人（`src/agents/storyteller_agent.py`）通过 LLM 后端（OpenAI 兼容 / DeepSeek / Mock）完成行动决策。每次决策前，系统构造一份**提示词（prompt）**交给 `backend.generate()`。提示词构造分散在：

| 模块 | 职责 |
|------|------|
| `src/agents/prompt/common_rules.py` | 全局静态层（`build_global_static_layer`：公共规则+核心原则+8 工具纯文本 schema+输出格式，跨 Agent 逐 token 一致） |
| `src/agents/prompt/prompt_factory.py` | 双层 system 构建（`build_stable_system_prompt`）/ 人格块 / 动作风格 / 动作补充 / 记忆简报 / 局势摘要 / 虚构预算 |
| `src/agents/ai_agent.py` `act()` | 三层前缀组装（system=层1+层2 / user1 / user2） |
| `src/agents/tools/action_tool_registry.py` | 8 个行动工具 schema（稳定字符串）+ `all_tool_defs()` 全量入口 + `tool_schema_text()` |
| `src/agents/ai_agent.py` `generate_draft_speech()` | 发言草稿生成（复用 act() system 前缀的轻量 prompt） |
| `src/agents/storyteller_delegation.py` | 说书人内心独白 prompt（稳定 system + 动态局势移 user） |

### 1.2 设计目标

1. **拟人化**：人格锚点 + 难度/阵营策略注入，让 LLM 扮演"真实玩家"而非规则机器。
2. **信息隔离**：只注入 `AgentVisibleState`（经 `InformationBroker` 过滤），私密信息按阵营/可见性分层。
3. **Token 控制**：草稿复用（speak 0 token）、本地策略判定（vote/nomination 0 token）、`LLM_STRATEGY_BY_ACTION` 控制 thinking / max_tokens。
4. **缓存命中**：三层前缀架构——稳定内容置前、变化内容后置，最大化 DeepSeek 等后端的前缀缓存命中。

## 2. 三层前缀架构

每次动作调用（`act()`）构造三个消息：

```
messages = [
  system  → stable_rules   （双层：层1 全局静态层 + 层2 Agent 局部静态层，见 §3）
  user    → stable_context （跨局玩家记忆，同局内逐 token 稳定）
  user    → dynamic_context（本局记忆+社交图谱+分层记忆+虚构预算+动作风格+局势+动作格式，全部动态）
]
```

**核心原则：变化点全部后置。** DeepSeek 等后端的前缀缓存按「messages 前缀逐 token 完全匹配」工作，任何变化点都会截断缓存。因此：

- **稳定内容**放 system：层 1 = 全局绝对静态层（公共规则、核心原则、8 工具 schema 文本、输出格式要求，跨所有 Agent 逐 token 一致），层 2 = Agent 局部静态（玩家名单、身份、人格锚点、目标，同 Agent 整局不变）；
- **次稳定内容**（跨局玩家记忆，整局不变）放 user1；
- **一切随轮次/动作变化的内容**（本局记忆、局势摘要、动作类型、JSON schema）集中放 user2 末尾。

> ⚠️ 2026-08-04 优化：此前动作类型 / JSON schema / 动作风格提示 / evil 战略 / 叙事一致性曾嵌在 system 内，实测同一玩家 system 每次调用都不同，缓存命中率仅 6-14%。优化后同一玩家 system **整局逐 token 稳定**（PLN-037 第一轮）；第二轮（PLN-039）进一步将 system 拆为「全局静态层 + Agent 局部静态层」，全局段跨 Agent 100% 共享（2361 字符），`tools` 全量固定传递消除 API 层前缀篡改，草稿与辅助调用复用同一 system 前缀。

## 3. system 层（双层：全局静态层 + Agent 局部静态层）

由 `prompt_factory.build_stable_system_prompt(visible_state)` 组装（`ai_agent.py act()` 与 `generate_draft_speech()` 复用同一函数），从上到下依次为：

### 3.1 层 1 — 全局绝对静态层（`common_rules.build_global_static_layer`）

纯静态字符串，跨所有 Agent / 轮次 / 动作 **100% 逐 token 一致**，用于跨玩家共享缓存（PLN-039 T1，当前 2361 字符）：

```
你是《血染钟楼》(Blood on the Clocktower) 的玩家。
【游戏规则】白天讨论→提名→投票→处决，夜晚按技能顺序行动。
...
【通用约束】
- 你只能使用你可见的信息推理，不可臆造或凭空得知私密信息。
...

【核心原则：玩家优先级】
1. 你是玩家，不是 AI：表现得像一个人在和朋友社交。
...
7. 记忆权重：【绝对客观事实】与【高可信度线索】优先。

【可用行动工具】
- speak：白天讨论环节向所有玩家发出公开发言。参数：content(string)...
- defense_speech：...
- vote：... decision(boolean)...
- nominate：... action(none/nominate/slayer_shot)...
- nomination_intent：...
- night_action：...
- slayer_shot：...
- private_message：...

【输出格式要求】
- 首选通过 Tool Calling 完成动作...
- 工具不可用或你决定不行动时，返回严格 JSON 对象...
```

> 约束：必须是纯静态字符串，禁止拼接任何 agent 状态，否则破坏前缀稳定（见 `common_rules.py` 头注释）。8 个工具 schema 文本化前置 + 核心原则 7 条已从旧 system 移入层 1（不依赖 agent 身份/动作）。

### 3.2 层 2 — Agent 局部静态层

同 Agent 整局不变、不同 Agent 独立的部分（顺序稳定）：

1. **玩家名单**：`p1(Player 1)、p2(Player 2)、...` —— 供 LLM 定位对象。
2. **身份**：`你的名字是 Player 2，你认知的角色是 imp，阵营是 evil。`（用「认知的角色」`perceived_role_id` 而非真实角色，防信息泄露）
3. **稳定人格锚点**（`build_persona_prompt_block`，见下）
4. **目标**：`作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。` / `作为正义阵营，通过逻辑与沟通找出恶魔并处决。`

### 3.3 稳定人格锚点（`build_persona_prompt_block`）

从 `persona_profile` / `persona` 读取，12 个属性（角色名/角色说明/个性提示/说话风格/人格签名/角色气质/表达锚点/决策风格/语句节奏/风险偏好/社交倾向/压力方式/行为约束），附加**难度风格 / 发言指导 / 邪恶策略 / 正义策略**（均为预设稳定内容）：

```
【稳定人格锚点】
- 角色名: 小恶魔
- 角色说明: 除首夜外，每晚选择一名玩家使其死亡；若你自杀，一名爪牙会成为新的小恶魔。
- 个性提示: 你是一个注重逻辑一致性和事实证据的玩家。
...
- 行为约束: 邪恶阵营
【发言指导】发言自然、有条理。先说观点再补理由。...
【邪恶策略】你需要在隐藏身份的同时参与讨论。...
```

**目标**（层 2 第 4 项）：

```
作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。
作为正义阵营，通过逻辑与沟通找出恶魔并处决。
```

## 4. user1 层（跨局玩家记忆）

跨局进化摘要（`PlayerProfileStore` 从 `data/agents/{player_id}/profile/` 读取），同局内逐 token 稳定（D013 约束③）：

```
【你的跨局玩家记忆（进化）】
你共打过 10 局，胜率约 20%（2 胜 / 8 负）。
阵营战绩：evil=2/5；good=0/5
【你最近的局后复盘】
- 上一局收获：作为imp（evil）获胜，本局有效打法可复用：...
【你以往的经验教训】
- 作为mayor（good阵营）落败。...
```

无跨局记忆时占位：`【跨局记忆】本局新玩家，尚无跨局记忆。`

## 5. user2 层（动态内容）

全部随轮次变化，从上到下：

| 段 | 说明 |
|----|------|
| `【你的记忆与档案】` | 情节记忆摘要（`episodic_memory.get_summary`，最近 8 条） |
| `【你心中的社交图谱】` | `social_graph.get_graph_summary()`（信任度/身份声明/分析） |
| `【核心分层记忆】` | 三档记忆：绝对客观事实 / 高可信度线索 / 公开讨论与声明（各带可信度标注，公开声明限 15 条并去重） |
| `【虚构预算】`（evil 专属） | `deception_budget_prompt`：按日虚构额度用尽提示 |
| `【当前动作风格与战略】` | `build_action_style_block`：动作风格提示 + evil 战略摘要 + 叙事一致性 |
| `【你可见的局势摘要】` | `build_visible_state_summary`：阶段/存活/玩家列表/剧本配置/提名链/投票 |
| `当前动作补充要求` | `build_action_context`：按动作类型定制 |
| `【动作与输出格式】` | 动作类型 + "请优先调用对应工具" + JSON schema |

## 6. 各动作类型的差异（`build_action_context`）

| 动作 | 动态补充内容 |
|------|-------------|
| `speak` | 阵营发言原则（evil 伪装引导 / good 自然表达）；首发言提示；猎手开枪提示；`memory_brief` |
| `defense_speech` | "你是被提名者"辩解指引（不暴露底牌的表述规范）+ `speech_priority_brief` + `memory_brief` |
| `vote` | 当前被提名者 / 已举手人数 / 所需票数 / 未表态名单 / 幽灵票提示 + `memory_brief` |
| `nominate` / `nomination_intent` | 合法提名目标 + 怀疑度阈值（`_nomination_threshold`）+ 猎手开枪提示 + `memory_brief` |
| `night_action` / `death_trigger` | 合法夜间目标 + 目标数量 + 可否选自己 + `memory_brief` |

`build_memory_signal_brief` 提供【高可信私密信息】/【公开信息】/ 共情者 / 厨师信号摘要（speak/defense 跳过私密信息段，避免泄底）。

`build_speech_priority_brief` 生成【逻辑焦点】：公开跳身份与高可信线索的冲突，供质问/抗推。

## 7. 工具调用主导 + JSON fallback（`GameActionToolRegistry`）

8 个行动工具（schema 为稳定字符串，可作公共缓存前缀）：

| 工具 | 关键参数 |
|------|---------|
| `speak` | content / tone(calm\|passionate\|accusatory\|defensive\|hesitant) / reasoning |
| `defense_speech` | content / tone / reasoning |
| `vote` | decision(boolean) / reasoning |
| `nominate` | action(none\|nominate\|slayer_shot) / target / reasoning |
| `nomination_intent` | 同上 |
| `night_action` | target / reasoning |
| `slayer_shot` | target / reasoning |
| `private_message` | target / content |

`act()` 执行路径（`ai_agent.py`）：

```
1. all_tool_defs()（8 工具全量固定，PLN-039 T2）→ 传入 backend.generate(tools=...)
2. 响应含 tool_calls → decision_from_tool_calls(action_type) 解析（优先匹配与 action_type 对应的工具，防误调；无匹配回退任意已知工具；speech_source='tool_calling'）
3. 无 tool_calls → _parse_llm_decision_json()（JSON fallback）
4. LLM 异常 → _fallback_decision()（speech_source='fallback'）
```

> ⚠️ tools 全量固定：每次 act/草稿调用统一传 8 工具全量 schema（稳定字符串），避免 `tools` 参数随动作变化截断缓存前缀；user2 的【动作与输出格式】引导模型"只调用与该动作对应的工具，其余忽略"。

## 8. 草稿生成与复用（`SpeechPreGenCache`）

- `orchestrator/day_discussion.py` 每轮开始为所有存活 AI 玩家启动 `pregenerate_batch`（后台 `generate_draft_speech`）。
- 草稿 prompt（`generate_draft_speech`）是 `act("speak")` 的轻量版：**system 复用 act() 的双层前缀**（`build_stable_system_prompt`，PLN-039 T3），社交图谱/局势摘要/记忆等动态内容全部移入 user 末条；跳过 reflect / 向量检索 / 完整情节记忆，记忆段有 token 上限（分层记忆 600、社交图谱 200）。
- 轮到玩家发言时 `get_or_wait` 取草稿，直接返回 → **`speech_source='cache_finalized_draft_reuse'`，0 次 LLM 调用、0 token**。
- 玩家发言后其余草稿被标记 stale（下一轮重新生成）。
- 效果：8 人局 40 次 speak 全部草稿复用，speak 动作 0 token。

## 9. LLM 策略表（`LLM_STRATEGY_BY_ACTION`）

| 动作 | thinking | reasoning_effort | max_tokens |
|------|:--:|:--:|:--:|
| vote / night_action / nominate / nomination_intent | disabled | — | 200 |
| speak / defense_speech | disabled | low | 400 |
| reflect / archive / claim | disabled | — | 150 |
| think | disabled | low | 200 |

效果：动作类 reasoning 全 0；5 人 day_1 实测 total 7365→4827（D015 后 2848），fallback 5.9%→0%。

## 10. 说书人 prompt（`storyteller_delegation.analyze_game_situation`）

PLN-039 T4 后改为**稳定 system + 动态局势移 user**：

```
system（稳定）:
你是一名《血染钟楼》的说书人（上帝视角）。
作为说书人，你的核心目标是让对局悬念迭起、充满戏剧性。如果某一方优势过大，
你需要考虑在规则允许的范围内暗中帮助劣势方。
请以第一人称写一段简短的"说书人内心独白"（100字以内），需包含：
1. 你对当前场上哪名玩家或哪个阵营处境最危险的敏锐洞察。
2. 你的下一步隐秘计划。

user（动态）:
当前核心局势：
- 阶段：first_night (Day 0, Round 1)
- 人数：正义 6 存活 / 邪恶 2 存活
- 系统客观评估：正义方大优 (平衡分值: 3.00)
- 近期关键裁量记录：[...]
请生成当前阶段的说书人内心独白。
```

- 受 `BOTC_ST_LLM_STRATEGY` 控制（默认 off，不调用）；开启时 `thinking="disabled"`、max_tokens=200。
- evil 频道协调（`strategy/evil_strategy.py`）同样 `thinking="disabled"`、max_tokens=150-200。
- `memory_controller.py` 的 reflect/think 辅助调用同样前置 `build_global_static_layer()` 公共段（T4），动态近期记忆仍留 user。

## 11. 真实案例（取自 `runtime_game_logs/` 真实 8 人局）

### 案例 A：完整 `defense_speech` 请求（Player 2，imp/evil，VOTING 阶段）

**system（节选）**：

```
[层1 全局静态层 — 跨所有 Agent 逐 token 一致（2361 字符）]
你是《血染钟楼》(Blood on the Clocktower) 的玩家。
【游戏规则】白天讨论→提名→投票→处决，夜晚按技能顺序行动。
...
【核心原则：玩家优先级】
1. **你是玩家，不是 AI**：...
3. **保密与欺骗 (CRITICAL)**：...绝对不可在公开频道直接承认你的真实身份或泄露队友...
【可用行动工具】
- speak：白天讨论环节向所有玩家发出公开发言。参数：content(string)...
- defense_speech：...
- vote：... decision(boolean)...
- nominate：... action(none/nominate/slayer_shot)...
- nomination_intent：...
- night_action：...
- slayer_shot：...
- private_message：...
【输出格式要求】
- 首选通过 Tool Calling 完成动作...
- 工具不可用或你决定不行动时，返回严格 JSON 对象...

[层2 Agent 局部静态层 — 同 Agent 整局不变]
【玩家名单】p1(Player 1)、p2(Player 2)、...
【你的身份】你的名字是 Player 2，你认知的角色是 imp，阵营是 evil。
【稳定人格锚点】
- 角色名: 小恶魔
- 角色说明: 除首夜外，每晚选择一名玩家使其死亡；若你自杀，一名爪牙会成为新的小恶魔。
...
【你的目标】
作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。
```

**user1（跨局记忆，整局稳定）**：

```
【你的跨局玩家记忆（进化）】
你共打过 10 局，胜率约 20%（2 胜 / 8 负）。阵营战绩：evil=2/5；good=0/5
【你最近的局后复盘】
- 上一局收获：作为imp（evil）获胜，本局有效打法可复用：控制信息节奏、团结可信队友、按可信线索行动。
```

**user2（动态，节选）**：

```
【你的记忆与档案】
【往期回忆摘要】
>> 第1天 夜晚  首夜结束，邪恶阵营已互认分工（P2跳管家、P5跳调查员），计划白天互相掩护并栽赃P3...
【你心中的社交图谱】
🟢 你比较信任的人: Player 5 (信任+1.0)
⚪ 你持保留态度的人: Player 1 (中立), ...
- 关于 Player 5 的分析: 已由邪恶私密信息确认是己方队友
- Player 1 公开跳身份为: washerwoman
【核心分层记忆】
【绝对客观事实 (OBJECTIVE - 100%可信)】
- 【绝密推演可用】已知邪恶同伴名单：Player 5
- 【伪装策略】适合邪恶阵营穿的衣服（bluff）：管家, 镇长, 调查员
【高可信度线索 (HIGH_CONFIDENCE - 夜晚结果或私密信息)】
- 邪恶阵营互认: 你的邪恶队友：Player 5 你的 3 个不在场角色：管家, 镇长, 调查员
【公开讨论与声明 (PUBLIC - 可能存在欺骗与伪装)】
- Player 1: 大家好，我是洗衣妇。我昨晚得到了一些信息，但我想先听听大家的看法。...
【虚构预算】你今天只剩最后一次虚构机会。谨慎使用，优先保持已有叙事的一致性。
【当前动作风格与战略】
你是被提名者。请像真人一样辩解，语气要贴合你的性格。
【你可见的局势摘要】
- 公开阶段：GamePhase.VOTING，第 1 天，第 1 轮
- 存活人数：8/8
- 当前提名链：p1 -> p2
- 今日被提名过的玩家：p2
当前动作补充要求：你是被提名者，需要进行简短辩解。请返回 action=speak 和一段自然中文。...
不要出现'根据我的信息'、'我的私密信息显示'等暴露底牌的表述。
【动作与输出格式】
当前需要执行的动作类型：defense_speech
请优先调用对应工具完成动作；工具不可用或需跳过时可返回如下 JSON（不要包含任何多余文字）：
{
  "action": "speak",
  "content": "你的辩解内容",
  "tone": "calm/passionate/defensive",
  "reasoning": "你的内部推理（不公开）"
}
```

**观察点**：① system = 层1（全局静态）+ 层2（Agent 局部静态），不含动作类型/JSON schema（已后置，同一玩家整局稳定）；② user1 仅跨局记忆；③ 私密信息（evil 队友/不在场角色）以分层记忆形式出现，同时【核心原则】与【动作格式】双重约束不得泄露；④ 动作类型与 JSON schema 位于 user2 末尾。

### 案例 B：草稿生成（Player 1，washerwoman/good，DAY_DISCUSSION）

PLN-039 T3 后草稿 system **复用 act() 的双层前缀**（逐 token 相同），动态内容全部移入 user：

```
system（与 act() 逐 token 一致）:
[层1 全局静态层] 你是《血染钟楼》...
[层2 Agent 局部静态层] 玩家名单 / 你的身份 / 稳定人格锚点 / 目标

user:
【你的记忆与档案】
{tiered_memory_text}（≤600）
{social_text}（≤200）
【你可见的局势摘要】
...
当前动作补充要求：...
【动作与输出格式】
当前需要执行的动作类型：speak，请只调用与该动作对应的工具；其余工具忽略。
请只返回一个 speak 动作的 JSON 决策，格式如下：
{ "action": "speak", "content": "...", "tone": "calm/...", "reasoning": "..." }
只返回 JSON，不要输出任何额外说明。
```

### 案例 C：说书人内心独白（`first_night`）

```
你是一名《血染钟楼》的说书人（上帝视角）。
当前核心局势：
- 阶段：first_night (Day 0, Round 1)
- 人数：正义 6 存活 / 邪恶 2 存活
- 系统客观评估：正义方大优 (平衡分值: 3.00)
...
请以第一人称写一段简短的"说书人内心独白"（控制在100字以内）...
```

## 12. 缓存设计考量（重要现实）

2026-08-04 实测（8 人局完整对局，DeepSeek）：

| 指标 | 值 |
|------|----|
| 全量缓存命中率 | ~12.7%（改前基线） |
| 同一玩家 system 完全一致时 | 0-29%（Player2=29%、Player7=0%） |
| archive/reflect/storyteller/evil 类（system 动态） | 0% 命中 |
| 跨 Agent 交叉命中 | 0%（8 个 Agent 8 个独立缓存池） |

**PLN-039 第二轮优化（2026-08-04）目标与手段**：

1. **tools 全量固定**（T2）：`tools` 参与 API 请求前缀拼装，旧实现 `tool_defs_for_action` 按动作返回不同工具，导致 system 相同的调用因 tools 不同而前缀失效。现在所有 act/草稿统一传 8 工具全量 schema。
2. **全局静态层**（T1）：system 前段跨所有 Agent 100% 逐 token 一致（公共规则+核心原则+工具用途文本+输出格式）。⚠️ 精简后 2026-08-04 实测 1,522 字符（原 2,361）：工具文本只保留"工具名+一句话用途"，参数细节由 tools 参数提供，消除与全量 tools schema 的重复膨胀；仍满足 T1 ≥1,500 目标。
3. **草稿/辅助对齐**（T3/T4）：草稿复用 act() 前缀；reflect/think/archive/说书人前置公共段或保持稳定 system，消除动态 system 污染。
4. **T6 实测**（2026-08-04，8 人局完整局 ×2，见 RPT-014）：命中率 **12.7% → 53.19%**（达成 ≥40%）；reasoning=0、fallback=0；archive/storyteller 前置全局层后命中率 0% → 62.7%/57.1%（计费当量 -10.8%）。⚠️ 真实总 token 370,931 > 基线 187,423（system 变长 + tools 全量 + 草稿对齐使每请求 prompt +132%），计费当量估算 +12.8%——命中率收益被输入增量部分抵消；已精简全局层工具文本（-35.5% 字符）缓解。

**精简后复测**（2026-08-04，8 人局 rounds=4）：命中率 46.00%（仍 ≥40%）；每请求平均 prompt 2,138→1,951（-8.7%）；真实总 token 370,931→339,663（-8.4%）；reasoning=0、error=0。

### 12.1 命中率剩余提升空间（2026-08-04 分析，`scripts/debug/analyze_cache_headroom.py`）

对精简后一局逐请求分析 system / user1 静态占比 vs 实测命中率：

| 分类 | 请求数 | avg_prompt | static%(sys+u1) | 命中率 | gap | 说明 |
|------|:---:|:---:|:---:|:---:|:---:|------|
| act | 12 | 8,559 | 49.9% | 46.6% | **3.4%** | 已接近理论上限（user2 每轮必变） |
| draft | 32 | 6,218 | 68.6% | 47.0% | 21.6% | system+user1 已稳定（变体=1），gap 来自 user2 动态段 |
| archive | 40 | 4,239 | 75.9% | 53.1% | 22.8% | 同上 |
| reflect | 21 | 6,011 | 58.6% | 33.9% | 24.7% | 命中率低于 static%，受 LRU/调用间隔影响 |
| storyteller | 12 | 6,351 | 56.2% | 44.0% | 12.1% | system 已稳定，user 动态局势 |
| evil_coord | 5 | 525 | 96.9% | **0.0%** | 96.9% | 修复前 system 含动态内容，**已修复**（2026-08-04） |
| other(claims) | 44 | 975 | 0.0% | 53.0% | — | system 为空，命中来自 user 内静态段 |

**关键结论**：
1. **act 已无提升空间**（gap 3.4%）：system+user1 已整局逐 token 稳定（同 player 变体数=1），剩余 gap 是不可消除的 user2 动态内容（局势/记忆/动作格式每轮变化）。
2. **draft 与 act system 逐 token 一致已验证**（T3 达成，同 player draft==act 100% True）；此前 headroom 工具首版比较"不同 player"导致 1655/2109 共同前缀误报，按 player 分组后确认完全一致。
3. **evil_coord 修复**（2026-08-04）：`build_evil_night_coordination_message` 原将今晚目标/战略/队友伪装/最近对话全部拼入 system → 前缀永不命中（0%）。已改为 system 稳定身份+任务、动态内容移入 user（与 T4 原则一致），下一局可验证命中率从 0% 提升。
4. **剩余 gap 本质是缓存机制限制**：DeepSeek 前缀缓存"必要不充分"（LRU/容量/TTL 淘汰），draft/archive/reflect 的 static% 高于命中率，但重复调用间隔长导致条目被淘汰。进一步压缩空间有限（结构性收益已被 T1-T5 吃尽）。

## 13. 调试工具

- `scripts/debug/dump_ai_prompt.py`：抽取某个 agent 在某状态下会看到的完整 prompt（system + messages），便于人工审查。
- `scripts/debug/analyze_llm_cache.py`：解析 `llm.jsonl` 统计全量/分类命中率、计费当量、T2.1 tools 恒等、T3.1 草稿前缀比对。
- `scripts/debug/analyze_cache_headroom.py`：逐请求静态段（system+user1）占比 vs 命中率 gap，定位剩余提升空间（注意跨 player 比较会误报，需按 player 分组）。
- `game_debug_logger`：每次 LLM 调用的完整 request/response（含 usage：cache_hit/miss/reasoning）写入 `runtime_game_logs/<slot>/llm.jsonl`，可离线回放分析。

## 14. 相关文档

- `docs/plans/agent-native-redesign-plan.md`（PLN-038：行动工具化 / 说书人 agent 化）
- `docs/plans/token-budget-optimization-plan.md`（PLN-037：三层前缀 / 策略表 / 缓存）
- `docs/plans/prompt-cache-optimization-plan.md`（PLN-039：第二轮缓存优化——全局静态层 / tools 全量固定 / 草稿对齐）
- `docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md`（RPT-013：live 验证）
- `docs/reference/test-system.md`（REF-005：测试系统）
- `docs/reference/tech-traps.md`（REF-004：技术陷阱）
