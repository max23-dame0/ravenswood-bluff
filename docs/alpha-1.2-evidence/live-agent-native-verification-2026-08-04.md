---
doc_id: "RPT-013"
title: "Alpha 1.2 Agent 原生重构 live 对局验收证据（真实 LLM）"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-04"
author: "Ravenswood Bluff"
---

# Alpha 1.2 Agent 原生重构 live 对局验收证据（真实 LLM）

> 本文档记录使用 **DeepSeek 真实 LLM**（`deepseek-v4-flash`）跑 5 人完整 day_1 对局的验证结果，
> 验证 Agent 原生重构功能 + token 优化效果。

## 1. 环境

- LLM：`deepseek-v4-flash`（`OPENAI_BASE_URL=https://api.deepseek.com`，见 `.env`）
- 命令：`simulate_game.py --backend live --player-count 5 --discussion-rounds 1 --stop-after day_1 --audit-mode --max-nomination-rounds 1`
- 时间：2026-08-04 12:06 / 12:08 / 12:09（三局）

## 2. 功能验证（真实 LLM 下 Agent 原生重构全部生效）

| 能力 | 证据 | 结论 |
|------|------|:--:|
| **工具调用主导** | `speech_source: 'tool_calling'`、`tool_used: True`（speak/night_action/defense_speech） | ✅ |
| **JSON fallback 兜底** | 局1 p3 defense（empty_response）、局2 p4 speak（JSONDecodeError）均安全 fallback | ✅ 不卡流程 |
| **草稿复用** | 局3 p1 speak `model: 'draft-reuse'`、`speech_source: 'cache_finalized_draft_reuse'`、**0 token** | ✅ |
| **本地策略判定** | `vote: 0`、`nomination_intent: 0`（两局均不走 LLM） | ✅ |
| **进化绑定** | 5 玩家角色同步、阶段记忆归档触发 | ✅ |
| **完整流程** | setup→first_night→day_discussion→nomination→voting→execution→night 全跑通，`stop_status: day_1` | ✅ |

## 3. Token 优化效果（关键实证）

### 3.1 简单动作关 thinking（验证 reasoning_tokens 归零）

DeepSeek 推理模型，`thinking=enabled` 会烧 reasoning tokens：

| 场景 | max_tokens | reasoning_tokens | total_tokens |
|------|:---:|:---:|:---:|
| `thinking=enabled`（简单问答） | 100 | **40** | 131 |
| `thinking=disabled`（简单问答） | 60 | **0** | 14 |

→ 简单动作关 thinking 后 **reasoning tokens 归零**，total 降低 ~90%。

### 3.2 speak/defense_speech 关 thinking（本次优化）

原策略 `speak/defense_speech` 配 `thinking=enabled`，deepseek 在 JSON fallback 路径烧 356-400 reasoning 并导致空响应/JSONDecodeError。改为 `thinking=disabled` 后（工具路径本就不烧 reasoning，无质量损失）：

| 指标 | 局1（enabled） | 局2（enabled） | 局3（disabled） |
|------|:---:|:---:|:---:|
| total_tokens | 7365 | 7558 | **2848** |
| avg/action | 433 | 445 | **178** |
| fallback_rate | 5.9% | 5.9% | **0.0%** |
| speak reasoning | 0/356 | 0/356 | **0** |
| defense reasoning | 400 | 0 | **0** |

→ **token 降低 62%**，fallback 归零，5 玩家 speak 全部正常（草稿复用 0 token）。

### 3.3 三层前缀 + usage 解析

- `prompt_cache_hit/miss_tokens`、`reasoning_tokens` 均在 live 局 metric 中正确记录（`ai_top_token_actions` 含完整 usage 字段）。
- 三层前缀稳定（离线基准 `token_budget_benchmark.py` RESULT: PASS）。

## 4. 结论

Agent 原生重构 + token 优化在**真实 DeepSeek LLM** 下验证通过：
- 工具调用主导、JSON fallback 兜底、草稿复用、本地策略判定全部生效；
- token 从 7365 → 2848（-62%），fallback 从 5.9% → 0%；
- 简单动作关 thinking 消除 reasoning tokens；发言关 thinking 无质量损失（工具路径不变）。

**遗留**：DeepSeek reasoning 模型在 JSON fallback 路径偶发空响应/解析失败（`thinking=disabled` 后大幅缓解，但工具不可用时仍有小概率），由 fallback 兜底，不影响流程。
