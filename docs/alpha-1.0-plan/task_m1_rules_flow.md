# M1 任务板：规则与流程封板

## 当前定位

- **阶段**：M1
- **状态**：`Completed`
- **目标**：确保《暗流涌动》规则主链在自动局、真人局、混合局中都稳定。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [rule_matrix.md](../rule_matrix.md)
  - [remediation_backlog.md](../remediation_backlog.md)
  - [validation_report.md](../validation_report.md)

## 第一性原则

`alpha 1.0` 的规则目标不是一次性宣称“全规则完美”，而是让所有内测会踩到的主链规则都有明确实现、回归测试和可复盘日志。

## 任务清单

### M1-1：模拟停止条件修复

- 优先级：`P0`
- 范围：
  - `simulate_game.py`
  - 新增或补充模拟审计测试
- 任务：
  - [x] 修复 `--stop-after first_execution` 命中后仍继续推进的问题。
  - [x] 补齐 `--stop-after day_1`。
  - [x] 补齐 `--stop-after night_2`。
  - [x] 输出停止命中原因，便于审计日志判断。
- 验收：
  - [x] 三种 stop-after 参数均在命中后立即退出。
  - [x] 退出日志包含命中的阶段或事件。

### M1-2：高风险角色专项回归

- 优先级：`P0`
- 范围：
  - `src/engine/roles/outsiders.py`
  - `src/engine/roles/minions.py`
  - `src/engine/roles/demons.py`
  - `src/engine/nomination.py`
  - `tests/test_engine/`
- 任务：
  - [x] `scarlet_woman` 接管触发链专项测试。
  - [x] `baron` 外来者增量与 setup 分布专项测试。
  - [x] `drunken` 虚假身份与信息失真专项测试。
  - [x] `recluse` 邪恶误判注册专项测试。
  - [x] `butler` 投票约束专项测试。
  - [x] `mayor` 夜晚转移与白天胜利边界专项测试。
  - [x] `slayer` 一次性消耗、UI/AI 双链路专项测试。
- 验收：
  - [x] 每个角色至少 1 条规则正确性测试。
  - [x] `rule_matrix.md` 对应状态同步更新。

### M1-3：夜晚与死亡触发链审计

- 优先级：`P0`
- 范围：
  - `src/orchestrator/game_loop.py`
  - `src/agents/storyteller_agent.py`
  - `src/engine/roles/`
- 任务：
  - [x] 复核夜晚行动顺序与官方规则书顺序。
  - [x] 复核死亡玩家跳过普通行动。
  - [x] 复核 `ON_DEATH` 触发器例外路径。
  - [x] 复核保护、士兵、市长转移、恶魔击杀交互。
  - [x] 复核处决、圣徒胜负、恶魔死亡接管交互。
- 验收：
  - [x] `role_acceptance.py` 覆盖范围已纳入 `alpha1_rules_acceptance.py` 并通过。
  - [x] 夜晚主链相关测试通过。

### M1-4：Alpha1 规则门禁脚本

- 优先级：`P1`
- 范围：
  - `scripts/alpha1_rules_acceptance.py`
- 任务：
  - [x] 聚合规则专项测试。
  - [x] 聚合模拟 stop-after 验收。
  - [x] 输出 P0 规则检查摘要。
- 验收：
  - [x] `.\.venv\Scripts\python.exe scripts\alpha1_rules_acceptance.py` 可运行。
  - [x] 失败时能指出具体规则区域。

## 阶段完成标准

- [x] `pytest tests -q` 通过。
  - 低内存全量回归入口：`.\.venv\Scripts\python.exe scripts\run_full_tests_low_memory.py`。
- [x] `scripts/alpha3_acceptance.py` 通过。
- [x] `scripts/alpha1_rules_acceptance.py` 通过。
- [x] `rule_matrix.md` 中无未说明的 P0 规则缺口。

## 风险记录

- 高风险角色之间存在交叉影响，单测通过不代表整局无问题。
- `drunken / recluse / spy` 这类注册错误角色必须和说书人裁量日志一起验。

## 完成记录

- 2026-04-27：修复 `simulate_game.py` stop-after 判断，新增 `StopMatch` 命中原因与自定义 `SimulationStop` 中断。
- 2026-04-27：补齐 `tests/test_simulate_game.py` 中 `day_1 / night_2` 停止边界测试。
- 2026-04-27：补齐陌客误注册 helper 与默认误判行为；修复管家首夜/day0 绑定日。
- 2026-04-27：统一间谍信息 payload 为 `spy_book/book`，避免 `spy_grimoire` 与主链契约不一致。
- 2026-04-27：修复说书人替身缺 `mode` 时的鲁棒性；修复说书人局势分析 backend 调用签名。
- 2026-04-27：Mock embedding 维度跟随 `EMBEDDING_DIMENSION`，避免 mock 模拟局向量摄入报错。
- 2026-04-27：新增 `scripts/alpha1_rules_acceptance.py`，当前结果：`77 passed`。
- 2026-04-27：实际 mock 验证 `first_execution / day_1 / night_2` 均能命中后立即退出。
- 2026-04-27：`scripts/alpha3_acceptance.py` 通过。
- 2026-04-27：为子进程验收测试补齐 timeout，并新增低内存全量测试入口。
- 2026-04-27：修复送葬者 (Undertaker) 在夜晚查询处决时的轮次匹配逻辑（round_number - 1）。
- 2026-04-27：补齐 `DummyStoryteller` 缺失的 `decide_initial_setup_info` 与 `analyze_game_situation` 方法，修复验收脚本报错。
- 2026-04-27：修正 `persona_divergence_test` 的 `player_count` 设定，确保触发记忆蒸馏逻辑。
- 2026-04-27：全量回归测试 (321 passed) 达到 100% 通过。
