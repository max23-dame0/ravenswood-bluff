# M5-R 修复计划：AI 发言质量回归与并行机制纠偏

## 背景

当前 Alpha 1.1 速度工程已经显著降低了部分 action 的等待时间，但测试中出现了 AI 多次输出“我还在想”“再看看”一类低信息发言的问题。该现象说明当前并行与 fallback 机制在白天讨论阶段破坏了原本的社交推理表现。

M5-R 的目标不是回退速度优化，而是纠正实现边界：让 AI 更快，同时保留智能性、人格表现、上下文反应和游戏性。

## 现象

- 多名 AI 在同一轮白天讨论中输出近似空话。
- 后位 AI 没有明显回应前位玩家刚刚说过的话。
- 速度验收通过，但真实对局体验下降。
- 并行机制保持了“事件发布顺序”，却没有保持“思考上下文顺序”。

## 根因判断

### R1：并行最终发言破坏上下文

`_run_day_discussion()` 当前把多个 AI speak action 同时启动，再按座位顺序发布结果。这样虽然 UI 事件顺序正确，但所有 AI 的发言都基于同一份旧 `visible_state`，无法吸收前面玩家刚发布的内容。

结论：白天发言不能并行最终决定。可以并行准备，但最终发言必须在轮到该 AI 时基于最新状态完成。

### R2：speak 双重超时导致低质量 fallback 抢先发布

当前 orchestrator 和 `AIAgent` 都有超时控制。外层超时一旦先触发，会直接使用 orchestrator 的粗糙 speak fallback，例如“我还在想”，导致 agent 内部更像真人的 fallback 没有机会执行。

结论：speak/defense 的 fallback 所有权应主要归 `AIAgent`，orchestrator 只做最后保险。

### R3：速度验收缺少内容质量门禁

`ai_speed_acceptance.py` 当前主要证明 P50/P95、fallback 和事件顺序，没有证明发言仍具备有效信息、上下文反应和非重复性。

结论：速度门禁必须绑定质量门禁。只快不够，快且不变傻才算通过。

## 第一性原则

在社交推理游戏中，发言不是低价值动作。发言承载：

- 信息释放。
- 伪装与欺诈。
- 质疑与站边。
- 对前序发言的回应。
- 人格和难度表现。

因此 Alpha 1.1 的速度优化必须遵守：

- 可以并行准备，不能并行最终发言。
- 可以限时响应，不能用低信息废话填充流程。
- 可以压缩 prompt，不能丢失最近公开发言。
- 可以让投票/提名本地优先，但公开发言必须保留社交智能。
- 玩家看到的规则和流程不变，AI 内部必须在轮到自己时基于最新局势作最终裁决。

## 修复目标

把当前机制从：

```text
AI 同时决定发言 -> 按顺序播放 -> 超时说空话
```

修正为：

```text
AI 可提前准备草稿 -> 轮到自己时读取最新局势 -> 快速完成最终发言 -> fallback 也必须是最低有效社交发言
```

## 任务列表

### A11-SPEED-FIX-037：取消并发最终发言，改为顺序 finalization

- 状态：`Done`
- 优先级：`P0`
- 范围：
  - `src/orchestrator/game_loop.py`
- 任务：
  - [x] 白天讨论阶段不再对所有 AI speak action 使用 `asyncio.gather` 生成最终发言。
  - [x] 每个 AI 轮到发言时重新获取最新 `visible_state` 和 `legal_context`。
  - [x] 发布一名 AI 发言后，再让下一名 AI 决定发言。
  - [x] 保留事件顺序与现有游戏流程。
- 验收：
  - [x] 后位 AI 的 prompt/visible state 包含前位 AI 本轮发言。
  - [x] `player_speaks` 事件顺序仍按座位顺序。
  - [x] 白天讨论不会因为某个 AI 超时而卡死。

### A11-SPEED-FIX-038：修正 speak/defense 双重超时与 fallback 所有权

- 状态：`Done`
- 优先级：`P0`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/ai_agent.py`
- 任务：
  - [x] `speak` 和 `defense_speech` 的智能 fallback 优先由 `AIAgent` 生成。
  - [x] orchestrator 外层超时只作为最后保险，预算应大于 agent 内部预算。
  - [x] orchestrator 不再直接发布”我还在想”类低信息 speak fallback。
  - [x] fallback reason 能区分 `agent_latency_fallback` 与 `orchestrator_hard_timeout`。
- 验收：
  - [x] 人为注入慢 backend 时，fallback 发言仍包含有效观点或可追踪线索。
  - [x] metrics 能看出 fallback 来源。

### A11-SPEED-FIX-039：建立最低有效发言 fallback

- 状态：`Done`
- 优先级：`P0`
- 范围：
  - `src/agents/ai_agent.py`
  - tests
- 任务：
  - [x] fallback speak 至少包含以下之一：质疑对象、站边倾向、提问、公开事件引用、可公开化私密线索、投票/提名倾向。
  - [x] 同一天同一轮避免多个 AI 输出同类空话。
  - [x] fallback 不泄露隐藏阵营、邪恶队友、私密底牌原文。
  - [x] fallback 仍保留 persona 和 difficulty 的基本差异。
- 验收：
  - [x] 低信息句比例低于质量门禁阈值。
  - [x] 连续重复 fallback 发言为 0。
  - [x] 信息隔离测试不回归。

### A11-SPEED-FIX-040：新增 AI 发言质量验收

- 状态：`Done`
- 优先级：`P0`
- 范围：
  - `scripts/ai_conversation_quality_acceptance.py`
  - tests
- 任务：
  - [x] 检查同一讨论轮内低信息发言数量。
  - [x] 检查重复句、近似重复句和空话模板。
  - [x] 检查每条发言是否包含最低有效信息。
  - [x] 检查后位 AI 是否能引用或回应前位玩家发言。
  - [x] 检查发言质量门禁与信息隔离门禁同时通过。
- 验收：
  - [x] `.\.venv\Scripts\python.exe scripts\ai_conversation_quality_acceptance.py` 通过。

### A11-SPEED-FIX-041：速度验收加入质量门禁

- 状态：`Done`
- 优先级：`P0`
- 范围：
  - `scripts/ai_speed_acceptance.py`
  - `scripts/alpha1.1_acceptance.py`
  - `docs/alpha-1.1-evidence/`
- 任务：
  - [x] `ai_speed_acceptance.py` 输出 fallback rate、low-content speech rate、duplicate speech rate。
  - [x] Alpha 1.1 聚合验收纳入 AI 发言质量脚本。
  - [x] 每次 M5-R 完成项在证据目录留下基线、命令、结果和残留风险。
- 验收：
  - [x] 速度门禁和质量门禁必须同时通过。
  - [x] 不能再用”P95 达标”单独判定 M5 完成。

## 推荐实现顺序

1. 先做 A11-SPEED-FIX-037，恢复白天讨论的真实上下文顺序。
2. 再做 A11-SPEED-FIX-038 与 A11-SPEED-FIX-039，保证超时时仍有最低有效社交发言。
3. 然后做 A11-SPEED-FIX-040，把玩家看到的问题变成自动化可测问题。
4. 最后做 A11-SPEED-FIX-041，把质量门禁接回 Alpha 1.1 聚合验收。

## 完成标准

M5-R 完成后，必须同时满足：

- AI 发言不再集中复读“我还在想/再看看/听大家说”类空话。
- 后位 AI 能基于前位发言作出反应。
- 白天讨论顺序、规则、信息边界不变。
- 多人局等待时间仍受控。
- 速度指标和发言质量指标同时通过。
