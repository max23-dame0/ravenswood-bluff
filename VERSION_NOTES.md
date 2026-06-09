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
