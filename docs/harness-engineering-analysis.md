# LLM Harness 工程解析报告：鸦木布拉夫小镇

> **项目**: 鸦木布拉夫小镇 (Ravenswood Bluff) — 基于 LLM 的多智能体社交推理游戏引擎
> **分析视角**: 大模型 Harness 工程架构
> **分析日期**: 2026-06-01
> **分析范围**: 全代码库，聚焦 Prompt 构建、输出解析、记忆管理、多智能体编排、可观测性五大子系统

---

## 目录

1. [核心命题：为什么这个项目是一个 Harness](#1-核心命题)
2. [Harness 五层架构总览](#2-harness-五层架构总览)
3. [第一层：Prompt 工程子系统](#3-第一层prompt-工程子系统)
4. [第二层：输出解析与结构化提取](#4-第二层输出解析与结构化提取)
5. [第三层：上下文与记忆管理](#5-第三层上下文与记忆管理)
6. [第四层：多智能体编排引擎](#6-第四层多智能体编排引擎)
7. [第五层：鲁棒性与可观测性](#7-第五层鲁棒性与可观测性)
8. [关键设计决策分析](#8-关键设计决策分析)
9. [改进空间与工程建议](#9-改进空间与工程建议)
10. [附录：关键文件索引](#10-附录关键文件索引)

---

## 1. 核心命题

### 1.1 Harness 的定义

在 LLM 工程语境中，**Harness（脚手架/测试架）** 是指围绕大语言模型构建的一整套基础设施，用于：

- 将非结构化的自然语言输入转化为结构化的 LLM 请求
- 将 LLM 的自由文本输出解析为可执行的动作
- 管理 LLM 的上下文窗口，决定"给模型看什么"
- 在多智能体场景中协调多个 LLM 实例的交互
- 处理 LLM 的不确定性（超时、幻觉、格式错误）

### 1.2 这个项目为什么是一个 Harness

这个项目不是简单的"调 API 生成文本"。它要解决的核心问题是：

> **让多个 LLM 在有规则、有状态、有信息不对称的博弈环境中可靠地协作和对抗。**

这比典型的 RAG 或 ChatBot 应用复杂一个数量级，因为：

- 每个 LLM agent 只能看到**部分信息**（信息隔离）
- agent 的输出会影响其他 agent 的输入（**因果链**）
- 游戏有严格的**规则约束**（LLM 不能做非法动作）
- 多个 agent 需要**顺序交互**（后面的能看到前面的发言）
- LLM 的不确定性需要**多层兜底**（超时、幻觉、格式错误）

---

## 2. Harness 五层架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    Layer 5: 鲁棒性与可观测性                   │
│  MetricsCollector · 断路器 · 延迟预算 · JSONL Trace · 接受门  │
├─────────────────────────────────────────────────────────────┤
│                    Layer 4: 多智能体编排引擎                    │
│  GameOrchestrator · InformationBroker · EventBus · PhaseHandler│
├─────────────────────────────────────────────────────────────┤
│                    Layer 3: 上下文与记忆管理                    │
│  WorkingMemory · EpisodicMemory · VectorMemory · SocialGraph │
├─────────────────────────────────────────────────────────────┤
│                    Layer 2: 输出解析与结构化提取                 │
│  DecisionEngine · SpeechSanitizer · TargetCoercion · Fallback │
├─────────────────────────────────────────────────────────────┤
│                    Layer 1: Prompt 工程子系统                   │
│  PromptFactory · DifficultyPreset · Persona · DeceptionTracker│
└─────────────────────────────────────────────────────────────┘
```

每一层都解决 LLM harness 中的一个核心问题，层层递进。

---

## 3. 第一层：Prompt 工程子系统

### 3.1 Prompt 构建架构

Prompt 系统采用**分层组合模式（Layered Composition）**，多个专用模块各自贡献 prompt 片段，最终组装成一个完整的 system prompt。

**核心文件**：
- `src/agents/prompt/prompt_factory.py` — Prompt 组装工厂
- `src/agents/ai_agent.py` (L497-535) — 最终 system prompt 组装
- `src/agents/difficulty_presets.py` — 难度预设的 prompt 修饰
- `src/agents/persona_registry.py` — 9 种人格原型
- `src/agents/deception/deception_tracker.py` — 欺骗预算系统
- `src/agents/strategy/evil_strategy.py` — 邪恶阵营策略 prompt

### 3.2 System Prompt 结构（单体 f-string 模式）

每个 AI agent 的 system prompt 是一个**单体大 f-string**，按以下顺序组装：

```
┌────────────────────────────────────────────┐
│ 1. 核心行为原则（硬编码）                      │
│    - 你是玩家不是 AI                          │
│    - 社交推演优先                              │
│    - 保密与欺骗规则                            │
│    - 沉浸式对话、拒绝机械复述                    │
│    - 发言多样性、长线记忆、记忆权重              │
├────────────────────────────────────────────┤
│ 2. 人格锚点（PromptFactory.build_persona_prompt_block）│
│    - 角色名/说明/个性/说话风格                   │
│    - 人格签名/角色气质/表达锚点                  │
│    - 决策风格/语句节奏/风险偏好                  │
│    - 社交倾向/压力方式/行为约束                  │
│    - 【难度风格】（条件注入）                    │
│    - 【发言指导】（条件注入）                    │
│    - 【邪恶/正义策略】（按阵营条件注入）          │
│    - 【叙事一致性】（邪恶且有欺骗历史时注入）      │
├────────────────────────────────────────────┤
│ 3. 欺骗预算（仅邪恶阵营）                      │
│    - 剩余虚构次数                              │
│    - 预算耗尽时的行为约束                       │
├────────────────────────────────────────────┤
│ 4. 情景记忆（episodic_memory.get_summary）     │
│    - 最近 5-8 个阶段摘要                       │
│    - 按天/夜分组，带关键事件列表                 │
├────────────────────────────────────────────┤
│ 5. 社交图谱（social_graph.get_graph_summary）  │
│    - 每个玩家的信任分/角色信念/阵营信念           │
│    - 按信任等级分组（信任/中立/怀疑）             │
│    - 最近声明和观察笔记                         │
├────────────────────────────────────────────┤
│ 6. 可见局势摘要（AgentVisibleState）            │
│    - 阶段/天数/轮次/存活人数                    │
│    - 玩家列表/板面设置/提名链                    │
├────────────────────────────────────────────┤
│ 7. 动作上下文（PromptFactory.build_action_context）│
│    - 动作类型特定的指令                          │
│    - 记忆信号摘要（角色相关的私密信息提示）        │
├────────────────────────────────────────────┤
│ 8. 目标（按阵营分支）                           │
│    - 邪恶：隐藏恶魔、误导推理                    │
│    - 正义：通过逻辑找出恶魔                      │
├────────────────────────────────────────────┤
│ 9. 三层分级记忆                                  │
│    - 【绝对客观事实 OBJECTIVE - 100%可信】       │
│    - 【高可信度线索 HIGH_CONFIDENCE】            │
│    - 【公开讨论与声明 PUBLIC - 可能存在欺骗】     │
├────────────────────────────────────────────┤
│ 10. 向量检索结果（RAG）                         │
│     - FAISS top-5 语义相关历史记忆               │
├────────────────────────────────────────────┤
│ 11. JSON Schema                                │
│     - 动作类型对应的输出格式规范                  │
└────────────────────────────────────────────┘
```

**User Message** 极简：
```
请只返回适用于动作 `{action_type}` 的 JSON 决策，不要输出任何额外说明。
```

**关键特征**：这是**单轮模式**（one system prompt + one user message），没有多轮对话链。

### 3.3 条件注入机制

Prompt 的组装不是静态的，而是基于多个维度**条件注入**：

| 维度 | 条件 | 注入内容 |
|------|------|---------|
| 阵营 | `agent.team == "evil"` | 邪恶策略 prompt、欺骗预算、叙事一致性 |
| 阵营 | `agent.team == "good"` | 正义策略 prompt |
| 难度 | `preset.prompt_modifier` | 推理风格修饰（如"多角度交叉验证"） |
| 难度 | `preset.speech_style_prompt` | 发言风格指导（如"戏剧化表达"） |
| 动作类型 | `action_type in ["night_action", "nomination_intent"]` | 邪恶战略分析摘要 |
| 欺骗状态 | `deception_tracker.get_consistency_guidance()` | 已声明身份的一致性约束 |

### 3.4 难度系统对 Prompt 的影响

四个难度预设通过 prompt 实现**语义层面的行为调控**：

| 预设 | Temperature | Prompt 策略 |
|------|------------|------------|
| **CASUAL（休闲）** | 0.9 | 直觉/情感推理、故事化发言、容错 |
| **STANDARD（标准）** | 0.7 | 平衡逻辑、适度欺骗、自然发言 |
| **MASTER（大师）** | 0.4 | 多角度交叉验证、控制信息释放、进攻型欺骗（编号战术手册） |
| **CHAOS（混沌）** | 1.0 | 阴谋论推理、戏剧化发言、不可预测行为 |

MASTER 预设的邪恶策略是一个**编号战术 playbook**：
```
1. 主动编造完整的虚假信息链...
2. 故意暴露一个'弱点'来引诱好人朝错误方向推理
3. 与同阵营玩家配合——制造假对立来迷惑好人
4. 在关键时刻发起出人意料的提名...
5. 选择性释放信息，制造信息差...
```

此外，难度还携带**按动作类型的 temperature 覆盖**和**人格参数覆盖**：
```python
temperature_by_action={"vote": 0.3, "nomination_intent": 0.35}  # master
persona_overrides={"nomination_threshold_offset": -0.05, "assertiveness": "high"}  # master
```

### 3.5 人格/原型系统

9 种人格原型，每种定义了行为参数偏差：

| 原型 | 核心特质 | 提名阈值偏移 | 信任衰减 |
|------|---------|-------------|---------|
| logic（冷静逻辑型） | 证据驱动 | +0.10（谨慎） | 1.2x |
| aggressive（强势领袖型） | 控制节奏 | -0.15（激进） | 1.5x |
| cooperative（随大流型） | 追随共识 | +0.05 | 0.7x |
| chaos（混乱搅局者） | 不可预测 | -0.05 | 默认 |
| silent（内向观察者） | 安静观察 | +0.20（极谨慎） | 默认 |
| paranoid（多疑侦探型） | 质疑一切 | -0.10 | 2.0x |
| protector（感性守护者） | 直觉驱动 | +0.10 | 0.5x |
| outsider_vibe（懵懂新人型） | 装傻 | +0.15 | 默认 |
| strategist（深谋远虑型） | 胜率优化 | 0.0 | 默认 |

**跨会话一致性**：使用确定性哈希（`_pick_stable`），基于 `player_id + role_id` 生成种子，为每个 agent 分配稳定的 `voice_anchor`、`decision_style`、`speech_rhythm` 等特质。这确保同一 agent 在不同会话中保持一致的人格。

**三层叠加**：`人格原型 → 难度覆盖 → 角色特质`，难度覆盖优先于原型默认值。

### 3.6 按动作类型的 Prompt 差异化

`PromptFactory.build_action_context` 为每种动作类型提供不同的指令：

| 动作类型 | Prompt 要点 |
|---------|------------|
| `speak` | 按阵营分支：邪恶=伪装指令+欺骗约束，正义=推理指令+自然发言；含首发提示、冲突检测、记忆信号 |
| `vote` | 当前投票对象、票数统计、阈值、剩余投票者、幽灵票上下文 |
| `nominate` | 合法目标列表、怀疑度阈值、猎人射击选项 |
| `night_action` | 合法目标、所需目标数、是否可自选 |
| `defense_speech` | 用私密信息推理但不直接引用原文 |

### 3.7 欺骗预算系统（DeceptionTracker）

邪恶 agent 的虚构行为受**每日配额**限制：

```python
max_fabrications_per_day = max(1, int(deception_level * 3))  # deception=0.7 → 2次/天
```

预算通过 prompt 注入实现**软约束**：
- 预算耗尽：`"【虚构预算】你今天的虚构额度已用完。不要再编造新信息..."`
- 剩余 1 次：`"【虚构预算】你今天只剩最后一次虚构机会。谨慎使用..."`

`get_consistency_guidance()` 确保邪恶 agent 维持叙事一致性：
```
你已公开跳身份为 X。后续发言必须与之一致，不要改口。
你正在推进的叙事线: ...。继续沿着这条线推进...
```

### 3.8 说书人（Storyteller）的独立 Prompt 模式

说书人使用与玩家不同的 prompt 模式——**两段式**（system prompt + user message）：

```
System: 你是一名《血染钟楼》的说书人（上帝视角）。
        当前核心局势：阶段/人数/平衡分值/近期裁量记录...
        你的核心目标是让对局悬念迭起...
User:   请生成当前阶段的说书人内心独白。
```

说书人的 prompt 注入**基于游戏优势的风味文本**：
- 优势 > 2.0：`"正义的锋芒势不可挡。"`
- 劣势 < -1.0：`"邪恶的阴霾挥之不去，小镇似乎命悬一线。"`

### 3.9 邪恶阵营夜间协调的多轮模式

邪恶阵营的首夜协调是项目中唯一的**顺序多轮模式**：

1. 恶魔先发言：分配伪装身份给每个队友
2. 爪牙后发言：看到恶魔的发言后回应

后发言者通过 `visible_state.public_chat_history` 看到先发言者的消息，形成对话链。

---

## 4. 第二层：输出解析与结构化提取

### 4.1 JSON 提取管道

`AIAgent._parse_llm_decision_json`（ai_agent.py L240-278）实现**多阶段提取**：

```
LLM 原始输出
  │
  ├─ 1. 提取 markdown fence 内容（```json ... ```）
  │
  ├─ 2. json.loads() 直接解析
  │
  ├─ 3. 扫描 { 位置，json.JSONDecoder.raw_decode() 提取首个 JSON 对象
  │
  └─ 4. 全部失败 → raise last_error
```

**设计意图**：LLM 输出格式不可靠——可能包含 markdown fence、前后多余文字、嵌套 JSON 等。这个管道以**最大宽容度**提取有效 JSON。

### 4.2 决策规范化（DecisionEngine.normalize_decision）

提取 JSON 后，按动作类型进行**语义验证和类型强制转换**：

| 动作类型 | 验证逻辑 | 失败回退原因 |
|---------|---------|------------|
| nominate | target 在 legal_nomination_targets 中 | `invalid_nomination_target` |
| vote | decision 字段为 bool | `invalid_vote_decision` |
| defense_speech | content 非空 | `empty_defense_speech` |
| night_action | target 数量 == required_targets，无重复，全在合法目标中 | `missing_night_target` / `illegal_night_target` 等 |
| speak | content 非空 | `empty_speech` |

### 4.3 目标值强制转换（Target Coercion）

LLM 返回的目标值格式极其不一致——可能是字符串、列表、嵌套列表、逗号分隔等。`coerce_target_values` 用递归展平处理：

```python
def coerce_target_values(raw_target) -> list[str]:
    # 字符串 → 按逗号分割
    # 列表/元组/集合 → 递归展平
    # 其他 → str() 转换
```

### 4.4 发言清洗（SpeechSanitizer）

防止 LLM 生成的发言泄露私密信息：

**泄露检测**：扫描两类泄露：
1. **不安全标记**（字面匹配）：`"【绝密"`, `"已知邪恶同伴"`, `"evil_teammates"`, `"spy_book"` 等
2. **原始记忆泄露**：检查发言中是否包含任何私密记忆的原文

**泄露响应**：检测到泄露时，用**人格感知的安全锚线**替换：
```
"{安全锚线} 我现在先按这个方向聊，不把所有细节一次性摊开。"
```

**发言稳定化**：短于 60 字的发言会被注入记忆锚线，使其引用实际游戏证据而非空洞发言。

**私密信息改述**：将私密情报转化为模糊的公开安全引用：
```
"我手里有一条信息让我暂时更关注 {name}，但我不想把底牌一次性说死。"
```

### 4.5 JSON Schema 强制

每种动作类型在 system prompt 末尾提供明确的 JSON schema：

```json
// speak
{"action": "speak", "content": "你的中文发言内容", "tone": "calm/passionate/accusatory/defensive", "reasoning": "...", "extracted_claims": [...]}

// vote
{"action": "vote", "decision": true/false, "reasoning": "..."}

// night_action
{"action": "night_action", "target": "player_id 或 [id1, id2]", "reasoning": "..."}
```

**注意**：这是通过 prompt 文本描述实现的"软约束"，不是 function calling 或 structured output 等"硬约束"。

---

## 5. 第三层：上下文与记忆管理

### 5.1 四层记忆架构

```
┌─────────────────────────────────────────────────┐
│ Layer 4: SocialGraph（社交图谱）                   │
│   每个玩家的信任分/角色信念/阵营信念/声明历史       │
│   冻结/解冻机制（死亡玩家的记忆压缩）               │
├─────────────────────────────────────────────────┤
│ Layer 3: VectorMemory（向量记忆 / RAG）            │
│   FAISS IndexFlatL2，容量 1000，FIFO 驱逐          │
│   每个可见事件自动摄入，语义检索 top-5              │
│   优雅降级：embedding 不可用时自动禁用              │
├─────────────────────────────────────────────────┤
│ Layer 2: EpisodicMemory（情景记忆）                │
│   按阶段摘要，保留关键事件列表                      │
│   Prompt 中只包含最近 5-8 个 Episode               │
├─────────────────────────────────────────────────┤
│ Layer 1: WorkingMemory（工作记忆）                 │
│   observations（当前阶段原始观察，上限 30）          │
│   internal_thoughts（私密推理链，上限 5）            │
│   impressions（反思蒸馏的印象，上限 5）              │
│   objective_memory（100% 可信事实，上限 40）        │
│   high_confidence_memory（夜晚结果/私密信息，上限 40）│
│   public_fact_memory（公开声明，可能存在欺骗，上限 40）│
└─────────────────────────────────────────────────┘
```

### 5.2 三层信任分级

工作记忆内部按**信任等级**分三层：

| 层级 | 信任度 | 内容来源 | Prompt 标签 |
|------|-------|---------|------------|
| OBJECTIVE | 100% | 角色分配、邪恶队友名单、间谍书 | `【绝对客观事实】` |
| HIGH_CONFIDENCE | 高 | 夜晚结果、说书人私密信息 | `【高可信度线索】` |
| PUBLIC | 低 | 公开讨论、他人声明 | `【公开讨论与声明 - 可能存在欺骗】` |

**去重逻辑**：渲染前自动去重——HIGH_CONFIDENCE 中与 OBJECTIVE 重复的项被移除，PUBLIC 中与社交图谱自我声明重复的项被过滤。

### 5.3 上下文窗口预算管理

每个记忆区块有**硬编码的 token 预算**：

| 区块 | Token 预算 | 草稿发言预算 |
|------|-----------|------------|
| 分级记忆（tiered_memory_text） | 800 | 600 |
| 情景记忆（episodic_text） | 400 | 0（不注入） |
| 社交图谱（social_text） | 300 | 200 |

`_cap_memory_section` 使用粗略启发式（混合中英文约 2 字符/token），超预算时按比例截断到 90%，在最后一个换行处切割，追加 `"... (记忆已截断以控制长度)"`。

**数据结构层面的额外限制**：
- 公开记忆项：prompt 中最多 15 条
- 每层分级记忆：最多 20 条
- 社交图谱笔记：每玩家最多 6 条（每条截断到 80 字符）
- 社交图谱声明：每玩家最多 5 条

### 5.4 阶段间记忆归档

**触发时机**：每次阶段转换时（`target_phase != current_phase`），`_archive_agent_phase_memories()` 并发调用所有 agent 的归档逻辑。

**归档流程**：
1. 收集当前阶段所有 observations + 最近 5 条 internal_thoughts
2. 如果 > 3 条 observations → 调用 LLM 蒸馏为 30 字摘要；否则规则拼接
3. 创建 Episode（摘要上限 280 字符）追加到 episodic_memory
4. 异步摄入 phase_summary 到向量记忆
5. 调用 `working_memory.clear_transient()`：清除 observations 和 thoughts，保留 impressions、anchor_facts、三层分级记忆

### 5.5 阶段内反思（Reflection）

**触发条件**：observation 数量超过阈值（`max(30, player_count * 5)`）。

**反思流程**：
1. 获取当前工作记忆上下文
2. 调用 LLM 生成 200 字的局势印象
3. 存入 `working_memory.impressions`
4. 调用 `working_memory.compact()`：所有 observations 替换为一条摘要，thoughts 截断到最近 5 条

### 5.6 向量记忆的优雅降级

- numpy/faiss 不可用 → 模块自禁用
- Embedding API 返回 404 或 "unsupported" → `_embeddings_disabled = True`，后续调用直接返回 `[]`
- `get_stats()` 暴露当前状态、禁用原因、最后一次查询，用于调试和数据快照

### 5.7 社交图谱的冻结/解冻机制

当玩家死亡且有稳定的自我声明（无冲突）时：
- `freeze_player()` 设置 `is_frozen=True`，存储一行摘要
- `get_graph_summary()` 中，冻结玩家只输出一行而非完整的 notes/claims
- **自动解冻**：trust_score 摆动超过 0.3，或玩家改变公开角色声明

### 5.8 遗忘策略汇总

| 机制 | 范围 | 触发 | 丢失内容 |
|------|------|------|---------|
| FIFO cap | 工作记忆 | `_remember_memory_fact()` | 超出 storage_limit(40) 的最旧事实 |
| compact() | 工作记忆 | 反思（observation > 阈值） | 所有原始观察替换为一条摘要 |
| clear_transient() | 工作记忆 | 阶段归档 | 当前阶段的 observations 和 thoughts |
| Episode 窗口 | 情景记忆 | Prompt 渲染 | 只展示最近 5-8 条；更早的不进 prompt |
| FAISS FIFO | 向量记忆 | 超容量时 | 最旧的向量和元数据；索引全量重建 |
| 冻结/解冻 | 社交图谱 | 玩家死亡 | 完整 notes/claims 替换为一行摘要 |
| _cap_memory_section() | Prompt | 每次 act() | 按比例截断以适配 token 预算 |
| 笔记/声明上限 | 社交图谱 | add_note()/record_claim() | 超出上限的最旧条目 |
| 公开记忆上限 | Prompt | act() 渲染 | 只展示最后 15 条公开项 |

---

## 6. 第四层：多智能体编排引擎

### 6.1 编排架构

```
GameOrchestrator（门面，~766 行）
  │
  ├── AgentManager        — agent 生命周期（注册、同步、反思）
  ├── InformationBroker   — 可见性过滤 + 事件路由
  ├── EventBus            — 异步 pub/sub 事件分发
  ├── NightPhaseHandler   — 夜晚阶段逻辑（~574 行）
  ├── DayDiscussionHandler — 白天讨论逻辑（~274 行）
  ├── NominationVotingHandler — 提名投票逻辑（~756 行）
  ├── MetricsCollector    — 延迟追踪、动作指标
  ├── GrimoireManager     — 魔典管理
  ├── ClaimExtractor      — 声明提取
  ├── SettlementBuilder   — 结算报告
  ├── PrivateInfoNormalizer — 私密信息规范化
  └── SpeechPreGenCache   — 发言预生成缓存
```

`GameOrchestrator` 的每个方法都是薄委托：
```python
async def _run_day_discussion(self):
    await self.day_discussion_handler._run_day_discussion()

async def _run_night(self):
    await self.night_phase_handler._run_night()
```

### 6.2 游戏循环

```python
while not self.winner:
    await _transition_and_run(target_phase)
```

每个阶段转换调用 `_transition_and_run(target_phase)`：
1. 归档 agent 阶段记忆（并发，10s 超时）
2. 更新 PhaseManager
3. 发布 `phase_changed` 事件
4. 拍快照
5. 说书人叙事（可选）
6. 分发到对应的 `_run_*` 处理器

### 6.3 信息隔离（InformationBroker）

这是 harness **最核心的设计**——解决"LLM 没有'不知道'的概念"这一根本问题。

**可见性枚举（Visibility）**：

| 级别 | 可见范围 |
|------|---------|
| PUBLIC | 所有玩家 |
| TEAM_EVIL | 邪恶阵营 + 说书人 |
| TEAM_GOOD | 正义阵营 + 说书人 |
| PRIVATE | 仅目标 + 说书人 |
| STORYTELLER_ONLY | 仅行为者/目标 + 说书人 |

**过滤链**：

```
GameEvent (带 visibility 字段)
  │
  ├─ event_bus.publish(event)
  │    └─ _on_any_event (通配符处理器)
  │         └─ broker.broadcast_event(event, state)
  │              │
  │              ├─ 根据 visibility 确定接收者集合
  │              │
  │              └─ 对每个接收者：
  │                   ├─ 计算过滤后的 AgentVisibleState
  │                   │    ├─ visible_event_log（过滤后的事件日志）
  │                   │    └─ public_chat_history（过滤后的聊天记录）
  │                   └─ agent.observe_event(event, visible_state)
```

**隔离保证**：agent 的 `visible_event_log` 在构造时就过滤了不该看到的事件。即使 agent 存储了 visible_state，它也永远不包含不该知道的信息。

**法律上下文**（`get_action_legal_context`）：构建 `AgentActionLegalContext`，包含合法提名目标、夜晚目标、投票阈值、剩余投票者、角色特定标志。

### 6.4 EventBus

轻量级异步 pub/sub：
- **类型订阅**：`subscribe(event_type, handler, priority)`
- **通配符订阅**：`"*"` 匹配所有事件类型
- **顺序执行**：handlers 按优先级排序后逐个 `await`（不是并行）
- **历史记录**：`deque(maxlen=500)` 存储最近事件

编排器订阅通配符 `"*"` 在优先级 0：
```
_publish_event → state.with_event(event) → event_bus.publish(event)
                                             → _on_any_event (priority 0)
                                               → event_log.append
                                               → broker.broadcast_event (并发通知 agent)
```

### 6.5 顺序 vs 并行调用模式

系统使用四种不同的 agent 调用模式：

**严格顺序**（顺序影响状态或后续 agent 依赖前置结果）：
- 夜晚行动：按夜晚顺序迭代
- 白天讨论 AI 发言：逐个处理，确保每个看到最新状态
- 邪恶首夜协调：恶魔先发言，爪牙后发言
- 投票应用到状态：按座位顺序

**asyncio.gather 并发**（agent 间独立）：
- 夜晚信息分发：所有角色信息决定并发收集
- 阶段记忆归档：所有 agent 并发归档（10s 超时）
- 批量反思：所有存活 AI agent 并发反思
- 事件广播：所有接收者并发通知

**asyncio.create_task 并发**（agent 独立但结果按序收集）：
- 提名意图：每个合格玩家的意图是独立 task，结果按座位顺序 await
- AI 投票：每个 AI 投票者的决定是独立 task，结果按座位顺序应用

**后台预生成（SpeechPreGenCache）**：
- 讨论轮开始前，所有 AI agent 的 LLM 调用作为后台 task 启动
- 轮到某个 AI 时，通过 `get_or_wait()` 获取预生成草稿
- 每次发言后，剩余草稿失效（因为游戏状态变了）
- 将 N 次顺序 LLM 调用转化为 ~1 次并行批次 + 每 agent 一次小的精炼调用

### 6.6 不可变状态模式（GameState）

`GameState` 和 `PlayerState` 使用 Pydantic `frozen=True`：

```python
# 状态永远不被修改，而是替换
self.state = self.state.with_update(phase=target_phase, ...)
self.state = self.state.with_player_update(player_id, is_alive=False)
```

**快照安全**：`SnapshotManager.take_snapshot` 在关键转换点存储 `GameState` 引用。由于 frozen，快照是安全的历史引用。

**双轨事件日志**：
- `EventLog`（运行时可变容器）：用于实时查询
- `GameState.event_log`（不可变元组）：用于快照和回放

---

## 7. 第五层：鲁棒性与可观测性

### 7.1 三层回退机制

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: 硬编码延迟回退（_latency_fallback）               │
│   最终安全网，返回最小但合法的动作                          │
│   speak → "我还在想。"  vote → False  night_action → none │
├─────────────────────────────────────────────────────────┤
│ Layer 2: 编排器级超时（_smart_latency_fallback）           │
│   先尝试 agent 的 _fallback_decision（人格感知）           │
│   失败则降级到 Layer 3                                    │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Agent 内部回退（AIAgent.act 异常处理）            │
│   LLM 超时/空响应/错误 → _fallback_decision               │
│   有缓存草稿 → 直接使用 sanitized 缓存                    │
│   DecisionEngine.fallback_decision：                      │
│     - 提名：评分系统选目标，人格偏差                       │
│     - 投票：启发式评分 + 人格偏差                          │
│     - 发言：persona_fallback_speech（人格感知的锚线发言）   │
│     - 夜晚行动：评分系统选目标                             │
└─────────────────────────────────────────────────────────┘
```

### 7.2 三级超时预算

| 层级 | 位置 | 典型值（speak, live） |
|------|------|---------------------|
| Agent 内部 | `AIAgent._action_timeout_seconds` | 300s |
| 编排器 | `MetricsCollector._timed_act` | 301.5s (agent + 1.5s margin) |
| 难度预设 | `DifficultyPreset.latency_budget` | 2000ms |

**预算计算**：
```python
orchestrator_budget = max(agent_budget + margin, orchestrator_default)
```

确保编排器超时始终大于 agent 内部超时，让 agent 的回退先触发。

**特殊处理**：实时后端的发言/辩解动作**跳过编排器超时**（`_should_wait_without_orchestrator_timeout`），只使用 agent 内部超时。

### 7.3 错误分类

| 错误类型 | 分类标签 | 触发的回退 |
|---------|---------|-----------|
| `asyncio.TimeoutError` | `latency_budget_exceeded:{action_type}` | Agent 内部回退 |
| `ValueError("empty_response")` | `empty_response` | Agent 内部回退 |
| 其他异常 | `llm_error:{ExceptionClassName}` | Agent 内部回退 |
| 编排器超时 | `orchestrator_hard_timeout:{action_type}` | 编排器回退 |

### 7.4 发言预生成缓存（SpeechPreGenCache）

解决顺序发言的延迟问题：

```
讨论轮开始
  │
  ├─ 后台并行：所有 AI agent 的 LLM 草稿生成
  │
  ├─ 人类玩家处理（顺序，阻塞）
  │
  └─ AI 玩家处理（顺序）：
       ├─ get_or_wait() 获取预生成草稿
       ├─ 精炼模式：带草稿的第二次 LLM 调用
       ├─ 成功 → 使用精炼结果
       └─ 失败 → 使用 sanitized 缓存草稿（speech_source="cache_finalized_after_llm_error"）
```

### 7.5 断路器

每个讨论轮监控回退率：
```python
if speech_count >= 3 and fallback_rate >= 0.4:
    logger.warning("[M5-L][release_blocker] day=%s round=%s fallback_rate=%.0f%% ...")
```

40% 或更高回退率触发 `release_blocker` 警告，追踪 LLM 成功/缓存最终化/编排器超时的细分。

### 7.6 指标收集（MetricsCollector）

每个 `agent.act()` 调用记录：
- `player_id`, `action_type`, `phase`, `latency_ms`
- `fallback_used`, `fallback_reason`, `timeout_budget_ms`, `budget_source`
- `agent_fallback_used`, `speech_source`, `backend_speed_profile`

**百分位计算**：P50, P95, max（按动作类型分组）

**运行时诊断**：当前阶段、最后进展时间、近期异常、阶段持续时间历史、节奏事件。

**数据快照**：在每个流程检查点（first_night_complete, day_discussion_complete 等）捕获结构化快照，包括存活/死亡计数、可见状态摘要、每个 agent 的 AI 数据（工作记忆、社交图谱、声明历史、检索摘要）。

### 7.7 数据持久化

**JSONL Trace**（GameDataCollector）：
- `thought_trace`：AI 思维链和决策追踪
- `action_latency`：每动作延迟记录
- `snapshot`：完整游戏状态快照

**SQLite 记录**（GameRecordStore）：
- `game_records` 表：游戏元数据 + 结算 JSON
- `game_players` 表：玩家详情
- 多层恢复：SQLite 失败 → sidecar 恢复 → JSON 文件回退

### 7.8 接受门（Acceptance Gates）

8 个自动化接受门：

| 门 | 验证内容 |
|---|---------|
| 1 | 现有测试无回归 |
| 2 | Agent 推理逻辑 |
| 3 | 难度配置验证（54 项检查） |
| 4 | 跨难度行为比较（62 项检查） |
| 5 | 行为级难度验证 |
| 6 | AI 速度：P50/P95 延迟 + 超时回退 |
| 7 | 对话质量：低信息率 ≤30%，重复率=0，回退率 ≤50% |
| 8 | Alpha 1.0 向后兼容 |

**速度阈值**：
- speak P95 ≤ 2000ms
- nomination_intent P95 ≤ 1000ms
- vote P95 ≤ 800ms
- night_action P95 ≤ 1500ms
- defense_speech P95 ≤ 2500ms

---

## 8. 关键设计决策分析

### 8.1 单体 System Prompt vs 多轮对话

**决策**：使用单体大 f-string system prompt + 极简 user message，不使用多轮对话。

**优势**：
- 简单、可预测、易于调试
- 每次调用完全自包含，无状态依赖
- 便于 token 预算控制

**代价**：
- prompt 冗长（可能 2000-4000 tokens）
- 无法利用 LLM 的多轮推理能力
- 复杂决策可能需要 chain-of-thought 但被限制为单轮

### 8.2 Prompt 文本 Schema vs Function Calling

**决策**：通过 prompt 文本描述 JSON schema，不使用 function calling 或 structured output。

**优势**：
- 兼容所有 LLM 后端（不要求 function calling 支持）
- 灵活——可以随时修改 schema 而不改代码

**代价**：
- LLM 不一定严格遵守 schema
- 需要复杂的解析和规范化管道
- 无法利用模型级别的 schema 约束

### 8.3 信息隔离在编排层 vs Agent 层

**决策**：在 InformationBroker 层面过滤，不在 agent 层面。

**优势**：
- Agent 代码不需要处理信息过滤逻辑
- 隔离保证是系统级的，不依赖 agent 的"自觉"
- 过滤逻辑集中、可审计

**代价**：
- 每次 agent 调用都需要重新计算可见状态
- 过滤逻辑本身可能有 bug（但比 agent 层面的"忘记过滤"好得多）

### 8.4 不可变状态 vs 可变状态

**决策**：GameState 使用 Pydantic frozen=True，所有转换生成新实例。

**优势**：
- 快照天然安全（引用即快照）
- 状态转换可审计（每次转换都有完整的前后状态）
- 避免并发修改问题

**代价**：
- 每次状态更新都需要全量重建（`model_dump()` + 重新构造）
- 大游戏可能有性能问题

### 8.5 顺序发言 vs 并行发言

**决策**：白天讨论严格顺序处理 AI 发言。

**优势**：
- 后面的 agent 能看到前面的发言，模拟真实游戏
- 信息传递是自然的因果链

**代价**：
- N 个 agent 的总延迟 = N × 单次延迟
- 通过 SpeechPreGenCache 缓解（预生成 + 精炼模式）

### 8.6 向量记忆的 FAISS vs 其他方案

**决策**：使用 FAISS IndexFlatL2（暴力搜索）。

**优势**：
- 实现简单，无需索引构建
- 对于 1000 条容量足够快

**代价**：
- 不支持删除，只能全量重建
- L2 距离对中文语义可能不是最优
- 依赖 numpy/faiss 安装

---

## 9. 改进空间与工程建议

### 9.1 Prompt 版本管理

**现状**：Prompt 散落在代码中，没有版本化。改一个 prompt 可能影响所有 agent 的行为，但很难追溯。

**建议**：
- 将 prompt 模板提取到外部配置文件（YAML/TOML）
- 为每个 prompt 片段添加版本号
- 记录每次游戏使用的 prompt 版本（写入 game_record）

### 9.2 输出解析的脆弱性

**现状**：依赖 prompt 文本描述的 JSON schema，需要复杂的解析管道。

**建议**：
- 对支持 structured output 的后端，使用 JSON schema 约束
- 对支持 function calling 的后端，使用 tool_use 模式
- 保留现有的文本 schema 作为降级方案

### 9.3 记忆系统的"遗忘"策略

**现状**：多种遗忘机制并存（FIFO cap、compact、clear_transient、冻结、截断），但缺乏统一的"重要性"评估。

**建议**：
- 引入记忆重要性评分（基于信任等级、新鲜度、引用频率）
- 实现基于重要性的加权淘汰，而非纯 FIFO
- 考虑跨 agent 的记忆共享（如"公共已知事实"）

### 9.4 多 agent 交互的涌现行为测试

**现状**：单 agent 测试和 mock 测试覆盖良好，但多 agent 交互的涌现行为难以测试。

**建议**：
- 引入"对抗性测试"：专门构造会暴露 agent 间不一致的场景
- 实现"回放+变异"测试：基于真实游戏 trace，变异输入观察行为变化
- 建立 agent 行为一致性指标（如同一事实的不同 agent 记忆差异）

### 9.5 Prompt 长度优化

**现状**：system prompt 可能达 2000-4000 tokens，包含大量冗余。

**建议**：
- 分析各区块的实际 token 消耗和对决策质量的影响
- 对低影响区块实施更激进的截断
- 考虑"分层 prompt"策略：核心信息始终注入，细节按相关性动态选择

### 9.6 错误重试策略

**现状**：OpenAI 后端没有自动重试。异常直接向上传播触发回退。

**建议**：
- 对瞬时错误（rate limit、timeout、5xx）实现指数退避重试
- 限制最大重试次数（如 2-3 次）
- 区分可重试错误和不可重试错误

### 9.7 向量记忆的语义质量

**现状**：使用 FAISS IndexFlatL2 + L2 距离，embedding 模型可配置。

**建议**：
- 评估当前 embedding 模型在中文社交推理场景下的检索质量
- 考虑使用 cosine similarity 替代 L2
- 引入检索质量指标（如 retrieved items 的实际引用率）

---

## 10. 附录：关键文件索引

### 10.1 Prompt 工程

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/agents/prompt/prompt_factory.py` | ~300 | Prompt 组装工厂 |
| `src/agents/ai_agent.py` | ~1100 | Agent 门面 + system prompt 组装 (L497-535) |
| `src/agents/difficulty_presets.py` | ~250 | 4 个难度预设 + prompt 修饰 |
| `src/agents/persona_registry.py` | ~200 | 9 种人格原型定义 |
| `src/agents/deception/deception_tracker.py` | ~200 | 欺骗预算 + 叙事一致性 |
| `src/agents/strategy/evil_strategy.py` | ~400 | 邪恶阵营策略 prompt |
| `src/agents/storyteller_agent.py` | ~1500 | 说书人 prompt + 裁量逻辑 |

### 10.2 输出解析

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/agents/decision/decision_engine.py` | ~1050 | 决策规范化 + 目标评分 + 回退决策 |
| `src/agents/speech/speech_sanitizer.py` | ~250 | 发言泄露检测 + 清洗 |
| `src/agents/decision/fallback_dispatcher.py` | ~100 | 回退分发 |

### 10.3 记忆管理

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/agents/memory/working_memory.py` | ~300 | 工作记忆（6 个列表 + 3 层信任） |
| `src/agents/memory/episodic_memory.py` | ~80 | 情景记忆（阶段摘要） |
| `src/agents/memory/vector_memory.py` | ~200 | 向量记忆（FAISS RAG） |
| `src/agents/memory/social_graph.py` | ~400 | 社交图谱（信任/信念/声明） |
| `src/agents/memory/memory_controller.py` | ~300 | 统一记忆管理（归档/反思） |

### 10.4 编排引擎

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/orchestrator/game_loop.py` | ~766 | GameOrchestrator 门面 |
| `src/orchestrator/information_broker.py` | ~250 | 可见性过滤 + agent 注册 |
| `src/orchestrator/event_bus.py` | ~100 | 异步 pub/sub |
| `src/orchestrator/agents/__init__.py` | ~100 | AgentManager |
| `src/orchestrator/phases/night_phase.py` | ~574 | 夜晚阶段处理器 |
| `src/orchestrator/phases/day_discussion.py` | ~274 | 白天讨论处理器 |
| `src/orchestrator/phases/nomination_voting.py` | ~756 | 提名投票处理器 |

### 10.5 鲁棒性与可观测性

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/orchestrator/metrics/__init__.py` | ~530 | MetricsCollector + _timed_act |
| `src/engine/data_collector.py` | ~200 | JSONL trace 持久化 |
| `src/state/game_record.py` | ~470 | SQLite 持久化 + 恢复 |
| `src/llm/mock_backend.py` | ~150 | Mock LLM 后端 |
| `src/llm/openai_backend.py` | ~300 | OpenAI 兼容后端 |
| `src/llm/base_backend.py` | ~50 | 抽象后端接口 |

### 10.6 状态模型

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `src/state/game_state.py` | ~400 | GameState/PlayerState（不可变 Pydantic） |
| `src/state/event_log.py` | ~50 | 事件日志容器 |
| `src/state/snapshot.py` | ~80 | 快照管理 |

### 10.7 测试与接受

| 文件 | 行数 | 职责 |
|------|-----:|------|
| `scripts/alpha1.1_acceptance.py` | ~200 | 聚合接受门 |
| `scripts/ai_speed_acceptance.py` | ~300 | 速度接受门 |
| `scripts/ai_conversation_quality_acceptance.py` | ~250 | 对话质量接受门 |
| `tests/test_orchestrator/test_game_loop.py` | ~500 | 游戏循环测试（ScriptedAgent/TrackingAgent） |
| `tests/test_agents/test_agent_reasoning.py` | ~1000 | Agent 推理/记忆/回退测试 |

---

## 总结

这个项目是一个**工业级的多智能体 LLM 协作 harness**，其工程复杂度体现在：

1. **Prompt 不是静态模板**，而是基于阵营、难度、人格、动作类型、记忆状态、欺骗预算等多维度动态构建的
2. **输出解析不是简单 JSON parse**，而是一个多阶段管道（fence 提取 → JSON parse → raw_decode → 类型强制转换 → 语义验证 → 泄露清洗）
3. **记忆不是简单的对话历史**，而是四层架构（工作/情景/向量/社交图谱）+ 三层信任分级 + 多种遗忘策略
4. **编排不是简单的顺序调用**，而是四种模式（严格顺序/gather 并发/create_task 并发/后台预生成）的混合
5. **鲁棒性不是简单的 try-catch**，而是三层回退（agent 内部 → 编排器 → 硬编码）+ 断路器 + 接受门

这比大多数"调 API 生成文本"的 LLM 应用复杂一个数量级。它解决的核心问题是：**如何让多个 LLM 在有规则、有状态、有信息不对称的环境中可靠地协作和对抗**——这是 harness 工程的高阶形态。
