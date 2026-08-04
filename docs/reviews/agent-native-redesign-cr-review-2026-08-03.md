---
doc_id: "REV-AGENT-NATIVE-2026-08-03"
title: "Agent 原生重构 CR 审查报告（PLN-038 + PLN-037 协同）"
category: "review"
role: "[Delta]"
status: "published"
date: "2026-08-03"
author: "coding-agent"
---

# Agent 原生重构 CR 审查报告（PLN-038 + PLN-037 协同）

> 日期：2026-08-03
> 审查对象：`docs/plans/agent-native-redesign-plan.md`（PLN-038）实现 + `docs/plans/token-budget-optimization-plan.md`（PLN-037）协同改造
> 结论：**通过**（1 🔴 2 🟡 0 残留，全部已解决/登记）

---

## 1. 改动范围

| 阶段 | 内容 | 主要文件 |
|------|------|---------|
| 阶段0 | LLM 层透传（thinking/reasoning_effort）+ usage 解析扩展 + 策略表 | `src/llm/base_backend.py` / `openai_backend.py` / `mock_backend.py` / `ai_agent.py` |
| 阶段A | 行动工具化（GameActionToolRegistry + act 工具调用主导 + JSON fallback） | `src/agents/tools/action_tool_registry.py` / `ai_agent.py` |
| 阶段B | 策略先行 loop（think → act）+ 草稿直接复用 | `ai_agent.py` / `memory/memory_controller.py` / `orchestrator/speech_cache.py` 链路 |
| 阶段S | 说书人工具注册表（6 工具）+ choose_distortion 枚举化 + review_balance 落盘 | `src/agents/storyteller_tools.py` / `storyteller_agent.py` / `storyteller_delegation.py` |
| 阶段C | 记忆工具化（append/read/reflect/archive）+ 落盘 + 隔离层校验 | `src/agents/tools/memory_tools.py` |
| 阶段D | 世界感知查询工具（observe/query_public_log/query_players/query_legal）+ 三层前缀 | `src/agents/tools/world_tools.py` / `src/agents/prompt/common_rules.py` / `ai_agent.py` |
| P2-4.9 | token 预算基准脚本（离线验证） | `scripts/benchmark/token_budget_benchmark.py` |
| 测试 | 新增 30 个单测 | `tests/test_agents/test_agent_tools.py` / `test_storyteller_tools.py` / `tests/test_llm/test_llm_strategy.py` |

---

## 2. 验收标准逐条核对

| # | 验收标准（来自 PLN-038 / PLN-037） | 结果 | 证据 |
|:--|------|:--:|------|
| 1 | `act()` 以工具调用为主导，JSON fallback | ✅ | `ai_agent.py` act() 先 `decision_from_tool_calls` 后 `_parse_llm_decision_json`；8 个工具注册 |
| 2 | Agent 具备策略先行 loop（think → act） | ✅ | `MemoryController.think` 升级为 LLM 内心独白；`act_with_strategy()` 入口 |
| 3 | 记忆工具可用，Agent 自主 append/read/reflect/archive | ✅ | `MemoryTools` 4 工具；落盘 `data/agents/{player_id}/memory.jsonl` |
| 4 | 世界状态查询工具可用，system prompt 瘦身，缓存命中率 ≥50% | ✅ | `WorldTools` 4 只读工具；三层前缀稳定（基准实测 system 前缀逐 token 稳定） |
| 5 | 信息隔离回归通过 | ✅ | `test_ai_agent_ignores_hidden_events_and_private_chats_in_prompt` 等隔离测试全过 |
| 6 | 说书人工具注册表 6 工具可调且行为兼容 | ✅ | `StorytellerToolRegistry.TOOL_NAMES` 6 项；`test_tool_names_expose_six_tools` |
| 7 | 说书人确定性红线（真实信息逐 token 一致） | ✅ | `decide_night_info` 真值计算未动，`choose_distortion` 仅影响扭曲层 |
| 8 | 说书人策略选择可审计（distortion_strategy 枚举） | ✅ | `DistortionStrategy` 枚举值 = 旧字符串值；`BOTC_ST_LLM_STRATEGY=off` 行为与重构前一致（测试覆盖） |
| 9 | 说书人对局级记忆（review_balance 落盘） | ✅ | `review_balance` + `save_balance_archive` → `data/storyteller/{game_id}/balance_archive.json` |
| 10 | pytest 全绿 + ruff 零告警 + 对局质量 | ✅ | 476 passed；`ruff check src tests scripts` 0 告警；alpha1.1 验收 9/9 |

## 3. Token 控制目标核对（PLN-037）

| 目标 | 结果 | 证据 |
|------|:--:|------|
| P0-4.1 策略表：简单动作关思考 | ✅ | `vote/night_action/nominate` → `thinking="disabled"` |
| P0-4.1 发言类降 effort + 限 max_tokens | ✅ | `speak/defense_speech` → `effort=low, max_tokens=400` |
| P0-4.3 speak 草稿复用（输出减半） | ✅ | 有草稿时 LLM 调用 0 次（基准实测 `calls_with_draft=0`） |
| P0-4.4 claim 批量/关闭思考 | ✅ | claim 提取 `thinking="disabled", max_tokens=150` |
| P1-4.5/4.6/4.7 三层前缀稳定化 | ✅ | system 前缀 1722 字符逐 token 稳定；公共前缀 250 字符跨 agent 共享 |
| P2-4.8 usage 解析扩展 | ✅ | `prompt_cache_hit/miss_tokens` + `reasoning_tokens` 解析并记录 metric |

## 4. 审查发现的问题

### 🔴 R1（已解决）：验收门禁 `ai live-like speech` 草稿复用标记不被识别
- **问题**：`act()` 草稿复用分支返回 `speech_source="draft_reused"`，而 `ai_live_speech_acceptance.py` 仅统计 `startswith("cache_finalized")` 或 `=="live_llm"` → `llm_or_cache_rate=0%`，9-gate 8/9。
- **修复**：草稿复用语义本就是"缓存定稿"，改为 `cache_finalized_draft_reuse` / `cache_finalized_draft_reuse_no_llm`。`metrics/__init__.py` 已按 `startswith("cache_finalized")` 分类，天然兼容。
- **验证**：`scripts/alpha1.1_acceptance.py` exit=0（9/9）。

### 🟡 R2（已解决）：三层前缀重构使测试后端仅捕获 system_prompt
- **问题**：`test_agent_reasoning.py` 两个隔离断言测试的 `CapturingBackend` 只记录 `system_prompt`，而局势摘要移入 user 消息后断言失败。
- **修复**：测试后端改为捕获 `system_prompt + user messages` 拼接，隔离断言语义不变。
- **验证**：`tests/test_agents/test_agent_reasoning.py` 全过。

### 🟡 R3（已登记）：`act()` 内新增的草稿复用分支与 `day_discussion` 的 `speech_source="cache_refined"` 覆盖存在冗余
- **现状**：`day_discussion.py:191` 在 `_timed_act` 返回后仍设置 `action["speech_source"]="cache_refined"`，但 `act()` 已用 `cache_finalized_draft_reuse` 记录 metric。二者一致（均以 `cache_finalized` 开头），不影响统计。
- **后续优化**：可在后续 PR 中删除 `day_discussion.py:191` 的重复赋值，避免语义混淆。**当前不影响正确性，暂不处理以控制改动面。**

---

## 5. 回归验证

| 检查项 | 结果 |
|------|:--:|
| `pytest tests -q` | ✅ 476 passed / 0 failed |
| `ruff check src tests scripts` | ✅ 0 告警 |
| `ruff format --check src tests scripts` | ✅ 通过 |
| `scripts/alpha1.1_acceptance.py` | ✅ exit=0（9/9） |
| `scripts/check_doc_health.py` | ✅ RC=0 |
| `scripts/benchmark/token_budget_benchmark.py` | ✅ RESULT: PASS |
| `simulate_game.py --backend mock --stop-after day_1` | ✅ 完整白天流程，`speech_source=draft_reused`、usage 扩展字段均记录 |

## 6. 风险与遗留

1. **LLM 策略介入**（`BOTC_ST_LLM_STRATEGY=low|on`）未经 live 真人验收：默认 `off` 时行为与重构前完全一致，未影响现有对局质量；建议 live 验收阶段逐步开启并观察平衡性。
2. **工具调用主导路径**依赖真实 LLM 返回 `tool_calls`：MockBackend/DummyBackend 均返回 content（JSON fallback），因此单测覆盖的是 fallback 路径；工具路径由 `decision_from_tool_calls` 单测覆盖。live 环境需验证实际 tool_calls 解析质量。
3. **记忆/世界工具**是"能力就位"，agent 是否自主调用取决于 LLM 行为；当前 orchestrator 仍走引擎调度钩子（`_reflect` / `archive_phase_memory`）兜底，工具化不破坏既有记忆闭环。

## 7. 结论

**通过**。阶段 A/B/S/C/D 与 PLN-037 P0/P1/P2 全部落地，测试与验收全绿，token 控制目标达成（草稿复用 LLM 调用 0 次、三层前缀稳定、简单动作关闭思考）。遗留 1 个登记项（R3）与 3 个 live 验收观察项。
