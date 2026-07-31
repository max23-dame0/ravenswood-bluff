---
description: 不可变状态与持久化模块规则
globs: src/state/**/*.py
alwaysApply: false
---
# 状态规则 (state)

> 适用于 `src/state/**`：GameState 模型、SQLite 持久化、事件日志、快照。

## 核心约束

- **GameState 不可变**：`frozen=True` Pydantic 模型。迁移只用 `with_update / with_player_update / with_event / with_message`，返回新快照。orchestrator 持有权威 `self.state` 并在每次迁移后替换。**why**：快照一致性 + 可重放。**when_remove**：重构为可变模型时。
- **持久化用 aiosqlite**：`GameRecordStore` 异步 SQLite。测试套件**每测自建 DB** 避免锁竞争；勿跨并行测试共享单 DB。**why**：SQLite 并发锁。
- **事件日志**：`event_log.py` 在内存容纳事件；`snapshot.py` 提供状态快照供重放/调试。

## 代码风格

- 核心模型集中在 `game_state.py`（`GameState / PlayerState / GamePhase / GameConfig` 等）。

## 禁止模式

- `state.players[idx].field = value` 直接赋值（必须用 `with_player_update(player_id, field=value)`）。
- 测试间共享同一 SQLite 文件。

## 推荐模式

- 新增状态字段：在 `game_state.py` 模型加字段，并确认 `with_*` 工厂透传。
