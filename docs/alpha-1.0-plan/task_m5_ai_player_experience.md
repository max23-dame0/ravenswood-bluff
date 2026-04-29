# M5 任务板：AI 玩家内测体验

## 当前定位

- **阶段**：M5
- **状态**：`Implemented`
- **目标**：AI 玩家足够稳定、可区分、可一起玩，而不是只在技术演示中成立。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [alpha-0.3-plan/full_plan.md](../alpha-0.3-plan/full_plan.md)
  - [alpha-0.3-plan/task_data.md](../alpha-0.3-plan/task_data.md)
  - [validation_report.md](../validation_report.md)

## 第一性原则

AI 玩家在内测局里首先要像可靠玩家：能说、能投、能提名、不卡流程、不泄露真相。人格和推理增强必须建立在合法动作与节奏稳定之上。

## 任务清单

### M5-1：Persona 差异增强

- 优先级：`P1`
- 范围：
  - `src/agents/ai_agent.py`
  - `src/agents/base_agent.py`
  - persona 配置
- 任务：
  - [x] 定义发言风格差异。
  - [x] 定义提名倾向差异。
  - [x] 定义投票偏好差异。
  - [x] 定义风险偏好差异。
  - [x] 避免所有 AI 使用同一套公开模板。
- 验收：
  - [x] 同一局不同 AI 的发言、提名、投票倾向可识别。

### M5-2：同质化行为限制

- 优先级：`P1`
- 范围：
  - AI 决策策略
  - nomination / vote heuristics
- 任务：
  - [x] 限制连续积极提名。
  - [x] 限制无意义跟票。
  - [x] 限制重复模板发言。
  - [x] 增加“观望 / 保留意见 / 防守”行为比例。
- 验收：
  - [x] mock 局中白天行为不再明显机械重复。

### M5-3：高可信信息公开表达边界

- 优先级：`P0`
- 范围：
  - memory summaries
  - speak / nominate / vote reason builder
- 任务：
  - [x] 高可信信息能进入公开表达。
  - [x] 私密信息表达符合角色视角。
  - [x] 邪恶队友、魔典、说书人内部裁量不得泄露。
  - [x] 公开表达可解释但不过度暴露推理底牌。
- 验收：
  - [x] AI 公开发言不泄露隐藏真相。

### M5-4：行为节奏控制

- 优先级：`P1`
- 范围：
  - day discussion
  - chat emission
  - action scheduling
- 任务：
  - [x] 控制单阶段发言量。
  - [x] 避免连续刷屏。
  - [x] 真人等待时避免 AI 抢阶段。
  - [x] 长时间无响应时明确 fallback。
- 验收：
  - [x] AI 不会因模型异常阻塞对局。
  - [x] 真人玩家有稳定操作窗口。

### M5-5：AI 行为审计样本

- 优先级：`P2`
- 范围：
  - exported traces
  - sample reports
- 任务：
  - [x] 导出一局 AI 行为样本。
  - [x] 汇总发言、提名、投票、fallback 统计。
  - [x] 记录明显同质化或异常行为。
- 验收：
  - [x] 形成可复查 AI 行为样本报告。

## 阶段完成标准

- [x] 同一局中不同 AI 的发言与投票倾向可识别。
- [x] AI 非法动作率可统计并低于内测阈值。
- [x] AI 不会因为模型异常阻塞对局。
- [x] AI 公开发言不泄露隐藏真相。

## 风险记录

- Persona 增强不能覆盖规则兜底。
- 公开表达私密信息时需要严格区分“玩家知道”和“系统知道”。

## 完成记录

- 2026-04-28：补齐公开发言安全边界：私密信息和邪恶队友/伪装池仍可参与内部推理与打分，但公开 `content` 只输出含蓄转述或公开可说信息。
- 2026-04-28：新增 M5 回归测试，覆盖信息位私密结果不原文泄露、邪恶阵营不公开泄露队友名单/`bluff`/魔典类信息。
- 2026-04-28：新增 `scripts/m5_ai_player_experience_acceptance.py`，串联 persona/reasoning 回归、AI evaluation 指标与 fallback 探针，并生成 [alpha-1.0-ai-behavior-sample.md](../alpha-1.0-ai-behavior-sample.md)。
- 2026-04-28：验证通过：`tests/test_agents/test_ai_persona.py tests/test_agents/test_agent_reasoning.py`，`scripts/ai_eval_acceptance.py`，`scripts/m5_ai_player_experience_acceptance.py`。
- 2026-04-28：补齐真人参与局的 AI 发言节奏控制：`GameConfig.ai_discussion_message_limit` 可限制每轮 AI 白天发言数量，默认仅在人类玩家局启用；被限流的 AI 记录到 runtime `pace_events`。
- 2026-04-28：补齐人类操作等待诊断：白天发言、提名、投票请求会标记 `human_action:<player_id>:<action>`，前端/metrics 可明确显示等待真人而不是 AI 卡住。
- 2026-04-28：验证通过：`tests/test_orchestrator/test_game_loop.py`，`scripts/m5_ai_player_experience_acceptance.py`。
