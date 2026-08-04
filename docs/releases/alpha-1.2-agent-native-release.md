---
doc_id: "REL-007"
title: "Alpha 1.2 Agent 原生重构版发布记录"
category: "release"
role: "[Delta]"
status: "published"
date: "2026-08-04"
author: "Ravenswood Bluff"
---

# Alpha 1.2 Agent 原生重构版发布记录

> 本文档记录 **agent 原生重构（PLN-038）** 与 **token 优化（PLN-037）** 两大重大改动，
> 以及 **记忆对局隔离 + 拟人化进化机制** 的落地。是相对 Alpha 1.1 的架构级演进版本。

## 1. 版本口径

当前版本口径：`alpha1.2`（Agent 原生重构版）。

Alpha 1.1 解决了"AI 玩家难度系统与响应流畅体验"。Alpha 1.2 将 AI 玩家从"集中式调度 + 单次无状态 LLM 调用"
演进为**受控自主 Agent**：保留 orchestrator 作为规则裁判与调度器，将行动标准化为工具调用、
世界状态按需查询、记忆维护工具化，并引入跨局玩家进化机制。同时达成 token 控制目标。

## 2. 核心变更

### 2.1 Agent 原生重构（PLN-038）

| 阶段 | 内容 |
|------|------|
| 阶段0 | LLM 层透传 `thinking`/`reasoning_effort` + usage 解析扩展（cache hit/miss + reasoning_tokens）+ 策略表 `LLM_STRATEGY_BY_ACTION` |
| 阶段A | 行动工具化：`GameActionToolRegistry`（8 个 ToolDef），`act()` 工具调用主导 + JSON fallback |
| 阶段B | 策略先行 loop：`MemoryController.think` 升级为低预算 LLM 内心独白；`act_with_strategy()` 入口 |
| 阶段S | 说书人工具注册表（6 工具）+ `DistortionStrategy` 枚举化 + `BOTC_ST_LLM_STRATEGY=off` 行为兼容 |
| 阶段C | 记忆工具化：`MemoryTools` append/read/reflect/archive + 落盘 + 隔离校验 |
| 阶段D | 世界感知查询化：`WorldTools` 4 只读工具 + 三层前缀稳定化（`common_rules.py`） |

### 2.2 Token 优化（PLN-037）

| 目标 | 达成 |
|------|------|
| P0-4.1 策略表：简单动作关思考 | `vote/night_action/nominate` → `thinking="disabled"` |
| P0-4.1 发言类降 effort + 限 max_tokens | `speak/defense_speech` → `effort=low, max_tokens=400` |
| P0-4.3 speak 草稿复用（输出减半） | 有草稿时 LLM 调用 **0 次** |
| P1-4.5/4.6/4.7 三层前缀稳定化 | system 前缀逐 token 稳定；公共前缀跨 agent 共享 |
| P2-4.8 usage 解析扩展 | `prompt_cache_hit/miss_tokens` + `reasoning_tokens` 解析并记录 |

### 2.3 记忆对局隔离 + 玩家/说书人进化（PLN-038 阶段 E）

```
data/agents/{player_id}/
    profile/                    跨局玩家档案（进化）
        profile.json            战绩统计 + tendency 四维画像 + evolution 计数
        long_term_memory.jsonl  跨局经验教训
        reflections.jsonl       局中反思
        game_reviews.jsonl      局后复盘
        lessons_learned.jsonl   学习他人经验
        strategies.jsonl        策略调整
    games/{game_id}/            单局记忆（对局隔离）
        memory.jsonl
data/storyteller/{game_id}/     说书人单局平衡档案
data/storyteller/profile/       说书人跨局档案
```

**拟人化进化四维**（参考人类玩家水平增长机制）：

| 维度 | 人类机制 | 实现 |
|------|---------|------|
| 局中反思 | 对局中不断自我校正 | `add_in_game_reflection()` → `reflections.jsonl` |
| 局后复盘 | 赢/输后总结 | `finalize_game_review()` → `game_reviews.jsonl` |
| 学习他人经验 | 观察高手打法 | `_learn_from_strong_players()` → `lessons_learned.jsonl` |
| 调整策略 | 基于战绩调整打法 | `evolve_strategies()` + `tendency` 画像 → `strategies.jsonl` |

## 3. 验证结果（全绿）

| 检查项 | 结果 |
|------|:--:|
| `pytest tests -q -m "not slow"` | ✅ **477 passed / 0 failed**（全量含 slow 共 495；2026-08-04 独立复核修正） |
| `ruff check src tests scripts` | ✅ 0 告警 |
| `ruff format --check` | ✅ 197 files 全绿 |
| `scripts/alpha1.1_acceptance.py` | ✅ 9/9 exit=0（曾因草稿复用标记修复后通过） |
| `scripts/benchmark/token_budget_benchmark.py` | ✅ RESULT: PASS |
| `scripts/check_doc_health.py` | ✅ RC=0 |
| `simulate_game --backend mock --stop-after day_1` | ✅ 完整白天流程 |
| 局末进化落盘端到端（mock） | ✅ 5 玩家自动触发 reviews/lessons/strategies |

## 4. Live 对局验收（真实 DeepSeek LLM，2026-08-04）

使用 `deepseek-v4-flash` 跑 5 人完整 day_1 对局验证（详见 `docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md`）：

| 验证点 | 结果 |
|------|:--:|
| 工具调用主导（speak/night/defense） | ✅ `speech_source: 'tool_calling'` |
| 草稿复用（0 token speak） | ✅ 局3 p1 `cache_finalized_draft_reuse` |
| 本地策略判定（vote/nomination_intent 0 token） | ✅ |
| JSON fallback 兜底（不卡流程） | ✅ |
| 完整流程 setup→…→night | ✅ `stop_status: day_1` |
| **token 优化**：7365 → 2848（-62%） | ✅ 见 §5 |
| **fallback 归零**：5.9% → 0% | ✅ |

### 4.1 关键优化：speak/defense_speech 关 thinking

原策略 `speak/defense_speech` 配 `thinking=enabled`，deepseek 推理模型在 JSON fallback 路径烧 356-400 reasoning 并导致空响应/JSONDecodeError。实测工具路径本就不烧 reasoning（reasoning_tokens=0），改 `thinking=disabled` 为纯收益：

- 局1（enabled）：total 7365，fallback 5.9%
- 局3（disabled）：total 2848，fallback 0.0%

## 5. 文档与决策

- 计划：`docs/plans/agent-native-redesign-plan.md`（PLN-038，status=published，验收清单全勾选）
- Token 计划：`docs/plans/token-budget-optimization-plan.md`（PLN-037）
- 审查报告：`docs/reviews/agent-native-redesign-cr-review-2026-08-03.md`
- Token 基准：`docs/plans/token-budget-benchmark.json`
- Live 验收证据：`docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md`
- 决策：`DECISIONS.md` D012（Agent 原生重构）、D013（记忆隔离+进化）、D014（拟人化进化）

## 5. 已知问题与遗留

1. **`ai_conversation_quality` 验收 gate 偶发 flaky**：MockBackend 下 5 人局同 round 从 20 句预置发言随机抽偶发重复（单跑即通过 RC=0），与本次改动无关，属既有随机性。
2. **`BOTC_ST_LLM_STRATEGY=low|on` 需 live 真人验收**：默认 off 时行为与重构前完全一致。
3. **工具调用主导路径依赖真实 LLM 返回 `tool_calls`**：mock 只测 fallback 路径，live 需验证实际解析质量。
4. **进化机制待 live 验证**：局中反思为工具能力（agent 自主调用），引擎钩子兜底保留；局末倾向微调为规则驱动。
