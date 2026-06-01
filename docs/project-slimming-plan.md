# Ravenswood Bluff 项目瘦身与审计计划

> **日期**: 2026-05-06 | **分支**: `alpha1.1` | **基于**: Gemini 初步审计 + Claude 深度复查
>
> **目的**: 本文档为项目维护计划，记录文件清理方案、代码审计发现、重构路线和测试缺口。仅记录计划，不包含实际改动。

---

## Context

项目当前总大小约 1.2 GB，其中 924 MB 来自 `data/sessions/` 中的 703 个 JSONL 会话文件，58 MB 来自 `__pycache__` 中的过期编译缓存。代码层面，两个"上帝对象"文件 (`ai_agent.py` 3513 行 + `game_loop.py` 2946 行) 占据了 `src/` 总代码量的 38%。同时存在未使用的依赖、重复代码模式、无界内存增长、并发安全隐患等问题。本计划旨在系统性清理文件膨胀、记录代码问题、规划重构路径。

---

## Part 1: 文件清理 (可回收 ~1 GB)

### 1.1 P0 — `data/sessions/` 会话文件 (~924 MB, 703 文件)

**现状**: 4/22–5/6 期间产生的 AI trace JSONL 文件，其中 10 个超大文件 (4/27 当天) 占 781 MB。未被 git 追踪，但占磁盘空间。

**操作**:
- 保留最近 7 天的会话文件用于质量审计
- 将 4/27 的 10 个超大文件 (>20 MB) 归档到 `data/sessions_archive/` 或直接删除
- 在 `data_collector.py` 或相关写入逻辑中添加会话文件轮转/大小上限机制

### 1.2 P1 — `__pycache__` 过期编译缓存 (~58 MB, 724 个 hash-suffix 文件)

**现状**: `.gitignore` 中有 `__pycache__/` 和 `*.py[cod]` 规则，但并行 pytest 产生的 `*.cpython-312.pyc.2485218947152` 这类带 hash 后缀的文件不匹配现有规则。

**操作**:
- 删除所有 `__pycache__/` 目录 (`.venv/` 除外)
- 在 `.gitignore` 中添加 `*.pyc.*` 规则以覆盖 hash-suffix 模式

### 1.3 P2 — `ref_docs/` PDF 文件 (~37 MB)

**现状**: `血染钟楼规则书.pdf` (25 MB) + `暗流涌动.pdf` (11.5 MB)，已提交到 git 历史。

**操作**:
- 评估是否需要继续版本控制。如仅为参考文档，迁移到 Git LFS 或外部存储
- 注意: 此操作涉及 git 历史重写，需团队协调

### 1.4 P2 — `tests/test_runs/` 测试产物 (~8.8 MB, 154 文件)

**现状**: `.gitignore` 已包含 `tests/test_runs/`，但目录仍在磁盘上。

**操作**:
- 清空 `tests/test_runs/` 目录

### 1.5 P3 — `data/` 目录零散探测/测试文件

| 文件 | 大小 | 性质 |
|------|------|------|
| `data/delete_test_*.txt` | 3 B | 删除探测残留 |
| `data/write_probe.txt` | 2 B | 写入探测残留 |
| `data/debug_game_logs/` | 3 B | 仅含一个测试文件 |
| `data/_json_fallback_game_record.records.json` | 2.3 KB | 测试 fallback JSON |
| `data/games.db-journal` | 29 KB | SQLite 未正常关闭残留 |
| `data/llm_latency_benchmark_latest.json` | 2.4 KB | 基准测试输出 |

**操作**: 全部删除。`games.db-journal` 在确认 DB 未使用后删除。

### 1.6 `.gitignore` 补充

当前缺失的规则:
```gitignore
# 补充规则
*.pyc.*                    # 并行 pytest 产生的 hash-suffix .pyc 文件
data/sessions/             # AI trace 会话文件 (不纳入版本控制)
data/debug_game_logs/      # 调试日志目录
data/*.json                # 运行时生成的 JSON 数据 (按需保留 games.records.json)
```

---

## Part 2: 依赖清理

### 2.1 未使用的依赖

| 依赖 | 验证结果 | 操作 |
|------|---------|------|
| `pyyaml>=6.0` | `src/`, `scripts/`, `tests/` 中均无 `import yaml` | 从 `pyproject.toml` 移除 |
| `structlog>=23.0` | 全项目使用 stdlib `logging`，无 `import structlog` | 从 `pyproject.toml` 移除 |

---

## Part 3: 代码审计发现 (按严重性分类)

### 3.1 HIGH — 需要优先处理

#### H1: EventBus `_event_history` 无界增长
- **文件**: `src/orchestrator/event_bus.py:37,70,99`
- **问题**: 每次 `publish()` 都 append，无容量上限。`event_history` 属性返回完整副本。
- **建议**: 改用 `collections.deque(maxlen=500)` 或添加滑动窗口。

#### H2: server.py 全局可变状态无同步保护
- **文件**: `src/api/server.py:59-65,69,89`
- **问题**: 7 个全局变量 (`global_orchestrator`, `global_storyteller` 等) 被多个 async handler 并发读写，无锁保护。并发 `/api/game/reset` 可能产生竞态。
- **建议**: 用 `asyncio.Lock` 包装全局状态变更，或封装为单例应用状态对象。

#### H3: VectorMemory 无界增长
- **文件**: `src/agents/memory/vector_memory.py:50,85,88`
- **问题**: Faiss `IndexFlatL2` 索引和 `metadata` 列表无限增长，`clear()` 仅在完全重置时调用。
- **建议**: 添加最大容量 (如 1000 向量)，超出时 FIFO 淘汰。

#### H4: WebSocket 消息无输入验证
- **文件**: `src/api/server.py:550-552`
- **问题**: 无消息大小限制、无速率限制、无 schema 验证、无输入消毒。
- **建议**: 添加 `max_size` 参数、每客户端速率限制、JSON schema 验证。

#### H5: 事件广播顺序瓶颈
- **文件**: `src/orchestrator/information_broker.py:215-219`
- **问题**: 15 人游戏中每个事件触发 15 次顺序 `observe_event` 调用，每次可能涉及 embedding API。
- **建议**: 使用 `asyncio.gather()` 并行广播 (需评估对上下文依赖的影响)。

### 3.2 MEDIUM — 需要规划处理

#### M1: Embeddings 异常被静默吞没
- **文件**: `src/llm/openai_backend.py:275`, `src/agents/memory/vector_memory.py:94`
- **问题**: `get_embeddings()` 捕获所有异常返回 `[]`，瞬态网络错误、认证失败、速率限制均不可见。
- **建议**: 区分瞬态/永久错误，瞬态重试，永久记录到 CRITICAL 级别。

#### M2: game_loop.py 多处静默异常吞没
- **文件**: `src/orchestrator/game_loop.py:197,208,785,1701`
- **问题**: claim extraction 失败 3 次后静默 (`if count <= 3 or count in {10, 25, 50}`)。
- **建议**: 所有被吞没的异常至少记录 DEBUG/WARNING 级别日志。

#### M3: GameRecordStore 类级别可变状态
- **文件**: `src/state/game_record.py:73-75`
- **问题**: `_path_locks` 懒初始化无原子性保护，两个并发调用可能创建不同锁。
- **建议**: 使用线程安全的锁工厂模式。

#### M4: Claim extraction 后台任务竞态
- **文件**: `src/orchestrator/game_loop.py:724,94`
- **问题**: `asyncio.create_task` 加入集合但永不 await，游戏重置时可能访问过期状态。
- **建议**: 添加完成回调清理，或在阶段转换前显式 await。

#### M5: 环境变量配置散乱 (15+ 个)
- **文件**: `src/llm/openai_backend.py`, `src/agents/ai_agent.py`
- **问题**: 无统一配置类，无效值仅在运行时通过 `try/except ValueError` 捕获。
- **建议**: 创建 Pydantic `Settings` 模型 + `.env` 支持，在启动时验证。

#### M6: 游戏中魔法数字散布
- **文件**: `src/orchestrator/game_loop.py` 多处
- **问题**: `margin = 1500`, `15.0` (embedding timeout), `max_episodes=5`, `[-10:]`, `[-200:]` 等无命名常量。
- **建议**: 提取到配置模块或 `DifficultyPreset` 系统。

#### M7: EpisodicMemory 无界增长
- **文件**: `src/agents/memory/episodic_memory.py:39`
- **问题**: `episodes` 列表永不裁剪。
- **建议**: 添加 `max_episodes=20` 参数，超出时淘汰最旧条目。

#### M8: GameState.event_log 无界增长
- **文件**: `src/state/game_state.py` (被 `server.py:308` 引用)
- **问题**: `filter_event_log()` 每次 API 调用遍历全部事件。
- **建议**: 实现事件日志窗口化，或为显示目的维护增量过滤视图。

#### M9: CORS 允许所有来源
- **文件**: `src/api/server.py:491-497`
- **问题**: `allow_origins=["*"]` + `allow_credentials=True` 是安全反模式。
- **建议**: 限制为 `["http://localhost:8000", "http://127.0.0.1:8000"]`。

#### M10: 无 API 速率限制
- **文件**: `src/api/server.py`
- **问题**: `/api/game/setup`, `/api/game/reset`, `/api/game/rematch` 触发昂贵操作但无限制。
- **建议**: 添加 `slowapi` 中间件或端点级冷却。

#### M11: 用户输入直接嵌入 LLM prompt
- **文件**: `src/orchestrator/game_loop.py:765`, `src/agents/ai_agent.py` 多处
- **问题**: 玩家发言内容直接插入提取 prompt，存在 prompt injection 风险。
- **建议**: 使用结构化分隔符 (XML 标签) + 输入长度限制。

#### M12: 同步文件 I/O 阻塞事件循环
- **文件**: `src/engine/data_collector.py:67-68`, `src/orchestrator/game_loop.py:2970-2977`
- **问题**: `open()` + `write()` 在 async 方法中同步执行。
- **建议**: 使用 `aiofiles` 或批量写入 + 定期 flush。

#### M13: get_visible_state N+1 模式
- **文件**: `src/orchestrator/information_broker.py:217`
- **问题**: 每次事件广播为每个玩家重建完整可见状态，O(players × events)。
- **建议**: 按阶段缓存可见状态，仅在状态变更时重建。

#### M14: 无认证/授权机制
- **文件**: `src/api/server.py`
- **问题**: `player_id` 通过 URL 参数传递，任何人可冒充。`"storyteller"` 和 `"admin"` 是公开后门。
- **建议**: 本地游戏可接受，但需文档化威胁模型。如暴露到网络需添加会话令牌。

### 3.3 LOW — 记录备查

| ID | 问题 | 文件 |
|----|------|------|
| L1 | rematch 广播静默异常 | `server.py:949` |
| L2 | 延迟预算三处重复定义 (2000ms/2s/3500ms) | `difficulty_presets.py:8`, `ai_agent.py:176`, `game_loop.py:84` |
| L3 | 错误响应暴露内部细节 (`str(e)`) | `server.py:831,851,868,893,906` |
| L4 | `_claim_extraction_failures` dict 无界增长 | `game_loop.py:95` |
| L5 | game_id URL 参数未验证格式 | `server.py:834,854,871` |

---

## Part 4: 上帝对象分析与重构路线

### 4.1 `ai_agent.py` (3513 行, ~90 方法)

**职责分组**:

| 职责 | 行范围 | 方法数 | 可提取性 |
|------|--------|--------|---------|
| 初始化/配置 | 120-450 | 5 | 低 (核心) |
| 观察/记忆摄入 | 450-910 | 5 | **高** → `memory_controller.py` |
| 邪恶策略 | 908-994 | 1 | 中 |
| Prompt 构建 | 995-1250, 1815-1960 | 7 | **高** → `prompt_factory.py` |
| 核心决策循环 | 1087-1470, 3245-3513 | 4 | 中 (编排层) |
| LLM 调用/超时 | 1473-1530 | 3 | **高** → `action_executor.py` |
| 事件格式化 | 1654-1814 | 4 | **高** → `event_formatter.py` |
| 可见性/状态构建 | 2018-2113 | 4 | 中 |
| 社交图谱 | 2189-2265 | 4 | **高** → 已有 `social_graph.py`，集成即可 |
| 提名/投票策略 | 2269-2715 | 7 | **高** → `nomination_strategy.py` |
| 夜间行动策略 | 2529-2660 | 4 | **高** → `night_action_strategy.py` |
| 发言消毒/稳定 | 2861-3240 | 5 | **高** → `speech_sanitizer.py` |
| 指标/哈希 | 242-346 | 5 | 低 (工具函数) |

### 4.2 `game_loop.py` (2946 行, ~70 方法)

**职责分组**:

| 职责 | 行范围 | 可提取性 |
|------|--------|---------|
| 代理时序/延迟 | 103-488 | **高** → `latency_manager.py` |
| 指标/诊断 | 342-700 | **高** → `diagnostics.py` |
| 事件系统 | 704-793 | 中 (已有 `event_bus.py`) |
| 设置/游戏循环 | 842-1147 | 低 (核心编排) |
| 结算/报告 | 1147-1320 | **高** → `settlement.py` |
| 夜间阶段 | 1320-1905 | **高** → `phases/night.py` |
| 日间讨论 | 1923-2170 | **高** → `phases/day.py` |
| 提名 | 2204-2929 | **高** → `phases/nomination.py` |
| 说书人辅助 | 554-1410 | 中 |

### 4.3 重复代码模式

| 模式 | 出现次数 | 位置 | 建议 |
|------|---------|------|------|
| 分层记忆组装 | 3× | `ai_agent.py:1160,1399,1634` | 提取为 `_get_tiered_memory_text()` |
| `perceived_role_id or role_id` | 15+× | 7 个文件 | 添加 `PlayerState.display_role_id` 属性 |
| `_percentile` (两个不同实现) | 2× | `game_loop.py:297,393` | 统一为一个工具函数 |
| Prompt 构建 (act vs draft) | 2× | `ai_agent.py:1195,1417` | 合并到 `PromptFactory` |
| 可见玩家格式化 | 2× | `ai_agent.py:1181,1393` | 提取为 `_format_visible_players()` |
| LLM 调用+超时+回退 | 2× | `ai_agent.py:1253`, `action_executor.py:17` | 统一到 `ActionExecutor` |

### 4.4 Refactor Preview 现状评估

**`src/agents/refactor_preview/`** (5 文件):
- `prompt_factory.py`: 仅覆盖 7/12 个 persona 字段，action_hints 文本与原版 diverge
- `agent_facade.py`: 薄包装层，大量方法仍委托回原始 agent
- `action_executor.py`: 同样委托模式
- `memory_controller.py`: **唯一完成度较高的提取** — 分层记忆组装逻辑

**`src/orchestrator/refactor_preview/`** (5 文件):
- `orchestrator_core.py`: 引用不存在的方法 `_run_original_phase_logic`
- 所有 phase handler 都是薄包装，直接委托回 orchestrator 原始方法
- **从未被生产代码导入，从未端到端测试**

**结论**: Preview 模块可作为架构参考，但不能直接集成。需要逐个完成到与原版 1:1 逻辑对等。

---

## Part 5: 测试覆盖缺口

### 5.1 无直接单元测试的关键文件

| 文件 | 行数 | 风险 |
|------|------|------|
| `src/agents/ai_agent.py` | 3513 | **最高** — 最大最复杂的文件，零直接单元测试 |
| `src/orchestrator/game_loop.py` | 2946 | **高** — 仅接受度级测试 |
| `src/agents/storyteller_agent.py` | 1178 | 中 |
| `src/engine/rule_engine.py` | — | 中 |
| `src/engine/roles/*.py` | ~1540 | 中 (被 `test_role_skill_audit.py` 间接覆盖) |

### 5.2 重构前必须覆盖的测试

在开始任何重构之前，需为以下方法添加聚焦单元测试:

**ai_agent.py**:
- `_normalize_decision()` — 决策归一化逻辑
- `_fallback_decision()` — 回退决策逻辑
- `_build_persona_prompt_block()` — persona prompt 构建
- `observe_event()` — 事件观察和记忆摄入

**game_loop.py**:
- `_timed_act()` — 带超时的代理行动
- `_run_nomination_phase()` — 提名阶段流程
- `_run_defense_and_voting()` — 辩护和投票流程
- `_action_budget_ms()` — 延迟预算计算

---

## Part 6: 已确认的良好实践

以下方面无需改动:

| 方面 | 状态 |
|------|------|
| SQL 查询参数化 | ✅ 全部使用 `?` 占位符，无注入风险 |
| 静态文件路径安全 | ✅ 使用 `os.path.dirname` 相对路径 |
| WorkingMemory/SocialGraph 容量控制 | ✅ 有明确限制并正确执行 |
| action_metrics 容量控制 | ✅ 限制为 200 条 |
| DeceptionTracker 裁剪 | ✅ 限制为 5 条 |
| 无 TODO/FIXME/HACK 标记 | ✅ 代码中无遗留工作项标记 |
| GameState 不可变性 | ✅ 使用 Pydantic `frozen=True` |
| 信息隔离 | ✅ `InformationBroker` 正确过滤可见性 |

---

## 执行顺序建议

| 阶段 | 内容 | 预计工作量 | 风险 |
|------|------|-----------|------|
| **Phase 0** | 文件清理 (1.1–1.6) + 依赖清理 (2.1) | 1 小时 | 极低 |
| **Phase 1** | `.gitignore` 更新 | 10 分钟 | 极低 |
| **Phase 2** | HIGH 修复 (H1–H5) | 4-6 小时 | 低-中 |
| **Phase 3** | 重构前测试补全 (5.2) | 4-8 小时 | 低 |
| **Phase 4** | 快速重构 (重复代码消除 4.3) | 2-4 小时 | 低 |
| **Phase 5** | 上帝对象拆分 (4.1–4.2) | 2-3 天 | 中 |
| **Phase 6** | MEDIUM 修复 (M1–M14) | 按需 | 低-中 |

---

## 验证方式

每个阶段完成后:
1. 运行 `.\.venv\Scripts\python.exe -m pytest tests -q` 确认无回归
2. 运行 `.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py` 确认 8 个 gate 全部通过
3. Phase 0 后检查 `git status` 确认无意外文件变更
4. Phase 2 后检查相关运行时指标 (事件历史大小、内存使用等)
