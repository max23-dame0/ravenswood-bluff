---
doc_id: "PLN-040"
title: "差异化玩家进化 + 量化基准方案与任务板"
category: "planning"
role: "[Delta]"
status: "draft"
date: "2026-08-07"
author: "Ravenswood Bluff"
---

# 差异化玩家进化 + 量化基准方案与任务板（PLN-040）

> **目标**：把 Alpha 1.2 已落地的"玩家进化"从"功能存在"推进到"**可量化证明 + 可感知差异化**"——即用户 2026-08-05 明确的未来方向：所有 agent 共享经验记忆、按玩家视角沉淀、实现人类玩家体验到不同 AI 差异化"活人感"。
> **执行方式**：本文档即任务板（Task Board）。新开窗口按 §6 任务顺序执行，每项完成需满足 §7 验收标准；全部完成后按清洁状态检查收尾。
> **前情**：Alpha 1.2（PLN-038 阶段 E / D013 / D014）已实现玩家进化四维（局中反思 / 局后复盘 / 学习他人 / 调整策略）+ `tendency` 四维画像，但**效果从未被量化验证**——当前所有验证仅是"文件落盘成功"（`reviews_done=1`），没有任何证据证明"进化后的 AI 真的变强了"或"不同 AI 真的可区分"。

---

## 1. 背景与动机

### 1.1 现状盘点（2026-08-07）

| 能力 | 状态 | 缺口 |
|------|------|------|
| 玩家进化四维（PLN-038 阶段 E / D014） | ✅ 已落地 | 效果零量化验证（胜率/Elo 对比、A/B 实验全空白） |
| `tendency` 四维画像（aggression/risk_taking/talkativeness/caution） | ✅ 已落地 | 微调幅度 ±0.02 级，**可能无法产生可感知差异**（未标定） |
| `learn_from_others` 学习他人经验 | ✅ 已落地 | 仅"胜方最佳玩家 → 全员"，无经验池检索/按视角差异化注入 |
| `PlayerProfileStore` 跨局档案 | ✅ 已落地 | 档案数据未反向驱动行为差异化（`build_evolved_tendency_summary` 仅 4 档标签） |
| AI trace 导出（`export_ai_traces.py`） | ✅ 已落地 | 无行为指纹聚合分析工具，无法量化玩家间差异 |
| 人格原型 `Archetype`（logic/aggressive/...） | ✅ 已落地 | 与进化倾向（tendency）未联动，差异化来源割裂 |

### 1.2 为什么是"下一个最值得做"

- **命中用户明确方向**：2026-08-05 用户提出"所有 agent 共享总结和经验记忆——按每个单独玩家视角沉淀，经验统一学习；新对局 agent 依经验+技巧+自身人格设定/性格游玩，实现人类玩家体验到不同 AI 差异化的活人感"。
- **补齐项目最大证据缺口**：进化机制"做了但没被证明"，是 Alpha 1.2 发布后最显眼的未闭环项（REL-009 Known Issue #3）。
- **天然可量化**："活人感"可指标化为**行为指纹距离**（玩家间）与**进化增益**（跨局胜率/Elo），均可用 mock 固定种子大批量跑（毫秒级、零成本），关键结论用少量 live 抽查。

---

## 2. 候选方向留档（2026-08-07 全量分析，本计划立项 A）

> 以下为方向分析时产生的**全部候选方向**，逐一留档（量化性 / 创新性 / 价值杠杆 / 成本），供后续独立立项参考。**本计划（PLN-040）只实施方向 A**，其余方向不在此推进。

| 方向 | 内容 | 量化性 | 创新性 | 价值杠杆 | 成本 | 结论 |
|------|------|:--:|:--:|:--:|:--:|------|
| **A. 差异化玩家进化 + 量化基准** | 共享经验池 → 人格差异化 → 可区分度/胜率验证闭环 | ★★★★★ | ★★★★★ | ★★★★★ | 中（mock 为主） | ✅ **本计划立项** |
| B. 进化有效性验证 | 固定种子 A/B：进化 K 局后 vs 冷启动的 Elo/胜率对比 | ★★★★★ | ★★★★ | ★★★ | 低 | 作为 A 的 T4 子集并入 |
| C. 对局数据飞轮 | trace/决策/token/胜负汇总为可查询数据仓库（分析仪表盘） | ★★★★★ | ★★★ | ★★★★ | 低 | A 的 P0 基础设施（行为指纹分析依赖 trace），不单独立项 |
| D. 数据驱动平衡性调优 | 大规模 mock 统计角色/阵营胜率，数据驱动调整说书人扭曲策略 | ★★★★★ | ★★★ | ★★★ | 低 | 暂缓（与 A 无依赖，可并行立项） |
| E. Token/缓存收尾 | PLN-039 剩余 gap（辅助调用三层化/阈值上调） | ★★ | ★ | ★ | 高（live） | 已近架构上限（命中率 43-63%），边际收益低，不推荐 |
| F. 说书人 LLM 策略 live 验收 | `BOTC_ST_LLM_STRATEGY=low|on` 真人局验收 | ★★ | ★ | ★★ | 高（live） | 待 REL-009 遗留，成本高收益低，暂缓 |

**选择 A 的理由**：唯一直接命中用户明确方向；量化闭环完整（可区分度 + 进化增益双指标）；差异化是社交推演游戏的核心卖点；B/C 是 A 的自然子集，做 A 可一箭三雕。

---

## 3. 方向 A 核心目标与量化指标

### 3.1 核心目标

1. **量化现状基线**：构建 AI 玩家行为指纹采集与评估基准，先量化"当前玩家到底有多同质"。
2. **实现可感知差异化**：共享经验池 + 差异化注入，让不同 AI 玩家行为指纹距离显著拉开、且跨局稳定。
3. **证明进化有效**：进化 K 局后的玩家 vs 冷启动玩家存在可测量的水平增益（胜率/Elo 差分）。

### 3.2 量化验收指标（定义）

| 指标 | 定义 | 目标值 | 采集方式 |
|------|------|:--:|------|
| **M1 玩家间指纹距离** | 同局两两玩家的行为指纹归一化欧氏距离均值 | **≥ 0.30**（对比基线现状值） | 行为指纹基准脚本（mock 固定种子） |
| **M2 指纹跨局稳定性** | 同一玩家连续 K 局的指纹向量自相关/方差 | 方差 ≤ 阈值（稳定） | 同上，跨局聚合 |
| **M3 盲测识别准确率** | 真人玩家识别"某段发言出自哪个 AI"（5 选 1）的猜中率 | **> 20%**（随机基线 20%，显著高于随机） | 盲测样本导出 + 真人标注 |
| **M4 进化增益** | 同种子下，进化 K 局后 vs 冷启动玩家的胜率差（Elo 差分） | **胜率 +5pp 或 Elo +25**（K=50 局） | Elo/胜率 A/B 基准（mock） |
| **M5 倾向标定响应** | `tendency` 微调幅度与行为指纹变化的相关性 | 相关性显著（可感知） | 标定实验（幅度扫描） |

> 说明：M1/M2/M3 度量"差异化（活人感）"，M4 度量"进化有效性"，M5 度量"差异化来源是否真实生效"。全部以 mock 为主，M3 需少量真人盲测。

---

## 4. 目标架构（本轮落地形态）

```
+--------------------------------------------------------------------------+
| ① 行为指纹层（新增 scripts/benchmark/player_distinctness_benchmark.py）    |
|    从对局 trace 聚合每玩家行为指纹向量：                                    |
|    - 发言特征：平均长度 / 长度方差 / 每天发言 token 趋势（信息释放节奏）      |
|    - 决策特征：主动提名频率 / 投票摇摆度（与自身历史一致性）/ 投 yes 率       |
|    - 社交特征：被提及次数 / 主动提及他人次数 / 谎言-事实比例（evil）        |
|    - 倾向特征：tendency 画像（aggression/risk_taking/talkativeness/caution）|
|    → 输出：指纹向量 CSV + 两两距离矩阵 + 基准报告                         |
+--------------------------------------------------------------------------+
| ② 共享经验池（新增 src/agents/memory/shared_pool.py）                      |
|    - 跨局经验统一沉淀（lessons/reflections/strategies 去私密化后入池）        |
|    - 按玩家视角检索注入（角色 + 阵营 + 战局相似度），而非"全员同一段文案"     |
|    - 保留信息隔离（敏感过滤复用 D013/D014 既有实现）                         |
+--------------------------------------------------------------------------+
| ③ 差异化注入（改造 PlayerProfileStore / persona 联动）                     |
|    - tendency 微调幅度标定（±0.02 → 可感知区间，仍守 0.05~0.95 边界）       |
|    - Archetype × tendency 联动：进化倾向落到"打法倾向文案 + 行为参数偏移"    |
|    - build_long_term_summary 注入时按玩家差异化（当前 4 档标签 → 连续画像）  |
+--------------------------------------------------------------------------+
| ④ 进化有效性验证（新增 scripts/benchmark/evolution_ab_benchmark.py）       |
|    - 固定种子：冷启动组 vs 进化组（同 seed 多局循环）                         |
|    - 统计胜率 / Elo 差分 / 决策质量代理指标                                  |
+--------------------------------------------------------------------------+
```

---

## 5. 涉及文件清单（初版，以实施为准）

| 文件 | 改动内容 |
|------|---------|
| `scripts/benchmark/player_distinctness_benchmark.py` | **新增**：行为指纹采集 + 两两距离矩阵 + 基准报告（P0 核心） |
| `scripts/benchmark/evolution_ab_benchmark.py` | **新增**：进化有效性 A/B（Elo/胜率差分） |
| `src/agents/memory/shared_pool.py` | **新增**：共享经验池（沉淀/检索/注入） |
| `src/agents/memory/player_profile.py` | 差异化注入：tendency 微调幅度标定 + 连续画像文案 + 经验池对接 |
| `src/agents/ai_agent.py` / `ai_agent_delegation.py` | 注入链路：共享经验池摘要接入 `act()` stable_context |
| `src/orchestrator/game_loop.py`（或 delegation） | 局末沉淀钩子扩展：去私密化后写入共享池 |
| `tests/test_agents/test_player_evolution.py` | 新增共享池/差异化/基准测试 |
| `tests/test_agents/`（新增指纹/AB 测试文件） | 行为指纹采集正确性、A/B 统计正确性 |

---

## 6. 任务板（Task Board）

| 任务 ID | 阶段 | 优先级 | 状态 | 目标 | 验收标准（DoD） |
|:--:|:--:|:--:|:--:|------|------|
| **T1** | 行为指纹 | 🥇P0 | ⬜ 待开始 | 行为指纹采集 + 基准脚本落地，量化**现状**玩家同质度 | T1.1 指纹向量 ≥ 10 维、从 mock 对局 trace 可采集；T1.2 脚本输出两两距离矩阵 + 基准报告（现状态基线值）；T1.3 `pytest` 新增指纹采集单测全绿 |
| **T2** | 共享经验池 | 🥇P0 | ⬜ 待开始 | 跨局经验池：沉淀 → 检索 → 按玩家视角注入 | T2.1 敏感过滤复用（恶魔/队友名单不入池）；T2.2 同角色/阵营相似战局可检索；T2.3 注入后 `act()` stable_context 仍逐 token 稳定（不破坏前缀缓存） |
| **T3** | 差异化注入 | 🥈P1 | ⬜ 待开始 | tendency 标定 + Archetype 联动，使差异**可感知** | T3.1 倾向幅度标定实验（M5）确定可感知区间；T3.2 同 archetype 不同 tendency 玩家指纹距离显著拉开（M1）；T3.3 旧 profile 兼容（tendency 字段向后兼容） |
| **T4** | 进化有效性 | 🥈P1 | ⬜ 待开始 | 进化 K 局后 vs 冷启动的胜率/Elo A/B | T4.1 固定种子 A/B 脚本落地；T4.2 进化组胜率 +5pp 或 Elo +25（K=50，M4）；T4.3 如不达标 → 输出诊断（进化为写入而未影响行为）并回退/调整 |
| **T5** | 盲测验证 | 🥉P2 | ⬜ 待开始 | 真人盲测：发言识别准确率 > 随机基线 | T5.1 盲测样本导出（每玩家 N 段发言匿名化）；T5.2 ≥ 3 名真人标注，5 选 1 猜中率 > 20%（M3）；T5.3 报告留档 evidence |
| **T6** | 收尾验证 | 🥇P0 | ⬜ 待开始 | 全量回归 + live 抽查 + 文档 | T6.1 `pytest -m "not slow"` 全绿 + ruff 0；T6.2 mock 8 人局 game_over；T6.3 少量 live 抽查（差异化/进化的真实 LLM 表现）；T6.4 PLN-040 状态 published + PROGRESS 登记 |

> 状态列：⬜ 待开始 → 🟨 进行中 → 🟢 已完成（完成后在 PROGRESS.md 待提交清单登记）
> 任务顺序：T1 → T2 → T3 → T4 → T5 → T6（T4/T5 可并行，T6 收尾）

## 6.1 T1 — 行为指纹采集 + 基准脚本

**改动文件**：`scripts/benchmark/player_distinctness_benchmark.py`（新增）、`tests/test_agents/`（新增单测）

**步骤**：
1. 定义行为指纹向量（≥10 维）：发言平均长度 / 长度方差 / 每日发言 token 趋势 / 主动提名频率 / 投票摇摆度 / 投 yes 率 / 被提及次数 / 主动提及他人次数 / 谎话比例（evil 可测）/ tendency 四维。
2. 从 `GameDataCollector.export_ai_traces` 或对局事件日志采集特征（优先 mock 可复现路径）。
3. 输出：每玩家指纹向量 CSV + 两两归一化欧氏距离矩阵 + 汇总报告（均值/最大/最小距离）。
4. 固定种子跑 N 局 mock（默认 N=10，可参数化），求距离统计。

**验收**：
- 脚本运行产出 `data/bench/player_distinctness_report.json`（含基线值）。
- 新增指纹采集单测（如"同局两玩家指纹向量可计算"、"固定种子可复现"）。
- **基线值记录为本计划 M1/M2 的"现状对照值"**（T3 完成后对比）。

## 6.2 T2 — 共享经验池

**改动文件**：`src/agents/memory/shared_pool.py`（新增）、`src/agents/memory/player_profile.py`、`src/orchestrator/game_loop*.py`、`src/agents/ai_agent*.py`

**步骤**：
1. 池结构：`data/agents/_shared_pool/lessons.jsonl`（去私密化后的角色通用经验 + 来源 meta）。
2. 局末沉淀钩子：`_finalize_agent_player_profiles` 中将 lessons/reflections/strategies 去私密化后写池（复用 D014 `_player_lesson_sensitive` 过滤）。
3. 检索：按（角色，阵营，战局相似度）检索 top-k 经验；每个玩家注入**个性化子集**（同角色优先 + 全局优秀经验）。
4. 注入 `act()` stable_context 首段，保持同局逐 token 稳定（复用 `build_long_term_summary` 通道，勿破坏 PLN-039 前缀结构）。

**验收**：
- 敏感过滤生效（恶魔/队友名单等不入池，单测断言）。
- 同角色不同玩家注入子集不同（差异化基础）。
- `token_budget_benchmark.py` 仍 PASS（前缀稳定未破坏）。

## 6.3 T3 — 差异化注入（tendency 标定 + Archetype 联动）

**改动文件**：`src/agents/memory/player_profile.py`、`src/agents/persona/persona_registry.py`、`scripts/benchmark/player_distinctness_benchmark.py`

**步骤**：
1. **倾向幅度标定实验**：扫描 tendency 微调幅度（±0.02/±0.05/±0.10/±0.15），跑指纹基准，找到"可感知差异"的最低幅度（M5）。保守原则：仍守 0.05~0.95 边界、±0.02 级起步，找到生效阈值。
2. **Archetype × tendency 联动**：把进化后的 tendency 映射到行为参数偏移（如 talkativeness 高 → 发言更长/更主动；caution 高 → 信息释放更慢），形成"人格基线 + 进化偏移"的复合画像。
3. `build_evolved_tendency_summary` 从 4 档标签升级为连续画像文案（可差异化描述）。

**验收**：
- M1：同 archetype 不同 tendency 的玩家指纹距离 ≥ 0.30（或相对基线显著提升）。
- M5：标定实验报告留档（确定生效幅度）。
- 旧 `profile.json` 无 tendency 时默认补齐（向后兼容）。

## 6.4 T4 — 进化有效性 A/B

**改动文件**：`scripts/benchmark/evolution_ab_benchmark.py`（新增）

**步骤**：
1. 固定种子框架：同 seed、同初始阵容，对照组（冷启动，无跨局档案）vs 实验组（进化 K 局后档案）。
2. 每组跑 N 局（默认 N=50，可参数化），统计胜率、Elo 差分（简单 Elo：胜 +10 / 负 -10 / 依对手调整）。
3. 输出置信区间（或用 win-rate 差分 + 样本量判断显著）。

**验收**：
- 进化组胜率 ≥ 冷启动 +5pp 或 Elo ≥ +25（K=50，M4）。
- 若不达标：脚本输出诊断（哪些倾向实际被注入、行为是否改变），据此调整（不硬凑达标）。

## 6.5 T5 — 真人盲测

**改动文件**：`scripts/export/export_blind_test_samples.py`（新增，可并入 T1 脚本）

**步骤**：
1. 导出盲测样本：每个 AI 玩家取 N 段公开发言（匿名化，去角色/名字）。
2. ≥ 3 名真人标注：5 选 1 判断发言属于哪个 AI。
3. 统计猜中率 vs 随机基线（20%）。

**验收**：
- 猜中率 > 20% 且样本量 ≥ 30 次标注（M3）。
- 报告留档 `docs/alpha-1.2-evidence/` 或 reviews。

## 6.6 T6 — 收尾验证与文档

**命令**：
```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -m "not slow"
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
.\.venv\Scripts\python.exe scripts\benchmark\token_budget_benchmark.py
.\.venv\Scripts\python.exe scripts\check_doc_health.py
```

**文档**：
- PLN-040 status draft → published，任务板状态回填。
- PROGRESS.md 登记新任务 + 验证状态。
- 若产生量化证据（基准报告/盲测/A-B 报告）→ `docs/alpha-1.2-evidence/` 或 reviews 归档。

---

## 7. 全局验收标准（DoD）

1. `pytest tests -m "not slow"` 全绿（含新增指纹/池/AB 单测）；`ruff check src tests scripts` 0 告警；`ruff format --check` 全绿。
2. `scripts/benchmark/token_budget_benchmark.py` → **RESULT: PASS**（前缀缓存结构未被差异化注入破坏）。
3. `scripts/alpha1.1_acceptance.py` 9/9 exit=0（信息隔离、难度行为等不回退）。
4. `scripts/check_doc_health.py` RC=0。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 差异化注入破坏前缀缓存结构 | token 成本回退 | T2/T3 每步跑 `token_budget_benchmark.py`，stable_context 结构不变仅内容变 |
| tendency 幅度过大导致行为失控 | 玩家不可信/破坏平衡 | 标定实验限幅（0.05~0.95 边界 + ±0.02 级起步），先测 M5 再放开 |
| 共享经验池泄露私密信息 | 信息隔离破坏 | 复用 D013/D014 敏感过滤，入池前强制去私密化 + 单测断言 |
| 进化 A/B 不显著 | 进化"写入未影响行为" | T4.3 输出诊断定位断点（注入未生效/倾向无感知），回退或调整参数，不硬凑达标 |
| mock 与 live 行为差异 | 量化结论不适用于真实 LLM | 以 mock 为量化主体（可复现），T6.3 少量 live 抽查关键结论 |
| 盲测样本量不足 | 结论无统计意义 | 每玩家 ≥ 10 段发言、≥ 3 标注人、≥ 30 次标注 |

## 9. 相关文档

- `docs/plans/agent-native-redesign-plan.md`（PLN-038：Agent 原生重构 + 阶段 E 进化）
- `docs/plans/prompt-cache-optimization-plan.md`（PLN-039：前缀缓存结构，T2/T3 须保持）
- `docs/releases/alpha-1.2-agent-native-release.md`（REL-007：Alpha 1.2 发布记录）
- `docs/releases/alpha-1.2-release-checklist.md`（REL-009：发布门禁，Known Issue #3 即"进化待 live 验证"）
- `DECISIONS.md`（D013 记忆隔离+进化 / D014 拟人化进化）
- `docs/guides/prompt-design.md`（REF-006：prompt 结构，注入链路参考）
- `.codebuddy/memory/2026-08-07.md`（方向分析记录）
