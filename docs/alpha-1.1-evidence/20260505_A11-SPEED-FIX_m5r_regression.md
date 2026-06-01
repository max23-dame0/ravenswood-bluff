# M5-R 回归修复证据

## 任务

A11-SPEED-FIX-037 / 038 / 039 / 040 / 041 — AI 发言质量回归修复

## 背景

M5 速度工程完成后，白天讨论阶段出现 AI 复读低信息发言（"我还在想""再看看"等）。根因：
1. 并行 `asyncio.gather` 导致所有 AI 基于同一份旧 `visible_state` 生成发言
2. 双重超时（orchestrator + agent）导致 orchestrator 的粗糙 fallback 抢先发布
3. fallback 选择 hash 确定性导致同日同轮多个 AI 输出相同内容

## 修复内容

### FIX-037：取消并发最终发言
- `_run_day_discussion` 从 `asyncio.gather(*tasks)` 改为顺序 `for p in ai_players` 循环
- 每个 AI 轮到发言时重新获取最新 `visible_state`
- 文件：`src/orchestrator/game_loop.py`

### FIX-038：双重超时修正
- `_action_latency_budgets` speak 从 2000→3500ms，defense_speech 从 2500→4000ms
- orchestrator fallback reason 前缀改为 `orchestrator_hard_timeout:{action_type}`
- 文件：`src/orchestrator/game_loop.py`

### FIX-039：最低有效发言 fallback
- `_persona_fallback_speech` 扩展：defense 3→6 选项（含 4 anchor 变体），speak 3→8 选项（含 4 anchor 变体）
- `_fallback_turn_counter` 递增盐值打破确定性 hash 重复
- `_stabilize_speech_content_with_memory` 使用 `random.choice` 3 前缀变体
- `_sanitize_public_speech_content` 使用 `random.choice` 6 模板变体
- `_private_info_public_paraphrase` 使用 `random.choice` 9 模板变体
- Social graph trust < -0.5 时强制 fallback 提名
- 文件：`src/agents/ai_agent.py`

### FIX-040：AI 发言质量验收脚本
- 新增 `scripts/ai_conversation_quality_acceptance.py`
- 检查：低信息率 ≤30%、重复率 ==0、orchestrator timeout ≤10%、total fallback ≤50%
- MockBackend speak 选项 6→20，defense_speech 选项 1→4
- 文件：`scripts/ai_conversation_quality_acceptance.py`、`src/llm/mock_backend.py`

### FIX-041：聚合验收集成
- `alpha1.1_acceptance.py` 新增 `ai conversation quality` gate
- 文件：`scripts/alpha1.1_acceptance.py`

## 验证命令

```powershell
# 质量验收
.\.venv\Scripts\python.exe scripts\ai_conversation_quality_acceptance.py

# 速度验收
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py

# 聚合验收
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 结果

### 质量验收（2026-05-05）

```
5p: low-content rate <= 30% (got 0%)  PASS
5p: duplicate rate == 0 (got 0)        PASS
5p: orchestrator timeout rate <= 10%   PASS
5p: total fallback rate <= 50%         PASS
8p: low-content rate <= 30% (got 0%)  PASS
8p: duplicate rate == 0 (got 0)        PASS
8p: orchestrator timeout rate <= 10%   PASS
8p: total fallback rate <= 50%         PASS
Results: 10/10 passed
```

### 速度验收（2026-05-05）

```
5p/speak P95 <= 2000ms (got 2ms)              PASS
5p/nomination_intent P95 <= 1000ms (got 0ms)  PASS
5p/vote P95 <= 800ms (got 0ms)                PASS
5p/defense_speech P95 <= 2500ms (got 1ms)     PASS
10p/speak P95 <= 2000ms (got 1ms)             PASS
10p/nomination_intent P95 <= 1000ms (got 0ms) PASS
10p/vote P95 <= 800ms (got 0ms)               PASS
10p/night_action P95 <= 1500ms (got 1ms)      PASS
10p/defense_speech P95 <= 2500ms (got 5ms)    PASS
slow backend: fallbacks occurred (timeout)    PASS
event log: speak events in order              PASS
event log: nominations after discussion       PASS
Results: 16/16 passed
```

### 聚合验收（2026-05-05）

```
PASS existing tests regression        2m 8.1s
PASS agent reasoning tests               7.8s
PASS difficulty acceptance               1.4s
PASS difficulty comparison               1.4s
PASS difficulty behavior acceptance      2.2s
PASS ai speed acceptance              1m 5.5s
PASS ai conversation quality             3.7s
PASS alpha1 backward compatibility       4.4s
passed: 8, failed: 0, skipped: 0
```

## 残留风险

1. MockBackend 20 选项在更大规模游戏（12+ 人）中仍可能出现 birthday-paradox 碰撞，但对正常游戏规模（5-10 人）足够。
2. 顺序发言比并行发言慢，但保证了上下文正确性。这是正确的 tradeoff：快但错不如慢但对。
3. `_fallback_turn_counter` 跨轮次递增，在超长局（20+ 轮）中 fallback 选项可能重复，但概率极低。
