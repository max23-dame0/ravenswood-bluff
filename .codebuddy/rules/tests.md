---
description: 测试系统与验收门禁模块规则
globs: tests/**/*.py, scripts/**/*acceptance*.py
alwaysApply: false
---

# 测试系统规则 (tests)

> 适用于 `tests/**` 与 `scripts/**/*acceptance*.py`。深度参考见 `docs/reference/test-system.md`。

## 核心约定

- **MockBackend 优先**：默认 `BOTC_BACKEND=mock`（离线），不依赖真实 LLM / API key。CI 与本地默认均走 mock。
- **每测试自建 SQLite**：每个测试自建独立 DB，避免锁竞争（见 `docs/reference/tech-traps.md` T6）。禁止共用同一 `game.db`。
- **测试替身单一来源**：所有 LLM 替身（`DummyBackend` / `CapturingBackend`）与 Agent / 说书人替身（`ScriptedAgent` / `DummyAgent` / `DummyStoryteller`）统一定义在 `tests/doubles.py`，**禁止在测试文件中重复定义**。需要变体时继承 `tests.doubles` 中的类。

## 公共设施（conftest.py）

- 替身：`DummyBackend` / `CapturingBackend` / `ScriptedAgent` / `DummyAgent` / `DummyStoryteller`（均 re-export 自 `tests.doubles`）。
- 辅助：`agent_ctx(agent, state)` 构建可见态 + 合法上下文。
- fixtures：`dummy_backend` / `mock_backend` / `capturing_backend` / `standard_game_state`(7人) / `small_game_state`(3人) / `dummy_state`(2人) / `sample_visible_state` / `make_ai_agent` / `make_orchestrator`。

## 新增单测步骤

1. 在对应 `tests/test_<module>/` 下新建 `test_*.py`。
2. 需要的替身 `from tests.doubles import DummyBackend, ...`；变体继承之。
3. 复用 `conftest` fixtures（GameState 工厂），不在测试内重复构造大型状态。
4. 异步测试靠 `asyncio_mode=auto`（pyproject 已配），或显式 `@pytest.mark.asyncio`。
5. `ruff check tests` 确保无未用导入（F401）/ 命名告警。

## 验收门禁（acceptance gates）

聚合脚本 `scripts/alpha1.1_acceptance.py` 跑 **9 个 gate**，证据写 `docs/alpha-1.1-evidence/`：
回归 / 推理 / 难度×3(CASUAL/STANDARD/MASTER) / 速度 / 对话 / 拟真发言 / 向后兼容。

每个 `*_acceptance.py` 遵循 `main() -> int`（0=通过）；门禁为发布 blocker，失败须具名记录。

## 运行

```bash
pytest tests -q                                       # 全量（mock）
pytest tests/test_agents/test_agent_reasoning.py -q   # 单文件
python scripts/alpha1.1_acceptance.py                 # 9 gate 验收
```

## 禁止

- ❌ 在测试文件重复定义 `DummyBackend` 等替身（仓库即唯一真实来源）。
- ❌ 多个测试共用同一 SQLite 文件。
- ❌ 仅靠 mock 全绿就宣称功能完成（live 需真人验收，见全局规则）。
