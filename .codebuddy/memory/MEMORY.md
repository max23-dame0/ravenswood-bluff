# 鸦木布拉夫小镇 (Ravenswood Bluff) 项目长期记忆

> 最后更新：2026-07-31
> 仓库：`d:/ravenswood-bluff` | 分支：`main`
> **硬上限**：200 行。超出时 AI 需自行精简历史记录，将细节移入子文件。

## ⚠️ 启动链

你是 coding agent。读取本文件后，**必须**依次读取：

```
MEMORY.md（本文件）→ AGENTS.md（操作手册）→ PROGRESS.md → DECISIONS.md
```

再根据任务模块加载 `.codebuddy/rules/` 下对应的规则文件。

---

## 1. 项目定位

基于多 Agent + 状态机驱动的《血染钟楼》(Blood on the Clocktower, Trouble Brewing 剧本) 社交推演引擎。LLM 驱动的 AI 玩家与 AI/人类说书人，配合通过浏览器 WebSocket UI 的人类玩家共同对局。当前阶段 **Alpha 1.1**（内部测试，难度系统 + 速度/质量优化 + 模块化重构已完成，待 live 真人验收）。

## 2. 技术栈

- 语言/运行时：Python 3.11+（建议 venv，依赖见 `pyproject.toml`）
- Web 框架：FastAPI + WebSocket + Pydantic v2
- 持久化：aiosqlite（SQLite）
- LLM 抽象：`OpenAI` 兼容接口 / `MockBackend`（模式匹配，离线）
- 测试：pytest + pytest-asyncio（`asyncio_mode=auto`）；ruff 做 lint
- 许可：MIT

## 3. 模块速查

| 模块 | 路径 | 职责 |
|------|------|------|
| 智能体 | `src/agents/` | AI 玩家(storyteller)；`ai_agent.py`/`storyteller_agent.py` 为 facade，分别委托 9 个子模块 |
| 规则引擎 | `src/engine/` | 阶段机、规则校验、角色能力、剧本分发、数据采集 |
| 编排 | `src/orchestrator/` | `game_loop.py` 为 facade；EventBus、InformationBroker、各阶段处理器 |
| 状态 | `src/state/` | 不可变 GameState、SQLite 持久化、事件日志、快照 |
| LLM | `src/llm/` | `LLMBackend` 抽象（openai / mock） |
| API | `src/api/` | FastAPI + WebSocket server |
| 内容 | `src/content/` | 剧本与术语定义 |
| 测试 | `tests/` | 单元/集成/验收（默认 MockBackend）；替身单一来源 `tests/doubles.py`；深度参考 `docs/reference/test-system.md` |
| 脚本 | `scripts/` | 验收门禁、导出、模拟、基准 |

## 4. 核心基础设施

- **不可变状态机**：`GameState`(frozen Pydantic) 为唯一真相源；所有迁移经 `with_update*` 返回新快照。
- **事件总线 + 信息代理**：所有状态变更经 `EventBus.publish`；`InformationBroker` 按 `Visibility` 枚举过滤，产出 `AgentVisibleState`。
- **双 facade 上帝对象**：`ai_agent.py`(~1100)、`game_loop.py`(~766) 仅做路由，逻辑在各自子模块（改行为进子模块）。
- **难度系统**：`DifficultyPreset` 五轴（competence/deception/volatility/expressiveness/information_openness）× 4 预设。

## 5. 关键状态与术语

```
GamePhase: SETUP → FIRST_NIGHT → DAY_DISCUSSION → NOMINATION → VOTING → EXECUTION → NIGHT → GAME_OVER
Visibility: PUBLIC / TEAM_EVIL / TEAM_GOOD / PRIVATE / STORYTELLER_ONLY
Team: GOOD(镇民/外来者) / EVIL(爪牙/恶魔)
DifficultyLevel: CASUAL / STANDARD / MASTER / CHAOS
后端: mock(离线) / openai(Live) / auto
胜负: 恶魔全亡→GOOD；仅剩≤2活且含恶魔→EVIL；市长特例(3活且今日未处决→GOOD)
```

## 6. 硬约束

- GameState 不可变；用 `with_update / with_player_update / with_event / with_message`。
- Agent 只接收 `AgentVisibleState`，绝不直接传 `GameState`。
- 事件 `visibility` 必须正确；`TEAM_EVIL` 不得入 `PUBLIC`。
- 改 Agent/Orchestrator 行为 → 改对应子模块，勿堆在 facade。
- 白天发言顺序处理，禁 `asyncio.gather` 最终发言。
- 双超时预算：orchestrator 预算必须 > agent 预算。
- Good AI 绝不得注入 evil strategy 提示（先查 `player.team`）。

## 7. 禁止事项

- ❌ 直接赋值 `state.players[idx].field`（用 `with_player_update`）
- ❌ 将 `GameState` 直传 Agent
- ❌ 泄露 evil 信息到 PUBLIC 可见事件
- ❌ 在 facade 文件内堆逻辑
- ❌ 并行 `asyncio.gather` 白天最终发言
- ❌ 仅靠 mock 通过即宣称完成（需 live 真人验收）

---

## 🤖 Auto Memory（AI 自主维护）

> 以下区域由 AI 在会话中自动追加。每次发现重要模式、踩坑经验、偏好决定时，AI 应将关键信息追加到此区域。
> **管理规则**：随时可追加（日期 + 内容）；超过 50 行自行精简；用户可自然语言控制"记住 X / 忘掉 Y"；不要把已明确的信息重复写入。

<!-- AUTO_MEMORY_START -->
- 2026-07-31 测试系统治理：① 代码去重——`DummyBackend` 等替身统一至 `tests/doubles.py`（唯一源），`conftest.py` re-export，3 个回归/推理测试文件改为 import；`DummyBackend` 加可配置 `content`（默认中文串，回归用 `content="{}"` 保持旧行为）。② 文档——新增 `.codebuddy/rules/tests.md`（测试规则）、`docs/reference/test-system.md`（测试系统参考，含 9 gate 验收）、`docs/reference/tech-traps.md` 增 T10-T12；`AGENTS.md`/`DECISIONS.md`(D007/D008)/`MEMORY.md` 同步接入。详见 `DECISIONS.md` D007(测试策略 MockBackend-first+门禁为发布 blocker)、D008(替身统一)。
<!-- AI 在此区域之下追加记忆，保留此标记以便定位 -->
- 2026-07-31 代码与文件规范化整理（P0-P5）完成并验证全绿：① 目录约定见 `DECISIONS.md` D010——根目录只留 `simulate_game.py`；`scripts/` 顶层仅放 4 个入口，其余分 `acceptance/`(27)/`benchmark/`(5)/`export/`(5)/`debug/`(3)，**子目录脚本用 `parents[2]`**；`tests/` 按被测模块分子目录（`test_simulate_game.py` 例外留根）；`docs/` 分 plans/releases/reviews/guides/reference 五类，但**被代码硬编码写入的文档必须留 `docs/` 根**（`frontend_acceptance.md`、`alpha-1.0-benchmark-results.md`、`alpha-1.1-evidence/`）。② **移动脚本的最大坑（D011）**：除聚合入口外，「叶子脚本调用兄弟脚本」的 subprocess 路径也必须同步，本次漏掉造成 9 个测试断链；`run_script(name)` 的 `name` 语义统一为「相对 `scripts/` 根」。③ ruff 阶段一（E4/E7/E9/F/W，ignore E501）已零告警，`scripts/**` 全局豁免 E402（`sys.path` bootstrap 模式）；format 已 100% 归一，pre-commit + CI 均为硬门禁。④ 验证基线：`pytest tests -q` = **447 passed / 0 failed**，`scripts/alpha1.1_acceptance.py` = **exit 0（9/9）**。

- 2026-07-31 文档治理收尾（doc-governance 增强 + 健康核对）：① 清理上轮治理遗留临时脚本（`.codebuddy/tmp_*.ps1/.py` 与 `docs/.gov_body.md`）；② 增强——`docs/README.md` §7 登记 29 个 `alpha-1.1-evidence/` 证据文件名（frontmatter 豁免），新增 `scripts/check_doc_health.py`（frontmatter+死链校验，绝对路径为非致命告警、`--strict` 升级为失败）作 CI 门禁；③ 健康核对——AGENTS/CLAUDE/MEMORY/DECISIONS 路径均有效（`docs/` 已重组为 plans/reference/releases/reviews/，参考文档在 `docs/reference/`）；④ 修复历史文档中的绝对机器路径断链（原指向不存在的 `鸦木布拉夫小镇` 路径，曾被误清空为 `]()`，已用相对路径修复，含 `game_loop.py`/`server.py` 等源码链接与中文描述性文档链接）。
- 教训（PowerShell 5.1 脚本）：① 读 `.ps1` 按 ANSI 而非 UTF-8，含中文会乱码致解析失败——脚本避免中文或显式写 BOM；② 相对链接改写用「文件深度 + 仓库相对路径」手动计算，勿用 `System.IO.Path.GetRelativePath`（本机 .NET Framework 无此方法会抛 MethodNotFound）；③ 批量改写语料前先备份/可回退，先小规模验证再全量。
- 2026-07-31 ruff 阶段二全部启用（D009 收官）：`select` = E4/E7/E9/F/W/I/UP/B/SIM；`ignore` = E501 + **UP042**（`str,Enum`→`StrEnum` 改 `str()` 行为，禁自动修）。**flaky 模式（重要）**：`GameState.game_id` 默认 `uuid.uuid4()`；任何用 `GameState()` 构造状态而**未固定 `game_id`** 的测试，其 `AgentVisibleState.game_id` 随机 → `DecisionNoise` 噪声种子随机 → 依赖阈值的决策（如提名）跨运行随机成败。**测试补丁**：构造器必须固定 `game_id`。另：`nomination_voting.py` 的提名循环内定义异步函数若引用循环变量（`player`/`action_type`），须用**默认参在定义时捕获**（`player_id=player.player_id`），否则 asyncio 任务真正运行时取到循环末值（B023 闭包延迟绑定真 bug）。基线：`ruff check src tests scripts` = 0 告警；`pytest tests -q` = 447 passed / 0 failed。
<!-- AUTO_MEMORY_END -->

---

## 下一步

读完本文件 → 立即读 `AGENTS.md`（含会话工作流、编码规范、分层规则加载指引）。
