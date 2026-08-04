---
doc_id: "PLN-039"
title: "Prompt 前缀缓存命中率优化方案与任务板（Gemini 建议落地）"
category: "planning"
role: "[Delta]"
status: "draft"
date: "2026-08-04"
author: "Ravenswood Bluff"
---

# Prompt 前缀缓存命中率优化方案与任务板（Gemini 建议落地）

> **目标**：将全量缓存命中率从 **12.7%**（2026-08-04 实测）提升到 **40%+**（保守）乃至 60%+（乐观），减少 Input cache miss 的计费成本（DeepSeek 命中 ¥0.1/M vs 未命中 ¥1.0/M，10 倍价差）。
> **执行方式**：本文档即任务板（Task Board）。新开窗口按 §6 任务顺序执行，每项完成需满足 §7 验收标准；全部完成后按 §8 清洁状态检查收尾。
> **前情**：2026-08-04 已完成第一轮三层前缀优化（PLN-037 P1 + 缓存命中优化，变化点后置 system/user1/user2），实测真实总 token 252,999→187,423（-25.9%），但缓存命中率仅 11.9%→12.7%。本计划为**第二轮缓存优化**，聚焦"前缀稳定最大化"。

---

## 1. 现状与数据

### 1.1 当前命中率（2026-08-04，DeepSeek 8 人完整局）

| 指标 | 值 |
|------|----|
| 全量缓存命中率 | ~12.7%（40,448 / 317,825，含全天多局） |
| 动作类（act）命中率 | 9.3%（改前）→ ~13%（改后） |
| 同一玩家 system 完全一致时 | **0-29%**（Player2=29%、Player7=0%） |
| archive/reflect/storyteller/evil 类（system 动态） | **0% 命中** |
| 跨 Agent 交叉命中 | **0%**（8 个 Agent 8 个独立缓存池） |

### 1.2 已完成的优化（第一轮，勿回退）

1. `ai_agent.py act()` 三层前缀重组：system=公共规则+名单+身份+稳定人格+目标（同玩家整局稳定）；user1=仅跨局记忆；user2=记忆/局势/动作类型/JSON schema/动作风格全部后置。
2. `prompt_factory.py` 新增 `build_action_style_block()`（动态动作风格/evil 战略/叙事一致性移出 persona 块）。
3. 说书人/evil 频道补 `thinking="disabled"`（reasoning 3650→0）。

> ⚠️ 本轮优化**必须保留**以上结构，在其之上继续加深前缀稳定。

---

## 2. 根因分析（4 个缓存失效"隐形漏点" + 实测验证）

### 2.1 tools 参数动态传递（最大杀手）✅ 实测成立

- **机制**：DeepSeek/OpenAI 兼容 API 中 `tools` 参与请求前缀拼装，`tool_defs_for_action(action_type)` 按动作返回不同工具（speak→`[speak]`，defense_speech→`[speak, defense_speech]`，night_action→`[night_action]`），导致**相同 system 的两次调用因 tools 不同而前缀失效**。
- **实测**：Player2 5 次调用（1×defense_speech + 4×night_action，system 完全一致）命中 29%≈4×system；**不同 tools 的 defense_speech 那次未命中**。

### 2.2 跨 Agent 全局公共前缀过早分化 ✅ 成立

- 8 个 Agent 从「玩家身份」开始各自分化（P1 是 washerwoman、P2 是 imp…），形成 8 个互不兼容缓存池；公共规则段仅 ~250 字符，收益极小。
- **实测**：跨 Agent 交叉命中 0%。

### 2.3 草稿生成（Draft Speech）动态 system → 缓存污染 ✅ 成立

- `generate_draft_speech` 的 system 直接把【社交图谱】【局势摘要】等动态内容写入开头（见 REF-006 案例 B），大批量预生成请求自身不命中且挤占节点缓存。

### 2.4 多 Agent 轮转导致的单 Agent 缓存退化 ⚠️ 机制存疑但现象存在

- DeepSeek 官方：缓存"几小时到几天"自动清理（非强 LRU），且 best-effort、首次构建有数秒延迟。
- **实测**：Player7 两次相同动作（相同 tools）命中 0%——更可能是 best-effort/构建延迟，而非严格 LRU；但"单 Agent 两次调用间隔长导致缓存不可用"的现象真实存在。

---

## 3. 可行性评估（Gemini 建议逐条）

| 建议 | 评估 | 依据 |
|------|:--:|------|
| **① tools 全量固定**（消除 API 底层前缀篡改） | ✅ 可行 | 实测 tools 变化与失命中强相关；改动小 |
| **② 超长全局公共前缀**（>1000 tokens 跨 Agent 100% 共享） | ✅ **最有价值** | 对抗"单 Agent 轮转间隔"：任一 Agent 请求都会重建/命中同一段共享前缀 |
| **③ 草稿/辅助 prompt 与 act() 结构对齐** | ✅ 可行 | 消除动态 system 污染 + 预热主缓存 |
| **④ user1/user2 格式稳定** | ⚠️ 收益小 | 占位符已固定；user2 在命中点之后，排序无意义 |

**两处修正**（不采纳为决策依据）：
- "1024 Token 最小门槛"：DeepSeek 官方**未给出**最小 token 门槛；但公共前缀凑长仍有收益（跨 Agent 共享收益与长度成正比）。
- "LRU 淘汰"：官方为"几小时到几天自动清理"，非强 LRU；Player7 0% 更可能是 best-effort/构建延迟。不过"让共享前缀持续活跃"的策略依然有效。

---

## 4. 目标架构（本轮落地形态）

### 4.1 system 重组为"双层"

```
+--------------------------------------------------------------------------+
| 层 1：全局绝对静态层（跨所有 Agent / 轮次 / 动作 100% 逐 Token 一致）         |
|   - 跨 Agent 公共游戏规则 (common_rules，如需可补足信息)                     |
|   - 玩家通用约束 & 核心原则（7 条玩家优先级原则，当前已在 system 内、纯静态）    |
|   - 8 个 Action 工具的完整纯文本 Schema 定义（写在 system 文本里）            |
|   - 标准 JSON / Tool Calling 输出格式要求                                  |
|   - （目标长度 ≥ 1500 字符，实测 1,522 ≈ 761 tokens（按 len//2 估算））        |
+--------------------------------------------------------------------------+
| 层 2：Agent 局部静态层（同一 Agent 整局不变，不同 Agent 独立）                 |
|   - 玩家名单 (p1~p8)                                                       |
|   - 身份信息（认知的角色 / 阵营）                                           |
|   - 稳定人格锚点 (build_persona_prompt_block)                              |
|   - 目标                                                                |
+--------------------------------------------------------------------------+
user1 = 跨局玩家记忆（保持现状，或压入层 2 以减少 message 边界）
user2 = 全部动态（记忆/局势/动作类型/JSON schema/动作风格）—— 保持现状后置
```

### 4.2 tools 全量固定

- 每次 `backend.generate()` 统一传 **8 个 Action Tools 全量 schema**（稳定字符串）。
- user2 的【动作与输出格式】保留"当前需要执行的动作类型"引导模型选对工具。
- 兜底：`decision_from_tool_calls` 解析失败时走 JSON fallback（现有机制，勿破坏）。

### 4.3 草稿/辅助 prompt 结构对齐

- `generate_draft_speech` 复用 act() 的 system 前缀（全局静态 + Agent 局部静态），动态内容（社交图谱/局势/记忆）移入 user 末条。

---

## 5. 涉及文件清单

| 文件 | 改动内容 |
|------|---------|
| `src/agents/prompt/common_rules.py` | 补充/整理全局静态规则段（可选，补足长度） |
| `src/agents/tools/action_tool_registry.py` | 新增 `all_tool_defs()` 全量 schema 入口；`tool_defs_for_action` 保留（或改为全量） |
| `src/agents/ai_agent.py` | `act()` system 双层重组（工具 schema 文本化前置）；`generate_draft_speech()` 结构对齐 |
| `src/agents/prompt/prompt_factory.py` | 输出格式要求文本（静态段）；草稿生成所需动态段的复用函数 |
| `src/agents/ai_agent_delegation.py` | 如新增 prompt 工厂方法则加委托 |
| `scripts/benchmark/token_budget_benchmark.py` | 三层前缀断言适配（system 变长后仍须 stable） |
| `tests/test_agents/test_agent_tools.py` 等 | 断言适配（tools 全量 / system 静态段位置） |

---

## 6. 任务板（Task Board）

| 任务 ID | 阶段 | 优先级 | 状态 | 目标 | 验收标准（DoD） |
|:--:|:--:|:--:|:--:|------|------|
| **T1** | 全局前缀 | 🥇P0 | 🟢 已完成 | system 重组为双层，全局静态层 ≥1500 字符 | T1.1 system 全局段跨 Agent 100% 逐 token 一致；T1.2 `token_budget_benchmark` three_tier_prefix PASS |
| **T2** | tools 固定 | 🥇P0 | 🟢 已完成 | `tools` 全量固定传递，消除 tools 前缀变化 | T2.1 所有 act 调用 tools 参数恒等（llm.jsonl 验证）；T2.2 工具调用主导 + JSON fallback 仍工作 |
| **T3** | 草稿对齐 | 🥈P1 | 🟢 已完成 | `generate_draft_speech` 复用 act() system 前缀，动态移 user | T3.1 草稿 system = act system 前缀（全局+局部）；T3.2 草稿调用命中共享全局层前缀（llm.jsonl 验证 hit>0；草稿与 act 的 user 首条不同，不命中 act 完整主缓存） |
| **T4** | 辅助对齐 | 🥈P1 | 🟢 已完成 | reflect/archive/storyteller 前缀能复用则复用；**补修 evil 频道动态 system** | T4.1 辅助调用不再产生"动态 system"格式（可复用前缀的复用）；T4.2 不改变功能语义 |
| **T5** | 格式稳定 | 🥉P2 | 🟢 已完成 | user1/user2 格式清理（占位符/换行/排序） | T5.1 无记忆时 user1 固定占位符；T5.2 测试无回归 |
| **T6** | 验证 | 🥇P0 | 🟨 部分完成（DoD #5 未达成） | live 8 人局完整对局实测命中率 | T6.1 完整局到 game_over（✅）；T6.2 命中率 ≥40%（✅ 53.19%）；T6.3 reasoning=0/fallback=0（✅）；❌ 真实总 token 370,931 > 187,423，计费当量 +12.8%（核心经济目标未达成，待精简后再验） |

> 状态列：⬜ 待开始 → 🟨 进行中 → 🟢 已完成（完成后在 PROGRESS.md 待提交清单登记）
> ⚠️ REV-008 F7：T1-T5 代码完成但**尚未 commit**（`git status` 可查），状态标注为"🟢 代码完成/待提交"；T6 因 DoD #5 未达成保持 🟨。commit 后回填 hash。

---

## 6.1 T1 — system 双层重组（全局静态层 + Agent 局部静态层）

**改动文件**：`src/agents/ai_agent.py act()`、`src/agents/prompt/common_rules.py`（可选补足）、`src/agents/tools/action_tool_registry.py`（schema 文本化辅助）

**步骤**：
1. 在 `common_rules.py` 确认/补足跨 Agent 公共规则段（当前 ~250 字符；把不依赖身份的规则尽量写足）。
2. 提取 system 中**纯静态**内容为层 1：公共规则 + 核心原则 7 条 + 全量 8 工具 schema 的纯文本描述 + 标准输出格式要求（均不依赖 agent 身份/动作）。
3. 层 2 保留：玩家名单 + 身份 + 人格锚点 + 目标。
4. 确保层 1 + 层 2 顺序稳定；`_json_schema_for_action(action_type)` 的 JSON 仍放 user2（动态）。

**验收**：
- 两个不同 Agent（如 p1/p2）的 system 前段（层 1）逐 token 相同（用脚本比对 `dump_ai_prompt` 或 llm.jsonl）。
- `scripts/benchmark/token_budget_benchmark.py` → RESULT: PASS。
- `pytest tests -m "not slow"` 全绿。

## 6.2 T2 — tools 全量固定

**改动文件**：`src/agents/tools/action_tool_registry.py`、`src/agents/ai_agent.py act()`

**步骤**：
1. `action_tool_registry.py` 新增 `all_tool_defs() -> list[dict]`（8 工具全量，schema 为稳定字符串，禁止运行时拼接状态）。
2. `act()` 中 `tool_defs_for_action(action_type)` 改为返回 `all_tool_defs()`（或保留单工具 + 全量二选一，以实测为准；推荐全量）。
3. user2 的【动作与输出格式】补充一句："当前需要执行的动作类型：{action_type}，请只调用与该动作对应的工具；其余工具忽略。"

**验收**：
- 解析 llm.jsonl：同一玩家不同动作的调用 `tools` 参数完全一致。
- defense_speech 与 night_action 交替调用时，system 命中率不归零。
- `test_agent_tools.py` 工具调用主导测试仍通过（含 JSON fallback 兜底路径）。

## 6.3 T3 — 草稿生成与 act() 结构对齐

**改动文件**：`src/agents/ai_agent.py generate_draft_speech()`、`src/agents/prompt/prompt_factory.py`

**步骤**：
1. 将 `generate_draft_speech` 的 system 改为 **act() 相同的前缀**（全局静态层 + Agent 局部静态层），即复用同一 system 构建函数。
2. 【社交图谱】【局势摘要】【记忆】等动态内容从 system 移入 user 末条。
3. 保持草稿的轻量特性（记忆段 token 上限：分层记忆 600 / 社交图谱 200 等，勿丢）。

**验收**：
- llm.jsonl：草稿请求的 system 与同 Agent act 请求的 system 前缀一致（逐 token 比对）。
- 草稿调用出现 `prompt_cache_hit_tokens > 0`（命中该 Agent 主缓存）。
- 发言质量不回归（对比 1 局 mock 对局发言长度/风格）。

## 6.4 T4 — 辅助调用前缀对齐（可选）

**改动文件**：`src/agents/memory/memory_controller.py`（reflect/archive）、`src/agents/storyteller_delegation.py`

**步骤**：
1. 检查 reflect/archive/storyteller 的 system 前缀是否可复用公共段；能复用则前置公共段。
2. 对无法复用的（如 archive 提炼），至少保证 system 为"稳定身份 + 稳定任务描述"，动态内容移 user。

**验收**：辅助调用语义不变；能复用的前缀在 llm.jsonl 中体现命中。

## 6.5 T5 — user1/user2 格式稳定清理

**改动文件**：`src/agents/ai_agent.py`、`src/agents/memory/`（摘要排序）

**步骤**：
1. 确认无跨局记忆时 user1 为固定占位符（当前已是"【跨局记忆】本局新玩家…"）。
2. 消除条件拼接产生的换行符差异（`\n\n` vs `\n`），统一模板。
3. 涉及列表（公开声明等）若进入 user1，按 `player_id` 字典序固定排序（user2 内无需，收益为零）。

**验收**：同一 Agent 整局 user1 逐 token 稳定（llm.jsonl 比对）；测试无回归。

## 6.6 T6 — live 8 人局实测验证

**命令**：
```powershell
.\.venv\Scripts\python.exe simulate_game.py --backend live --player-count 8 --stop-after game_over --timeout-seconds 1800 --audit-mode
```

**分析**：解析最新 `runtime_game_logs/<slot>/llm.jsonl`，统计：
- 全量缓存命中率（要求 ≥40%，对比 12.7%）
- act 类 / 草稿类 / 辅助类命中率
- 真实总 token（对比 187,423 基线）、reasoning（应为 0）、fallback（应 0）

**⚠️ 日志归档流程（REV-008 F1）**：live 实测结束后**立即**归档原始日志到不可覆盖路径，再跑分析脚本，否则 `runtime_game_logs/<slot>/` 会被下一局轮转覆盖、数字不可复核：
```powershell
# 对局结束后立即执行（含 metadata，文件名带局次）
Copy-Item runtime_game_logs/recent_1/llm.jsonl docs/alpha-1.2-evidence/pln039-live-<日期>-局1.llm.jsonl
Copy-Item runtime_game_logs/recent_1/metadata.json docs/alpha-1.2-evidence/pln039-live-<日期>-局1.metadata.json
# 再跑分析脚本
python scripts/debug/analyze_llm_cache.py docs/alpha-1.2-evidence/pln039-live-<日期>-局1.llm.jsonl
```
归档文件属证据类，随 commit 入库（不入 .gitignore）。

---

## 7. 全局验收标准（DoD）

1. `pytest tests -m "not slow"` = **477 passed / 0 failed**（若新增测试则相应增加）。
2. `ruff check src tests scripts` 0 告警；`ruff format --check` 全绿；`check_doc_health.py` RC=0。
3. `scripts/benchmark/token_budget_benchmark.py` → **RESULT: PASS**。
4. mock 8 人局完整局正常（stop_status=game_over）。
5. live 8 人局完整局：**缓存命中率 ≥40%**、真实总 token ≤ 改前（187,423）、reasoning=0、fallback=0。
6. 三层前缀语义保持（信息隔离、工具调用主导、草稿复用、本地策略判定全部不回退）。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| tools 全量后模型误调不相关工具 | 动作解析失败 | user2 动作类型提示 + `decision_from_tool_calls` 校验 + JSON fallback 兜底；mock 对局回归验证 |
| system 变长（加工具 schema 文本） | 每次请求 prompt 增大 | 命中率提升的收益（10 倍价差）远超输入增量；T6 实测验证净收益 |
| 草稿与 act 结构对齐改动面大 | 引入回归 | 分步实施 + 发言质量对比（mock 1 局） |
| DeepSeek best-effort 缓存不可控 | 命中率达不到 40% | 以相对提升为验收（12.7%→翻倍+）；T1 共享前缀策略保证"任一 Agent 活跃即共享段活跃" |

## 9. 相关文档

- `docs/guides/prompt-design.md`（REF-006：当前 prompt 设计总览与案例）
- `docs/plans/token-budget-optimization-plan.md`（PLN-037：第一轮三层前缀）
- `docs/plans/agent-native-redesign-plan.md`（PLN-038：Agent 原生重构）
- `docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md`（RPT-013：live 验证基线）
- `docs/alpha-1.2-evidence/pln039-live-8p-cache-verification-2026-08-04.md`（RPT-014：PLN-039 T6 实测）
- `.codebuddy/memory/2026-08-04.md`（缓存分析历史与实测数据）
