---
doc_id: "REF-004"
title: "技术陷阱速查 (tech-traps)"
category: "reference"
role: "[Cold]"
status: "published"
date: "2026-07-30"
author: "Ravenswood Bluff"
---

# 技术陷阱速查 (tech-traps)

> 违反硬约束的"踩坑→代价"案例。新人/新会话必读。**模式**（非具体代码）：展示"若违反约束会怎样"，便于识别同类错误。
> 来源：`CLAUDE.md` §9 gotchas + harness 通用陷阱。

## 项目专属陷阱

### T1: 直接改 GameState 字段
- **错误模式**：`state.players[0].alive = False`。
- **后果**：绕过 `with_player_update`，快照不一致，重放/调试全乱，下游订阅者收不到迁移。
- **正确**：`state = state.with_player_update(player_id, alive=False)`。

### T2: 把 GameState 直传 Agent
- **错误模式**：`agent.act(state, ...)` 直接传全量状态。
- **后果**：Agent 能看到 evil 私密信息，游戏失衡。
- **正确**：`broker.get_visible_state(agent_id, state)`。

### T3: evil 信息泄露到 PUBLIC 事件
- **错误模式**：在 PUBLIC visibility 事件里嵌"恶魔是谁"。
- **后果**：所有玩家（含 Good）瞬时知道 evil 身份。
- **正确**：evil 私聊用 `ChatMessage(recipient_ids=[...])`，visibility 设 `TEAM_EVIL`。

### T4: 白天发言 asyncio.gather
- **错误模式**：`await asyncio.gather(*[gen_speech(p) for p in players])`。
- **后果**：后发言者拿不到先发言者事件，上下文错乱。
- **正确**：逐次 `await`，由 `day_discussion.py` 顺序驱动。

### T5: 仅 mock 通过就宣称完成
- **错误模式**：`pytest` 全绿（MockBackend 毫秒级）→ 标记 ✅。
- **后果**：live 模式真实 LLM 超时，公开发言兜底率飙升，游戏卡死。
- **正确**：live 模式需真人验收（`CLAUDE.md` §9.9）。

### T6: 测试共享 SQLite
- **错误模式**：多个并行测试共用同一 `game.db`。
- **后果**：SQLite 锁竞争，随机 `database is locked`。
- **正确**：每测试自建 DB。

### T7: 路径/密钥硬编码
- **错误模式**：代码写死 `/home/user/.env` 或 `sk-xxxx`。
- **后果**：换环境即崩；密钥泄露。
- **正确**：`python-dotenv` 读 `.env`；相对路径或环境变量。

### T8: claim 提取阻塞讨论
- **错误模式**：`_extract_claims_via_llm` 同步等待、失败时重复告警。
- **后果**：live 讨论出现可见卡顿与日志噪声。
- **正确**：异步、限流、非阻塞，失败时静默降级。

### T9: facade 堆逻辑
- **错误模式**：在 `ai_agent.py` / `game_loop.py` 内直接写决策/阶段逻辑。
- **后果**：上帝对象膨胀，不可维护（二者已 ~1100/~766 行）。
- **正确**：逻辑下沉到对应子模块。

## 通用陷阱（来自 harness 框架）

### G1: 时间/排序依赖
- **错误模式**：假设 `list(dict)` 保序、用本地时间比对跨时区事件。
- **后果**：偶发失败、跨环境不一致。
- **正确**：显式排序键；统一 UTC。

### G2: 空值/边界未处理
- **错误模式**：`x.name` 未判 None、`for` 空集合后直接取 `result[0]`。
- **后果**：`AttributeError` / `IndexError`。
- **正确**：用 `or` 默认值、判空、断言输入契约。

### G3: 资源泄漏
- **错误模式**：开文件/连接不 `close`，循环中反复新建对象。
- **后果**：句柄耗尽、内存涨。
- **正确**：`with` 上下文、连接池、复用实例。

### G4: 忽略并发安全
- **错误模式**：多协程共享可变状态无锁、`asyncio.gather` 内共享写入。
- **后果**：竞态、数据损坏。
- **正确**：不可变优先、加锁、`EventBus` 串行化。

### G5: 错误吞掉
- **错误模式**：`except: pass`。
- **后果**：问题隐形，难排查。
- **正确**：至少 `logger.warning` + 上下文；必要时向上抛。

### G6: 魔法数字/字符串
- **错误模式**：散落 `if phase == 3`、`timeout=42`。
- **后果**：语义不清、易错。
- **正确**：枚举/常量（如 `GamePhase.NIGHT`、`GameConfig.timeout`）。

### G7: 跨平台路径
- **错误模式**：`'data\\x.json'` 硬编码分隔符。
- **后果**：非 Windows 崩。
- **正确**：`pathlib.Path` / `os.path.join`。

### G8: 浮点比较
- **错误模式**：`if a == b`（浮点）。
- **后果**：精度误差致判断失败。
- **正确**：`abs(a-b) < 1e-9`。

## 测试专项陷阱

### T10 · 测试替身重复定义（仓库即唯一真实来源）
- **症状**：在多个测试文件各自 `class DummyBackend(LLMBackend)`，改一处忘改另一处，行为漂移。
- **根因**：无单一来源。
- **修复**：所有替身定义在 `tests/doubles.py`；变体继承之，禁止重复定义。（见 D008 / `docs/reference/test-system.md` §4）

### T11 · mock / live 行为差异
- **症状**：`MockBackend` 全绿，但真实 LLM 下发言超时、JSON 解析失败、噪声策略不一致。
- **根因**：`MockBackend` 毫秒级、确定性；真实 LLM 有延迟/非确定/工具调用格式差异。
- **修复**：性能与解析断言用 mock；语义/质量须真人 live 验收。mock 全绿 ≠ 完成。

### T12 · 测试内 Python 包导入路径
- **症状**：`from tests.doubles import ...` 报 `ModuleNotFoundError`，或 fixtures 找不到。
- **根因**：`pyproject.toml` 配 `pythonpath=["."]` + `testpaths=["tests"]`，测试文件需以 `tests.` 包路径引用（需 `tests/__init__.py` 已存在）。
- **修复**：统一用 `from tests.doubles import X`；跑测试用 `pytest tests`（勿脱离项目根目录）。

## 更新日志

- 2026-07-30: 初版（T1-T9 项目专属 + G1-G8 通用）
- 2026-07-31: 新增测试专项陷阱 T10-T12（替身重复 / mock-live 差异 / 包导入路径）
