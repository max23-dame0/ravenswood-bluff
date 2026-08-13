# DECISIONS — 架构决策记录

> 记录关键设计决策及原因。**上班必读**，避免新会话推翻已有决定。
> 格式：日期 + 决策 + 原因 + 否决方案 + **回退/可逆方案** + 约束条件（L05 标准）

---

## D001: 项目 Harness 体系采用五子系统架构

- **日期**：2026-07-30
- **决策**：采用 Harness Engineering 五子系统模型（指令+工具+环境+状态+反馈），通过入口文件 `AGENTS.md` / `PROGRESS.md` / `MEMORY.md` / `DECISIONS.md` 四个核心文件 + 分层规则建立 coding agent 工作环境。已有全面的 `CLAUDE.md` 作为深度参考，harness 文件仅做轻量路由与状态追踪层。
- **原因**：结构化 harness 可提升跨会话连续性，渐进式披露避免上下文溢出。
- **否决方案**：纯 Prompt 驱动（无结构化 harness 文件，上下文效率低、跨会话无法连续性）。
- **回退/可逆方案**：harness 文件均为 Markdown，可随时 `git revert`；误伤某规则删该行即可，无代码级风险。
- **约束**：所有 Agent 会话必须遵守入口文件中的上班/下班/WIP 显式登记流程。

## D002: 规则采用 MDC 风格分层管理

- **日期**：2026-07-30
- **决策**：项目规则按作用域（global → 模块 → 文件级）分层管理，每个规则文件用 YAML frontmatter 声明生效条件（globs / alwaysApply）。
- **原因**：避免一次性全量加载所有规则导致上下文溢出，支持 `src/` 下多模块差异化规则。
- **否决方案**：所有规则写入单文件（上下文预算不可控）。
- **约束**：规则文件 < 80 行，入口文件 < 200 行，MEMORY.md < 200 行。

## D003: 状态不可变 + 事件溯源

- **日期**：2026-05-08（源自 CLAUDE.md §3.3 / §8.1）
- **决策**：`GameState` 为 frozen Pydantic 模型，所有迁移经 `with_update / with_player_update / with_event / with_message` 返回新快照；orchestrator 持有权威 `self.state`。
- **原因**：不可变快照支撑复盘/调试与时间旅行调试，避免并发状态污染。
- **否决方案**：可变共享状态（易引发阶段处理器间脏写）。
- **回退/可逆方案**：无（核心设计）；任何破坏不可变性的改动须单独评审。

## D004: 信息隔离经 InformationBroker + Visibility 枚举

- **日期**：2026-05-08（源自 CLAUDE.md §3.3 / §8.3）
- **决策**：Agent 只接收 `AgentVisibleState`（按 `Visibility` 过滤后的视图），绝不直接接触 `GameState`；evil 私聊用 `ChatMessage(recipient_ids=[...])`。
- **原因**：防止信息泄露破坏游戏平衡（TEAM_EVIL 不得入 PUBLIC）。
- **否决方案**：向所有 Agent 广播全量状态。
- **回退/可逆方案**：仅调试开关可临时放开可见性。

## D005: 难度为五轴配置而非单一 temperature

- **日期**：2026-05-08（源自 CLAUDE.md §3.3 / §8.4）
- **决策**：`DifficultyPreset` 用 competence/deception/volatility/expressiveness/information_openness 五轴 × 4 预设（CASUAL/STANDARD/MASTER/CHAOS）。
- **原因**：单 temperature 无法表达"善意的谎言""信息释放节奏"等难度维度。
- **否决方案**：仅用 temperature 控制难度。
- **约束**：新增难度轴须为 4 预设全设值，并由 `difficulty_behavior_acceptance.py` 验证产生行为差异。

## D006: 双 facade 上帝对象仅做路由

- **日期**：2026-05-08（源自 CLAUDE.md §9.1/§9.2）；2026-07-31 复核并更新状态
- **决策**：`ai_agent.py`、`game_loop.py` 为 facade，行为逻辑下沉到各自子模块（agents 下 decision/prompt/speech/observation/strategy/memory/reasoning/dialogue/persona/deception；orchestrator 下 phases/agents/claims/grimoire/info/metrics/settlement）。`storyteller_agent.py` 同属 facade，须一并治理。
- **原因**：控制单文件规模，提升可维护性。
- **否决方案**：逻辑全堆在 facade。
- **约束**：改 Agent/Orchestrator 行为 → 改对应子模块，勿堆在 facade。
- **当前状态（2026-07-31 复核，已达标 ✅）**：三 facade 已全部拆分并达行数目标——`ai_agent.py` = 802（<1000）、`game_loop.py` = 497（<700）、`storyteller_agent.py` = 25（<1100）；逻辑分别下沉至 `ai_agent_delegation.py`(706) / `game_loop_delegation.py`(383) / `storyteller_delegation.py`(1369)，行为零变更。落地方式为「facade 继承委托 Mixin/委托类」，调用点保持 `self._x(...)`（详见重构计划文档）。
- **重构计划**：`docs/releases/v0.8/AGENTS_refactor.md`（目标已达成；含实际委托拆分映射与进度看板）。

## D007: 测试策略 — MockBackend-first + 验收门禁为发布 blocker（2026-07-31）

- **日期**：2026-07-31
- **决策**：项目测试遵循 MockBackend-first——默认 `BOTC_BACKEND=mock` 离线运行，不依赖真实 LLM/API key；每测试自建 SQLite 避免锁竞争。`scripts/alpha1.1_acceptance.py` 聚合 **9 个验收 gate**（回归/推理/难度×3/速度/对话/拟真发言/向后兼容），任一失败返回非 0，**为发布 blocker**。
- **原因**：mock 毫秒级跑完整套单测，可复现、可 CI；但 mock 全绿 ≠ 完成，live（真实 LLM）行为仍须真人验收（见全局规则）。
- **否决方案**：依赖真实 LLM 跑单测（慢、非确定、需 key、易 CI 抖动）。
- **回退/可逆方案**：门禁脚本独立，移除 `scripts/alpha1.1_acceptance.py` 调用即可降级为纯 pytest。
- **约束**：发布前 9 gate 须全绿；mock 通过不得单独宣称功能完成。

## D008: 测试替身统一至 tests/doubles.py（2026-07-31）

- **日期**：2026-07-31
- **决策**：所有 LLM / Agent / 说书人测试替身（`DummyBackend` / `CapturingBackend` / `ScriptedAgent` / `DummyAgent` / `DummyStoryteller`）统一定义在 `tests/doubles.py` 作为**唯一来源**；`conftest.py` re-export，3 个仍残留本地定义的测试文件改为 `from tests.doubles import ...`。`DummyBackend` 加可配置 `content` 参数（默认中文占位串，回归测试用 `content="{}"` 保持旧行为）。
- **原因**：原先 `DummyBackend` 在 `conftest.py` 与 4 个测试文件各自重复定义，违反"仓库即唯一真实来源"，改动易漏同步。
- **否决方案**：保留各文件重复定义（维护噩梦）。
- **回退/可逆方案**：`git revert tests/doubles.py` 即回退；替身纯测试侧，无生产代码风险。
- **约束**：禁止在测试文件重复定义替身；变体继承 `tests.doubles` 中的类。

## D009: ruff 规则集渐进启用（2026-07-31）

- **日期**：2026-07-31
- **决策**：`pyproject.toml` 显式声明 ruff 规则集，分两阶段。**阶段一（已生效并已收敛到零告警）**：`select = ["E4","E7","E9","F","W"]` + `ignore = ["E501"]`；配套 `[tool.ruff.lint.isort]`（`known-first-party = ["src","tests"]`）、`[tool.ruff.lint.per-file-ignores]`（conftest/`__init__.py` 豁免 F401；`tests/test_agents/test_vector_memory.py` 与 `scripts/**/*.py` 豁免 E402）、`[tool.ruff.format]`。存量 112 项告警的处置：F401(20)/F541(8) 经 `ruff check --fix` 自动收敛；E402(76) 全部落在 `scripts/**`，属 `sys.path.insert(REPO_ROOT)` bootstrap 后再 import 的预期模式，加 per-file-ignores 而非改代码；F841(7)/E712(1) 手工清理死变量与 `== False` 比较。**阶段二（待启用）**：`I` → `UP` → `B` → `SIM` 逐族开启，每族先 `ruff check --statistics` 摸底再单独提交。
- **原因**：静态摸底发现存量违规集中在三处——超 100 字符行大量存在（E501）、26 个文件用 `from typing import List/Optional`（UP006/UP007/UP035）、多处 `= Path(...)` 默认参数（B008）。一次性开全会产生大批告警，与"整理不改语义"冲突；且本次整理所处环境无 Python，无法用 `--fix` 收敛。
- **否决方案**：① 一次性开启严格规则集（告警爆炸、需大范围改代码）；② 完全不配置沿用 ruff 默认（行为不可复现，达不到"配置完整"目标）。
- **回退/可逆方案**：全部为 `pyproject.toml` 声明式配置，删除 `[tool.ruff.lint]` 段即回到默认行为；`.pre-commit-config.yaml` / `.github/workflows/ci.yml` 可独立删除。
- **约束**：① `ruff format --check src tests scripts` 实测 182 文件全部已符合（无需一次性 format 提交），故已启用 pre-commit 的 `ruff-format` 钩子并移除 CI 该步骤的 `continue-on-error`，format 自此为硬门禁；② `[tool.pytest.ini_options].pythonpath = ["."]` 是根级 `simulate_game.py` 可被测试 import 的前提，禁止删除。

## D010: 代码与文件组织规范（2026-07-31）

- **日期**：2026-07-31
- **决策**：
  1. **根目录**：只保留 `simulate_game.py` 一个 .py（根级 CLI 入口）；部署文件 `Dockerfile` / `docker-compose.yml` / `run_server.bat` 留根。零引用的临时脚本一律删除。
  2. **scripts/**：顶层只放用户/CI 直接调用的入口（`alpha1.1_acceptance.py`、`alpha1_acceptance.py`、`alpha3_acceptance.py`、`check_doc_health.py`），其余按用途分入 `acceptance/`（被聚合调用的 gate）、`benchmark/`、`export/`、`debug/`。子目录脚本 `REPO_ROOT = Path(__file__).resolve().parents[2]`。详见 `scripts/README.md`。
  3. **tests/**：按被测模块归入 `test_<模块>/` 子目录；例外是 `test_simulate_game.py`——被测对象是根级 CLI 而非 `src` 七包之一，随入口留在 `tests/` 根。
  4. **docs/**：分 `plans/` `releases/` `reviews/` `guides/` `reference/` 五类；**被代码硬编码写入的文档保留在 `docs/` 根**（`frontend_acceptance.md`、`alpha-1.0-benchmark-results.md`、`alpha-1.1-evidence/`），移动它们等于改运行时行为。
  5. **src/agents/**：单一职责模块归入对应子包（`decision_noise.py`→`decision/`、`persona_registry.py`→`persona/`）；`difficulty_presets.py` 是跨 decision/prompt/speech 的横切配置，留在包根。
  6. **历史存证不改路径**：`docs/alpha-1.1-evidence/`、`CHANGELOG.md`、已完成的 `task_m*.md` 中的旧路径是当时事实的快照，不随本次整理改写；只更新"活文档"（AGENTS / CLAUDE / MEMORY / DECISIONS / PROGRESS / `docs/README.md` / `docs/reference/` / `.codebuddy/rules/`）。
- **原因**：入口与实现分离使调用路径稳定（用户与 CI 命令不因整理而失效）；按用途分类降低检索成本；把"代码写入的路径"钉死可避免整理误伤运行时行为。
- **否决方案**：① 把 `simulate_game.py` 也迁入 `scripts/`（被 `tests/test_simulate_game.py` 以模块名 import、3 个脚本以相对路径子进程调用、多份文档引用，收益低于断链风险）；② 把全部脚本平铺重命名为 `动词_对象.py`（重命名面更大，且不解决分类问题）；③ 移动 `alpha-1.1-evidence/`（脚本写入路径，属行为变更）。
- **回退/可逆方案**：全部改动为 `git mv` + 机械路径替换，按 P0-P5 分阶段提交，任一阶段 `git revert` 即可单独回滚。
- **约束**：① 新增 gate 放 `scripts/acceptance/` 并在 `alpha1.1_acceptance.py` 登记完整路径；② 移动任何文件前必须全仓库 grep 引用（含 `subprocess` 字符串、`_script_exists` 检查、md 内联路径）；③ 跨脚本 import 用完整包路径（如 `from scripts.acceptance.ai_evaluation import ...`）。

## D011: 脚本互调一律使用「相对 scripts/ 根」的完整路径（2026-07-31）

- **日期**：2026-07-31
- **决策**：脚本之间以子进程互相调用时，路径基准统一为 `REPO_ROOT / "scripts" / <子目录> / <文件名>`；`wave*_acceptance.py` / `a3_memory_acceptance.py` 内的 `run_script(name)` 辅助函数，其 `name` 参数语义明确为**相对 `scripts/` 根的路径**（如 `"acceptance/frontend_acceptance.py"`、`"debug/persona_divergence_test.py"`），函数内 docstring 已固化该约定。
- **原因**：P3 分目录后，聚合入口的路径被同步更新，但「叶子 gate 调用兄弟 gate」这类二级引用极易遗漏——本次即因此产生 9 个测试回归（`can't open file ...\scripts\storyteller_balance_acceptance.py`）。把参数语义显式钉在 docstring 上，可让后续新增调用一眼看出必须带子目录前缀。
- **否决方案**：① 改成 `Path(__file__).parent / name`（只能调同目录兄弟，`wave3` 需调 `debug/persona_divergence_test.py` 会失效）；② 保持裸文件名 + 遍历各子目录查找（隐式魔法，调错文件时静默 skip，正是本次 `test_storyteller_balance_sample_export` 被静默跳过的成因）。
- **回退/可逆方案**：纯字符串常量，逐行 `git revert` 即可。
- **约束**：新增跨脚本调用必须写全「子目录/文件名」；`subprocess` 调用的脚本若不存在应显式报错，禁止 silent skip。

## D011: 文档治理规范 — 单一语料根 + frontmatter 受控词表 + 证据豁免（2026-07-31）

- **日期**：2026-07-31
- **决策**：文档语料根统一为单一 `docs/`（已删除孤儿 `documents/`）；所有人工文档必须带 frontmatter（`doc_id` / `title` / `category` / `role` / `status` / `date` / `author`），其中 `role ∈ {[State],[Delta],[Cold]}`、`category ∈ {architecture,planning,review,release,report,reference,api,template,spec}`、`status ∈ {draft,review,published,archived,superseded}`；`docs/alpha-1.1-evidence/`（脚本自动产出）豁免 frontmatter，仅在 `docs/README.md` §7 登记文件名索引；`docs/README.md` 为五要素标准索引（场景查找表 / 结构树 / 分类索引 / ADR 索引 / 模板索引）。
- **原因**：frontmatter 受控词表让 Agent 可结构化检索语料、CI 可机械校验（`scripts/check_doc_health.py`）；单一根避免双语料分裂；证据豁免避免对自动产物做低价值 churn。
- **否决方案**：① 迁到 doc-governance 技能默认 `documents/` numbered 目录（churn 巨大、易断链）；② 仅给顶层文档加 frontmatter（子目录内细分仍不可检）。
- **回退/可逆方案**：frontmatter 为纯文本头，删除即回退；`check_doc_health.py` 为独立脚本，移除调用即不影响运行。
- **约束**：① 新增人文档必须带完整 frontmatter；② 文档链接须为相对路径（禁止绝对机器路径 `/d:/...`、`file:///`）；③ 改 `docs/` 布局前先全仓 grep 引用。

## D012: Agent 原生重构落地（PLN-038 阶段 A/B/S/C/D + PLN-037 P0/P1/P2 协同）

- **日期**：2026-08-03
- **决策**：① 行动工具化——新建 `GameActionToolRegistry`（8 个 ToolDef），`act()` 以 tool calling 为主导、JSON 为 fallback；② 策略先行 loop——`MemoryController.think` 升级为低预算 LLM 内心独白，`AIAgent.act_with_strategy()` 为策略入口；③ 说书人工具注册表（6 工具），`choose_distortion` 收敛为 `DistortionStrategy` 枚举（值=旧字符串，审计兼容），`BOTC_ST_LLM_STRATEGY=off|low|on` 默认 off（行为与重构前一致）；④ 记忆工具化（append/read/reflect/archive + 落盘 `data/agents/{player_id}/` + 隔离校验）；⑤ 世界感知查询化（observe_state/query_public_log/query_players/query_legal_context + 三层前缀稳定化）；⑥ LLM 策略表（简单动作关思考、发言降 effort/限 max_tokens）、usage 解析扩展（cache hit/miss + reasoning_tokens）、speak 草稿复用（有草稿时 0 次 LLM）。
- **原因**：agent 从「集中式提示词调用」演进为「受控自主 agent」，同时达成 PLN-037 token 控制目标（speak 输出减半、前缀可缓存、简单动作零思考）。
- **否决方案**：大爆炸式全量工具化（改动面失控）；LLM 全程决策（破坏说书人确定性红线）。
- **回退/可逆方案**：`BOTC_ST_LLM_STRATEGY` 默认 off 即行为兼容；工具注册表是独立模块，可整体移除；三层前缀是纯字符串重组，逐行 revert 即可。
- **约束**：① 说书人真实信息计算保持确定性，LLM 仅影响「是否/如何扭曲」；② 记忆工具写入必须过隔离层（sensitive/private 拒绝）；③ 工具 schema 为稳定字符串（缓存前缀，禁运行时拼接状态）；④ 新增动作类型必须先注册 ToolDef 再接策略表。

## D013: 记忆对局隔离 + 玩家/说书人进化机制（PLN-038 阶段 E）

- **日期**：2026-08-04
- **决策**：① 记忆对局隔离——`MemoryTools` 单局记忆落盘 `data/agents/{player_id}/games/{game_id}/memory.jsonl`，无 `game_id` 回退玩家根目录；② 玩家进化机制——新建 `PlayerProfileStore`（`profile.json` 战绩统计 + `long_term_memory.jsonl` 跨局经验），AIAgent 在 setup 时 `load_player_profile()`、GAME_OVER 时 `finalize_game_lesson()`，跨局经验经敏感过滤后注入 `act()` 的 stable_context（同局内稳定，不破坏前缀缓存）；③ 说书人进化——`StorytellerProfileStore` + `StorytellerAgent.finalize_game_profile()`，局末统计决策账本（判决数/扭曲数）落盘 `data/storyteller/profile/`。
- **原因**：原记忆固定 `data/agents/{player_id}/` 导致跨局串味；用户要求每个 AI 玩家拥有"个人玩家视角"的长期记忆库，以实现玩家进化——agent 随对局累积经验、水平精进、表现更接近有记忆的人类玩家。说书人同理。
- **否决方案**：① 把跨局经验直接并入 persona 参数（会与角色能力耦合、污染人格稳定性）；② 局末用 LLM 蒸馏经验（LLM 故障时无兜底，且增加 live 成本——当前用规则模板，留后续演进）。
- **回退/可逆方案**：`game_id` 目录为纯路径变更，无 `game_id` 时回退旧路径；`PlayerProfileStore` 是独立模块可整体移除；跨局注入仅增加 stable_context 首段，删掉 `build_long_term_context()` 调用即回退。
- **约束**：① 跨局经验注入前必须过敏感过滤（恶魔/队友名单等）；② 战绩/胜负/角色一律来自 `settlement_report`（确定性），LLM 不参与局末提炼；③ 跨局摘要必须放在 user 首条 stable_context（同局内逐 token 稳定），不得混入动态段；④ `games/{game_id}/` 只存本局记忆，跨局档案只存可复用经验。

## D014: 拟人化进化机制（局中反思 / 局后复盘 / 学习他人 / 调整策略）

- **日期**：2026-08-04
- **决策**：在 D013 玩家进化基础上增强为四个拟人化维度（参考人类玩家水平增长机制）：① **局中反思**——`PlayerProfileStore.add_reflection()`（`reflections.jsonl`），AIAgent 暴露 `add_in_game_reflection()`，沉淀对局中的自我校正；② **局后复盘**——`add_game_review()`（`game_reviews.jsonl`）+ `finalize_game_review()`，局末记录"赢在哪/败在哪/下次怎么改"并微调倾向；③ **学习他人经验**——`learn_from_others()`（`lessons_learned.jsonl`），game_loop 局末从**胜方表现最好的玩家**提炼角色通用战术写入所有 AI 玩家；④ **调整策略**——`evolve_strategies()`（`strategies.jsonl`）+ `tendency` 四维画像（aggression/risk_taking/talkativeness/caution），基于胜负/阵营规则微调 + 轻微随机扰动，`build_evolved_tendency_summary()` 生成可注入的"打法倾向"。`build_long_term_summary()` 综合战绩+倾向+复盘+学到的打法+经验教训，注入 `act()` 的 stable_context 首段。
- **原因**：用户要求进化设计更拟人——人类玩家水平增长来自局中反思、局后复盘、观察高手、调整自我认知四类机制；单一"经验教训"过于单薄，无法让 agent 表现随对局持续精进。
- **否决方案**：① 仅靠 LLM 蒸馏复盘（live 成本高、失败无兜底——当前倾向微调为规则驱动 + 确定性，留后续演进）；② 让倾向直接改变人格 persona 参数（会污染人格稳定性、与其他难度覆盖冲突——独立 `tendency` 画像不触碰 persona_profile）。
- **回退/可逆方案**：四维存储是独立 JSONL 文件，删除即回退；`_derive_tendency_delta` 仅微调 `tendency` 字段（±0.02 级），不影响既有行为；`_learn_from_strong_players` 是独立钩子，移除即关闭学习。
- **约束**：① 学习他人经验只提炼**角色通用战术**，禁止携带该玩家私密信息/真实身份；② 倾向微调范围 0.05~0.95，增量 ±0.02 级防失控；③ 复盘/反思/学习均须过敏感过滤（恶魔/队友名单等）；④ 所有落盘 JSONL 保持向后兼容（旧 `profile.json` 自动合并新字段）。

## D015: speak/defense_speech 关闭 thinking（live 实测 token 优化）

- **日期**：2026-08-04
- **决策**：将 `LLM_STRATEGY_BY_ACTION` 中 `speak` 与 `defense_speech` 的 `thinking` 从 `enabled` 改为 `disabled`（保留 `reasoning_effort=low`、`max_tokens=400`）。
- **原因**：DeepSeek 推理模型实测——工具调用路径（主路径）本就 `reasoning_tokens=0`，`thinking=enabled` 不带来额外推理质量；但 JSON fallback 路径 `thinking=enabled` 会烧 356-400 reasoning tokens 并导致空响应/`JSONDecodeError`（fallback 率 5.9%）。改 `disabled` 后三局 live 对比：total_tokens 7365→2848（-62%）、fallback 5.9%→0%，5 玩家发言正常（草稿复用 0 token）。
- **否决方案**：① 保持 enabled（live 空响应/JSON 解析失败高发，浪费 token）；② 完全删除 speak 的 LLM 调用（牺牲发言质量，草稿复用已处理常见场景，仍需 LLM 处理复杂局势）。
- **回退/可逆方案**：改回 `"thinking": "enabled"` 即可恢复原策略；`_llm_strategy_for_action` 返回值可被单测断言。
- **约束**：① 该策略面向 deepseek 等推理模型有效，切换非推理模型（如 GPT-4o）时需重新评估是否恢复 enabled；② `reasoning_effort=low` 保留（不破坏 `test_llm_strategy` 断言）；③ 工具调用主导（PLN-038 阶段A）是此优化的前提——工具路径不依赖 thinking。

## D016: 工作流 + RAG 融入落地（PLN-041）

- **日期**：2026-08-12
- **决策**：① **检索基础设施**——新增 `src/agents/memory/retrieval/`（chunker 分块 / BM25 稀疏检索 / Faiss 稠密可选 / RRF 融合 / RetrievalStore 落盘 `data/agents/_retrieval/` / RetrievalPipeline 统一注入管线），依赖 `rank-bm25`（必装）+ `numpy`/`faiss-cpu`（可选，缺失自动降级 BM25-only）；② **规则书静态注入**——`src/content/rule_knowledge.py` 从 terms + night_order + RoleDefinition 导出结构化条目，`build_role_rulebook_context` 在 AIAgent setup 期注入 stable_context 首段（同局稳定、零缓存破坏），直接约束"角色能力边界/阵营红线"发言幻觉；③ **工作流引擎**——`src/agents/workflow/`（Workflow DSL：ToolCallNode/ConditionNode/ParallelNode + WorkflowEngine 调度/超时/重试 + WorkflowTrace 落盘回放），说书人裁决 6 工具编排为显式工作流试点（包装非重写、LLM 仅保留 choose_distortion 节点）；④ **玩家行动轨迹**——`ActionTrace` 落盘 `data/agents/{player_id}/games/{game_id}/action_trace.jsonl`，仅 live 后端（`BOTC_BACKEND != mock`）启用，mock 测试零污染；⑤ **评测与门禁**——`scripts/benchmark/retrieval_quality_benchmark.py`（Recall@k/MRR，BM25-only 实测 Recall@5=1.0/MRR=1.0）+ `scripts/acceptance/retrieval_workflow_acceptance.py`（检索质量 + 工作流轨迹双 gate），已登记进 `alpha1.1_acceptance.py`（10 gate 全绿）。
- **原因**：用户要求"每次 agent 玩家决策/发言包装为工作流 + 引入 RAG 检索规则书/对局经验/网络经验减少幻觉"；可行性核查（PLN-041 §5）发现 Faiss 依赖未装实际不可用、玩家侧已有防幻觉防线（normalize/fallback/sanitize）、残余幻觉集中在发言内容层面——规则静态注入是最高性价比解。
- **否决方案**：① 重写 `act()` 为声明式工作流（击穿 token 预算/草稿复用/前缀缓存/480+ 测试，风险不可接受——红线"包装非重写"）；② 动态 RAG 注入进 act()（破坏 D013/D014 同局稳定约束、烧 token）。
- **回退/可逆方案**：全部为新增独立模块（retrieval/ workflow/ rule_knowledge.py）+ 两处最小挂接点（`load_player_profile` 规则注入、`_record_action_metric` trace 落盘），删除挂接点即完全回退；`rank-bm25` 依赖可从 pyproject 移除。
- **约束**：① 规则注入只在 setup 期（stable_context 首段），禁止 act() 内动态重算；② 检索结果注入前必须过敏感过滤（`type=rule` 白名单放行，其余过 `is_sensitive`）；③ mock 环境检索评测默认 BM25-only（mock embeddings 无语义会污染 MRR）；④ trace 仅 live 落盘（`BOTC_TRACE_ACTIONS=1` 可强制）；⑤ 说书人真实信息计算永远走规则引擎，工作流 LLM 仅限 `choose_distortion`（`BOTC_ST_LLM_STRATEGY` 默认 off）；⑥ 新增 gate 已登记 `alpha1.1_acceptance.py`，全量 676 测试 + ruff 0 + 10/10 gate 为验收基线。

## D017: 验收 flaky 根因修复 — persona_vote_bias 纳入 archetype 维度（2026-08-13）

- **日期**：2026-08-13
- **决策**：`DecisionEngine.persona_vote_bias`（good 阵营分支）在 decision_style 文案兜底**之前**，先按 `archetype.assertiveness` 定倾向：`high`（aggressive/paranoid/strategist）→ 投 yes；`low`（silent/cooperative/protector/outsider_vibe）→ 投 no；`neutral` 或无 archetype 时回退原文案判断。
- **原因**：全量 slow 模式 6 项验收长期 flaky（wave3 / a3_memory / alpha3 / long_game_ai / ai_evaluation 等），根因是 **mock 下不同 archetype 投票行为趋同**：vote 走本地判定路径，suspicion 常落在 threshold±margin(0.06) 模糊带内，由 `persona_vote_bias` 兜底；而该函数只看**随机 pick 的 decision_style 文案**（与 archetype 弱相关，`refresh_persona_profile` 用 `_pick_stable` 从 6 个模板 pick），导致 aggressive/silent 全投 yes（`aggressive_vote_push_rate 1.0 <= 1.0`）、行为签名趋同（`persona_diversity_score 0.2`）。修复后：long_game_ai `aggressive_vote_push_rate` 恢复区分（1.0 vs 0.0）、ai_evaluation `persona_diversity_score` 达标；同时符合 PLN-040"差异化玩家活人感"目标（archetype 是稳定人格锚点，跨局/跨轮次一致）。
- **否决方案**：① 放宽验收断言（治标，掩盖真实回归；项目已有 T1 洞察"mock 噪声失真"先例但 vote 趋同是行为缺陷而非噪声）；② 调 vote 场景信号强度（suspicion 需精确落 0.50-0.58 区间，脆弱不可维护）。
- **回退/可逆方案**：仅改 `persona_vote_bias` 一个函数，删除 archetype 分支即回退原行为；不触碰 evil 分支（evil 保持原 decision_style 文案判定）。
- **约束**：① 只改 good 阵营分支，evil 行为不变；② `archetype` 从 `persona_profile["archetype"]`（Archetype 实例）读取，该字段是稳定锚点且已被 `nomination_threshold_offset` 等消费，无新增依赖；③ 回归基线：全量 676 测试（含 slow）/ 0 failures + ruff 0 + format 0 + 10/10 聚合 gate + mock 8 人局 game_over。

## D018: 认知工作流落地（PLN-042）— 观点-证据层 + 人类式决策/发言工作流

- **日期**：2026-08-13
- **决策**：① **观点-证据模型**——`src/agents/reasoning/viewpoint.py`（Evidence hard/soft 分级 + Viewpoint 断言/证据链/置信度/状态 + ViewpointStore 落盘 `data/agents/{player_id}/games/{game_id}/viewpoints.jsonl`，仅 live）；② **确定性证据引擎**——`viewpoint_engine.py` 硬证据高权重、软证据低权重、置信度公式封顶 0.95、门控要求 **hard_count ≥ 1**（纯软印象一律拦截，防止"软印象当硬事实"）、强断言（"一定是"）自动降级为"可能"——**幻觉在生成前拦截**；③ **认知工作流**——`cognitive_workflow.py` 显式节点 recall→reason→speak→record（复用 Workflow 引擎 + trace），LLM 不参与论证数值（确定性红线）；④ **AIAgent 集成**——认知块挂在 `act()` 开头（orchestrator 全部走 act()，不经 act_with_strategy），`build_memory_snapshot` 排除阵营私密类别，观点摘要并入 strategic_thought 注入 user 段；开关 `BOTC_COGNITIVE_SPEAK` **默认 off**（mock 全量零回归）。
- **原因**：用户愿景（2026-08-13）——agent 决策/发言/行动应形成人类式完整工作流：先基于印象与前人发言**建立观点和逻辑链**，再推导行动；RAG 作为真实可信信息来源保证。live 实测验证：观点落盘 5/5 玩家、fallback=0、A/B 对比开启后发言从"断言式"（直接亮底牌）变为"论证式"（依据+前人说辞+隐藏信息）。（初版实测"硬证据 0.95 vs 软印象 0.59-0.65"中的 0.95 系 P1-1 证据提取双重循环 bug 的虚高效应，修复后单条硬证据置信度 ≈0.52、两条 ≈0.69，分级区分度恢复——见 RPT-018 修正注。）
- **否决方案**：① 让 LLM 直接生成"观点链"（数值不可审计、确定性红线被破——置信度/门控必须确定性计算）；② 认知块挂 `act_with_strategy`（orchestrator 从不调用该方法，live 实测 0 落盘证明）；③ 动态 RAG 进 recall 节点（本阶段不做，token 成本未评估，列为后续建议）。
- **回退/可逆方案**：全部为新增独立模块（reasoning/ cognitive_workflow）+ act() 一处认知块（开关关闭即完全回退）；viewpoints.jsonl 与 action_trace/thoughts 同约定（仅 live）。
- **约束**：① 开关默认 off，开启仅影响 speak/defense_speech；② 置信度/门控/证据分级全确定性；③ 快照排除 evil_teammates/evil_bluffs（信息隔离）；④ 观点摘要只进 user 段（system 前缀稳定，D013/D014）；⑤ 回归基线：快速单测 696 全绿（CR P1 修复后）+ ruff 0 + format 0 + doc health PASS + 10/10 gate + mock 8 人局 game_over + live 实测（RPT-018）。
