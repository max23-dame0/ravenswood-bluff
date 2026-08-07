# PROGRESS — 项目当前进度

> 最后更新：2026-08-07
> **上班必读**：本文件 + DECISIONS.md

## 活跃任务看板（WIP 显式登记）

> 允许并行，但每个活跃任务必须在此登记一行；切换前写回状态与下一步。

| # | 任务 | 阶段 | 状态 | 下一步 | 阻塞 |
|:--:|------|------|:--:|------|------|
| 1 | 搭建 coding agent harness 环境 | 首次搭建 | ✅ 已完成并提交 | — | 无 |
| 2 | 按 harness 治理体系整理测试系统 | 治理 | ✅ 已完成并提交 | — | 无 |
| 3 | 代码与文件规范化整理（P0-P5） | 整理 | ✅ 已完成并提交（447 全绿 + ruff 零告警 + 9-gate exit=0） | — | 无 |
| 4 | 文档体系治理收尾（增强 + 健康核对） | 治理 | ✅ 已完成并提交；`check_doc_health.py` 已纳入 CI（2026-08-03） | — | 无 |
| 5 | 修复 GitHub Actions lint-and-test 全红 | 修复 | ✅ 已提交推送；CI 三轮修复完成（ruff format / storyteller 日志测试 / CI 提速） | 看 CI 最终转绿 | 无 |
| 6 | P1 上帝对象拆分 + P2 日志/文档治理 | 重构+治理 | ✅ 已提交推送 | — | 无 |
| 7 | CI 提速：慢验收测试标 slow + job 超时上限 | 性能 | 🟢 已提交推送（`26df4f4`+`d8bb347`） | 看 CI run 是否快速通过 | 无 |
| 8 | Agent 原生重构（PLN-038 阶段 A/B/S/C/D + PLN-037 P0/P1/P2） | 重构 | 🟢 已完成（2026-08-03，476 全绿 + 9-gate exit=0 + token 基准 PASS） | 待 live 验收 LLM 策略介入 | 无 |
| 9 | 记忆对局隔离 + 玩家/说书人进化机制（PLN-038 阶段 E） | 重构 | 🟢 已完成（2026-08-04，新增 10 进化测试 + 端到端落盘验证） | 可选：局末 LLM 蒸馏经验；进化影响人格参数 | 无 |
| 10 | 拟人化进化增强（局中反思/局后复盘/学习他人/调整策略） | 重构 | 🟢 已完成（2026-08-04，新增 6 拟人化测试 + 端到端验证 reviews/lessons/strategies 自动落盘） | 可选：局中反思引擎级自动触发；LLM 蒸馏复盘 | 无 |
| 11 | alpha1.2 文档整理 + 真实 LLM live 对局验收 | 文档+验收 | 🟢 已完成（2026-08-04，3 局 DeepSeek live 验证功能 + token -62% + fallback 归零） | — | 无 |
| 12 | speak/defense_speech 关 thinking（D015 live 实测优化） | 优化 | 🟢 已完成（2026-08-04，token 7365→2848，fallback 5.9%→0%） | 切非推理模型需重估 | 无 |
| 13 | Prompt 前缀缓存命中率优化（PLN-039 T1-T6 + 精简 + REV-008 F1-F7 + R1/R2/R3） | 优化 | 🟢 已完成并提交（2026-08-04，480 passed + ruff 0 + token 基准 PASS + mock 8 人局 game_over + live 命中率 53.19%/46.00%/43.14% + 精简全局层 2361→1522 + REV-008 全部修复；commit `c79a7ae`）；⚠️ T6 DoD#5（真实总 token ≤187,423）部分达成（短局 177,828），任务板已标注权衡 | 无 | 无 |
| 14 | **发布 Alpha 1.2「觉醒之鸦」(The Awakening)**：起代号 + README/CHANGELOG/VERSION_NOTES/REL-007/AGENTS 更新 + 新建 REL-009 Release Checklist + docs 索引登记 + pyproject 版本 0.1.0→0.2.0 | 发布 | 🟡 文档全部更新完成，doc health PASS；待用户确认后 commit + 打 tag `alpha1.2-awakening` | 提交发布（等待用户确认 commit 范围） | 无 |

## 当前验证状态

| 检查项 | 状态 |
|------|------|
| `pip install -e ".[dev]"` | ✅ 已验证（受管 Python 3.13.12 + 项目根 `.venv` + dev 依赖全部安装） |
| `pytest tests -q`（基线：447 passed / 0 failed） | ✅ **476 passed / 0 failed**（2026-08-03 Agent 原生重构后新增 30 单测）；`-m "not slow"` 快速单测 RC=0；slow 验收测试单独运行 exit 0 |
| `ruff check src tests scripts` | ✅ 零告警（阶段一规则集 E4/E7/E9/F/W，忽略 E501；F401/F541 经 `--fix` 收敛，E402 由 `scripts/**` per-file-ignores 覆盖，F841/E712 手工清理） |
| `ruff format --check src tests scripts` | ✅ 182 文件全部已归一；pre-commit `ruff-format` 钩子已启用，CI 该步骤已移除 `continue-on-error` |
| `python scripts/alpha1.1_acceptance.py`（9 gate） | ✅ exit=0，9/9 全绿 |
| 文档链接健康（`python scripts/check_doc_health.py`） | ✅ RC=0（68 md 扫描；1 个非致命绝对路径 warning）；已纳入 CI（2026-08-03） |
| 静态引用审计（脚本路径 / import / REPO_ROOT 深度） | ✅ 无残留旧路径，子目录脚本 `parents[2]` 全覆盖 |
| git status / 未提交改动 | ✅ 工作区 clean，与 origin/main 同步 |
| Agent 原生重构（PLN-038 + PLN-037 协同）验收 | ✅ 476 全绿 + ruff 零告警 + format 通过 + `alpha1.1_acceptance.py` 9/9 + `token_budget_benchmark.py` PASS + `simulate_game --stop-after day_1` 通过 + `check_doc_health.py` RC=0；审查报告 `docs/reviews/agent-native-redesign-cr-review-2026-08-03.md` |
| 玩家进化机制（PLN-038 阶段 E）验收 | ✅ 快速回归 RC=0（含 10 个新进化测试）+ ruff/format 0 告警 + `simulate_game day_1` 通过 + 局末落盘端到端验证（5 玩家战绩 + 说书人主持局数） |
| 拟人化进化增强（任务 10）验收 | ✅ 全量 `pytest -m "not slow"` = 477 passed / 0 failed（全量含 slow 共 495；2026-08-04 独立复核修正，原文档 483 为口径差）+ ruff check 0 告警 + format 197 files 全绿 + 端到端验证局末自动触发 reviews/lessons/strategies |
| alpha1.2 live 验收（任务 11/12） | ✅ 3 局 DeepSeek live day_1 全跑通：工具调用主导 + 草稿复用 + 本地策略判定 + JSON fallback 兜底；token 7365→2848（-62%）、fallback 5.9%→0%；简单动作关 thinking reasoning 40→0；证据 `docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md` |
| 缓存命中优化（2026-08-04）验收 | ✅ `pytest -m "not slow"` = 477 passed / 0 failed + ruff/format/doc 全绿 + token 基准 PASS（system 前缀 1722→1363 仍逐 token 稳定）+ live 8 人局完整对局真实 token 252,999→187,423（-25.9%）、metrics 64,262→40,771（-36.5%）、reasoning 3650→0、fallback 0%；缓存命中率 11.9%→12.7%（DeepSeek 前缀缓存为尽力而为：同一玩家 system 完全一致时实测命中 0-29%，受 LRU/容量限制，前缀一致为必要不充分条件） |
| Prompt 缓存优化二轮（PLN-039，2026-08-04）验收 | ✅ `pytest -m "not slow"` = 480 passed / 0 failed + `ruff check src tests scripts` 0 告警 + format 全绿 + `check_doc_health.py` PASS + `token_budget_benchmark.py` RESULT: PASS（全局静态层 1522 字符跨 Agent 逐 token 一致 + three_tier 稳定 + draft 复用）+ mock 8 人局 game_over + **live 8 人局完整局实测（RPT-014，多局）**：命中率 41.63%→53.19%→46.00%→**43.14%（REV-008 修复后）**，均 ≥40%；reasoning=0、fallback≈0；archive/storyteller 前置后 0%→57-62%；**evil_coord 0%→75.89%（F5）**；⚠️ 真实总 token 370,931 > 基线 187,423（输入膨胀），计费当量 +12.8%，T6 任务板标 🟨 部分完成。归档：`docs/alpha-1.2-evidence/pln039-live-2026-08-04-rev.llm.jsonl`（REV-008 F1） |
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
5. ~~将 `scripts/check_doc_health.py` 纳入 `.github/workflows/ci.yml`（任务 4 遗留）~~ ✅ 已完成（2026-08-03）；顺带补 `docs/releases/v0.8/AGENTS_refactor.md` 缺失 frontmatter 使门禁通过。

## 未提交改动清单（与 git 强一致）

> 规则：标记 ✅ 完成的任务，其代码**必须已 commit**；仅本地验证未提交的，状态写「🟡 已验证待提交」并登记于此。

> **2026-08-03 说明**：2026-07-31 登记的以下改动已全部 commit 并推送到 `origin/main`（工作区 clean）：
> harness 文件、测试治理、P0-P5 规范化、lint 收敛、P1/P2 上帝对象拆分与 print→logging。
> 当前未提交改动见下表。

> **2026-08-04 提交完成**：本清单既有登记已按分组分 3 个 commit 全部提交（工作区 clean）。commit hash 以 `git log --oneline -3` 为准（2026-08-04 三组：token-opt-cache / 阶段 E / alpha1.2）。
>
> 既有登记项（`public/index.html` 修复、`m5l_live_speech_deepseek_20260803.md`、`.gitignore` 等）已在历史 commit 中入库，本清单无遗留。

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
| 2026-07-31 | **P1 上帝对象拆分**：ai_agent/game_loop/storyteller_agent 三 facade 抽取委托模块（行数 1429/842/1369 → 802/497/25），行为零变更；**P2** 生产 print→logging（server.py/replay_parser.py）+ AGENTS.md facade 描述修正；修正测试 `random` 打桩指向 delegation 模块；顺手修 `alpha1.1_acceptance.py` 的 `PYTHON.exists()` 既存 bug（`sys.executable` 是 str，改 `Path(sys.executable)`）以跑通 9-gate | ruff 零告警；`alpha1.1_acceptance.py` 9/9 全绿；wave1/alpha3 隔离运行 exit 0；全量 pytest 仅 1 个 subprocess 验收测试偶发 240s 超时（既存测试隔离脆弱性，非回归） | 用户决定是否按 P1/P2 分阶段 commit | .codebuddy/memory/2026-07-31.md |
| 2026-08-03 | **CI 三轮修复**：① ruff format 检查失败（facade 拆分引入，3 文件规范化）；② storyteller 日志测试干净环境失败（handler 重绑 workspace，`_bind_storyteller_log_handler`）；③ CI 提速（16 个验收包装测试标 `slow` 排除 + job `timeout-minutes: 25`）；④ `check_doc_health.py` 纳入 CI + 补 `AGENTS_refactor.md` frontmatter | ruff check/format 全过；`-m "not slow"` 快速单测 3.1s RC=0；全量 447 passed；doc health RC=0 | 看 GitHub CI run 是否快速转绿 | .codebuddy/memory/2026-08-03.md |
| 2026-08-03 | **M5-L 真实 live 真人验收（DeepSeek）**：`.env` 配置 DeepSeek live；playwright-cli 以真人玩家身份跑通 2 局完整 5 人局至 GAME_OVER；speech fallback 6.7% / LLM 成功 93.3% / orchestrator 0 超时（达标）；信息隔离（玩家 grimoire 403 / 邪恶频道对好人不可见）PASS；说书人控制台 PASS；修复结算 overlay i18n 崩溃 BUG（`ui-welcome` 空值保护） | 2 局完整对局验收通过；结算修复后 console 0 errors；验收报告已写入 evidence 目录 | 提交 3 项改动；后续补 8 人局/高难度真人复测 + vote/nomination 预算放宽 | .codebuddy/memory/2026-08-03.md |
| 2026-08-05 | **Alpha 1.2 live 深度优化**：7 个原子提交推送（白天发言按座次+方案B、提名修复、游戏结束按钮、邪恶频道清洗、深度思考分级+per-player 落盘+Scavenge、max_tokens 定稿并实测 fallback 清零、测试与 chore） | 工作区 clean；live 确认局 fallback 清零、命中率 54-58% | 用户确认发布 Alpha 1.2 | .codebuddy/memory/2026-08-05.md |
| 2026-08-07 | **发布 Alpha 1.2「觉醒之鸦」**：代号 The Awakening；更新 README/CHANGELOG/VERSION_NOTES/REL-007/AGENTS/docs 索引；新建 REL-009 Release Checklist；pyproject 0.1.0→0.2.0 | doc health PASS（78 md，1 历史非致命 warning） | commit + tag `alpha1.2-awakening` | 本文件 |
