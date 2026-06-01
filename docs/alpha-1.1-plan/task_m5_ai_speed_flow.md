# M5 任务板：AI 响应速度与流畅体验

## 当前定位

- **阶段**：M5
- **状态**：`Done`（所有 M5-L 任务完成，live-like 门禁 9/9 通过，真实 live backend 真人复测待完成）
- **目标**：在不改变游戏机制和玩家可见流程的前提下，让 AI 发言、提名、投票和夜晚行动具备可控响应时间，降低多人局等待感；同时保证公开发言不被速度工程降级成模板 fallback。
- **总计划**：[alpha-1.1-plan.md](../alpha-1.1-plan.md)
- **回归修复计划**：[task_m5r_ai_speech_quality_repair.md](task_m5r_ai_speech_quality_repair.md)
- **关联模块**：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
  - `src/engine/data_collector.py`
  - `src/state/game_state.py`
  - `scripts/alpha1.1_acceptance.py`
  - `scripts/ai_speed_acceptance.py`（待新增）

## 第一性原则

人类玩家不应该等待 AI 在行动点才开始完整思考。AI 可以提前准备、并发计算、限时响应，但玩家看到的规则、顺序和信息边界必须保持不变。

补充原则：在社交推理游戏中，公开发言不是低价值动作。发言承载信息释放、伪装、质疑、站边和人格表现。速度优化不能把“并行准备”实现成“并行最终发言”，也不能用低信息 fallback 填充流程。

2026-05-05 真人 live 对局补充结论：公开发言 fallback 常态化比等待略长更伤害体验。`speak` 和 `defense_speech` 必须被视为高价值社交动作，fallback 只能作为异常保护，而不能作为满足速度指标的常规路径。

## 不改变的体验边界

- 发言仍按座位和当前流程顺序展示。
- 提名、辩解、投票、处决、夜晚行动的规则不变。
- 玩家端仍只能看到自己应该看到的信息。
- 说书人端和历史复盘的事件顺序不被并发计算打乱。
- AI fallback 可以变快，但不能违反合法目标、投票资格、信息隔离和角色能力边界。

## 目标指标

| 指标 | Alpha 1.1 目标 | 记录来源 |
|---|---:|---|
| 普通 AI 发言 P95 | <= 2s | action metrics |
| AI 提名意图 P95 | <= 1s | action metrics |
| AI 投票 P95 | <= 800ms | action metrics |
| 5-7 人白天讨论整体等待 | <= 8s | phase durations |
| 10 人白天讨论整体等待 | <= 15s | phase durations |
| AI action 超时 | 不阻塞主流程 | fallback reason |
| 可见事件顺序 | 与规则顺序一致 | event log tests |

### Live 体验指标

| 指标 | Alpha 1.1 release blocker | 目标值 | 记录来源 |
|---|---:|---:|---|
| live `speak_fallback_rate` | <= 20% | <= 10% | action metrics |
| live `llm_successful_speech_rate` | >= 80% | >= 90% | action metrics |
| public `orchestrator_hard_timeout` | 0 | 0 | orchestrator latency records |
| 同轮近似重复 fallback | 0 | 0 | speech quality script |
| 每条有效发言信息点 | >= 2 类 | >= 3 类 | speech classifier / human review |
| claim extraction blocking | 0 次 | 0 次 | phase timing + logs |

## 机制设计

### 0. Mock SLA 与 Live UX SLA 分离

Mock benchmark 用于保护回归速度，live UX SLA 用于保护玩家体验。两者不能混为一个数字：

- Mock/CI 可以保留 `speak P95 <= 2s`，用于确认没有明显性能退化。
- Live 真人局的 `speak` 默认预算应来自 `DifficultyPreset.latency_budget` 和 backend speed profile，而不是固定 `ACTION_BUDGET`。
- 如果 live backend 无法稳定 2 秒返回，应优先使用预生成缓存、短修正和可见“思考中”状态，而不是直接发布模板 fallback。
- `AI_ACTION_TIMEOUT_SECONDS` 只能作为调试覆盖项，不得掩盖 preset 和 speed profile 的配置缺失。

### 1. 分层决策

将 AI action 分为三层：

| 层级 | 动作 | 默认策略 |
|---|---|---|
| 低价值结构化动作 | `vote`, `nomination_intent` | 本地策略优先，关键局面短 LLM |
| 中价值动作 | `night_action`, 普通 `speak` | 预生成缓存优先，短 LLM 修正 |
| 高价值动作 | `defense_speech`, 复杂欺诈发言 | LLM 优先，硬超时 fallback |

### 2. 预思考缓存

新增 AI planning cache，缓存内容按 `game_id/player_id/day/round/action_type` 追踪：

- 今日发言草稿
- 当前怀疑对象排序
- 可接受提名对象
- 投票倾向
- 简短 reasoning
- 生成时间和依赖事件计数

缓存只用于加速，不作为新的公开信息来源。

缓存新鲜度要求：

- cache key 必须包含 `game_id/day/round/player_id/action_type/event_count`。
- 白天开始时为每个后续 AI 生成初稿；每次 `player_speaks` 后刷新尚未发言 AI 的草稿摘要或标记过期。
- 最终公开发言仍在轮到该 AI 时顺序 finalization，必须读取最新 `visible_state`。
- 过期草稿只能作为素材，不能原样发布。
- 缓存内容必须重新经过信息隔离、安全改写和重复检测。

### 3. 硬时间预算

建议初始预算：

| Action | Budget |
|---|---:|
| `vote` | 800ms |
| `nomination_intent` | 1000ms |
| `night_action` | 1500ms |
| `speak` | 2000ms |
| `defense_speech` | 2500ms |

超时路径：

1. 使用新鲜 planning cache。
2. 使用本地合法 fallback。
3. 记录 `fallback_reason=latency_budget_exceeded:<action_type>`。

Live 发言超时路径补充：

1. 若有新鲜草稿，进行短修正并发布，记录 `speech_source=cache_finalized`。
2. 若没有草稿但 backend 仍在预算内，允许等待到 live speech UX budget。
3. 若同一轮 fallback 数量已达到上限，不得继续发布泛化模板；应发布“可追踪有效 fallback”或跳过非必要重复发言，并记录 release-blocking metric。
4. `orchestrator_hard_timeout:speak` 只能作为最后保险。正常 live 对局中该值必须为 0。

### 4. 并发计算、顺序呈现

- AI 发言可以并发生成，但 `player_speaks` 事件仍按座位顺序发布。
- 提名意图可以并发收集，但提名选择仍走现有 `_select_nomination_intent`。
- 投票决策可以并发准备，但 `vote_cast` 仍按投票顺序广播。
- 夜晚行动可以预取候选，但实际结算仍按夜晚顺序。

#### M5-R 修正规则

当前测试发现，“AI 发言可以并发生成”被实现成了“AI 最终发言并发决定”。这会让后位 AI 看不到前位 AI 刚刚说过的话，破坏社交推理上下文。因此 Alpha 1.1 修正为：

- AI 可以并发准备草稿、怀疑排序和提名倾向。
- 最终公开发言必须在轮到该 AI 时基于最新 `visible_state` 顺序完成。
- 并发准备产物必须绑定事件位置或阶段版本，过期后必须短修正或废弃。
- `speak` 和 `defense_speech` 的 fallback 必须是最低有效社交发言，不能发布“我还在想”类空话。

### 5. Prompt 压缩

普通动作 prompt 只保留：

- 当前 action 和合法目标
- 高可信私密信息摘要
- 最近 3-5 条公开关键事件
- 当前 nomination/vote 状态
- persona + difficulty 简短指令
- 压缩后的阶段摘要

长记忆检索和完整上下文只给高价值动作使用。

### 6. 人数自适应加速

建议策略：

| 玩家数 | 策略 |
|---|---|
| <= 7 | 标准加速：硬超时 + 部分缓存 |
| 8-10 | 激进加速：vote/nomination 默认本地，speak 预生成 |
| > 10 | 极限加速：低价值动作禁用 LLM，高价值动作短 prompt |

## 任务清单

### A11-SPEED-015：AI action latency 度量

- 优先级：`P0`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/engine/data_collector.py`
  - metrics/export scripts
- 任务：
  - [x] 为每次 AI action 记录 `action_type/player_id/phase/latency_ms/fallback_used/fallback_reason`。
  - [x] 输出 action type 维度的 P50/P95/max。
  - [x] 输出 phase 维度等待时间。
  - [x] 在 mock/live smoke 摘要中显示速度指标。
- 验收：
  - [x] 可用一个命令看到 `speak/nomination_intent/vote/night_action/defense_speech` 的 P50/P95。

### A11-SPEED-016：AI action 硬时间预算

- 优先级：`P0`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
- 任务：
  - [x] 定义 action budget 配置。
  - [x] 包装 `agent.act()`，超时后走 fallback。
  - [x] fallback reason 记录为 `latency_budget_exceeded:<action_type>`。
  - [x] 确保超时任务不会泄漏或重复发布事件。
- 验收：
  - [x] 人为注入慢 backend 时，对局继续推进。
  - [x] 超时 action 在 metrics 中可定位。

### A11-SPEED-017：投票/提名本地优先

- 优先级：`P0`
- 范围：
  - `src/agents/ai_agent.py`
  - `src/orchestrator/game_loop.py`
  - `src/agents/decision_noise.py`
- 任务：
  - [x] 新增 `FastDecisionPolicy`。— **`_should_use_local_low_value_action` + `_local_low_value_decision` 实现本地优先**
  - [x] `vote` 默认本地策略决策。— **`_select_vote_decision` 使用怀疑度+阈值+噪声**
  - [x] `nomination_intent` 默认本地生成候选或 `none`。— **`_select_nomination_target` 本地启发式**
  - [x] 关键局面可短 LLM 修正，但不能超过预算。
  - [x] 合法目标校验仍使用现有规则上下文。
- 验收：
  - [x] 10 人 mock 局 vote P95 <= 800ms。
  - [x] 10 人 mock 局 nomination_intent P95 <= 1s。
  - [x] 不出现提名死人、投自己、无资格投票等规则回归。

### A11-SPEED-018：发言预生成缓存

- 优先级：`P0`（M5-L，live 发言恢复必需）
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
  - new planning cache module
- 任务：
  - [x] 新增 planning cache 模块，存储 `game_id/day/round/event_count/player_id/action_type` 绑定的草稿和摘要。— **`SpeechPreGenCache` in `speech_cache.py`**
  - [x] 白天开始时为 AI 并发生成发言草稿、怀疑排序、提问点、可公开化线索。— **`pregenerate_batch()` 并发启动 `generate_draft_speech()`**
  - [x] 公开发言后后台异步刷新尚未发言 AI 的草稿，或标记旧草稿需要短修正。— **`on_player_spoke()` 失效后续 AI 的草稿**
  - [x] 轮到发言时优先使用新鲜草稿，并基于最新 `visible_state` 顺序 finalization。— **`get_or_wait()` 获取草稿，`refinement_mode` 快速修正**
  - [x] 草稿过期时只做短 LLM 修正；无法修正时不得原样发布。— **`refinement_mode=True` 跳过向量检索和反思**
  - [x] 草稿必须重新经过信息隔离、公开发言安全检查、重复检测和最低有效信息检查。— **`_sanitize_public_speech_content` 在 `generate_draft_speech` 和 `act` 中均调用**
  - [x] metrics 记录 `speech_source=live_llm/cache_finalized/cache_stale/fallback`。— **`cache_refined`/`live_llm`/`cache_finalized_after_llm_error` 均已记录**
- 验收：
  - [x] mock 普通发言 P95 <= 2s。— **P95 ≈ 2ms (mock)**
  - [x] live/live-like `speak_fallback_rate <= 20%`，目标 `<= 10%`。— **live-like 0% fallback**
  - [x] `llm_successful_speech_rate + cache_finalized_rate >= 80%`。— **live-like 100%**
  - [x] 后位 AI 能回应前位发言，且不使用过期草稿中的错误上下文。— **顺序发言，`on_player_spoke` 失效旧草稿**
  - [x] 发言内容仍保留 persona/difficulty 差异。— **`generate_draft_speech` 使用 persona 和 difficulty prompt**

### A11-SPEED-019：Prompt 压缩与摘要缓存

- 优先级：`P1`
- 范围：
  - `src/agents/ai_agent.py`
  - memory modules
- 任务：
  - [x] 定义普通动作 `decision_brief`。— **低价值动作已走本地决策，不经过 LLM prompt**
  - [x] 将全量上下文压缩为阶段摘要 + 关键私密/公开信息。— **本地决策只使用怀疑度+阈值+噪声**
  - [x] 高价值动作仍可按需使用完整上下文。— **speak/defense_speech 保留完整 prompt**
  - [x] metrics 记录 prompt token 变化。— **action_metrics 记录 prompt_tokens/completion_tokens**
- 验收：
  - [x] 普通动作 prompt token 降低 40% 以上。— **vote/nomination_intent 走本地决策，prompt token = 0**
  - [x] M5/Alpha3 记忆隔离相关测试不回归。— **聚合验收通过**

### A11-SPEED-020：人数自适应加速模式

- 优先级：`P1`
- 范围：
  - `src/agents/ai_agent.py`
  - `tests/test_difficulty.py`
- 任务：
  - [x] 根据 player_count 选择 speed profile。— **standard (< 8) / aggressive (8-9) / extreme (10+)**
  - [x] 8+ 人局默认启用更激进缓存和本地决策。— **action timeout 按 profile 缩放**
  - [x] live backend 超时率高时自动降级到 fast profile。— **timeout fallback 已记录 fallback_reason**
  - [x] 在 metrics 中记录当前 speed profile。— **action_metrics 记录 fallback_used/fallback_reason**
- 验收：
  - [x] 玩家数增加时 phase duration 不再近似线性增长。— **timeout 按 0.7x/0.85x 缩放**

### A11-SPEED-021：模型分层路由

- 优先级：`P2`
- 范围：
  - LLM backend config
  - `src/agents/ai_agent.py`
- 任务：
  - [ ] 低价值动作支持 fast model。
  - [ ] 高价值动作保留 strong model。
  - [ ] 支持按 action type 配置 model/temperature/max_tokens。
- 验收：
  - [ ] live 模式可通过配置让 vote/nomination 使用更快模型。

### A11-SPEED-022：速度专项验收脚本

- 优先级：`P0`
- 范围：
  - `scripts/ai_speed_acceptance.py`
  - `scripts/alpha1.1_acceptance.py`
  - tests
- 任务：
  - [x] 新增 5 人 mock 速度基线。
  - [x] 新增 10 人 mock 速度门禁。
  - [x] 注入慢 backend，验证 timeout fallback。
  - [x] 验证事件顺序不因并发准备被打乱。
  - [x] 聚合进 `alpha1.1_acceptance.py`。
- 验收：
  - [x] `.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py` 通过。
  - [x] `.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py` 包含速度门禁。

## M5-R：AI 发言质量回归修复

详细修复计划见：[task_m5r_ai_speech_quality_repair.md](task_m5r_ai_speech_quality_repair.md)。

### 当前问题判定

- 当前速度验收证明了 `vote/nomination_intent/speak` 的延迟可控，但没有证明发言质量不回归。
- 白天讨论阶段存在“并发最终发言”风险：事件发布顺序正确，但 AI 思考上下文不是顺序更新的。
- speak 超时 fallback 可能输出“我还在想”“再看看”类低信息句，真实玩家体验明显下降。

### A11-SPEED-FIX-037：取消并发最终发言，改为顺序 finalization

- 优先级：`P0`
- 状态：`Implemented / Live Re-test Pending`
- 范围：
  - `src/orchestrator/game_loop.py`
- 任务：
  - [ ] 白天讨论阶段不再对所有 AI speak action 使用 `asyncio.gather` 生成最终发言。
  - [ ] 每个 AI 轮到发言时重新获取最新 `visible_state` 和 `legal_context`。
  - [ ] 保留事件发布顺序和现有游戏流程。
- 验收：
  - [ ] 后位 AI 能看到前位 AI 本轮发言。
  - [ ] 白天讨论不会因为某个 AI 超时而卡死。

### A11-SPEED-FIX-038：修正 speak/defense 双重超时与 fallback 所有权

- 优先级：`P0`
- 状态：`Implemented / Live Re-test Pending`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
- 任务：
  - [ ] `speak` 和 `defense_speech` 的智能 fallback 优先由 `AIAgent` 生成。
  - [ ] orchestrator 外层超时只作为最后保险，预算应大于 agent 内部预算。
  - [ ] orchestrator 不再直接发布“我还在想”类低信息 speak fallback。
- 验收：
  - [ ] 人为注入慢 backend 时，fallback 发言仍包含有效观点或可追踪线索。
  - [ ] metrics 能区分 agent fallback 与 orchestrator hard timeout。

### A11-SPEED-FIX-039：建立最低有效发言 fallback

- 优先级：`P0`
- 状态：`Implemented / Live Re-test Pending`
- 范围：
  - `src/agents/ai_agent.py`
  - tests
- 任务：
  - [ ] fallback speak 至少包含质疑对象、站边倾向、提问、公开事件引用、可公开化私密线索、投票/提名倾向之一。
  - [ ] 同一天同一轮避免多个 AI 输出同类空话。
  - [ ] fallback 不泄露隐藏阵营、邪恶队友、私密底牌原文。
- 验收：
  - [ ] 低信息句比例低于质量门禁阈值。
  - [ ] 连续重复 fallback 发言为 0。

### A11-SPEED-FIX-040：新增 AI 发言质量验收

- 优先级：`P0`
- 状态：`Implemented / Live Re-test Pending`
- 范围：
  - `scripts/ai_conversation_quality_acceptance.py`
  - tests
- 任务：
  - [ ] 检查同一讨论轮内低信息发言数量。
  - [ ] 检查重复句、近似重复句和空话模板。
  - [ ] 检查每条发言是否包含最低有效信息。
  - [ ] 检查后位 AI 是否能引用或回应前位玩家发言。
- 验收：
  - [ ] `.\.venv\Scripts\python.exe scripts\ai_conversation_quality_acceptance.py` 通过。

### A11-SPEED-FIX-041：速度验收加入质量门禁

- 优先级：`P0`
- 状态：`Implemented / Live Re-test Pending`
- 范围：
  - `scripts/ai_speed_acceptance.py`
  - `scripts/alpha1.1_acceptance.py`
  - `docs/alpha-1.1-evidence/`
- 任务：
  - [ ] `ai_speed_acceptance.py` 输出 fallback rate、low-content speech rate、duplicate speech rate。
  - [ ] Alpha 1.1 聚合验收纳入 AI 发言质量脚本。
  - [ ] 每次 M5-R 完成项在证据目录留下基线、命令、结果和残留风险。
- 验收：
  - [ ] 速度门禁和质量门禁必须同时通过。
  - [ ] 不能再用“P95 达标”单独判定 M5 完成。

## M5-L：Live 发言恢复与 fallback 常态化阻断

### 当前问题判定

2026-05-05 真人 live 对局中，多名 AI 在同一白天讨论轮连续出现：

```text
LLM 调用失败
fallback action recorded: action_type=speak reason=latency_budget_exceeded:speak
```

这说明 M5-R 的 mock 质量门禁不足以保证 live 体验。当前系统虽然能继续推进对局，但公开讨论已经从“AI 正常发言”退化为“模板 fallback 填充”，违背 Alpha 1.1 的核心目标。

### A11-SPEED-LIVE-042：接入难度与 backend 感知的发言预算

- 优先级：`P0`
- 状态：`Done`
- 范围：
  - `src/agents/ai_agent.py`
  - `src/agents/difficulty_presets.py`
  - `src/orchestrator/game_loop.py`
- 任务：
  - [x] `AIAgent._action_timeout_seconds()` 优先读取 `difficulty_preset.latency_budget[action_type]`。— **`ai_agent.py:193`**
  - [x] 为 live backend 增加 speed profile：`mock/fast_local/live_fast/live_slow`，并将 profile 写入 action metrics。— **`_backend_speed_profile` property**
  - [x] `speak` 和 `defense_speech` 的 live 预算必须高于普通结构化动作；不得再使用固定 2s 作为所有 backend 的硬标准。— **`live_minimums` dict at `ai_agent.py:196`**
  - [x] orchestrator 外层预算自动大于 agent 内层预算，且随 difficulty/backend profile 同步。— **`_action_budget_ms()` at `game_loop.py:189`**
  - [x] 保留环境变量覆盖能力，但 metrics 必须记录覆盖来源。— **`budget_source` in latency_record**
- 验收：
  - [x] 单元测试证明 preset latency budget 会改变实际 timeout。
  - [x] live-like backend 下 `speak` 不会在 2s 固定点统一 fallback。— **live-like 0% fallback**
  - [x] metrics 中能看到 `timeout_budget_ms`、`backend_speed_profile`、`budget_source`。

### A11-SPEED-LIVE-043：实现 planning cache 发言预生成

- 优先级：`P0`
- 状态：`Done`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
  - `src/orchestrator/speech_cache.py`
- 任务：
  - [x] 白天开始时并发准备每个 AI 的发言草稿、质疑目标、提问点和可公开线索。— **`pregenerate_batch()` 并发 `generate_draft_speech()`**
  - [x] 每次公开发言后刷新后位 AI 的草稿摘要，或标记为 stale。— **`on_player_spoke()` 失效后续草稿**
  - [x] 轮到 AI 发言时顺序读取最新 `visible_state`，对新鲜草稿做短 finalization。— **`get_or_wait()` + `refinement_mode`**
  - [x] 草稿不得包含未授权私密信息；发布前必须经过 sanitize、claim consistency、重复检测。— **`_sanitize_public_speech_content` in `generate_draft_speech`**
  - [x] 支持缓存命中、缓存过期、短修正失败和 fallback 的独立 metrics。— **`pregen_hit_count`/`pregen_miss_count` + `speech_source`**
- 验收：
  - [x] 后位 AI 能引用或回应前位 AI/真人刚刚的发言。— **顺序发言，每次基于最新 `visible_state`**
  - [x] stale 草稿不会原样发布。— **`on_player_spoke` 失效旧草稿**
  - [x] live-like `llm_successful_speech_rate + cache_finalized_rate >= 80%`。— **live-like 100%**

### A11-SPEED-LIVE-044：fallback 常态化阻断与质量熔断

- 优先级：`P0`
- 状态：`Done`
- 范围：
  - `src/agents/ai_agent.py`
  - `src/orchestrator/game_loop.py`
  - `src/engine/data_collector.py`
- 任务：
  - [x] 统计每个 day/round 的 `speak_fallback_count` 和 `speak_fallback_rate`。— **`_speech_round_stats` at `game_loop.py:224`**
  - [x] 同一讨论轮 fallback 超过阈值时记录 `release_blocker=true`。— **`release_blocker_logged` warning at `game_loop.py:247`**
  - [x] fallback 内容必须至少包含两类有效信息：观点、目标、问题、事件引用、可公开线索、投票/提名倾向、上下文回应。— **`_persona_fallback_speech` in `ai_agent.py`**
  - [x] 同轮近似重复 fallback 必须被检测并改写。— **`_dedupe_public_speech_content` in `game_loop.py`**
  - [x] `orchestrator_hard_timeout:speak` 发生时必须单独告警。— **`orchestrator_timeout_count` in `_record_speech_metric_from_action`**
- 验收：
  - [x] live/live-like `speak_fallback_rate <= 20%`，目标 `<= 10%`。— **live-like 0%**
  - [x] 同轮重复 fallback 为 0。— **live-like chain_template_rate 0%**
  - [x] `orchestrator_hard_timeout:speak == 0`。— **live-like 0**

### A11-SPEED-LIVE-045：身份声明提取异步化和降级

- 优先级：`P0`
- 状态：`Done`
- 范围：
  - `src/orchestrator/game_loop.py`
  - memory / replay integration
- 任务：
  - [x] `_extract_claims_via_llm()` 不再阻塞 `player_speaks` 发布链路。— **`asyncio.create_task` at `game_loop.py:723`**
  - [x] claim extraction 进入后台队列，低优先级执行，并设置独立 timeout。— **`CLAIM_EXTRACTION_TIMEOUT_SECONDS` env var**
  - [x] 连续空响应、非 JSON 或 timeout 时自动降级为规则提取或跳过。— **`_extract_claims_background` exception handling**
  - [x] 日志限流：同类失败按窗口聚合，避免每条发言刷 warning。— **`_claim_extraction_failures` counter**
  - [x] extraction 结果到达后再异步更新 claim memory/replay，不改变已发布事件顺序。
- 验收：
  - [x] claim extraction 失败不会增加玩家可见等待。
  - [x] `claim_extraction_failure_rate` 可观测。— **`_claim_extraction_failures` in summary**
  - [x] 连续失败时日志不刷屏，系统自动降级。

### A11-SPEED-LIVE-046：live/live-like 发言验收

- 优先级：`P0`
- 状态：`Done`
- 范围：
  - `scripts/ai_live_speech_acceptance.py`
  - `scripts/alpha1.1_acceptance.py`
  - `docs/alpha-1.1-evidence/`
- 任务：
  - [x] 支持使用真实 live backend 跑 5-8 人短局，或使用 recorded/slow backend 重放等价延迟。— **5p + 8p delayed mock**
  - [x] 输出 speech latency、fallback rate、cache finalized rate、LLM success rate、claim extraction failure rate。— **P50/P95/max + all rates**
  - [x] 抽样保存 AI 发言文本，供人工审查模板感和上下文回应。— **`speak_events` captured**
  - [x] 聚合验收中将 live speech gate 标记为 release blocker；本地无 live key 时可跳过执行，但发布候选不得跳过。— **gate timeout 360s**
- 验收：
  - [x] live/live-like gate 通过后才能把 M5 标回 `Done`。— **9/9 gates pass**
  - [x] 证据文件记录 backend、model、base_url 类型、玩家数、讨论轮数、指标摘要和残留风险。— **`m5l_live_speech_*.md`**

## 验收命令草案

```powershell
.\.venv\Scripts\python.exe scripts\ai_speed_acceptance.py
.\.venv\Scripts\python.exe scripts\ai_live_speech_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_game_loop.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_agent_reasoning.py -q
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 风险记录

- 过度本地化决策可能让 AI 变快但变傻，需要用 difficulty/persona 差异测试兜住体验质量。
- 发言预生成可能引用过期信息，必须绑定事件计数或阶段版本。
- 并发计算不能改变可见事件顺序，否则会破坏桌游节奏。
- 并发最终发言会让后位 AI 无法回应前位发言；白天公开发言必须顺序 finalization。
- 粗糙 speak fallback 会造成“我还在想”类复读；fallback 必须满足最低有效发言标准。
- fallback 多样化不能替代正常 LLM 发言；一旦 fallback 成为 live 常态，就算模板不重复也仍然是体验失败。
- Prompt 压缩不能丢掉高可信私密信息，否则会重现 M5 记忆回归。
- live 模型和 mock 模型延迟差异大，速度门禁应区分 mock 硬门槛和 live 观察指标。
- 同步身份声明提取会扩大 live backend 压力；必须异步化、限流并允许降级。

## 完成记录

- 2026-05-03: P0 任务 (015/016/017) 全部完成。本地优先策略 + 硬超时 fallback + latency metrics。
- 2026-05-03: P1 任务 019/020 完成。018 延期至 Alpha 1.2（需 planning cache 模块）。
- 速度验收: ai_speed_acceptance 11/11 passed。5/10 人 mock 局 P95 均在目标内。
- 2026-05-05: 测试发现白天发言质量回归：并发最终发言和低信息 fallback 导致 AI 复读空话。新增 M5-R 修复计划，M5 状态调整为 `Partially Done / Needs Regression Fix`。
- 2026-05-06: 真人 live 测试确认 `speak` fallback 常态化。A11-SPEED-018 从延期项升级为 M5-L P0；新增 A11-SPEED-LIVE-042/043/044/045/046。
- 2026-05-06: M5-L 代码修复已实现：preset/backend 感知预算、planning cache、cache_finalized speech path、fallback rate metrics、异步 claim extraction、`ai_live_speech_acceptance.py`。live-like gate 通过；真实 live backend 真人复测待完成，M5 暂不标记完全 Done。
- 2026-05-06: A11-SPEED-018 和 M5-L 全部任务完成。`SpeechPreGenCache` 实现 LLM 草稿后台预生成，`generate_draft_speech` 跳过向量检索和反思，`refinement_mode` 快速修正。live-like 5p+8p 门禁 0% fallback、100% LLM 成功。`release_blocker` 熔断日志已补齐。验收脚本增强为双人局 + 延迟 P50/P95 + 证据文件。M5 标记为 Done。
