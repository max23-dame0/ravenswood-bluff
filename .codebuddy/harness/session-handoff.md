# 会话交接文档 (session-handoff)

> 填写规则：每次会话结束时，由结束方填写；下一会话开始时，由开始方确认"已读并理解"。**禁止**留空占位符。
> 标准格式：4 段式（背景 / 进展 / 阻断 / 下一步）。

---

## 会话交接记录

### 会话 2026-08-13（PLN-042 认知工作流全量实施 + live 实测）

**背景 (Context)**
承接 PLN-042：用户要求把"观点-证据层 + 人类式决策/发言工作流"写成计划文档，按 SpecForge TDD 逐项实施，严格验收，最后 live 实测确保实际效果。

**进展 (Progress)**
- **T1-T4（35 新测试）**：`src/agents/reasoning/`（viewpoint.py 观点-证据模型 + viewpoint_engine.py 确定性置信度/门控）+ `src/agents/workflow/cognitive_workflow.py`（recall→reason→speak→record）+ AIAgent act() 认知块（开关 `BOTC_COGNITIVE_SPEAK` 默认 off）+ build_memory_snapshot（排除阵营私密）。
- **T5 回归**：快速单测 692 全绿 + ruff 0 + format 0 + doc health PASS + 10/10 gate + mock 8 人局 game_over（viewpoints 零污染）。
- **T6 live 实测**（DeepSeek 5 人局 day_1）：观点 5 玩家落盘（分级 0.95 vs 0.59-0.65）、fallback=0、A/B 对比开启=论证式（隐藏底牌）vs 关闭=断言式（直接亮牌）。
- **文档**：DECISIONS D018 + RPT-018 + PLN-042 published + PROGRESS 任务 25 ✅。

**关键踩坑（已固化 MEMORY.md）**
① **orchestrator 全部走 `agent.act()`，不经 `act_with_strategy`**——认知块最初挂错位置 live 0 落盘；② pytest-asyncio auto 未生效需显式 `@pytest.mark.asyncio` + await；③ safe-delete 拦截 basetemp 清理（>50 文件）→ 每次唯一 basetemp（时间戳）；④ `simulate_game.py` 用 `--backend live` 参数（env 不生效）+ `--timeout-seconds 600`；⑤ PowerShell 中文内联脚本乱码 → 脚本文件 + `-X utf8`。

**验证 (Verification)**
- 692 快速单测 + ruff 0 + format 0 + doc health PASS + `alpha1.1_acceptance.py` **10/10** + mock 8 人局 game_over + live 五条验收全过（RPT-018）。
- ⚠️ 全量含 slow 时 `test_storyteller_acceptance` 并发 240s 超时（已知 slow 并发 flaky，单独跑通过）。

**阻断 (Blockers)**
- 无。**未提交改动**：PLN-042 全部（reasoning/cognitive_workflow/ai_agent + 4 测试文件）+ PLN-041 遗留 + D017 + 文档治理，等用户确认后 commit。

**下一步 (Next Steps)**
1. 用户确认后分组 commit（PLN-042 建议：reasoning 基础设施 / 认知工作流 / AIAgent 接入 / 文档 4 组）。
2. 观点演化接入 act() 主循环（update_with_new_evidence/supersede 已实现未接入）。
3. 动态 RAG 进 recall 节点（局内前人发言检索，token 成本评估）。

**确认 (Confirmed by)**
- 填写人：coding agent（2026-08-13）
- 确认人（下一会话）：________

---

### 会话 2026-08-12（PLN-041 工作流 + RAG 融入全量实施）

**背景 (Context)**
承接「PLN-041 工作流与 RAG 融入」：用户要求按 SpecForge 工作流逐项完成任务，全部功能须经单测与实测，且完成后做 harness 治理与文档治理。计划文档已在前两轮完成可行性核查（§5）与任务板（§9）。

**进展 (Progress)**
- **检索基础设施**：`src/agents/memory/retrieval/`（chunker 分块 / BM25 稀疏检索 / Faiss 稠密可选 + RRF 融合 / RetrievalStore 落盘 `data/agents/_retrieval/` / RetrievalPipeline 统一注入管线：retrieve→敏感过滤→门控→注入）；依赖 `rank-bm25`（必装）+ numpy/faiss-cpu（可选，缺失自动降级 BM25-only）。
- **规则书静态注入（防幻觉核心）**：`src/content/rule_knowledge.py` 从 terms + night_order + RoleDefinition 导出 22 角色结构化条目；`build_role_rulebook_context` 在 AIAgent `load_player_profile` setup 期注入 stable_context 首段（同局稳定、零缓存破坏）。
- **工作流引擎**：`src/agents/workflow/`（Workflow DSL：ToolCallNode/ConditionNode/ParallelNode + WorkflowEngine 调度/超时/重试 + WorkflowTrace 落盘回放）；说书人裁决 6 工具编排为显式工作流试点（`storyteller_workflows.py`，包装非重写、LLM 仅限 choose_distortion、默认路径零 LLM）；玩家行动轨迹 `ActionTrace`（`data/agents/{player_id}/games/{game_id}/action_trace.jsonl`，仅 live 落盘，mock 零污染）。
- **评测与门禁**：`scripts/benchmark/retrieval_quality_benchmark.py`（Recall@5=1.0/MRR=1.0）+ `scripts/acceptance/retrieval_workflow_acceptance.py`（检索质量 + 工作流轨迹双 gate）已登记进 `alpha1.1_acceptance.py`。
- **治理收尾**：DECISIONS 新增 D016；PROGRESS 任务 24 ✅ + 验证状态表 + 会话记录；PLN-041 status draft→published + 任务板全勾选。

**验证 (Verification)**
- `pytest tests -q` 全量（含 slow）= **676 passed / 0 failed / 0 errors**（2026-08-13 D017 修复后）；ruff check 0；ruff format 0（保留 ruff 0.16.1 格式改动，用户确认）；`check_doc_health.py` PASSED；`alpha1.1_acceptance.py` **10/10 全绿**；mock 8 人局 game_over 且 trace 零污染。
- 此前「6 项 slow 验收基线 flaky」已由 D017 修复：根因是 `persona_vote_bias` 与 archetype 无关导致 vote 模糊带内行为趋同，非 mock 噪声。

**阻断 (Blockers)**
- 无技术阻断。**未提交改动较多**（新增 retrieval/workflow/rule_knowledge + 6 个测试文件 + ai_agent 挂接 + 文档），等用户确认后 commit（用户偏好：提交须确认）。

**下一步 (Next Steps)**
1. 用户确认后按逻辑分组 commit（建议：基础设施 / 注入 / 工作流 / gate 与文档 4 组）。
2. （可选）live 后端检索抽查（`--dense` 需真实 embeddings）。
3. （可选）网络玩家分析经验知识源人工整理后走同一条索引管线。

**确认 (Confirmed by)**
- 填写人：coding agent（2026-08-12）
- 确认人（下一会话）：________

---

### 会话 2026-07-31-04（规范化整理收尾验证）

**背景 (Context)**
承接「代码与文件规范化整理（P0-P5）」。六阶段改动已在此前会话落盘，但仅完成静态审计；本会话在已就绪的 `.venv`（受管 Python 3.13.12）中执行真实四条验证命令，并修复由此暴露的问题。

**进展 (Progress)**
- **修复 P3 二级引用断链（9 处，根因见 DECISIONS D011）**：分目录后「叶子 gate 调用兄弟 gate」的 `scripts/xxx.py` 路径未同步。已修 `wave1~4_acceptance.py` + `a3_memory_acceptance.py`（`run_script` 参数统一为「相对 `scripts/` 根」并在 docstring 固化语义）、`ai_eval_acceptance.py`、`storyteller_acceptance.py`、`storyteller_balance_acceptance.py`，以及 `tests/test_orchestrator/` 下 2 个测试的 `export/` 路径。pytest 失败数 17 → 12 → 1 → 0。
- **lint 收敛至零告警**：`--statistics` 摸底 112 项 → F401(20)/F541(8) 用 `ruff check --fix`；E402(76) 全落在 `scripts/**`（`sys.path` bootstrap 预期模式）加 per-file-ignores；F841(7)/E712(1) 手工清理死变量与 `== False` 比较。
- **消除 flaky**：`test_storyteller_balance_sample_export.py` 与 `storyteller_balance_acceptance.py::_run` 的 `timeout=60` → `180`（二者真跑整局 mock 对局，全量并发下稳定超时、单跑 <20s）。
- **启用 format 硬门禁**：`ruff format --check src tests scripts` 实测 182 文件已全部归一，故直接启用 pre-commit 的 `ruff-format` 钩子并移除 CI 该步骤的 `continue-on-error`（原计划的「format-only 提交」不再需要）。
- **文档同步**：DECISIONS 更新 D009、新增 D011；PROGRESS 更新验证状态表 / 未提交改动清单 / 会话记录。

**阻断 (Blockers)**
- 无。四条验证命令全部通过：`ruff check src tests scripts` 零告警；`ruff format --check` 182 文件已归一；`pytest tests -q` 447 passed（连跑两轮稳定）；`python scripts/alpha1.1_acceptance.py` exit=0（9/9）。

**下一步 (Next Steps)**
1. 按 P0-P5 分 6 个 commit 提交 240 项改动（commit message 标注阶段号，便于单独 `git revert`）。
2. 逐族启用 ruff 阶段二规则（I → UP → B → SIM），每族先 `--statistics` 摸底再单独提交（D009）。
3. 将 `scripts/check_doc_health.py` 纳入 `.github/workflows/ci.yml`。

**确认 (Confirmed by)**
- 填写人：coding agent（2026-07-31）
- 确认人（下一会话）：________

---

### 会话 2026-07-30-01

**背景 (Context)**
本会话由用户执行 `@command://init` 与 `@command://harness-setup`。项目为《血染钟楼》多 Agent 推演引擎（Alpha 1.1）。git 环境已就绪（main 分支，与 origin/main 同步，工作区 clean）。

**进展 (Progress)**
- 按 init 命令创建 `CODEBUDDY.md`（含命令 + 架构摘要）。
- 按 harness-setup 生成全套 Harness：入口 `AGENTS.md`、项目认知 `.codebuddy/memory/MEMORY.md`、进度 `PROGRESS.md`、决策 `DECISIONS.md`（D001–D006）、分层规则 `.codebuddy/rules/`（global/agents/engine/orchestrator/state/llm/api 共 7 个）、技术陷阱 `documents/05-reference/tech-traps.md`、会话交接与上下文预算（`.codebuddy/harness/`）。
- 将 `CODEBUDDY.md` 内容整合进 `AGENTS.md` / `MEMORY.md`，计划删除 `CODEBUDDY.md` 以避免双入口冲突。

**阻断 (Blockers)**
- 无技术阻断。待用户决定：是否 `git add` 并提交这些 harness 文件（当前未提交）。

**下一步 (Next Steps)**
1. 用户确认是否提交 harness 文件。
2. （可选）运行 `pip install -e ".[dev]"` + `pytest tests -q` 建立测试基线。
3. 后续功能开发：编辑对应子模块（如 `src/agents/*` 调 AI 行为），遵循 `AGENTS.md` 上班/下班流程。

**确认 (Confirmed by)**
- 填写人：coding agent（2026-07-30）
- 确认人（下一会话）：________
