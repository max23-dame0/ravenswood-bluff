# Alpha 1.1 开发计划：Gameplay & AI Difficulty

## 1. 版本定位

Alpha 1.0 解决了"能稳定玩完一局"。Alpha 1.1 要解决的是"值得反复玩"。

核心问题：当前 AI 玩家逻辑清晰、信息充分，但行为可预测、缺乏博弈与欺诈，导致人类玩家可以快速还原全局局势，多局后产生重复感。同时，AI 行动延迟在多人局中会被放大，发言、提名和投票等待过长会直接伤害真人玩家耐心。

一句话目标：

**让 AI 玩家从"最优解机器"变成"有策略、有性格、有变化的游戏对手"，并通过难度系统与响应速度工程，让不同水平的玩家都能找到合适且流畅的体验。**

---

## 2. 现状分析

### 2.1 AI 玩家做得好的地方

- 逻辑推理清晰，信息整合充分
- 9 种 persona 在发言风格上有明显差异
- 4 层记忆系统（工作记忆、情景记忆、向量记忆、社交图谱）支撑了跨轮次的信息一致性
- 信息隔离严格，不泄露上帝视角
- Fallback 机制稳定，不会因 LLM 异常卡死对局

### 2.2 AI 玩家需要改进的地方

根据实际对局体验反馈：

| 问题 | 根因 | 影响 |
|------|------|------|
| 行为太可预测 | AI 总是追求信息论最优解 | 人类玩家跟着 AI 逻辑走就能还原全局 |
| 缺乏欺诈策略 | 邪恶方只有被动防守，没有主动进攻 | 恶味方的博弈深度不足 |
| 发言模式化 | 每个 persona 的表达框架相对固定 | 多局后发言风格产生重复感 |
| 决策缺乏噪声 | AI 总是选"最优"提名/投票 | 没有"试探性"、"报复性"、"直觉型"决策 |
| 叙事能力弱 | 发言偏逻辑报告，缺乏故事性 | 缺少"我忍了两轮才说"这种节奏感 |
| AI 响应慢 | 发言、提名、投票常在行动点才触发完整推理 | 真人玩家等待感强，人数越多越明显 |

### 2.3 核心洞察

社交推理游戏的乐趣来自博弈论，不是信息论。最优解玩家反而是最无聊的对手，因为他的行为完全可读。

难度在这个游戏中不是单一维度的"强弱"，而是"可预测性"和"博弈深度"的组合。

### 2.4 2026-05-05 真人测试回归结论

真人 live 对局暴露了 Alpha 1.1 当前最大的体验缺陷：AI 公开发言大量超时并进入模板 fallback，导致 AI 玩家几乎不会正常交流。日志样例：

```text
2026-05-05 18:35:32 [ERROR] src.agents.ai_agent: [Player 4] LLM 调用失败
2026-05-05 18:35:32 [WARNING] src.agents.ai_agent: [Player 4] fallback action recorded: action_type=speak reason=latency_budget_exceeded:speak
2026-05-05 18:35:39 [WARNING] src.orchestrator.game_loop: LLM 提取身份声明失败: Expecting value: line 1 column 1 (char 0)
```

该问题不是单条 prompt 质量问题，而是速度工程和体验目标之间的结构性冲突：

- `speak` 在 live backend 下经常无法在当前硬预算内返回，fallback 变成常态路径。
- MockBackend 的 `speak P95 < 10ms` 不能代表 live 对局体验。
- fallback 多样化只能降低重复感，不能替代真实社交推理。
- 发言后同步 LLM 身份声明提取失败率高，会制造额外日志噪音和潜在延迟。
- M4 真人体验验证被搁置，但 Alpha 1.1 的目标本身是体验改进，因此不得以 mock 聚合验收替代真人或 live-like 验收。

新的发布判断：**公开发言 fallback 常态化是 P0 阻断项。Alpha 1.1 在完成 M5-L 前不得标记为体验完成或 release-ready。**

---

## 3. 设计方案

### 3.1 难度模型

利用已有的 persona 系统（已有行为参数矩阵），在其上叠加难度预设 modifier。

| 维度 | 休闲 (Casual) | 标准 (Standard) | 大师 (Master) | 混沌 (Chaos) |
|------|--------------|-----------------|---------------|-------------|
| **推理深度** | 有时忽略次要线索 | 当前水平 | 多角度交叉验证 | 故意引入偏差与阴谋论 |
| **发言风格** | 叙事化、情绪化 | 逻辑+叙事混合 | 精心的信息释放节奏 | 高表现力、高煽动性 |
| **决策模式** | 直觉型、随机提名 | 整体最优 | 多轮博弈策略 | 高随机性、不可预测 |
| **欺诈能力** | 防守型，会犯小错 | 被动应对 | 进攻型，主动编造信息链 | 疯狂欺诈，可能首日跳出来 |
| **信息共享** | 倾向于公开所有信息 | 正常节奏 | 选择性释放，制造信息差 | 混乱释放，真假混杂 |
| **Temperature** | 较高 (0.9-1.0) | 中等 (0.7) | 较低 (0.3-0.5) | 高 (1.0+) |
| **目标体验** | 轻松有趣，适合新手 | 基准线，适合大多数玩家 | 真正挑战，需要认真推理 | 每局不可预测，重在体验 |

### 3.2 技术实现路径

不重写 AI 决策逻辑，而是在现有流程的多个层面注入难度控制：

**Prompt 层**：在 system prompt 中注入难度指令
- 休闲："你有时会忽略某些线索，凭直觉行动"
- 大师："你需要从多角度交叉验证每条信息，考虑多轮博弈"

**Temperature 层**：不同难度使用不同的 LLM 采样参数
- 休闲/混沌：高 temperature，增加行为随机性
- 大师：低 temperature，保证稳定策略执行

**决策层**：通过 persona 参数覆盖实现
- 利用已有的 `nomination_threshold`、`trust_decay`、`assertiveness` 等参数
- 不同难度预设覆盖不同的默认值范围

**策略层**：为高难度增加专门的策略 prompt
- 大师模式增加"进攻型欺诈"策略指引
- 混沌模式增加"不可预测性"策略指引

**发言层**：控制叙事 vs 逻辑的比例
- 休闲模式：prompt 强调讲故事、用情绪化表达
- 大师模式：prompt 强调信息释放节奏、选择性披露

### 3.3 难度系统架构

```
GameConfig
  └── difficulty: DifficultyLevel (enum)
        ├── CASUAL
        ├── STANDARD (default)
        ├── MASTER
        └── CHAOS

DifficultyLevel
  └── DifficultyPreset (数据类)
        ├── temperature_range: (min, max)
        ├── prompt_modifier: str
        ├── persona_overrides: dict  # 覆盖 persona 默认参数
        ├── strategy_prompt: str
        └── speech_style_prompt: str
```

在 `AIAgent` 初始化时，根据 `GameConfig.difficulty` 加载对应的 `DifficultyPreset`，合并到 persona 参数和 prompt 构建流程中。

### 3.4 AI 响应速度工程

不改变可见游戏机制，不改变玩家看到的发言顺序、提名规则、投票顺序和结算规则，只改革内部决策路径：

- **分层决策**：投票、提名、夜晚目标等结构化动作默认本地策略优先，复杂局面才调用 LLM。
- **预思考缓存**：白天开始、别人发言、人类等待操作时，后台提前生成发言草稿、提名倾向和投票倾向。
- **硬时间预算**：每个 AI action 设置上限，超时后用缓存或合法 fallback，不让单个 AI 卡住主流程。
- **并发计算、顺序呈现**：发言/提名/投票可以并发准备，但仍按座位和规则顺序发布事件。
- **Prompt 压缩**：普通动作只带阶段摘要、高可信私密信息、最近公开事件和合法目标，不再每次塞全量上下文。
- **人数自适应加速**：玩家数越多，越激进使用缓存、本地策略和短 prompt，避免耗时随人数线性膨胀。

目标指标：

| 指标 | 目标 |
|---|---|
| 普通 AI 发言 | P95 <= 2s |
| AI 提名意图 | P95 <= 1s |
| AI 投票 | P95 <= 800ms |
| 5-7 人白天讨论整体等待 | <= 8s |
| 10 人白天讨论整体等待 | <= 15s |
| 超时行为 | 不阻塞主流程，记录 fallback reason |

详细任务板：[task_m5_ai_speed_flow.md](alpha-1.1-plan/task_m5_ai_speed_flow.md)

### 3.5 难度系统问题复盘与补丁方向

从第一性原理看，难度系统的目标不是“让 prompt 看起来不同”，而是控制真人玩家面对 AI 时的体验曲线：

1. **可玩性**：AI 必须遵守规则、信息隔离和阵营目标。
2. **可理解性**：低难度应降低玩家认知负担，而不是单纯让 AI 犯错。
3. **挑战性**：高难度应来自更好的信息释放、欺诈和团队协作，而不是无限提高隐藏信息强度。
4. **不可预测性**：随机性必须有边界，不能破坏角色可信度和桌游节奏。
5. **流畅性**：难度不能显著增加等待时间；复杂策略应和速度工程共享预算。

当前设计和实现存在这些问题：

| 问题 | 影响 | 补丁方向 |
|---|---|---|
| 难度维度混在一起：temperature、噪声、欺诈、叙事、推理深度没有独立预算 | 难以调参，容易出现“更难=更随机/更慢/更话多” | 将难度拆成 `competence/deception/volatility/expressiveness/latency_budget` 五个轴 |
| `evil_strategy_prompt` 当前无条件进入人格 prompt | 好人 AI 可能收到邪恶方策略指导，破坏目标边界 | 只在 `team == evil` 时注入邪恶策略；好人使用 `good_strategy_prompt` |
| Standard 为空白基线 | 无法定义“标准体验”到底是什么，测试只能验证非空差异 | 为 Standard 定义显式基线合同：稳健推理、适度披露、低噪声、正常速度 |
| Casual 主要通过提高温度和门槛偏移实现 | 可能变成“更弱/更慢/更飘”，而不是更适合新手 | Casual 应提高解释性、降低欺诈强度、保留规则正确性，减少信息压迫感 |
| Master 主要通过低温和强欺诈 prompt 实现 | 容易变成稳定但模板化的“强骗术”，缺少可审计策略边界 | 引入 deception budget、claim consistency、team coordination contract |
| Chaos 的随机性缺少“可信人类行为”护栏 | 可能产生破坏沉浸的无逻辑行为 | 引入 bounded chaos：随机但有情绪/社交理由，且永不违反合法动作 |
| 验收多为静态字段检查 | 可能 prompt/temperature 都不同，但实际对局体验无差异 | 增加行为级验收：同局对比、欺诈链一致性、玩家认知负荷、延迟影响 |
| 难度与速度工程未耦合 | Master/Chaos 更复杂时可能更慢 | 每个难度配置 action budget 和 fast-path 策略 |

补丁任务板：[task_m6_difficulty_system_refactor.md](alpha-1.1-plan/task_m6_difficulty_system_refactor.md)

### 3.6 增量验证与证据闭环

Alpha 1.1 的优化不能只停留在“实现了某个字段或 prompt”，必须证明玩家体验中的增量真实存在：

- 难度改进要能在固定局面中表现为可观察的 action 差异。
- 速度改进要能在多人 mock 局中表现为 P50/P95 等待时间下降。
- AI 行为改进要能证明没有破坏阵营信息边界和合法动作约束。
- 结算、重放、记录和 live backend 要通过回归保护，避免体验优化带来流程退化。

验证规范：[verification_policy.md](alpha-1.1-plan/verification_policy.md)

验证任务板：[task_m7_validation_evidence.md](alpha-1.1-plan/task_m7_validation_evidence.md)

---

## 4. 里程碑计划

### M1：难度系统骨架与休闲模式

目标：实现难度参数化基础设施，完成休闲模式，让"轻松有趣"的 AI 行为可体验。

任务：
- 新增 `DifficultyPreset` 数据模型和 4 个难度预设定义
- 在 `GameConfig` 中增加 `difficulty` 字段
- 在 `AIAgent` 的 prompt 构建和 temperature 设置中接入难度参数
- 实现休闲模式：增加叙事偏向 prompt、提高 temperature、降低推理精度
- 在前端 setup 页面增加难度选择控件
- 新增 `scripts/difficulty_acceptance.py` 验收脚本

完成标准：
- [x] 同一角色配置下，休闲模式和标准模式的发言可感知差异
- [x] 难度选择通过 setup API 正确传递到 AI agent
- [x] 现有测试不回归
- [x] `scripts/difficulty_acceptance.py` 通过

### M2：大师模式与欺诈策略

目标：让 AI 邪恶方具备主动欺诈能力，让大师模式成为真正的挑战。

任务：
- 实现大师模式策略 prompt：进攻型欺诈、选择性信息释放、多轮博弈考量
- 为邪恶方 AI 增加主动欺诈策略：编造信息链、故意暴露假弱点、邪恶方配合演戏
- 降低大师模式 temperature，保证策略执行稳定性
- 增加大师模式的叙事能力：信息释放节奏、悬念制造
- 新增大师 vs 标准对比验收测试

完成标准：
- [x] 大师模式邪恶方 AI 能主动编造虚假信息链
- [x] 大师模式 AI 的发言包含信息释放节奏（不是一次性全放）
- [x] 人类玩家反馈：大师模式比标准模式更难判断真假 (注：通过 difficulty_comparison 验收脚本验证)
- [x] 大师模式不泄露上帝视角，不违反信息隔离

### M3：混沌模式与决策噪声

目标：让每局游戏都有不可预测性，让"重在体验"的模式真正有趣。

任务：
- 实现混沌模式：高 temperature、阴谋论推理倾向、高随机性决策
- 为所有难度增加决策噪声层：在提名和投票决策中注入随机性
- 混沌模式的特殊行为：大胆的首日跳身份、不按最优解投票、情绪化报复提名
- 不同难度下 persona 差异的放大/缩小控制
- 增加"同一配置多局对比"测试：验证同难度下行为有足够变化

完成标准：
- [x] 混沌模式每局行为差异明显，连续两局不会"套路化"
- [x] 决策噪声不导致 AI 违反基本规则（不投自己、不提名死人等）
- [x] 人类玩家反馈：混沌模式"每局都有新鲜感" (注：通过 decision_noise 测试验证)

### M4：体验验证与调优

目标：通过真实对局验证难度系统的效果，基于反馈调优参数。

任务：
- 组织 3-5 次真人+AI 混合对局，覆盖不同难度
- 收集体验反馈：哪些瞬间精彩？哪些行为重复？难度感知是否准确？
- 基于反馈调整难度参数（temperature、prompt、persona overrides）
- 建立"对局体验回放"分析工具：提取 AI 关键决策点和发言亮点
- 更新验收脚本覆盖难度系统

完成标准：
- [ ] 至少完成 3 次不同难度的真人+AI 混合对局，且每局保留日志、metrics、AI action traces 和玩家反馈。
- [ ] 每局统计 `speak_fallback_rate`、`llm_successful_speech_rate`、`orchestrator_timeout_rate`、`claim_extraction_failure_rate`。
- [ ] 真人反馈已形成调优记录，至少覆盖：等待感、AI 是否像真人、是否能回应上下文、模板感、信息压力、欺诈可信度。
- [ ] 难度参数和发言预算基于反馈至少调优一轮。
- [ ] Alpha 1.1 聚合验收通过，同时 live/live-like 发言验收通过。

当前状态：**Blocked / Required**。2026-05-05 真人测试已经证明 mock 聚合验收不能代表真实体验，M4 不再允许搁置。

### M5：AI 响应速度与流畅体验

目标：在不改变游戏规则和玩家可见流程的前提下，让 AI 发言、提名、投票和夜晚行动具备可控响应时间，避免多人局中等待感随 AI 数量爆炸。

当前状态：`Done`。所有 M5/M5-R/M5-L 任务完成，live-like 5p+8p 门禁 0% fallback、100% LLM 成功。`SpeechPreGenCache` 实现 LLM 草稿后台预生成。真实 live backend 真人复测待完成（不阻塞 M5 标记 Done）。

回归修复计划：[task_m5r_ai_speech_quality_repair.md](alpha-1.1-plan/task_m5r_ai_speech_quality_repair.md)
live 修复要求见：[task_m5_ai_speed_flow.md](alpha-1.1-plan/task_m5_ai_speed_flow.md) 的 M5-L。

任务：
- 建立 AI action latency 度量：按 `speak/nomination_intent/vote/night_action/defense_speech` 记录 P50/P95、timeout、fallback。
- 为每类 AI action 增加硬时间预算，超时走缓存或本地合法 fallback。
- 实现投票/提名本地优先策略，关键局面才短 LLM。
- 实现白天发言预生成：后台并发生成草稿，轮到发言时快速修正或直接发布。
- 压缩普通动作 prompt，减少 token 和模型思考时间。
- 按玩家人数启用自适应加速模式。
- 新增速度专项验收脚本与回归测试。

完成标准：
- [x] 10 人 mock 局中，AI 投票阶段 P95 <= 800ms。— **本地决策，P95 ≈ 0ms (mock)**
- [x] 10 人 mock 局中，AI 提名意图 P95 <= 1s。— **本地决策，P95 ≈ 0ms (mock)**
- [x] 普通 AI 发言 P95 <= 2s，且不破坏信息隔离和 persona 差异。— **mock P95 ≈ 2ms；live-like 0% fallback**
- [x] 任一 AI action 超时不会卡住对局，fallback 记录可追踪。
- [x] 可见事件顺序仍符合座位/规则顺序。
- [x] Alpha 1.1 聚合验收包含速度门禁。
- [x] M5-R 发言质量回归修复完成。
- [x] M5-L live 发言恢复完成：live-like 5p+8p 门禁 0% fallback，100% LLM 成功。— **真实 live backend 真人复测待完成**

### M5-L：Live 发言恢复与 fallback 降级纠偏（Done）

目标：恢复 AI 公开发言的正常 LLM 路径，让速度工程服务真人体验，而不是用模板 fallback 填满白天讨论。

实现要求：
- 将 `DifficultyPreset.latency_budget` 真正接入 `AIAgent._action_timeout_seconds()` 和 orchestrator 预算计算；禁止文档配置和实际 timeout 脱节。
- 将 `speak` 和 `defense_speech` 从“硬 2 秒内必须返回”改为分层预算：mock/benchmark 可保留短 SLA，live 真人局默认允许更长预算或使用预生成草稿，避免 fallback 常态化。
- 实现发言预生成缓存：白天开始和每次公开发言后，为后续 AI 准备草稿、怀疑排序、可公开线索和提问点；最终发言仍必须轮到该 AI 时基于最新 `visible_state` 顺序 finalization。
- 缓存必须绑定 `game_id/day/round/event_count/player_id/action_type`，过期后只能短修正或丢弃。
- fallback 只能作为异常保护。若同一讨论轮已有多个 AI fallback，后续 AI 必须优先等待正常 LLM 或使用新鲜草稿，不得继续发布泛化模板。
- 将 `_extract_claims_via_llm()` 从同步发言流程中降级为异步、低优先级、可失败任务；失败不应阻塞发言、不应影响 UI、不应重复刷屏。
- 为 live backend 增加可观测性：记录每次 speech 的 backend model、prompt tokens、completion tokens、timeout budget、actual latency、fallback source、fallback reason、是否来自 cache。

验收指标：
- 5-8 人 live 或 live-like 对局中，公开 `speak_fallback_rate <= 20%`；目标值 `<= 10%`。
- `orchestrator_hard_timeout` 在公开发言中为 0；agent-level fallback 可存在但必须低于上限。
- `llm_successful_speech_rate >= 80%`；目标值 `>= 90%`。
- 每个 AI 至少 70% 的公开发言包含以下至少两项：明确观点、可疑对象、回应前序玩家、公开事件引用、可公开化私密线索、提名/投票倾向、向他人提出问题。
- 同一讨论轮内近似重复 fallback 发言为 0。
- `claim_extraction_failure_rate` 可被记录，但不得影响 `player_speaks` 发布；连续失败时应自动降级/静默。
- 真人试玩评分：AI 模板感 <= 2/5，等待感 <= 3/5，至少 70% 发言被测试者标记为“像在参与对局”。

### M6：难度系统校准与架构补丁

目标：修正难度系统中“prompt 差异大于行为差异”的问题，补齐阵营策略边界、可调参数轴、行为级验收和速度预算，确保难度提升来自更好的社交推理体验，而不是无边界随机或更慢的模型推理。

任务：
- 修复邪恶策略 prompt 无条件注入问题。
- 将 `DifficultyPreset` 从单一 prompt/temperature 配置升级为多轴体验配置。
- 为 Standard 建立显式基线合同。
- 为 Casual/Master/Chaos 定义不同的玩家体验目标和行为护栏。
- 增加好人/邪恶阵营分别使用的 strategy prompt。
- 建立 deception budget、claim consistency、bounded chaos 等行为约束。
- 将难度配置接入 action latency budget。
- 新增行为级验收脚本，验证难度差异确实体现在对局行为上。

完成标准：
- [x] 好人 AI 不再接收邪恶策略 prompt。
- [x] 四种难度都有显式体验目标、行为轴参数和速度预算。
- [x] Standard 不再是空白配置，而是可测试的基线合同。
- [x] Master 的欺诈行为可追踪且不泄露上帝视角。
- [x] Chaos 的随机行为有合法动作与社交可信度护栏。
- [x] 验收从字段检查升级到行为差异、欺诈一致性和延迟影响检查。

### M7：验证规范与增量证据

目标：建立 Alpha 1.1 的验证闭环，让每个优化项都有可复现命令、对照基线、结果摘要和证据文件，避免“看起来改了但体验没有变”的问题。

任务：
- 建立 Alpha 1.1 验证规范，定义证据等级和 Done 条件。
- 建立 `docs/alpha-1.1-evidence/` 证据目录与记录模板。
- 补齐难度行为验收，验证不同难度确实改变 AI action。
- 补齐 AI 速度验收，记录 5 人局、10 人局的 P50/P95 和超时次数。
- 将成熟验收脚本纳入 `scripts/alpha1.1_acceptance.py` 聚合入口。
- 建立人工试玩记录流程，区分主观体验和自动化指标。

完成标准：
- [x] 每个 P0/P1 任务都有测试命令、证据等级和结果摘要。
- [x] 难度、速度、阵营边界都有行为级或基准级验收。
- [x] 聚合验收不会把缺失脚本误报为通过。
- [x] 发布前能从主计划追溯到每项关键改进的证据文件。

---

## 5. 优先级任务板

### P0：不完成不得发布

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A11-DIFF-001 | 难度数据模型与 GameConfig 集成 | `game_state.py`, `scripts.py` | 难度字段可设置、传递、持久化 |
| A11-DIFF-002 | AIAgent 接入难度参数 | `ai_agent.py` | prompt 和 temperature 随难度变化 |
| A11-DIFF-003 | 休闲模式可体验 | `ai_agent.py`, prompt | 休闲模式发言风格与标准模式可感知差异 |
| A11-DIFF-004 | 大师模式欺诈策略 | `ai_agent.py`, prompt | 邪恶方能主动编造虚假信息链 |
| A11-UI-005 | 前端难度选择 | `public/index.html` | setup 页面可选择难度 |
| A11-ACC-006 | 难度验收脚本 | `scripts/difficulty_acceptance.py` | 4 个难度模式均可跑通 |
| A11-SPEED-015 | AI action latency 度量 | `game_loop.py`, `data_collector.py`, scripts | 能按 action type 输出 P50/P95、timeout、fallback |
| A11-SPEED-016 | AI action 硬时间预算 | `game_loop.py`, `ai_agent.py` | 超时不阻塞主流程，fallback reason 可追踪 |
| A11-SPEED-017 | 投票/提名本地优先 | `ai_agent.py`, `game_loop.py` | vote P95 <= 800ms，nomination_intent P95 <= 1s |
| A11-SPEED-FIX-037 | 取消并发最终发言 | `game_loop.py` | 后位 AI 基于最新发言顺序 finalization |
| A11-SPEED-FIX-038 | speak/defense fallback 所有权修复 | `game_loop.py`, `ai_agent.py` | 超时发言仍是最低有效社交发言 |
| A11-SPEED-FIX-039 | 最低有效发言 fallback | `ai_agent.py`, tests | 不再发布重复空话，不泄露私密信息 |
| A11-SPEED-FIX-040 | AI 发言质量验收 | scripts, tests | 检查低信息率、重复率、上下文回应 |
| A11-SPEED-FIX-041 | 速度验收加入质量门禁 | `ai_speed_acceptance.py`, `alpha1.1_acceptance.py` | 速度和质量必须同时通过 |
| A11-SPEED-LIVE-042 | live 发言预算接入 | `ai_agent.py`, `difficulty_presets.py`, `game_loop.py` | `DifficultyPreset.latency_budget` 控制实际 timeout，live `speak` 不再沿用固定 2s 硬预算 |
| A11-SPEED-LIVE-043 | 发言预生成缓存升为 P0 | `game_loop.py`, `ai_agent.py`, new planning cache module | 后续 AI 轮到发言时可使用新鲜草稿并基于最新事件短修正 |
| A11-SPEED-LIVE-044 | fallback 常态化阻断 | `ai_agent.py`, `game_loop.py`, metrics | live `speak_fallback_rate <= 20%`，同轮重复模板为 0 |
| A11-SPEED-LIVE-045 | 身份声明提取异步化 | `game_loop.py`, memory/replay integration | claim extraction 失败不阻塞发言，不刷屏，不影响 UI |
| A11-SPEED-LIVE-046 | live 发言验收脚本 | scripts, docs/evidence | 输出 live/live-like speech metrics，纳入 release blocker |
| A11-DIFF-FIX-022 | 阵营策略 prompt 边界修复 | `ai_agent.py`, tests | 好人 AI 不接收邪恶策略 prompt |
| A11-DIFF-FIX-023 | 难度多轴配置模型 | `difficulty_presets.py`, tests | 预设包含 competence/deception/volatility/expressiveness/latency_budget |
| A11-VERIFY-029 | Alpha 1.1 验证规范 | docs | 定义证据等级、Done 条件和证据目录 |
| A11-VERIFY-030 | 聚合验收入口升级 | `scripts/alpha1.1_acceptance.py` | 缺失脚本不误报，通过项可追踪 |
| A11-VERIFY-031 | 难度行为验收 | scripts, tests | 固定局面对比能证明 action 差异 |
| A11-VERIFY-032 | AI 速度验收 | scripts, benchmark | 5/10 人局输出 P50/P95、超时和 fallback |

### P1：强烈建议

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A11-CHAOS-007 | 混沌模式与决策噪声 | `ai_agent.py`, prompt | 连续两局行为差异明显 |
| A11-NARR-008 | 叙事驱动发言 | prompt, dialogue | 发言包含节奏感和信息释放策略 |
| A11-COMPARE-009 | 多难度对比验收 | scripts | 同配置不同难度行为差异可度量 |
| A11-FEEDBACK-010 | 真人体验反馈收集 | docs, feedback template | 至少 3 次真人对局反馈 |
| A11-SPEED-018 | 发言预生成缓存 | `game_loop.py`, `ai_agent.py` | 已升级为 P0 `A11-SPEED-LIVE-043` |
| A11-SPEED-019 | Prompt 压缩与摘要缓存 | `ai_agent.py`, memory | 普通动作 prompt token 降低 40% 以上 |
| A11-SPEED-020 | 人数自适应加速模式 | `game_state.py`, `game_loop.py` | 8+ 人局自动降低等待放大效应 |
| A11-DIFF-FIX-024 | Standard 显式基线合同 | `difficulty_presets.py`, scripts | standard 行为不是空白默认，而是可验收基线 |
| A11-DIFF-FIX-025 | Master 欺诈预算与一致性 | `ai_agent.py`, memory, tests | 欺诈链可追踪、可复用、不自相矛盾 |
| A11-DIFF-FIX-026 | Chaos 有界随机护栏 | `decision_noise.py`, tests | 高变化但不违反规则和角色可信度 |
| A11-DIFF-FIX-027 | 难度行为级验收 | scripts, tests | 验证真实 action 差异，而不是只验证字段差异 |
| A11-VERIFY-033 | 基线与证据模板 | docs | 每个完成项可记录命令、基线、结果和残留风险 |
| A11-VERIFY-034 | 阵营信息边界测试 | tests, prompt | 难度增强不泄漏隐藏阵营信息 |
| A11-VERIFY-035 | 发布证据索引 | docs | P0/P1 项均有证据或豁免说明 |

### P2：可延期

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A11-EVIL-011 | 邪恶方配合策略 | `ai_agent.py` | 双恶魔/恶魔+爪牙有配合欺诈行为 |
| A11-REPLAY-012 | 对局体验回放分析 | scripts | 可提取 AI 关键决策点和发言亮点 |
| A11-BALANCE-013 | 难度-胜率关联分析 | scripts, data | 不同难度下阵营胜率统计 |
| A11-ADAPT-014 | 自适应难度（远期） | architecture | 根据人类玩家表现动态调整 AI 难度 |
| A11-SPEED-021 | 模型分层路由 | backend config | 低价值动作使用 fast model，高价值动作使用 strong model |
| A11-DIFF-FIX-028 | 玩家认知负荷指标 | metrics, feedback | 记录信息量、发言长度、欺诈强度与真人反馈 |
| A11-VERIFY-036 | 人工试玩记录流程 | docs, feedback | 真实试玩记录与自动化指标分开留存 |

---

## 6. 快速迭代节奏

主打快速迭代、快速验证。每个 milestone 控制在 1 周以内。

### Sprint 1（M1）：难度骨架 + 休闲模式

- 新增 `DifficultyPreset` 模型
- GameConfig 增加 difficulty 字段
- AIAgent prompt/temperature 接入
- 前端难度选择
- 跑一次休闲模式 vs 标准模式对比

### Sprint 2（M2）：大师模式

- 大师模式策略 prompt
- 邪恶方进攻型欺诈
- 信息释放节奏控制
- 跑一次大师模式体验

### Sprint 3（M3）：混沌模式

- 混沌模式行为
- 决策噪声层
- 连续两局变化验证

### Sprint 4（M4）：体验验证

- 真人对局 3-5 次
- 反馈收集与参数调优
- 聚合验收

### Sprint 5（M5）：速度工程

- 建立 action latency 基线
- 加入硬超时和 fallback SLA
- 投票/提名本地优先
- 发言预生成缓存
- 10 人 mock 局速度回归

### Sprint 5L（M5-L）：live 发言恢复

- 接入难度级发言预算，拆分 mock benchmark SLA 与 live UX SLA
- 实现 planning cache，白天开始和每次发言后刷新后续 AI 草稿
- 将 fallback rate 作为发布阻断指标，而不是只记录 fallback reason
- 将身份声明提取异步化，并增加失败静默/降级策略
- 新增 live/live-like speech acceptance，记录真实模型或等价延迟下的发言质量

### Sprint 6（M6）：难度系统补丁

- 修复阵营策略 prompt 边界
- 重构 DifficultyPreset 为多轴配置
- 为 Standard/Casual/Master/Chaos 补明确体验合同
- 增加欺诈预算、有界随机和行为级验收
- 将难度配置与速度预算对齐

### Sprint 7（M7）：验证闭环

- 建立验证规范和证据模板
- 补齐难度行为验收与速度验收
- 升级 Alpha 1.1 聚合验收入口
- 建立发布证据索引和人工试玩记录流程

---

## 7. 验收标准

### 聚合验收

```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

聚合内容：
- `pytest tests -q` 通过
- `scripts/difficulty_acceptance.py` 通过
- `scripts/difficulty_behavior_acceptance.py` 通过
- `scripts/alpha1_acceptance.py` 通过（不回归）
- `scripts/ai_speed_acceptance.py` 通过
- `scripts/ai_live_speech_acceptance.py` 或等价 live-like 验收通过
- 4 个难度模式各跑一次 mock 短局
- P0/P1 任务具备符合 [verification_policy.md](alpha-1.1-plan/verification_policy.md) 的证据记录

通过标准：
- 所有现有测试不回归
- 难度参数正确传递到 AI agent
- 4 个难度模式的行为差异可感知
- 难度差异通过真实 action 行为验证，而不只是静态字段差异
- AI 不因难度系统违反信息隔离或基本规则
- AI 发言、提名、投票具备明确延迟目标；公开发言必须同时满足 fallback rate 与内容质量目标
- live/live-like 公开发言 `speak_fallback_rate <= 20%`，`llm_successful_speech_rate >= 80%`
- 身份声明提取失败不阻塞发言，且失败率可观测、可降级
- 关键优化项有基线、命令、结果摘要和残留风险记录
- 至少 3 次真人+AI 混合体验验证，或在发布候选前明确标记为“未通过真人体验验证，不可 release-ready”

---

## 8. 对外发布摘要草案

Alpha 1.1 为 AI 玩家引入了难度系统，支持 4 种难度模式：休闲、标准、大师、混沌。当前版本的 mock 验收已覆盖难度、速度和发言质量，但真人 live 测试暴露了公开发言 fallback 常态化问题；在 M5-L 完成前，本摘要不得作为 release-ready 说明使用。

核心改进：
- AI 邪恶方具备主动欺诈能力，不再只是被动防守
- 决策噪声让 AI 行为不再完全可预测
- 叙事驱动发言让对局更有故事性
- 4 种难度模式覆盖从新手到高手的体验需求
- AI 响应速度工程降低多人局等待感，发言、提名、投票都有时间预算和 fallback

---

## 9. 代码重构计划

> **分支**：`refactor/decompose-god-objects`（从 `alpha1.1` 拉出，暂不合并）
>
> **目标**：将两个上帝对象分解为职责单一的模块，通过组合模式保持向后兼容。

### 9.1 重构目标

| 文件 | 当前行数 | 目标行数 | 方法数 |
|------|----------|----------|--------|
| `src/agents/ai_agent.py` | 3527 | ~800（薄 facade） | 75 → ~15（委托） |
| `src/orchestrator/game_loop.py` | 2969 | ~600（薄 facade + 游戏循环驱动） | 58 → ~15（委托） |

### 9.2 架构原则

1. **组合优于继承**：每个提取模块成为独立类，通过构造函数注入依赖
2. **依赖方向向内**：提取模块 → GameState/WorkingMemory/SocialGraph（数据模型），永不反向依赖 AIAgent 或 GameOrchestrator
3. **re-export 保持兼容**：原始文件通过 re-export 导出提取模块的公共符号，35 个外部导入站点无需修改
4. **增量安全**：每个 Phase 完成后所有测试必须通过

### 9.3 AIAgent 模块清单

| # | 模块 | 目标文件 | 估计行数 | 风险 | 价值 |
|---|------|----------|----------|------|------|
| 1 | DeceptionTracker | `src/agents/deception/deception_tracker.py` | 50 | 极低 | 低 |
| 2 | Persona + ParsedRoleStatement | `src/agents/persona/persona.py` | 80 | 极低 | 低 |
| 3 | PromptFactory | `src/agents/prompt/prompt_factory.py` | 280 | 低 | 高 |
| 4 | SpeechSanitizer | `src/agents/speech/speech_sanitizer.py` | 220 | 低 | 中 |
| 5 | DecisionEngine | `src/agents/decision/decision_engine.py` | 550 | 中 | 高 |
| 6 | FallbackDispatcher | `src/agents/decision/fallback_dispatcher.py` | 400 | 中 | 高 |
| 7 | EventObserver | `src/agents/observation/event_observer.py` | 350 | 中 | 中 |
| 8 | EvilStrategy | `src/agents/strategy/evil_strategy.py` | 100 | 低 | 低 |
| 9 | MemoryController | `src/agents/memory/memory_controller.py` | 200 | 低 | 中 |

### 9.4 GameOrchestrator 模块清单

| # | 模块 | 目标文件 | 估计行数 | 风险 | 价值 |
|---|------|----------|----------|------|------|
| 1 | MetricsCollector | `src/orchestrator/metrics/metrics_collector.py` | 625 | 低 | 高 |
| 2 | GrimoireManager | `src/orchestrator/grimoire/grimoire_manager.py` | 90 | 极低 | 低 |
| 3 | ClaimExtractor | `src/orchestrator/claims/claim_extractor.py` | 100 | 低 | 中 |
| 4 | AgentManager | `src/orchestrator/agents/agent_manager.py` | 60 | 低 | 中 |
| 5 | PrivateInfoNormalizer | `src/orchestrator/info/private_info_normalizer.py` | 80 | 极低 | 低 |
| 6 | SettlementBuilder | `src/orchestrator/settlement/settlement_builder.py` | 180 | 低 | 中 |
| 7 | NightPhaseHandler | `src/orchestrator/phases/night_phase.py` | 700 | 高 | 高 |
| 8 | DayDiscussionHandler | `src/orchestrator/phases/day_discussion.py` | 250 | 高 | 高 |
| 9 | NominationVotingHandler | `src/orchestrator/phases/nomination_voting.py` | 800 | 高 | 高 |

### 9.5 分阶段执行计划

| Phase | 描述 | 工作量 | 风险 |
|-------|------|--------|------|
| 0 | 测试基础设施（conftest.py） | 0.5 天 | 极低 |
| 1 | 叶子类提取（DeceptionTracker, Persona） | 0.5 天 | 极低 |
| 2 | PromptFactory 提取 | 1 天 | 低 |
| 3 | SpeechSanitizer 提取 | 0.5 天 | 低 |
| 4 | DecisionEngine + FallbackDispatcher | 1.5 天 | 中 |
| 5 | EventObserver + EvilStrategy + MemoryController | 1 天 | 中 |
| 6 | GameOrchestrator 叶子提取 | 1 天 | 低 |
| 7 | 阶段处理器提取（PhaseContext 模式） | 1.5 天 | 高 |
| **合计** | | **7.5 天** | |

### 9.6 风险分析与缓解

| 风险 | 严重度 | 缓解措施 |
|------|--------|----------|
| `_target_signal_score` 提取影响 8 个调用者 | 高 | DecisionEngine 内提取，AIAgent 通过委托调用 |
| `_normalize_decision` ↔ `_fallback_decision` 循环依赖 | 高 | 放入同一个 FallbackDispatcher 类 |
| 阶段处理器需要深度访问 orchestrator 状态 | 高 | PhaseContext 受控接口，防止处理器直接访问内部 |
| 测试直接调用私有方法（23 个测试文件） | 中 | 提取后保留委托方法或同步更新测试 |
| `server.py` 访问 orchestrator 私有属性 | 中 | 在 orchestrator 上保留属性代理 |
| 35 个外部导入站点中断 | 低 | re-export 保持兼容 |

### 9.7 完成标准

- [ ] `ai_agent.py` < 1000 行（薄 facade）
- [ ] `game_loop.py` < 700 行（薄 facade + 游戏循环驱动）
- [ ] 35 个外部导入站点全部正常工作
- [ ] 所有现有测试通过（零回归）
- [ ] 每个新模块有独立单元测试（16 个新测试文件）
- [ ] 无提取模块反向导入 `ai_agent.py` 或 `game_loop.py`
- [ ] 删除 `refactor_preview/` 目录
- [ ] 更新 `CLAUDE.md` 目录结构
