---
description: 全项目通用约束（语言/框架无关）
globs: **/*.py
alwaysApply: true
---
# 全局规则 (global)

> 本规则始终生效。涉及具体模块时叠加对应模块规则。

## 核心约束

- **GameState 不可变**：所有状态迁移用 `with_update / with_player_update / with_event / with_message`，禁止 `state.x = y` 或 `state.players[i].x = y`。**why**：快照一致性。**when_remove**：重构为可变模型时。
- **信息隔离**：Agent 只接收 `AgentVisibleState`（经 `InformationBroker` 过滤），绝不直接传 `GameState`。**why**：防信息泄露。**when_remove**：设计支持全知 Agent 时。
- **事件可见性**：`EventBus.publish` 必须带正确 `visibility`；`TEAM_EVIL` 不得泄露到 `PUBLIC`。**why**：破坏游戏平衡。**when_remove**：调试开关。
- **facade 不堆逻辑**：`ai_agent.py` / `game_loop.py` 仅路由，逻辑在各自子模块。**why**：可维护性。
- **白天发言顺序**：最终发言逐次处理，禁 `asyncio.gather`。**why**：后发言者需先发言者事件。
- **完整闭环才算完成**：mock 通过 ≠ 完成，live 模式需真人验收（见 `CLAUDE.md` §9.9）。

## 代码风格

- ruff 管理；`target-version=py311`，`line-length=100`（见 `pyproject.toml`）。
- 运行 `ruff check src tests` 应无告警。

## 禁止模式

- 直接修改 `GameState` 字段（绕过 `with_*` 工厂）。
- 将全量 `GameState` 传给 Agent / 在 PUBLIC 事件内嵌私密信息。
- 仅在 mock 通过就标记任务 ✅（清洁状态第 6 项）。

## 推荐模式

- 新增能力先查 `src/agents/` 或 `src/orchestrator/` 对应子模块。
- 测试默认 `MockBackend`（`BOTC_BACKEND=mock`），每个测试自建 SQLite DB 避免锁竞争。
