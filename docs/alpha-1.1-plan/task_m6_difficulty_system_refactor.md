# M6 任务板：难度系统校准与架构补丁

## 当前定位

- **阶段**：M6
- **状态**：`Done`
- **目标**：修正 Alpha 1.1 难度系统中”静态配置差异大于真实对局行为差异”的问题，让难度成为可调、可验收、可解释的玩家体验系统。
- **总计划**：[alpha-1.1-plan.md](../alpha-1.1-plan.md)
- **关联模块**：
  - `src/agents/difficulty_presets.py`
  - `src/agents/decision_noise.py`
  - `src/agents/ai_agent.py`
  - `src/orchestrator/game_loop.py`
  - `scripts/difficulty_acceptance.py`
  - `scripts/difficulty_comparison.py`
  - `scripts/difficulty_behavior_acceptance.py`（待新增）
  - `tests/test_difficulty.py`
  - `tests/test_decision_noise.py`

## 第一性原则

难度不是“AI 更聪明或更随机”的单轴滑杆。社交推理游戏中的难度来自真人玩家面对 AI 时的认知负荷、欺诈压力、信息释放节奏和可预测性。

因此难度系统必须满足：

- **规则正确**：任何难度都不能违反 BOTC 基础规则。
- **信息隔离**：难度只能改变 AI 如何使用自己知道的信息，不能改变 AI 知道什么。
- **目标隔离**：好人和邪恶方拿到不同策略指导，不能共享阵营目标 prompt。
- **体验可控**：低难度降低压力，高难度增加博弈深度，混沌增加变化但不破坏可信度。
- **速度可控**：高难度不能默认等于更慢；每个难度都有 action budget。
- **可验收**：必须从实际 action 行为、发言内容、欺诈链和延迟指标验收，而不是只检查字段非空。

## 当前问题清单

| ID | 问题 | 现象 | 风险 |
|---|---|---|---|
| D-P0-1 | 邪恶策略 prompt 无条件注入 | ~~`_build_persona_prompt_block` 只判断 `preset.evil_strategy_prompt` 非空~~ **已修复：按 team 分支注入** | ~~好人 AI 可能收到邪恶方策略指导~~ **已消除** |
| D-P0-2 | Standard 是空白配置 | ~~`standard` 的 prompt/strategy/style/overrides 都为空~~ **已修复：Standard 有显式空值基线** | ~~无法定义和测试基线体验~~ **可测试** |
| D-P1-1 | 难度轴混杂 | ~~temperature、噪声、欺诈、叙事、阈值散落在不同结构~~ **已修复：新增 competence/deception/volatility/expressiveness/information_openness 五轴** | ~~难以调参和解释回归~~ **可独立调参** |
| D-P1-2 | Casual 被实现为更高温度和更保守阈值 | 可能只是变慢、变弱或更飘 | 不等于新手友好 |
| D-P1-3 | Master 欺诈缺少预算和一致性 | prompt 要求编造信息链，但没有 claim tracking | 可能前后矛盾或露出上帝视角 |
| D-P1-4 | Chaos 缺少有界随机 | 高噪声和大胆行为没有社交可信度约束 | 可能破坏沉浸和角色可信度 |
| D-P1-5 | 验收偏静态 | 多数检查 temperature/prompt/字段 | 实际对局行为可能没有显著差异 |
| D-P1-6 | 难度与速度预算未对齐 | 高难度 prompt 更复杂 | 多人局更慢 |

## 目标架构

### 多轴 DifficultyPreset

将 `DifficultyPreset` 从单层 prompt 配置升级为体验配置：

```python
@dataclass(frozen=True)
class DifficultyPreset:
    name: str
    description: str
    competence: float
    deception: float
    volatility: float
    expressiveness: float
    information_openness: float
    latency_budget: dict[str, int]
    temperature_by_action: dict[str, float]
    good_strategy_prompt: str
    evil_strategy_prompt: str
    speech_style_prompt: str
    safety_contract: str
    persona_overrides: dict[str, Any]
```

### 四种难度的体验合同

| 难度 | 第一目标 | 不应该做的事 |
|---|---|---|
| Casual | 降低新人认知压力，发言更解释性、少强压 | 不能靠乱玩或漏规则来变简单 |
| Standard | 稳定、可复现、适合多数玩家 | 不能是空白默认，必须有显式基线 |
| Master | 提高欺诈链、信息释放和团队协作质量 | 不能泄露上帝视角，不能无限强 |
| Chaos | 提供高变化和戏剧性 | 不能无理由乱投/乱跳，必须保持社交可信度 |

### 阵营策略边界

Prompt 注入必须分支：

```python
if self.team == Team.EVIL.value and preset.evil_strategy_prompt:
    block += f"\n【邪恶策略】{preset.evil_strategy_prompt}"
elif self.team == Team.GOOD.value and preset.good_strategy_prompt:
    block += f"\n【正义策略】{preset.good_strategy_prompt}"
```

任何非阵营共享指导只放入 `safety_contract` 或 `speech_style_prompt`。

## 补丁任务

### A11-DIFF-FIX-022：阵营策略 prompt 边界修复

- 优先级：`P0`
- 范围：
  - `src/agents/ai_agent.py`
  - `tests/test_difficulty.py`
  - `tests/test_agents/test_agent_reasoning.py`
- 问题：
  - 当前 `evil_strategy_prompt` 可能被所有阵营看到。
- 补丁：
  - [x] `evil_strategy_prompt` 只在 `self.team == "evil"` 时注入。
  - [x] 新增 `good_strategy_prompt` 字段。
  - [x] 好人 prompt 中禁止出现 `【邪恶策略】`。
  - [x] 邪恶方 prompt 中允许出现 `【邪恶策略】`，但仍带安全约束。
- 验收：
  - [x] 构造 good agent，生成 persona block，不包含邪恶策略。
  - [x] 构造 evil agent，生成 persona block，包含邪恶策略。
  - [x] Alpha3/M5 信息隔离测试不回归。

### A11-DIFF-FIX-023：难度多轴配置模型

- 优先级：`P0`
- 范围：
  - `src/agents/difficulty_presets.py`
  - `tests/test_difficulty.py`
  - `scripts/difficulty_acceptance.py`
- 补丁：
  - [x] 增加 `competence`：推理强度。
  - [x] 增加 `deception`：欺诈强度。
  - [x] 增加 `volatility`：行为波动。
  - [x] 增加 `expressiveness`：发言表现力。
  - [x] 增加 `information_openness`：信息披露倾向。
  - [x] 增加 `latency_budget`：按 action type 配置速度预算。
  - [x] 增加 `temperature_by_action`：不同动作不同温度。
- 验收：
  - [x] 四个 preset 都具备完整多轴字段。
  - [x] 每个字段范围在 `[0, 1]` 或明确配置范围内。
  - [x] 不再只用单一 `temperature` 表达难度。

### A11-DIFF-FIX-024：Standard 显式基线合同

- 优先级：`P1`
- 范围：
  - `src/agents/difficulty_presets.py`
  - `scripts/difficulty_comparison.py`
- 问题：
  - Standard 为空白导致无法验收”标准体验”。
- 补丁：
  - [x] 定义 Standard 的 `good_strategy_prompt`、`evil_strategy_prompt`、`speech_style_prompt`。
  - [x] Standard 的噪声、披露、欺诈、速度预算作为其他难度比较基线。
  - [x] 验收不再检查 “standard prompt_modifier is empty”，而是检查基线合同存在。
- 验收：
  - [x] Standard 配置非空且不含极端行为指导。
  - [x] Casual/Master/Chaos 与 Standard 的差异可量化。

### A11-DIFF-FIX-025：Master 欺诈预算与一致性

- 优先级：`P1`
- 范围：
  - `src/agents/ai_agent.py`
  - memory modules
  - tests
- 补丁：
  - [x] 引入 `deception_budget`，限制每阶段主动虚构的数量和强度。
  - [x] 记录 AI 已公开 claim，后续发言优先保持一致。
  - [x] 邪恶方可以编造合理信息链，但不能直接引用队友名单或真实魔典。
  - [x] Master 的欺诈重点是”选择性释放 + 一致叙事”，不是每次都造新故事。
- 验收：
  - [x] 大师邪恶 AI 连续两轮发言不自相矛盾。
  - [x] 伪造 claim 不包含未授权上帝视角字段。
  - [x] 欺诈链能在 replay/export 中追踪。

### A11-DIFF-FIX-026：Chaos 有界随机护栏

- 优先级：`P1`
- 范围：
  - `src/agents/decision_noise.py`
  - `src/agents/ai_agent.py`
  - `tests/test_decision_noise.py`
- 补丁：
  - [x] 为 bold move 增加社交理由标签：`retaliation/pressure_test/intuition/story_hook`。
  - [x] 随机目标仍必须通过合法目标和最低信号阈值。
  - [x] Chaos 可以高变化，但必须保留同一 persona 的稳定声线。
  - [x] 随机种子应绑定 game_id/day/round/player/action，避免跨局套路化。
- 验收：
  - [x] Chaos 连续多局目标和发言有变化。
  - [x] Chaos 不出现非法动作。
  - [x] Chaos 的理由文本不是纯随机，而有社交动机。

### A11-DIFF-FIX-027：难度行为级验收

- 优先级：`P1`
- 范围：
  - `scripts/difficulty_behavior_acceptance.py`
  - `scripts/alpha1.1_acceptance.py`
  - tests
- 补丁：
  - [x] 固定同一局面，比较四种难度的 action 输出差异。
  - [x] 检查 Casual 发言更解释性、信息压迫更低。
  - [x] 检查 Master 邪恶方有一致欺诈链。
  - [x] 检查 Chaos 变化率高但合法。
  - [x] 检查不同难度不会显著超过 action latency budget。
- 验收：
  - [x] `.\.venv\Scripts\python.exe scripts\difficulty_behavior_acceptance.py` 通过。
  - [x] `alpha1.1_acceptance.py` 聚合该门禁。

### A11-DIFF-FIX-028：玩家认知负荷指标

- 优先级：`P2`
- 范围：
  - metrics/export scripts
  - feedback docs
- 补丁：
  - [ ] 记录发言长度、公开 claim 数、强指控次数、欺诈 claim 数。
  - [ ] 给每局输出 `cognitive_load_summary`。
  - [ ] 真人反馈模板增加“等待感”和“信息压力”字段。
- 验收：
  - [ ] 能比较不同难度下的信息压力和等待感。

## 建议补丁顺序

1. **先修 P0 边界**：A11-DIFF-FIX-022，避免好人收到邪恶策略。
2. **再重构配置**：A11-DIFF-FIX-023，让后续调参有轴。
3. **补基线**：A11-DIFF-FIX-024，Standard 变成可测试合同。
4. **补高难与混沌护栏**：A11-DIFF-FIX-025/026。
5. **最后补行为级验收**：A11-DIFF-FIX-027，避免再次只测字段。

## 验收命令草案

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_difficulty.py tests\test_decision_noise.py -q
.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_agent_reasoning.py -k "private_info or high_confidence or deception" -q
.\.venv\Scripts\python.exe scripts\difficulty_acceptance.py
.\.venv\Scripts\python.exe scripts\difficulty_comparison.py
.\.venv\Scripts\python.exe scripts\difficulty_behavior_acceptance.py
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

## 风险记录

- 多轴配置会影响现有静态测试，需要同步改测试口径，而不是为了旧测试保留错误抽象。
- 修复阵营 prompt 后，部分现有“非标准都有 evil_strategy_prompt”的测试需要重写为“邪恶方才使用 evil_strategy_prompt”。
- Master 欺诈如果没有 claim memory，可能短期看起来更强，长期反而更容易被真人抓矛盾。
- Chaos 的随机性如果只靠阈值噪声，会显得像 bug；必须给随机行为社交动机。
- 难度系统与速度系统需要共同调参，否则高难度会变成“更慢的 AI”。

## 完成记录

- 2026-05-03: P0 任务 022/023 完成。阵营边界修复 + 多轴配置模型。
- 2026-05-03: P1 任务 024/025/026/027 完成。Standard 基线 + deception budget + Chaos 护栏 + 行为验收。
- 验收: difficulty_acceptance 100/100, difficulty_comparison 62/62, difficulty_behavior 50/50, 聚合验收 7/7 PASS。
