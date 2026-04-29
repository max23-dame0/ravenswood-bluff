# M6 任务板：发布工程与内测包

## 当前定位

- **阶段**：M6
- **状态**：`Done`
- **目标**：让内测发布不是“开发者本机能跑”，而是有明确启动、诊断、回滚和反馈流程。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [README.md](../../README.md)
  - [CHANGELOG.md](../../CHANGELOG.md)
  - [VERSION_NOTES.md](../../VERSION_NOTES.md)

## 第一性原则

发布工程的目标是降低内测沟通成本。内测玩家知道怎么启动、怎么反馈；开发者拿到 `game_id` 就能定位问题。

## 任务清单

### M6-1：发布文档更新

- 优先级：`P0`
- 范围：
  - `README.md`
  - `CHANGELOG.md`
  - `VERSION_NOTES.md`
- 任务：
  - [x] README 更新到 alpha1.0 口径。
  - [x] 增加 alpha1.0 changelog。
  - [x] 更新版本说明，保持内测口径保守。
  - [x] 明确 mock/live 模式启动方式。
- 验收：
  - [x] 新人按 README 可以启动并进入 UI。

### M6-2：发布 Checklist

- 优先级：`P0`
- 范围：
  - `docs/alpha-1.0-release-checklist.md`
- 任务：
  - [x] 新增发布 checklist。
  - [x] 覆盖 P0 完成情况。
  - [x] 覆盖验收命令。
  - [x] 覆盖前端真人验收记录。
  - [x] 覆盖已知问题确认。
- 验收：
  - [x] checklist 全部勾选后才能打 `alpha1.0` 标签。

### M6-3：Known Issues

- 优先级：`P0`
- 范围：
  - `docs/alpha-1.0-known-issues.md`
- 任务：
  - [x] 列出可接受遗留问题。
  - [x] 标注影响范围。
  - [x] 标注规避方式。
  - [x] 标注计划修复阶段。
- 验收：
  - [x] 所有未完成 P1/P2 都有去向。

### M6-4：Alpha1 聚合门禁

- 优先级：`P1`
- 范围：
  - `scripts/alpha1_acceptance.py`
- 任务：
  - [x] 聚合 `pytest tests -q`。
  - [x] 聚合 `alpha3_acceptance.py`。
  - [x] 聚合 `frontend_acceptance.py`。
  - [x] 聚合 `storyteller_acceptance.py`。
  - [x] 聚合 `role_acceptance.py`。
  - [x] 聚合 `alpha1_rules_acceptance.py`。
  - [x] 支持 live smoke 手动开关。
- 验收：
  - [x] `scripts/alpha1_acceptance.py` 可作为发布前总门禁。

### M6-5：内测反馈模板

- 优先级：`P1`
- 范围：
  - docs
  - issue template 或 markdown 模板
- 任务：
  - [x] 记录 `game_id`。
  - [x] 记录发生时间。
  - [x] 记录玩家模式。
  - [x] 记录复现步骤。
  - [x] 记录导出包路径。
  - [x] 记录预期行为与实际行为。
- 验收：
  - [x] 内测问题能通过 `game_id` 找到对应数据资产。

### M6-6：日志与数据目录控制

- 优先级：`P1`
- 范围：
  - `data/`
  - logs
  - collector config
- 任务：
  - [x] 梳理数据目录结构。
  - [x] 标注可清理目录。
  - [x] 控制快照与日志体积。
  - [x] 提供内测前清理说明。
- 验收：
  - [x] 内测多局后磁盘占用风险可控。

## 阶段完成标准

- [x] README、CHANGELOG、VERSION_NOTES 更新。
- [x] 发布 checklist 完成。
- [x] Known Issues 完成。
- [x] Alpha1 聚合门禁可运行。
- [x] 至少保留一份真实内测候选局导出资产。

## 发布冻结规则

冻结后只允许：

- P0 bugfix。
- 文档修正。
- 发布脚本修正。
- 不改变行为的日志与诊断增强。

## 风险记录

- 内测问题如果缺少 `game_id`，定位成本会急剧升高。
- 日志和快照在长局中可能增长很快，需要明确清理策略。

## 完成记录

- 2026-04-29：发布文档已更新到 Alpha 1.0 内测候选口径：`README.md`、`CHANGELOG.md`、`VERSION_NOTES.md`。
- 2026-04-29：新增 `docs/alpha-1.0-feedback-template.md`，内测问题反馈包含 `game_id`、发生时间、玩家/说书人模式、复现步骤、导出包路径、预期行为与实际行为。
- 2026-04-29：新增 `docs/alpha-1.0-data-operations.md`，梳理 `data/games.db`、`data/sessions/`、`data/exports/<game_id>/`、`storyteller_run.log`、测试产物和 corrupt 备份的保留/清理策略。
- 2026-04-29：`docs/alpha-1.0-release-checklist.md` 已覆盖 P0/P1 门槛、验收命令、mock/live smoke、前端真人/半真人验收、known issues 与冻结规则。
- 2026-04-29：`scripts/alpha1_acceptance.py` 已纳入 `alpha1_rules_acceptance.py`、`frontend_acceptance.py`、`storyteller_acceptance.py`、`role_acceptance.py`、`m5_ai_player_experience_acceptance.py`、`alpha3_acceptance.py`，并保留 full pytest 与 live smoke 显式开关。
- 2026-04-29：修复 M5/Alpha3 门禁暴露的高可信私密信息记忆回归：`WorkingMemory.get_recent_context()` 重新渲染客观/高可信/公开分层记忆，AI 行动上下文重新带入高可信与公开记忆摘要。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -m pytest tests\test_agents\test_agent_reasoning.py -k "high_confidence_private_info_survives_phase_archive_and_public_noise or private_info_is_pinned_in_anchor_memory or speak_prompt_prioritizes_high_confidence_over_conflicting_public_claims or vote_reasoning_stays_high_confidence_first_after_multi_day_archives" -q`，结果 `4 passed`。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -B scripts\m5_ai_player_experience_acceptance.py`，结果 `m5 ai player experience acceptance: ok`；`.\.venv\Scripts\python.exe -B scripts\alpha3_acceptance.py`，结果 `alpha3 acceptance: ok`。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -B scripts\alpha1_acceptance.py`，结果 `alpha1 acceptance: ok`；默认门禁 `6 passed / 0 failed / 2 skipped`，skipped 为需显式开启的 full pytest 与 live smoke。
- 2026-04-29：修复 `simulate_game.py --stop-after game_over` 提前截断结算落库的问题；完整 mock 候选局 `225c0271-fa41-465e-9114-dce7379c1f9f` 已落库并导出至 `data/exports/225c0271-fa41-465e-9114-dce7379c1f9f/`，导出资产包含 `game_history.json`、`ai_traces.json`、`storyteller_judgements.json`、`metrics_summary.json`、`manifest.json` 与日志尾部。
- 剩余发布前人工项：live smoke 与浏览器真人/半真人验收需要在发布冻结前按 checklist 补实际执行信息。
