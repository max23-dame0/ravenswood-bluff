---
name: codebase-normalization
overview: 对鸦木布拉夫项目做「编码规范 + 文件组织」整理：补全 pyproject ruff/pytest 配置、清理根目录散落脚本、归位 tests 根级文件、规范化 scripts 与 docs 目录、微调 agents 模块文件归属，全程只整理不改业务语义。
todos:
  - id: p0-config
    content: 补全 pyproject 的 ruff lint/format/isort 配置，新增 pre-commit 与 CI 门禁，验证零告警
    status: completed
  - id: p1-root-cleanup
    content: 删除 debug_imports.py 与 read_log.py，登记 simulate_game.py 保留决策
    status: completed
    dependencies:
      - p0-config
  - id: p2-tests-relocate
    content: 迁移 test_difficulty.py、test_decision_noise.py 至 test_agents/，同步 alpha1.1_acceptance.py 与 test-system.md 路径
    status: completed
    dependencies:
      - p1-root-cleanup
  - id: p3-scripts-reorg
    content: 用 [subagent:code-explorer] 全量扫描引用后，scripts 按 acceptance/benchmark/export/debug 分目录并同步聚合脚本路径
    status: completed
    dependencies:
      - p2-tests-relocate
  - id: p4-docs-reorg
    content: 用 [skill:doc-governance] 重组 docs 分类目录，同步 AGENTS/CLAUDE/MEMORY 交叉引用，evidence 存证不动
    status: completed
    dependencies:
      - p3-scripts-reorg
  - id: p5-agents-tidy
    content: 迁移 decision_noise.py、persona_registry.py 入子包并更新 10 处 import，facade 复核仅标注优化项
    status: completed
    dependencies:
      - p3-scripts-reorg
  - id: final-verify
    content: 全量运行 ruff/pytest/9 gate 验收，更新 PROGRESS、DECISIONS、MEMORY 收尾
    status: completed
    dependencies:
      - p4-docs-reorg
      - p5-agents-tidy
---

## 用户需求

对 `d:/ravenswood-bluff` 全项目进行「编码规范 + 文件组织」规范化整理，使其符合现代 Python 工程组织规范：模块化清晰、架构分层明确、命名一致、配置完整。**仅整理结构，不重构业务逻辑，不改动任何运行时行为与架构语义。**

## 产品概览

基于多 Agent + 状态机的《血染钟楼》推理桌游引擎（Alpha 1.1）的代码库治理任务，按低风险优先的 P0-P5 六阶段执行，每阶段独立提交、可回滚、附验证命令。

## 核心内容

- **P0 配置补全**：pyproject 补齐 `[tool.ruff.lint]`（select/ignore 规则集）、`[tool.ruff.format]`、isort 导入排序；可选 pre-commit 与 CI 门禁。
- **P1 根目录清理**：删除 0 引用的临时脚本 `debug_imports.py`、`read_log.py`；`simulate_game.py` 因被测试/脚本/文档大量引用保留为根级 CLI 入口。
- **P2 tests 归位**：`tests/` 根级散落测试文件按被测模块归入子目录，同步更新脚本硬编码路径与文档。
- **P3 scripts 规范化**：43 个脚本按用途分子目录（acceptance / benchmark / export / debug），改前全量 grep 引用防断链。
- **P4 docs 重组**：97 个 md 建立分类子目录，保全 AGENTS.md / CLAUDE.md / MEMORY.md / test-system.md 交叉引用。
- **P5 agents 模块微调**：`decision_noise.py` / `persona_registry.py` / `difficulty_presets.py` 归入对应子包；facade 复核仅标注优化项，不强行拆分。

## 边界与约束

- 严禁破坏六条硬约束（GameState 不可变 / 信息隔离 / 事件可见性 / facade 路由 / 发言顺序 / 双超时预算）。
- 禁止删除/移动有引用的文件（改前必须全仓库 grep）；非必要不改字符串字面量与 prompt 文案。
- 验收标准：`ruff check` 零告警、`ruff format --check` 一致、`pytest tests -q` 全绿、`alpha1.1_acceptance.py` 9 gate 全绿、无引用断链。

## 技术栈（沿用现有，不引入新依赖）

- Python 3.11+ / FastAPI / Pydantic v2 / aiosqlite
- pytest + pytest-asyncio（`asyncio_mode=auto`）、ruff（py311, line-length=100）
- 新增仅限工程配置：`[tool.ruff.lint]`、`[tool.ruff.format]`、`.pre-commit-config.yaml`（可选）、`.github/workflows/ci.yml`（可选）

## 实施策略

**方法**：只读审计已完成（证据见下），按 P0→P5 低风险优先顺序分阶段落地；每阶段 = 独立 git commit + 引用同步 + 验证命令，任一阶段失败以 `git revert` 单独回滚，不影响其他阶段。

**关键决策**：

1. `simulate_game.py` **保留根目录**：被 `tests/test_simulate_game.py:15`（`importlib.import_module("simulate_game")`，依赖 `pythonpath=["."]`）、`scripts/batch_benchmark.py:22`、`scripts/parallel_benchmark.py:16`、`scripts/alpha1_acceptance.py:147` 及 CLAUDE.md/CHANGELOG/多份 docs 引用。迁移收益低、断链风险高，现代 Python 项目允许根级 CLI 入口。
2. `tests/test_simulate_game.py` **保留 tests 根**：其被测对象是根级 CLI 而非 src 七包之一，且被 `scripts/alpha1_rules_acceptance.py:31` 硬编码引用；仅移动 `test_difficulty.py`、`test_decision_noise.py` 至 `tests/test_agents/`（被测对象在 `src/agents/`），将改动面降到最小。
3. P5 agents 文件归子包采用 **直接更新全部 import**（引用面已核实仅 10 处：src 4 处、tests 2 处、scripts 4 处），不留 re-export shim，避免技术债；`ai_agent.py` facade 内 import 路径同步修改属允许的机械替换，不算堆逻辑。
4. **历史存证文档不改**：`docs/alpha-1.1-evidence/*.md` 中的旧路径引用是验收快照，保留原样并在 DECISIONS.md 登记该决策；仅更新「活文档」（AGENTS.md / CLAUDE.md / test-system.md / MEMORY.md / .codebuddy/rules/）。
5. ruff lint 规则集采取 **渐进式**：首选 `select = ["E", "F", "W", "I", "UP", "B", "SIM"]` + 按现状 `ignore` 存量告警类别（先 `ruff check --statistics` 摸底），保证 P0 零代码改动即可通过；isort 配置 `known-first-party = ["src"]`。

## 审计证据摘要（已核实）

| 项 | 证据 | 结论 |
| --- | --- | --- |
| `debug_imports.py`(10行) / `read_log.py`(19行，硬编码失效路径) | 全仓库 0 引用 | 安全删除 |
| `simulate_game.py` | 4 处代码引用 + 多份文档 | 保留根目录 |
| `tests/test_difficulty.py` | `scripts/alpha1.1_acceptance.py:128` 硬编码（9 gate 之一） | 移动须同步该行 |
| `tests/test_decision_noise.py` | scripts 0 处硬编码，仅 docs 引用 | 可安全移动 |
| scripts 互引 | 仅 `alpha1_acceptance.py` / `alpha1.1_acceptance.py`（含 `_script_exists` 检查）/ `alpha3_acceptance.py` 三个聚合脚本硬编码 `scripts/xxx.py` | src 0 引用，重组只改 scripts 内部 + docs |
| agents 模块级文件 | `decision_noise` / `difficulty_presets` / `persona_registry` 共 10 处 import | 可控迁移 |
| pyproject | 无 lint/format/isort 配置；`pythonpath=["."]` 是 test_simulate_game 可运行的前提，**不可删** | P0 补齐 |


## 分阶段方案

### P0 配置补全（零行为风险）

- 改动：`pyproject.toml`（补 `[tool.ruff.lint]` select/ignore + `isort` + `[tool.ruff.format]`；pytest 补 `addopts = "-q"` 可选）；新增 `.pre-commit-config.yaml`、`.github/workflows/ci.yml`（ruff + pytest mock 模式）。
- 风险：新规则可能暴露存量告警 → 先摸底，用 ignore 白名单保证零告警起步。
- 回滚：`git revert` 单 commit。
- 验证：`ruff check src tests`、`ruff format --check src tests`、`pytest tests -q`。

### P1 根目录散落脚本清理

- 改动：删除 `debug_imports.py`、`read_log.py`；`simulate_game.py`、`run_server.bat`、`Dockerfile`、`docker-compose.yml` 保留根目录（在 README 或 CLAUDE.md 标注根级文件定位）。
- 风险：极低（0 引用已核实）。回滚：`git revert`。

### P2 tests 根级文件归位

- 改动：`tests/test_difficulty.py`、`tests/test_decision_noise.py` → `tests/test_agents/`；同步 `scripts/alpha1.1_acceptance.py:128`、`docs/test-system.md:26-28`、`.codebuddy/rules/tests.md`（如有路径）。`tests/test_simulate_game.py` 保留（理由见决策 2）。
- 风险：conftest/doubles 位于 tests 根，子目录可正常继承 fixture，`tests/__init__.py` 包路径不受影响；9 gate 中 difficulty gate 路径必须同步。
- 验证：`pytest tests -q` + `python scripts/alpha1.1_acceptance.py`。

### P3 scripts 目录规范化

- 改动：按用途分子目录并迁移——`scripts/acceptance/`（约 27 个 *acceptance*.py + `ghost_vote_test.py`、`persona_divergence_test.py` 重命名为 `*_acceptance.py` 或归入 debug）、`scripts/benchmark/`（batch/parallel/llm_latency + parse_*metrics）、`scripts/export/`（export* / *_sample_export / generate_*_samples）、`scripts/debug/`（dump_ai_prompt / ai_evaluation / difficulty_comparison / run_full_tests_low_memory）。
- 同步：三个聚合脚本内全部 `scripts/xxx.py` 硬编码路径与 `_script_exists` 检查；AGENTS.md（`python scripts/alpha1.1_acceptance.py` 命令）、CLAUDE.md、docs/test-system.md、`.codebuddy/rules/tests.md`（生效条件 glob `scripts/*acceptance*.py` 需改为 `scripts/**/*acceptance*.py`）。
- 权衡：`alpha1.1_acceptance.py` 是发布 blocker 入口，**入口路径保持 `scripts/` 顶层不动**（或顶层留同名转发入口），只下沉被聚合的子脚本，最大限度不破坏用户/CI 已有命令。
- 风险：中。回滚：`git revert` + 路径还原。验证：9 gate 全绿。

### P4 docs 目录重组（最低优先级，谨慎）

- 前置：git status 显示 docs/ 大量 modified 未提交 → **必须先提交/处理现有改动获得干净基线**。
- 改动：建 `docs/architecture/`、`docs/plans/`（收拢 alpha-*-plan）、`docs/reviews/`（handoff/review/backlog 类）、`docs/acceptance/`；`docs/alpha-1.1-evidence/` 原地保留（存证）。同步 AGENTS.md 专题文档索引、CLAUDE.md、MEMORY.md、DECISIONS.md 中的相对路径。
- 风险：交叉引用面大 → 移动前对每个文件名全量 grep，产出「引用映射表」后批量替换。回滚：`git revert`。

### P5 agents 模块归属微调 + facade 复核

- 改动：`decision_noise.py` → `src/agents/decision/`、`persona_registry.py` → `src/agents/persona/`、`difficulty_presets.py` → 建议留在 `src/agents/`（难度是横切五轴配置，非单一子包职责，移动收益低）或归入 `decision/`（二选一，落地时按 import 图确认）；同步 10 处 import。
- facade 复核：审读 `ai_agent.py`(~1100 行)、`game_loop.py`(~766 行)，确认仅路由；发现可下沉逻辑仅在 PROGRESS.md 登记为优化项，**本任务不拆**。
- 风险：中低（import 机械替换 + 全量测试兜底）。验证：全套四命令。

## 执行注意事项

- **环境**：当前环境可能无 Python 可执行文件。首步先 `pip install -e ".[dev]"` 确认可跑；若确无，每阶段验证显式标注「待用户在可运行环境闭环验证」，且不得宣称完成（清洁状态第 6 项）。
- **每阶段一个 commit**，commit message 标注阶段号，保证独立回滚。
- 不改任何字符串字面量 / 日志文案 / prompt 文案；`pythonpath=["."]` 与 `tests/doubles.py`（D008 替身唯一来源）不动。
- 收尾按项目工作流更新 PROGRESS.md / DECISIONS.md / MEMORY.md / session-handoff.md。

## 目录结构（目标态，仅列变更）

```
d:/ravenswood-bluff/
├── pyproject.toml                  # [MODIFY] P0：补 [tool.ruff.lint]/[tool.ruff.format]/isort；pytest addopts
├── .pre-commit-config.yaml         # [NEW] P0（可选）：ruff check + ruff format 钩子
├── .github/workflows/ci.yml        # [NEW] P0（可选）：ruff + pytest(mock) 门禁
├── debug_imports.py                # [DELETE] P1：0 引用临时脚本
├── read_log.py                     # [DELETE] P1：0 引用、路径已失效
├── simulate_game.py                # [KEEP] 根级 CLI 入口，多处引用
├── tests/
│   ├── test_agents/
│   │   ├── test_difficulty.py      # [MOVE] P2：自 tests/ 根迁入
│   │   └── test_decision_noise.py  # [MOVE] P2：自 tests/ 根迁入
│   └── test_simulate_game.py       # [KEEP] 对应根级 CLI，脚本硬编码引用
├── scripts/
│   ├── alpha1.1_acceptance.py      # [MODIFY] P2/P3：更新 tests 与子脚本路径（入口位置不动）
│   ├── alpha1_acceptance.py        # [MODIFY] P3：更新子脚本路径
│   ├── alpha1_rules_acceptance.py  # [MODIFY] P2：确认 tests 路径（test_simulate_game 不动则免改）
│   ├── alpha3_acceptance.py        # [MODIFY] P3：更新子脚本路径
│   ├── acceptance/  benchmark/  export/  debug/   # [NEW] P3：四类子目录，43 个脚本按用途迁入
├── docs/
│   ├── architecture/  plans/  reviews/  acceptance/  # [NEW] P4：分类子目录
│   └── alpha-1.1-evidence/         # [KEEP] 历史存证原地保留
├── src/agents/
│   ├── decision/decision_noise.py  # [MOVE] P5：自 agents/ 根迁入，同步 3 处 import
│   ├── persona/persona_registry.py # [MOVE] P5：自 agents/ 根迁入，同步 5 处 import
│   └── difficulty_presets.py       # [REVIEW] P5：横切配置建议留原地，落地时定夺
├── AGENTS.md / CLAUDE.md / MEMORY.md / .codebuddy/rules/tests.md  # [MODIFY] 各阶段同步路径引用
└── PROGRESS.md / DECISIONS.md      # [MODIFY] 收尾：登记决策（evidence 不改路径等）与进度
```

## Agent Extensions

### SubAgent

- **code-explorer**
- Purpose：在 P3/P4/P5 每次移动/重命名前，对目标文件名与 import 路径做全仓库多目录引用扫描（scripts 互引、docs 交叉引用、src/tests import），产出「文件 → 引用位置」映射表。
- Expected outcome：每个待移动文件均有完整引用清单，移动后按清单逐一同步，实现零断链。

### Skill

- **doc-governance**
- Purpose：P4 阶段对 docs/ 下 97 个 md 执行文档体系诊断与重组（分类归档、腐败检测、索引同步），并保全 AGENTS.md / CLAUDE.md / MEMORY.md 的交叉引用。
- Expected outcome：docs/ 形成 architecture / plans / reviews / acceptance 分类结构，活文档索引全部更新，存证文档原地保留且决策入档。