# PROGRESS — 项目当前进度

> 最后更新：2026-07-31
> **上班必读**：本文件 + DECISIONS.md

## 活跃任务看板（WIP 显式登记）

> 允许并行，但每个活跃任务必须在此登记一行；切换前写回状态与下一步。

| # | 任务 | 阶段 | 状态 | 下一步 | 阻塞 |
|:--:|------|------|:--:|------|------|
| 1 | 搭建 coding agent harness 环境 | 首次搭建 | 🟢 已落地待提交 | 用户决定是否 commit harness 文件 | 无 |
| 2 | 按 harness 治理体系整理测试系统 | 治理 | 🟢 代码+文档完成，环境已就绪并已跑通 `pytest tests` + `ruff check tests` | 用户决定是否 commit | 无 |
| 3 | 代码与文件规范化整理（P0-P5） | 整理 | 🟢 六阶段改动落盘，四条验证命令全部通过（ruff 零告警 + `ruff format --check` 182 文件已归一 + pytest 447 全绿 + 9-gate exit=0） | 用户决定是否按 P0-P5 分阶段 commit + 逐族启用阶段二规则 | 无 |
| 4 | 文档体系治理收尾（增强 + 健康核对） | 治理 | 🟢 已完成 | 纳入 CI（check_doc_health.py）；用户跑环境后一并 commit | 无 |
| 5 | 修复 GitHub Actions lint-and-test 全红 | 修复 | 🟢 已提交（6 个 commit，待推送验证） | 推送后看 CI 是否转绿 | 无 |

## 当前验证状态

| 检查项 | 状态 |
|------|------|
| `pip install -e ".[dev]"` | ✅ 已验证（受管 Python 3.13.12 + 项目根 `.venv` + dev 依赖全部安装） |
| `pytest tests -q`（基线：447 passed / 0 failed） | ✅ 全绿（连续两轮 447 passed；仅 fastapi 第三方 `StarletteDeprecationWarning`） |
| `ruff check src tests scripts` | ✅ 零告警（阶段一规则集 E4/E7/E9/F/W，忽略 E501；F401/F541 经 `--fix` 收敛，E402 由 `scripts/**` per-file-ignores 覆盖，F841/E712 手工清理） |
| `ruff format --check src tests scripts` | ✅ 182 文件全部已归一；pre-commit `ruff-format` 钩子已启用，CI 该步骤已移除 `continue-on-error` |
| `python scripts/alpha1.1_acceptance.py`（9 gate） | ✅ exit=0，9/9 全绿 |
| 文档链接健康（相对链接扫描） | ✅ 与整理前基线一致（23 处失效，均为整理前既有的绝对路径与第三方 skill 文档） |
| 静态引用审计（脚本路径 / import / REPO_ROOT 深度） | ✅ 无残留旧路径，子目录脚本 `parents[2]` 全覆盖 |
| git status / 未提交改动 | ✅ 工作区 clean；本地 6 个 commit 待推送（CI 跨平台修复 + ruff UP/B/SIM 三族） |
| 当前 blocker | ✅ 无 |

> **CI 跨平台修复（2026-07-31，commit `ad4e974`）**：GitHub Actions（ubuntu runner）报 20 个失败。
> 根因一（19 个）：测试/脚本硬编码 `repo_root/".venv"/"Scripts"/"python.exe"` 拉子进程，Windows-only
> → 全部改用 `sys.executable`（35 文件）。根因二（1 个）：`tests/test_runs/` 被 gitignore，CI 全新 checkout
> 不存在，而 `mkdir(exist_ok=True)` 不建父目录 → 改 `mkdir(parents=True, exist_ok=True)`。
> 陷阱已固化为 `docs/reference/tech-traps.md` T13/T14。另将验收 subprocess 测试超时统一提到 300s
> （本机全量并发下 `storyteller_balance`/`alpha3` 曾偶发超时，CI runner 更慢）。

> **P3 二级引用回归修复（2026-07-31 收尾）**：分目录后「叶子 gate 调用兄弟 gate」的路径未同步，导致 9 个测试报
> `can't open file ...\scripts\<name>.py`。已修 `wave1~4_acceptance.py`、`a3_memory_acceptance.py`（`run_script`
> 参数改为带子目录前缀，并在 docstring 固化"相对 `scripts/` 根"语义）、`ai_eval_acceptance.py`、
> `storyteller_acceptance.py`、`storyteller_balance_acceptance.py` 及 2 个测试文件的 `export/` 路径。决策见 D011。
>
> **超时时限放宽**：`test_storyteller_balance_sample_export.py` 第二个用例与 `storyteller_balance_acceptance.py`
> 的 `_run` 均为真跑整局 mock 对局，原 `timeout=60` 在全量 pytest 并发下稳定超时（单跑 <20s），已统一放宽至 180s。
>
> **此前记录的「9-gate 7/9 + 2 门禁 flaky」已不复现**：修复二级引用后连续两轮 `pytest tests -q` 447 passed、
> `alpha1.1_acceptance.py` exit=0。原 flaky 判断部分源于路径断链的连锁失败。

### 规范化整理剩余待办

1. ~~四条验证命令跑通~~ ✅ 已完成（ruff check / ruff format --check / pytest / 9-gate 全绿）。
2. ~~启用 format 门禁~~ ✅ 已完成（pre-commit `ruff-format` 钩子 + CI 移除 `continue-on-error`）。
3. **按 P0-P5 分阶段 commit**（240 项改动，建议 6 个 commit，commit message 标注阶段号以便单独 `git revert`）。
4. 逐族启用 ruff 阶段二规则（I → UP → B → SIM），每族先 `--statistics` 摸底再单独提交（见 D009）。
5. 将 `scripts/check_doc_health.py` 纳入 `.github/workflows/ci.yml`（任务 4 遗留）。

## 未提交改动清单（与 git 强一致）

> 规则：标记 ✅ 完成的任务，其代码**必须已 commit**；仅本地验证未提交的，状态写「🟡 已验证待提交」并登记于此。

| 改动 | 状态 | 计划 commit | 关联任务 |
|------|:--:|------|------|
| 新建 harness 文件（AGENTS/MEMORY/PROGRESS/DECISIONS + .codebuddy/rules/* + .codebuddy/harness/*） | 🟡 已验证待提交 | 搭建后由用户决定 | 1 |
| 测试治理：新增 tests/doubles.py(替身唯一源) + 改 conftest.py 与 3 个测试文件去重；新增 .codebuddy/rules/tests.md、docs/reference/test-system.md、docs/reference/tech-traps.md(T10-T12)；更新 AGENTS/DECISIONS(D007/D008)/MEMORY | 🟡 文档+代码完成，pytest/ruff 因无 Python 环境未运行 | 装环境后由用户决定 | 2 |
| **P0** 配置补全：pyproject 补 `[tool.ruff.lint]`/`[tool.ruff.format]`/isort/per-file-ignores（含 `scripts/**` 豁免 E402）+ pytest `addopts`；新增 `.pre-commit-config.yaml`（含已启用的 ruff-format 钩子）、`.github/workflows/ci.yml`；ruff 依赖提至 `>=0.5` | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **P1** 根目录清理：删除 0 引用的 `debug_imports.py`、`read_log.py`；`simulate_game.py` 保留为根级 CLI 入口 | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **P2** tests 归位：`test_difficulty.py`/`test_decision_noise.py` → `tests/test_agents/`；同步 `scripts/alpha1.1_acceptance.py` gate 路径与 test-system/verification_policy 文档 | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **P3** scripts 规范化：40 个叶子脚本迁入 `acceptance/`(27)、`benchmark/`(5)、`export/`(5)、`debug/`(3)，3 个聚合入口留顶层；35 个脚本 `parents[1]`→`parents[2]`；同步 3 个聚合脚本硬编码路径 + 14 个测试文件引用 + 跨脚本 import + **9 处叶子脚本二级互调路径**（D011）；新增 `scripts/README.md` | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **P4** docs 重组：31 项迁入 `plans/`、`releases/`、`reviews/`、`guides/`、`reference/`；脚本写入的 `frontend_acceptance.md`/`alpha-1.0-benchmark-results.md`/`alpha-1.1-evidence/` 保留原位；重写 `docs/README.md` 索引；链接扫描回落至基线 | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **P5** agents 归属微调：`decision_noise.py`→`decision/`、`persona_registry.py`→`persona/`（10 处 import 已同步，两个子包补 `__all__` 再导出）；`difficulty_presets.py` 作为横切配置留包根 | 🟡 已验证待提交 | 建议单独 commit | 3 |
| **收尾** lint 收敛（F401/F541 `--fix`、F841/E712 手工）+ 两处 `timeout=60`→`180` 消除 flaky + DECISIONS 补 D011 | 🟡 已验证待提交 | 随 P0/P3 提交 | 3 |

## 整体进度

| Phase | 内容 | 状态 | 完成日期 |
|:--|:--|:--:|:--:|
| 项目初始化(git) | 仓库已存在（main，与 origin/main 同步） | ✅ | 既有 |
| 代码架构 | Alpha 1.1：难度系统 + 速度优化 + 模块化重构 | ✅ | 2026-05-08 |
| Harness 环境搭建 | AGENTS/MEMORY/PROGRESS/DECISIONS + 分层规则 | 🟢 进行中 | 2026-07-30 |

## 阻塞项

无当前阻塞。

## 最近会话记录（三行摘要，详情见 daily memory）

| 日期 | 做了什么（一行） | 验证 | 下一步 | 日志 |
|------|---------|:--:|------|
| 2026-07-30 | 按 harness-setup 生成全套 harness（含整合 CODEBUDDY.md 内容） | 文件已落盘 | 用户决定是否 commit | .codebuddy/memory/2026-07-30.md |
| 2026-07-31 | 测试系统治理：替身统一至 tests/doubles.py + 新增 tests.md/test-system.md/tech-traps T10-T12 + 接入 AGENTS/DECISIONS(D007/D008)/MEMORY | 文档+代码去重完成；ruff/pytest 因无 Python 环境未运行 | 装环境后跑 `pytest tests` + `ruff check tests` | .codebuddy/memory/2026-07-31.md |
| 2026-07-31 | 代码与文件规范化整理 P0-P5：ruff/pytest 配置补全 + pre-commit/CI、根目录清理、tests 归位、scripts 四类分目录、docs 五类重组、agents 子包归属 | 静态审计通过（引用零断链、链接回落基线）；ruff/pytest/9 gate 因无 Python 未运行 | 装环境后跑四条验证命令 + `ruff format` 归一 | .codebuddy/memory/2026-07-31.md |
| 2026-07-31 | 文档治理收尾：清理临时脚本 + docs/README.md §7 登记证据文件名 + 新增 scripts/check_doc_health.py（CI 门禁）+ 核对并修复 harness 文档与历史文档绝对路径断链（→相对路径） | harness 文档路径均有效；61 处空链接已修复为相对链接并验证目标存在 | 纳入 CI；用户跑环境后随 P0-P5 一并 commit | .codebuddy/memory/2026-07-31.md |
| 2026-07-31 | 环境就绪后按 PROGRESS/DECISIONS/handoff 修复：ruff 阶段一零告警（406→0）+ pytest 17→0 全绿 + 9-gate 7/9 稳定；修 data_collector 双装饰器、vector_memory reload、GBK 解码、两处 F821 | pytest 全绿、ruff 零告警；9-gate 2 门禁为预存 flaky（非回归） | 用户决定是否 commit + 逐族启用 ruff 阶段二（I→UP→B→SIM） | .codebuddy/memory/2026-07-31.md |
| 2026-07-31 | 规范化整理收尾：补修 P3 遗漏的 9 处叶子脚本二级互调路径（D011）+ lint 收敛至零告警 + 两处 timeout 60→180 消除 flaky + 启用 format 硬门禁 | ✅ 四条命令全绿：ruff check 0、`ruff format --check` 182 已归一、pytest 447 passed（连跑两轮）、9-gate exit=0 | 按 P0-P5 分 6 个 commit 提交 240 项改动 | .codebuddy/memory/2026-07-31.md |
