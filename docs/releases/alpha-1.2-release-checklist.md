---
doc_id: "REL-009"
title: "Alpha 1.2「觉醒之鸦」Release Checklist"
category: "release"
role: "[Delta]"
status: "published"
date: "2026-08-07"
author: "Ravenswood Bluff"
---

# Alpha 1.2「觉醒之鸦」(The Awakening) Release Checklist

本 checklist 用于 `alpha1.2-awakening` 内测发布冻结。全部 P0 项必须完成；P1 项若未完成，必须在 known issues 中给出影响范围、规避方式和后续去向。

## 版本口径

- [x] 当前版本代号：**Alpha 1.2「觉醒之鸦」(The Awakening)**，口径 `alpha1.2-awakening`。
- [x] README 已更新为 Alpha 1.2 口径（徽章、版本描述、核心能力、验收入口、架构链接、版本记录）。
- [x] 未使用"完美""生产级""零缺口""完全真人级 AI"等过度承诺。
- [x] `CHANGELOG.md` / `VERSION_NOTES.md` 已同步 alpha1.2 内容与代号。
- [x] `docs/releases/alpha-1.2-agent-native-release.md`（REL-007）已登记在 `docs/README.md` 索引。
- [x] 发布负责人确认当前 tag/commit 与本 checklist 对应。

## P0 发布门槛

- [x] `pytest tests -q -m "not slow"` 通过（477+ passed / 0 failed）。
- [x] `ruff check src tests scripts` 0 告警；`ruff format --check` 全绿。
- [x] `scripts/alpha1.1_acceptance.py` 9/9 exit=0（9 Gate 聚合验收）。
- [x] `scripts/benchmark/token_budget_benchmark.py` RESULT: PASS（策略表 / 三层前缀 / 草稿复用 / 公共前缀）。
- [x] `scripts/check_doc_health.py` RC=0（frontmatter + 链接健康）。
- [x] mock 8 人局可完整推进至 game_over（无卡局）。
- [x] 信息隔离红线保持：Agent 只接收 `AgentVisibleState`；`TEAM_EVIL` 不泄露到 PUBLIC。
- [x] 白天发言顺序处理（禁止 `asyncio.gather` 最终发言）。

## P1 发布门槛

- [x] 工具调用主导路径经 live 验证（`speech_source: tool_calling`）。
- [x] 草稿复用路径经 live 验证（`cache_finalized_draft_reuse`，0 token speak）。
- [x] 本地策略判定路径经 live 验证（vote/nomination_intent 0 token）。
- [x] JSON fallback 兜底不卡流程（live fallback 归零或有明确记录）。
- [x] 跨局玩家/说书人进化落盘端到端验证（mock 局末 reviews/lessons/strategies 自动落盘）。
- [x] 缓存命中率 live 实测达标（≥40%，实测 43-53%；DeepSeek 尽力而为上限内）。
- [x] `BOTC_ST_LLM_STRATEGY=off` 行为兼容（说书人确定性红线保持）。

## 已知限制（Known Issues）

1. **`BOTC_ST_LLM_STRATEGY=low|on` 尚未 live 真人验收**：默认 off 行为与重构前一致，LLM 策略介入需真人局确认平衡性与戏剧性。
2. **工具调用主导路径依赖真实 LLM 返回 `tool_calls`**：mock 只测 fallback 路径；DeepSeek 偶发把 tool call 写入 thinking 块，已由 Scavenge 机制兜底。
3. **进化机制待 live 验证**：局中反思为工具能力（agent 自主调用），局末倾向微调为规则驱动 + 轻微随机，LLM 蒸馏留后续演进。
4. **`ai_conversation_quality` 验收 gate 偶发 flaky**：MockBackend 下 5 人局同 round 预置发言随机抽偶发重复（单跑即通过 RC=0），与本次改动无关。
5. **DeepSeek 前缀缓存为尽力而为**：前缀逐 token 一致是必要不充分条件（受 LRU/容量/TTL 限制），命中率 43-63% 为当前架构实测区间；输入膨胀已通过精简全局层缓解。
6. **live 模式耗时/token 基线**：5 人局约 100-320s、计费约 0.1-0.5 CNY/局，随模型 thinking 长度波动；长局需关注 `max_tokens` 余量与成本。

## 验收命令（在发布 commit 上执行并记录结果）

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -m "not slow"
.\.venv\Scripts\python.exe ruff check src tests scripts
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
.\.venv\Scripts\python.exe scripts\benchmark\token_budget_benchmark.py
.\.venv\Scripts\python.exe scripts\check_doc_health.py
```

记录：

| 命令 | 结果 | 执行人 | 时间 | 备注 |
|---|---|---|---|---|
| `pytest tests -q -m "not slow"` |  |  |  | 477+ passed / 0 failed |
| `ruff check src tests scripts` |  |  |  | 0 告警 |
| `scripts\alpha1.1_acceptance.py` |  |  |  | 9/9 exit=0 |
| `scripts\benchmark\token_budget_benchmark.py` |  |  |  | RESULT: PASS |
| `scripts\check_doc_health.py` |  |  |  | RC=0 |

## Mock Smoke

- [x] Mock server 可启动：`.\.venv\Scripts\python.exe -m src.api.server`。
- [x] 浏览器可打开 `http://127.0.0.1:8000` 或 `http://127.0.0.1:8000/ui/index.html`。
- [x] 8 人 mock 局可完成整局（模拟局实测 game_over）。
- [x] 历史列表、单局详情、结算报告可打开。
- [x] 局末玩家进化档案自动落盘（`data/agents/{pid}/profile/`）。

## Live Smoke

- [x] 已设置 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `DEFAULT_MODEL`（`.env`，gitignore）。
- [x] 5/8 人 live 短局完成完整流程（setup→…→game_over）。
- [x] 记录 token 基线（2026-08-04/05 多轮实测：命中率 43-63%、fallback 归零、reasoning 归零）。
- [x] AI 超时、空响应、非法结构不阻塞主链（fallback/Scavenge 兜底）。

记录：

| 项目 | 结果 | game_id / 证据 | 执行人 | 时间 | 备注 |
|---|---|---|---|---|---|
| 5 人 live day_1（D015 后） | Pass | `docs/alpha-1.2-evidence/live-agent-native-verification-2026-08-04.md` | AI | 2026-08-04 | total 7365→2848，fallback 5.9%→0% |
| 8 人 live 完整局（PLN-039 后） | Pass | `docs/alpha-1.2-evidence/pln039-live-8p-cache-verification-2026-08-04.md` | AI | 2026-08-04 | 命中率 43-53%，reasoning 0 |
| 5 人 live 确认局（max_tokens 定稿） | Pass | `.codebuddy/memory/2026-08-05.md` | AI | 2026-08-05 | fallback 清零，命中率 54-58% |

## 冻结与发布

- [x] 冻结后只允许 P0 bugfix、文档修正、发布脚本修正、非行为日志/诊断增强。
- [x] 确认 `CHANGELOG.md` / `VERSION_NOTES.md` / `README.md` / release checklist 口径一致。
- [x] 确认 tag 后发布（代号 **awakening**）。
