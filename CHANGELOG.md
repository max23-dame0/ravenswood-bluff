# Changelog

## [alpha1.1] - 2026-05-02

Alpha 1.1 引入 AI 玩家难度系统，支持 4 种难度模式，让不同水平的人类玩家都能找到合适的对局体验。

### 新增与强化

- **难度系统**：新增 `DifficultyLevel` 枚举（casual/standard/master/chaos），集成到 `GameConfig`、`AIAgent`、前端 setup 页面和 API。
- **难度预设模块**：新增 `src/agents/difficulty_presets.py`，定义 4 种难度的温度、提示词、欺诈策略和人格参数覆盖。
- **AI Agent 难度集成**：`AIAgent` 根据难度调整 LLM 温度、系统提示词、提名/投票阈值和发言风格。
- **前端难度选择**：setup 页面新增 4 种难度单选控件，支持中英文国际化。
- **验收与测试**：新增 `scripts/difficulty_acceptance.py`（54 项检查）和 `tests/test_difficulty.py`（26 项单元测试）。
- **决策噪声层**：新增 `src/agents/decision_noise.py`，为提名和投票决策注入难度分级的可控随机性（chaos 0.18 > casual 0.12 > standard 0.05 > master 0.02）。
- **多难度对比验收**：新增 `scripts/difficulty_comparison.py`（62 项检查）和 `tests/test_decision_noise.py`（31 项测试），验证 4 种难度的行为差异。

### 验收入口

- `scripts/difficulty_acceptance.py`
- `scripts/alpha1.1_acceptance.py`
- `tests/test_difficulty.py`
- `scripts/difficulty_comparison.py`
- `tests/test_decision_noise.py`

## [alpha1.0-candidate] - 2026-04-29

Alpha 1.0 是首个正式内测候选版本，目标不是扩大功能面，而是把主流程、真人入口、AI 玩家、说书人复盘和发布门禁收束到可组织小范围内测的状态。

### 新增与强化

- **规则与流程封板**：补齐 Trouble Brewing 主链的夜晚、白天讨论、提名、辩解、投票、处决、结算和 rematch 验收入口。
- **真人前端内测流**：玩家端覆盖身份查看、私密信息、聊天、提名、投票、死亡状态、结算历史；说书人端保留魔典、夜晚步骤和裁量摘要。
- **Live backend smoke**：`simulate_game.py --stop-after` 支持短局停止点，`scripts/alpha1_acceptance.py --include-live-smoke` 可手动纳入 live smoke。
- **说书人 judgement ledger**：固定信息、醉酒/中毒失真、隐士/间谍误注册、红鲱鱼选择与命中、市长夜杀转移均有可导出的裁量记录。
- **AI 玩家内测体验**：公开发言边界、私密信息表达、fallback 行为、投票/提名差异和行为样本由 M5 acceptance 覆盖。
- **问题定位包**：`scripts/export_all_assets.py` 可按 `game_id` 导出历史、AI traces、说书人裁量、metrics 摘要、日志尾片段和 manifest。
- **发布工程**：新增 alpha1 release checklist、known issues、反馈模板、数据目录说明和聚合门禁。

### 验收入口

- `scripts/alpha1_acceptance.py`
- `scripts/alpha1_rules_acceptance.py`
- `scripts/frontend_acceptance.py`
- `scripts/storyteller_acceptance.py`
- `scripts/role_acceptance.py`
- `scripts/m5_ai_player_experience_acceptance.py`
- `scripts/export_all_assets.py`

### 已知限制

- Alpha 1.0 仍为内测候选，不承诺生产级稳定。
- Live 模式耗时、token/调用量基线和浏览器级真人 smoke 记录仍需在 release checklist 中逐项确认。
- 长局日志与 trace 体积需要按 `docs/alpha-1.0-data-operations.md` 管理。
 
## [alpha0.3] - 2026-04-24
 
本版本是项目向“可观测性”与“战略智能”迈进的关键一步。
 
### 🌟 新增特性 (New Features)
- **导演级 AI 说书人 (Strategic Storyteller)**：
  - 引入了基于全局局势评分的 **智能平衡 (Smart Balancing)** 逻辑。
  - 支持 **内心独白 (Storyteller Monologue)**，在控制台中展示说书人的平衡意图。
  - 针对占卜师、间谍、隐士、厨师、共情者等核心角色实现了更合理的扰动策略。
- **全量对局资产化 (Data Assets)**：
  - 实现了 `scripts/export_all_assets.py`，一键导出对局快照、AI 思维链与说书人判决。
  - `GameDataCollector` 全量集成，每局捕获 5 个维度的关键阶段快照。
- **高保真记忆系统 (High-Fidelity Memory)**：
  - 正式落地 **三层记忆架构**：Objective (事实), High-Confidence (私密结果), Public (社交声明)。
  - **向量记忆 (RAG)**：支持基于历史事件与聊天的语义检索，大幅提升 AI 的逻辑一致性。
- **复杂规则补完**：
  - 实现了 **圣女 (Virgin)** 的自动处决机制与提名链中断。
  - 实现了 **猎手 (Slayer)** 的白天主动技能发动与 AI 战略打击。
  - 优化了 **小恶魔传位 (Star-pass)** 后的身份与伪装继承。
 
### 🛠 修复与架构改进 (Fixes & Improvements)
- 修正了 `_evaluate_team_advantage` 的评分逻辑，平衡了“僵局风险”对好人阵营的影响。
- 修复了 `StorytellerAgent` 的异步扰动逻辑因缺少后端而崩溃的错误。
- `VectorMemory` 增加了自动降级保护，支持在无 Embedding 环境下的稳定运行。
- 完善了说书人控制台的活动流水展示，解决了 `undefined` 字段显示的 UI 问题。

## [alpha0.2_dev] - 2026-04-11

本版本作为 Alpha 0.2 阶段的起始线，沉淀并加固了 Alpha 0.1 期间建立的引擎主流程。

### 🌟 新增特性 (New Features)
- **完备的长期计划管理体系**：新增 `docs/alpha-0.2-plan/` 目录，涵盖从 AI 玩家智能增强、前端迭代到说书人平衡裁量的详细路线图和任务看板。
- **说书人平衡裁量与日志框架**：
  - 新增 `storyteller_balance.py` 与专属平衡裁定验收体系。
  - 支持更好的后台日志生成、输出样本记录（`generate_storyteller_balance_samples.py`），优化模拟裁定体验。
  - 说书人智能已可对酒鬼、间谍等特殊角色的触发进行更高层维度的决策。
- **录像回放与解析器**：新增 `replay_parser.py` 解析器支持，增强了后端引擎回溯调试的能力。
- **自动化验收链路全面升级**：为不同子系统提供了针对性的独立验证脚本。
  - `night_info_acceptance.py`：负责夜晚私密信息链断言验证
  - `nomination_acceptance.py`：负责各类提名环节流转逻辑约束和断言
  - `role_acceptance.py` & `storyteller_acceptance.py`：负责角色能力及说书人裁断的综合判定
  - `frontend_acceptance.py`：负责验收前、后端 WebSocket 连接和 API 通信契约
  - Wave 1 & Wave 2 的总体流程测试套件完善。

### 🛠 修复与架构改进 (Fixes & Improvements)
- 根除了前端的局间状态污染机制，修正了 `index.html` 中的轮次历史缓存溢出和错误。
- 优化了 `game_loop.py` 主循环：细化了阶段（Phase）更迭、事件投递与死者信息的播报时机，减少了 AI 行为错位现象。
- 完善了核心 API 服务 (`server.py`) 中客户端掉线重连的状态处理，重开局状态彻底解耦。
- `test_orchestrator` 下增加大量单元与集成测试，覆盖说书人决策、夜间阶段等各类异常情况处理。
