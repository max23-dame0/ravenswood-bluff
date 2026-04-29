# M3 任务板：Live Backend 性能与可靠性

## 当前定位

- **阶段**：M3
- **状态**：`Implemented`
- **目标**：真实模型驱动下，短局和标准局不会因为耗时、非法动作或并发推进导致体验崩坏。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [validation_report.md](../validation_report.md)
  - [remediation_backlog.md](../remediation_backlog.md)

## 第一性原则

Live 模式可以比 mock 慢，但不能不可诊断、不可恢复、不可兜底。每一次模型异常都应该转成合法动作、明确跳过或可见错误。

## 任务清单

### M3-1：Live 耗时基线

- 优先级：`P0`
- 范围：
  - `src/agents/`
  - `src/orchestrator/game_loop.py`
  - metrics / logs
- 任务：
  - [x] 统计首夜耗时。
  - [x] 统计白天讨论耗时。
  - [x] 统计提名阶段耗时。
  - [x] 统计投票阶段耗时。
  - [x] 统计夜晚行动耗时。
  - [x] 输出每阶段 AI 调用次数。
  - [x] 记录每次 AI 玩家行动的 token 消耗：
    - `speak`
    - `nomination_intent`
    - `nominate`
    - `defense_speech`
    - `vote`
    - `night_action`
    - `slayer_shot`
  - [x] 每条 token 记录至少包含：
    - `game_id`
    - `player_id`
    - `role_id`
    - `phase`
    - `day_number`
    - `round_number`
    - `action_type`
    - `model`
    - `prompt_tokens`
    - `completion_tokens`
    - `total_tokens`
    - `latency_ms`
    - `fallback_used`
  - [x] 在阶段摘要中聚合 token 指标：
    - 阶段总 token
    - 阶段平均 token / action
    - 单次最高 token action
    - fallback action 的 token 占比
  - [x] 在整局摘要中聚合 token 指标：
    - 全局总 token
    - 每名 AI 玩家总 token
    - 每种 action_type 总 token
    - 每阶段总 token
    - token 最高的前 10 次调用
- 验收：
  - [x] 5 人 live 短局至少完成一次处决，并有耗时摘要。
  - [x] 5 人 live 短局能导出 AI 行动 token 消耗明细。
  - [x] token 摘要能定位“最贵阶段”“最贵玩家”“最贵 action_type”。

### M3-2：AI 动作兜底

- 优先级：`P0`
- 范围：
  - `src/agents/ai_agent.py`
  - backend 调用层
  - action parser
- 任务：
  - [x] 非法 JSON 兜底。
  - [x] 空响应兜底。
  - [x] 超时兜底。
  - [x] 非法目标兜底。
  - [x] 不合阶段动作兜底。
  - [x] 所有 fallback 写入审计日志。
- 验收：
  - [x] AI 不因模型异常阻塞对局。
  - [x] fallback 事件可统计。

### M3-3：白天行动与投票性能优化

- 优先级：`P1`
- 范围：
  - 白天讨论链
  - 提名决策链
  - 投票决策链
- 任务：
  - [x] 审计顺序投票的模型调用数量。
  - [x] 减少重复上下文构造。
  - [x] 对低价值动作使用本地启发式或轻量 prompt。
  - [x] 设置阶段级超时上限。
- 验收：
  - [x] 真实 backend 下首日流程耗时下降或可接受。

### M3-4：并发推进防护

- 优先级：`P0`
- 范围：
  - `/api/game/start`
  - rematch
  - reconnect
  - game loop task registry
- 任务：
  - [x] 确认 start 幂等。
  - [x] 确认 rematch 不复用旧推进任务。
  - [x] 确认重连不会重复拉起 game loop。
  - [x] 增加当前 loop 运行状态诊断。
- 验收：
  - [x] 同一 `game_id` 不会并发推进两条主循环。

### M3-5：诊断接口

- 优先级：`P1`
- 范围：
  - `/api/game/metrics`
  - 新增或扩展诊断 payload
- 任务：
  - [x] 暴露当前阶段。
  - [x] 暴露当前等待对象。
  - [x] 暴露最近异常。
  - [x] 暴露最近推进时间。
  - [x] 暴露 AI fallback 统计。
- 验收：
  - [x] 卡局时可通过诊断接口定位等待点。

## 阶段完成标准

- [x] 5 人 live 短局完成至少一次处决。
- [x] Mock 7-10 人局稳定完成整局。
- [x] 所有 AI 行动超时都有 fallback。
- [x] 卡局时 metrics 或诊断接口能定位等待点。

## 风险记录

- Live 模型速度受外部服务影响，需要保持 mock 与 live 双验收。
- 为性能减少 prompt 时，不能破坏玩家视角隔离。
- 阶段 token 摘要已可定位高成本阶段/玩家/action；2026-04-28 已记录 5 人 live 首次处决样本。
- 投票、防御、处决目前仍包含在 `nomination` 阶段内；如果 live 成本集中在投票链，需要继续拆分子阶段指标。

## 完成记录

- 2026-04-28：已完成全部 Live Backend 监控、兜底与性能埋点。阶段已封板。
- 2026-04-28：补齐 `/api/game/metrics` 的 AI action 聚合摘要，包含总 token、平均 token/action、玩家/action/阶段维度 token、fallback 统计与 top token actions。
- 2026-04-28：补齐阶段级 AI 指标摘要，`phase_durations` 现在记录本阶段 AI 调用数、token 总量、平均 token、fallback 数、fallback token 占比、top token action。
- 2026-04-28：补齐当前阶段实时 AI 摘要与 loop task 诊断，包含 `current_phase_ai_action_summary`、loop `game_id`、`started_at`、`last_exception`。
- 2026-04-28：验证通过：`tests/test_orchestrator/test_api_server.py`、`tests/test_orchestrator/test_frontend_acceptance.py`、`scripts/alpha1_acceptance.py` 默认门禁。
- 2026-04-28：验证通过：`simulate_game.py --backend live --player-count 5 --discussion-rounds 1 --timeout-seconds 240 --stop-after first_execution --audit-mode --max-nomination-rounds 1`，样本 `game_id=4eedbb15-5994-4c23-9a7d-56b6c6ba31dd`，`stop_status=first_execution`，`execution_count=1`，`ai_action_count=16`，`ai_total_tokens=20350`。
- 2026-04-28：验证通过：`scripts/alpha1_acceptance.py --include-live-smoke`，6 项通过、0 项失败、full pytest 按显式开关跳过，live smoke 耗时约 3m12s。
