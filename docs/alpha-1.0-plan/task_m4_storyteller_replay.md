# M4 任务板：说书人真相源与复盘封板

## 当前定位

- **阶段**：M4
- **状态**：`Done`
- **目标**：说书人成为内测版本中稳定、可解释、可导出的裁定源。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [alpha-0.3-plan/task_st_ai.md](../alpha-0.3-plan/task_st_ai.md)
  - [alpha-0.3-release-summary.md](../alpha-0.3-release-summary.md)
  - [rule_matrix.md](../rule_matrix.md)

## 第一性原则

说书人可以有主观裁量，但每个主观裁量都必须有输入、分类、理由和可复盘出口。玩家视角只能看到该看的结果，不能看到幕后真相。

## 任务清单

### M4-1：固定信息来源审计

- 优先级：`P0`
- 范围：
  - `src/agents/storyteller_agent.py`
  - `src/orchestrator/game_loop.py`
  - 信息角色实现
- 任务：
  - [x] 审计洗衣妇信息来源。
  - [x] 审计图书馆员信息来源。
  - [x] 审计调查员信息来源。
  - [x] 审计厨师信息来源。
  - [x] 审计共情者信息来源。
  - [x] 审计送葬者信息来源。
  - [x] 审计占卜师红鲱鱼链路。
- 验收：
  - [x] 每类私密信息都能追踪到说书人或明确规则来源。

### M4-2：弹性规则 judgement 强化

- 优先级：`P0`
- 范围：
  - judgement ledger
  - storyteller balance
  - history export
- 任务：
  - [x] 中毒信息失真记录。
  - [x] 醉酒信息失真记录。
  - [x] 隐士误判注册记录。
  - [x] 间谍误判注册记录。
  - [x] 红鲱鱼选择与命中记录。
  - [x] 市长转移裁量记录。
- 验收：
  - [x] `storyteller_acceptance.py` 覆盖关键 judgement 分类。
  - [x] 每局结束后可导出裁量摘要。

### M4-3：玩家/说书人复盘边界

- 优先级：`P0`
- 范围：
  - history API
  - frontend history detail
  - export assets
- 任务：
  - [x] 玩家历史详情只展示玩家可见信息与已公开结果。
  - [x] 说书人历史详情展示完整裁量摘要。
  - [x] 测试玩家端不泄露未公开真相。
  - [x] 测试说书人端能读取裁量摘要。
- 验收：
  - [x] 玩家历史详情与说书人历史详情的信息边界不同且可测试。

### M4-4：内测问题导出包

- 优先级：`P1`
- 范围：
  - `scripts/`
  - data exports
  - logs
- 任务：
  - [x] 按 `game_id` 导出 game history。
  - [x] 按 `game_id` 导出 AI traces。
  - [x] 按 `game_id` 导出 storyteller judgements。
  - [x] 附带 metrics 摘要。
  - [x] 附带关键日志片段。
- 验收：
  - [x] 单命令可生成内测问题定位包。

## 阶段完成标准

- [x] `storyteller_acceptance.py` 通过并纳入 alpha1 聚合门禁。
- [x] 每局结束后能导出完整裁量摘要。
- [x] 玩家接口不泄露说书人内部日志。
- [x] 固定信息与特殊裁量来源可追踪。

## 风险记录

- 裁量摘要进入历史详情时最容易引入视角泄露。
- “可解释”不等于“公开给玩家”，需要严格区分玩家端和说书人端。

## 完成记录

- 2026-04-28：自动化契约已验证通过：`scripts/storyteller_acceptance.py` 输出 `storyteller acceptance: ok`；低内存全量 pytest 已知输出为 `321 passed`，但外层命令曾因工具超时返回 124。
- 已有保护覆盖说书人裁量摘要导出、说书人历史详情读取、judgement 分类分布，以及 balance sample export 的 suppressed/distorted/legacy fallback 样本检查。
- 2026-04-28：`scripts/export_all_assets.py` 已升级为 alpha1 内测问题包导出器：单命令按 `game_id` 生成 `game_history.json`、`ai_traces.json`、`storyteller_judgements.json`、`metrics_summary.json`、日志尾片段和 `manifest.json`。
- 2026-04-28：新增问题包回归测试，验证 history、AI trace、storyteller judgement、metrics、log tail 与 manifest 全部落盘；补齐 settlement judgement summary 的 `bucket` 聚合导出。
- 2026-04-28：验证通过：`.\.venv\Scripts\python.exe -m pytest tests\test_state\test_game_record.py tests\test_engine\test_data_collector.py -q`，结果 `8 passed`；`.\.venv\Scripts\python.exe -B scripts\storyteller_acceptance.py`，结果 `storyteller acceptance: ok`。
- 2026-04-29：新增玩家视角历史详情导出与 API：`/api/game/history/{game_id}/player/{player_name}`，玩家端递归剔除 `true_role_id`、`storyteller_judgements`、`judgement_summary` 等幕后字段；说书人完整详情仍保留完整裁量摘要。
- 2026-04-29：玩家前端历史详情已切到玩家视角 API，并移除说书人裁量摘要渲染；新增 API/UI 回归测试覆盖玩家端不泄露真实身份与裁量摘要。
- 2026-04-29：清理动作：已将 `data/_pytest*/`、`data/_probe*`、`data/*.corrupt_*`、`tests/test_runs/` 等测试/恢复产物加入 `.gitignore`；实际删除受当前文件 ACL 限制，`Remove-Item` 对这些旧生成文件返回 `Access denied`，未强制改权限。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -m pytest tests\test_state\test_game_record.py tests\test_orchestrator\test_gameover_api.py tests\test_orchestrator\test_gameover_ui.py -q`，结果 `15 passed`；`.\.venv\Scripts\python.exe -B scripts\storyteller_balance_acceptance.py`，结果 `storyteller balance acceptance: ok`；`.\.venv\Scripts\python.exe -B scripts\storyteller_acceptance.py`，结果 `storyteller acceptance: ok`。
- 2026-04-29：补齐特殊裁量 judgement：隐士/间谍误注册 active 与 inactive 都记录到 `registration.*` bucket；红鲱鱼选择记录到 `setup.red_herring`，占卜师命中/未命中记录到 `night_info.red_herring`；市长夜杀转移记录到 `night_kill.mayor_redirect`。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_storyteller_judgement_logging.py -q`，结果 `21 passed`；`.\.venv\Scripts\python.exe -B scripts\storyteller_acceptance.py`，结果 `storyteller acceptance: ok`。
- 2026-04-29：固定信息来源审计完成：`tests/test_engine/test_role_skill_audit.py` 覆盖洗衣妇、图书馆员、调查员、厨师、共情者、送葬者与占卜师红鲱鱼规则来源；`tests/test_orchestrator/test_storyteller_judgement_logging.py` 覆盖固定信息经由 storyteller build contract，并输出 `source=build_storyteller_info`、`bucket=night_info.fixed_info`、`contract_mode=fixed_info`、`adjudication_path=fixed_info.adjudicated`。
- 2026-04-29：验证通过：`.\.venv\Scripts\python.exe -m pytest tests\test_engine\test_role_skill_audit.py tests\test_orchestrator\test_storyteller_judgement_logging.py -q`，结果 `46 passed`。
- M4 当前任务清单已全部完成；后续进入 M6 前仍建议保留全量 alpha1 聚合门禁作为发布前确认。
