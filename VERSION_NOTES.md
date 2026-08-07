# Alpha 1.2「觉醒之鸦」(The Awakening) 内部测试版本说明

当前版本口径：`alpha1.2-awakening`。

Alpha 1.2「觉醒之鸦」是《鸦木布拉夫小镇》的架构级演进版本，将 AI 玩家从"集中式调度 + 单次无状态 LLM 调用"演进为**受控自主 Agent**：保留 orchestrator 作为规则裁判与调度器，将行动标准化为工具调用、世界状态按需查询、记忆维护工具化，并引入跨局玩家进化机制。同时达成 token 控制目标。

## 面向玩家与内测者的变化

- **更拟人的 AI 玩家**：AI 玩家拥有跨局长期记忆，会随对局累积"局后复盘 / 局中反思 / 学习他人打法 / 调整策略"，逐渐形成个人打法倾向（更激进或更谨慎），表现更接近有记忆的人类玩家。
- **白天发言动态响应**：AI 白天发言按座次与人/机穿插进行，后发言者会基于场上最新发言精炼自己的表达，不再照念预生成草稿。
- **记忆对局隔离**：每局记忆独立存放，避免跨局串味。
- **说书人进化**：说书人跨局累积主持经验与扭曲率画像。
- **修复无人提名**：AI 更积极地推动提名（day>=2 主动提名、LLM 放弃时本地兜底），对局节奏更紧凑。

## 面向开发者的重构与优化

- **行动工具化**：`GameActionToolRegistry`（8 个 ToolDef），`act()` 工具调用主导 + JSON fallback。
- **世界感知查询化**：`WorldTools` 4 只读工具；system prompt 三层前缀稳定化，跨 agent 共享公共规则前缀（缓存命中率提升基础）。
- **策略先行 loop**：`think` → `act`，`cached_speech_draft` 草稿直接复用（有草稿时 0 次 LLM，输出减半）。
- **记忆工具化**：`MemoryTools` append/read/reflect/archive。
- **说书人工具注册表**：6 工具 + `DistortionStrategy` 枚举化 + `BOTC_ST_LLM_STRATEGY=off` 行为兼容。
- **Token 控制（PLN-037）**：策略表（简单动作关 thinking、发言降 effort、claim/reflect 限 token）、usage 扩展解析（cache hit/miss + reasoning_tokens）。
- **Prompt 缓存优化（PLN-039）**：全局静态层 + 双层 system + tools 全量固定，live 命中率 12.7%→43-53%。
- **深度思考分级（AI_THINKING_LEVEL）**：按难度预设 off/low/medium/high，`reasoning_content` 记录 + `thoughts.jsonl` 落盘 + Scavenge 机制恢复 thinking 块内的工具调用。
- **拟人化玩家进化（PLN-038 阶段E）**：跨局档案四维 + `tendency` 画像 + 局末自动触发复盘/学习/调整。

## 发布前校验与复现

```text
pytest tests -q -m "not slow"       → 477+ passed / 0 failed
ruff check src tests scripts         → 0 告警
scripts/alpha1.1_acceptance.py      → 9/9 exit=0
scripts/benchmark/token_budget_benchmark.py → RESULT: PASS
```

完整发布门禁与验收记录见 `docs/releases/alpha-1.2-release-checklist.md`。

---

# Alpha 1.1 内部测试版本说明

当前版本口径：`alpha1.1`。

Alpha 1.1 是《鸦木布拉夫小镇》的重大优化与重构版本。相较于 Alpha 1.0 “稳定跑完对局”的目标，Alpha 1.1 的焦点是“值得反复玩”与“流畅的真实对局体验”。该版本正式引入了 AI 玩家难度系统，实施了深度的响应速度工程优化，修复了高延迟下的发言质量退化，并对核心的庞大对象（AIAgent 与 GameOrchestrator）进行了彻底的模块化重构。

## 面向玩家与内测者的变化

- **AI 玩家难度选择**：前端 Setup 页面新增了 4 种难度模式单选控件（休闲、标准、大师、混沌），且支持中英文国际化语言切换。
- **让 AI 拥有“博弈策略”与“性格”**：
  - **休闲模式 (Casual)**：AI 发言更具叙事感和情绪化，推理较浅，适合新手。
  - **标准模式 (Standard)**：基准对局体验，逻辑与叙事结合。
  - **大师模式 (Master)**：AI 拥有更低的决策随机度，邪恶方能制定精细的信息释放节奏与进攻型欺诈策略，带来深度的社交推理挑战。
  - **混沌模式 (Chaos)**：具备较高的决策随机度，AI 会采纳情绪化提名或非理性投票，每局充满新鲜感与不确定性。
- **决策噪声与不可预测性**：提名和投票中注入了受控的随机噪声，AI 的行为不再完全可预测，但保留了基本的游戏规则和逻辑护栏。
- **更流畅的等待体验**：大幅压缩了多人对局下的发言、提名与投票等待时间，消除了高并发延迟。

## 面向开发者的重构与优化

- **上帝对象模块化分解**：
  - `src/agents/ai_agent.py` 从 3500 行分解为薄 Facade 加上 9 个职责单一的子类（推理、决策、提示词工厂、发言过滤、欺诈追踪等）。
  - `src/orchestrator/game_loop.py` 从 2900 行分解为薄 Facade 加上 9 个子系统（魔典管理、信息分发、阶段处理器等）。
  - 利用 Python 的模块重导出机制保持对外接口完全兼容，无需修改任何外部导入端。
- **响应速度工程 (Speed Engineering)**：
  - **本地策略优先**：投票和提名动作默认执行本地高速判定，只有在复杂局势下才调用 LLM（P95 响应时间从数秒降至 ~0ms）。
  - **发言异步预生成**：实现 `SpeechPreGenCache`，在其他玩家行动时后台并发生成发言草稿，轮到自己发言时仅进行瞬时微调即可发布。
  - **硬超时门禁**：对每个 AI 动作设立硬耗时上限，超时安全回退到本地合法 fallback 动作，绝不卡死游戏主线程。
- **对话质量修复**：
  - 取消讨论轮次的并发 LLM 请求，改为顺序处理以确保后位 AI 基于最新发言情景做决策，解决发言“复读机”问题。
  - 优化了 fallback 发言选择算法与模板库，确保即使发生超时也不会输出完全重复的空话。
  - 将 `_extract_claims_via_llm()` 身份提取逻辑改为异步非阻塞任务，其失败不会阻塞正常的发言投递，亦不会污染 UI 日志。

## 发布前校验与复现

我们已经建立了完善的 Alpha 1.1 发布验收大门，所有 9 个 Gate 均通过了自动化验收，门禁结果如下：

```text
alpha1.1 acceptance summary
========================================================================
PASS existing tests regression           5.7s
PASS agent reasoning tests               1.0s
PASS difficulty acceptance               0.4s
PASS difficulty comparison               0.5s
PASS difficulty behavior acceptance      0.5s
PASS ai speed acceptance                43.0s
PASS ai conversation quality             0.9s
PASS ai live-like speech              3m 0.8s
PASS alpha1 backward compatibility       1.2s
========================================================================
passed: 9
failed: 0
skipped: 0

alpha1.1 acceptance: ok
```

运行以下命令可一键复现全部门禁：
```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```
