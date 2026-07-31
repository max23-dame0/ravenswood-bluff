---
doc_id: "REF-005"
title: "测试系统参考 (test-system)"
category: "reference"
role: "[Cold]"
status: "published"
date: "2026-07-31"
author: "Ravenswood Bluff"
---

# 测试系统参考 (test-system)

> 测试体系深度参考。规则要点见 `.codebuddy/rules/tests.md`。

## 1. 概览

项目测试遵循 **MockBackend-first** 策略：默认离线运行，不依赖真实 LLM / API key，可毫秒级跑完整套单测与集成测试。发布前还需 `scripts/alpha1.1_acceptance.py` 聚合的 **9 个验收 gate** 通过；live（真实 LLM）行为须真人验收，mock 全绿 ≠ 完成。

## 2. 目录结构

```
tests/
  conftest.py                       # 公共 fixtures + 替身 re-export
  doubles.py                        # 测试替身单一来源（NEW，去重后）
  __init__.py
  test_simulate_game.py             # 根级 CLI（simulate_game.py）单测，随入口留在 tests 根
  test_agents/                      # 推理/记忆回归/对话/难度/决策噪声等
    test_difficulty.py              # 难度系统单测（原 tests/ 根，已归位）
    test_decision_noise.py          # 决策噪声单测（原 tests/ 根，已归位）
  test_engine/                      # 规则引擎单测
  test_llm/                         # LLM 后端单测
  test_orchestrator/                # 27 个：阶段机/事件/信息代理等
  test_state/                       # 不可变状态单测
scripts/
  alpha1.1_acceptance.py            # 9 gate 聚合验收（发布 blocker）
  *_acceptance.py                   # 各 gate 实现，main() -> int
docs/alpha-1.1-evidence/            # 验收证据输出目录
```

## 3. 核心约定

| 约定 | 说明 |
|------|------|
| MockBackend 优先 | `BOTC_BACKEND=mock`（默认）。`MockBackend` 走模式匹配，确定性可复现。 |
| 每测试自建 SQLite | 每个测试自建独立 DB 文件，避免 `database is locked`（见 tech-traps T6）。 |
| async 模式 | `pyproject.toml`: `asyncio_mode=auto` + `testpaths=["tests"]` + `pythonpath=["."]`。 |
| 替身单一来源 | 见 §4。 |

## 4. 测试替身（tests/doubles.py）

2026-07-31 治理：原先 `DummyBackend` 在 `conftest.py` 与 **4 个测试文件**各自重复定义（conftest 注释自承 "Duplicated in 4 test files; consolidated here"）。已统一抽到 `tests/doubles.py` 作为**唯一来源**，`conftest.py` 与 3 个仍残留定义的测试文件改为 `from tests.doubles import ...`。

| 替身 | 用途 |
|------|------|
| `DummyBackend` | 固定返回占位串的 LLM；构造可传 `content=`（如 `"{}"` 供 JSON 解析断言）。 |
| `CapturingBackend` | 记录每次 `system_prompt` 到 `.calls`，用于断言 prompt 构造。 |
| `ScriptedAgent` | 按 `action_type` 顺序回放预置动作。 |
| `DummyAgent` | 记录 `observe_event` 事件、返回空动作。 |
| `DummyStoryteller` | orchestrator 测试用的说书人桩。 |

> **规则**：禁止在测试文件重复定义上述替身；变体（如返回 `"{}"`、`"not-json"` 的子类）应继承 `tests.doubles` 中的类。

## 5. conftest.py 公共设施

| 设施 | 说明 |
|------|------|
| `agent_ctx(agent, state)` | 构建 `(visible_state, legal_context)`。 |
| fixtures | `dummy_backend` / `mock_backend` / `capturing_backend` / `standard_game_state`(7人) / `small_game_state`(3人) / `dummy_state`(2人) / `sample_visible_state` / `make_ai_agent` / `make_orchestrator`。 |

## 6. 新增单测步骤

1. 在 `tests/test_<module>/` 下新建 `test_*.py`。
2. 替身：`from tests.doubles import DummyBackend, ...`；需要特殊响应则子类化。
3. 复用 `conftest` 的 GameState fixtures，不要内联重建大型状态。
4. 异步测试无需手动标记（`asyncio_mode=auto`），或显式 `@pytest.mark.asyncio`。
5. `ruff check tests` 确保无 F401（未用导入）/ 命名告警。

## 7. 验收门禁架构

`scripts/alpha1.1_acceptance.py` 聚合 **9 个 gate**，任一失败返回非 0（发布 blocker）：

1. **回归** — 既有行为不被破坏
2. **推理** — Agent 推理链正确
3. **难度 ×3** — CASUAL / STANDARD / MASTER 产生可观测行为差异（`difficulty_behavior_acceptance.py`）
4. **速度** — 单步延迟预算内
5. **对话** — 对话/claim 提取正确
6. **拟真发言** — 发言自然度/一致性
7. **向后兼容** — 接口/快照格式兼容

每个 `*_acceptance.py` 实现 `main() -> int`（0=通过），证据写入 `docs/alpha-1.1-evidence/`。

**脚本目录约定**（2026-07-31 规范化后）：`scripts/` 顶层只放用户直接调用的聚合入口
（`alpha1.1_acceptance.py` / `alpha1_acceptance.py` / `alpha3_acceptance.py` / `check_doc_health.py`），
被调用的实现脚本按用途分入 `scripts/acceptance/`、`scripts/benchmark/`、`scripts/export/`、`scripts/debug/`。
详见 `scripts/README.md`。新增 gate 请放 `scripts/acceptance/`。

## 8. 运行命令

```bash
pip install -e ".[dev]"                              # 安装（Python 3.11+）
pytest tests -q                                      # 全量（mock）
pytest tests/test_agents/test_agent_reasoning.py -q  # 单文件/子集
BOTC_BACKEND=mock python -m src.api.server           # 手动起服务（mock，无需 key）
python scripts/alpha1.1_acceptance.py                # 9 gate 聚合验收
```

## 9. 已知债务 / 陷阱

- **`_agent_ctx` 仍残留**：`test_numeric_info_memory_regression.py` / `test_claim_memory_regression.py` 内仍有与 `conftest.agent_ctx` 同构的 `_agent_ctx` 辅助函数，未去重（低风险，待后续）。
- **`CapturingBackend` 变体**：`test_agent_reasoning.py` 内有本地 `CapturingBackend`（属性名 `prompts`，与 `tests.doubles` 的 `calls` 不同），属有意变体，保留。
- **mock/live 差异**：`MockBackend` 确定性，真实 LLM 有延迟/非确定/超时，mock 全绿不代表 live 可用（tech-traps T5）。
- **SQLite 并发**：共用 DB 文件会触发 `database is locked`（tech-traps T6）。
