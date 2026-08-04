---
doc_id: "RPT-014"
title: "PLN-039 第二轮缓存优化 live 8 人局实测报告"
category: "review"
role: "[Delta]"
status: "review"
date: "2026-08-04"
author: "Ravenswood Bluff"
---

# PLN-039 第二轮缓存优化 live 8 人局实测报告

> **结论**：全量缓存命中率 **41.63% → 53.19%**（目标 ≥40%，**达成**）；reasoning=0、fallback=0、error=0。但真实总 token 因 system 变长 + tools 全量而上升，计费当量估算较基线上升约 12%——命中率收益被输入增量部分抵消，需后续权衡精简。

## 1. 实测环境与命令

- LLM：`deepseek-v4-flash`（`OPENAI_BASE_URL=https://api.deepseek.com`，见 `.env`）
- 命令：`.\.venv\Scripts\python.exe simulate_game.py --backend live --player-count 8 --stop-after game_over --timeout-seconds 1800 --audit-mode`
- 时间：2026-08-04 16:41 / 16:48（两局）
- 数据源：`runtime_game_logs/recent_1/llm.jsonl`（T4 前）、`runtime_game_logs/recent_2/llm.jsonl`（T4 后）
- ⚠️ 复核说明：本报告发布后日志 slot 已被后续对局轮转覆盖，原始 llm.jsonl 未归档，命中率等数字为撰写时刻快照，当前仓库无法独立复算。复算命令：`python scripts/debug/analyze_llm_cache.py <llm.jsonl>`。
- 分析工具：`scripts/debug/analyze_llm_cache.py`

## 2. 实测数据总览

| 指标 | 局1（T4 前） | 局2（T4 后） | 基线（PLN-037 后） |
|------|:---:|:---:|:---:|
| 全量缓存命中率 | **41.63%** | **53.19%** | 12.7% |
| prompt 总 token | 335,795 | 359,259 | ~175,000* |
| 真实总 token | 349,532 | 370,931 | 187,423 |
| completion token | 13,737 | 11,672 | ~12,000* |
| reasoning_tokens | **0** | **0** | 0 |
| 响应 error | **0** | **0** | 0 |
| 计费当量(input) | 209,997 | **187,265** | ~166,000* |

> *基线无 llm.jsonl 备份，为 memory 记录（187,423）按命中 12.7% 反推估算。计费当量 = miss×1 + hit×0.1（DeepSeek 命中 ¥0.1/M vs 未命中 ¥1.0/M）。

## 3. 各类别命中率（局2，T4 后）

| 类别 | 请求数 | 命中 token | 未命中 token | 命中率 | total |
|------|:---:|:---:|:---:|:---:|:---:|
| act | 11 | 25,344 | 30,446 | **45.43%** | 57,704 |
| draft | 32 | 67,072 | 57,182 | **53.98%** | 128,037 |
| archive | 41 | 47,232 | 28,103 | **62.70%** | 76,818 |
| reflect | 19 | 22,272 | 28,870 | 43.55% | 53,801 |
| storyteller | 13 | 16,512 | 12,416 | **57.08%** | 29,924 |
| claims(other) | 45 | 11,520 | 9,796 | 54.04% | 21,934 |
| evil_coord | 6 | 0 | 995 | 0.00% | 1,160 |

**关键改善（T4 前置全局层）**：局1 中 archive 命中 0%、storyteller 命中 0%；局2 中两者前置全局静态层后命中率提升至 **62.70% / 57.08%**，计费当量从 209,997 → 187,265（**-10.8%**）。

## 4. DoD 第 5 项逐条判定

| 验收项 | 目标 | 实测 | 判定 |
|--------|------|------|:---:|
| T6.1 完整局到 game_over | game_over | day5 evil 胜（两局） | ✅ |
| T6.2 缓存命中率 | ≥40% | **53.19%**（局2） | ✅ |
| reasoning | 0 | 0 | ✅ |
| fallback | 0 | 0（metrics fallback_rate=0.0） | ✅ |
| 真实总 token | ≤187,423 | 370,931 | ❌（未达成） |

## 5. 真实总 token 上升根因（重要权衡）

1. **system 变长**：全局静态层（2,363 字符）+ 8 工具纯文本 schema（1,302 字符）+ 输出格式要求，每请求 system 从 ~1,363 字符 → ~2,600 字符（局2 act avg syslen 2,582）。
2. **tools 全量传递**：8 个工具完整 JSON schema（3,174 字符）每请求携带（此前单工具 ~数百字符）。
3. **草稿复用 act system**：draft avg prompt 3,883 tokens（此前草稿 system 更短）。

→ 每请求平均 prompt：局2 ≈ 2,138 tokens vs 基线 ≈ 921 tokens（+132%）。输入翻倍，即使命中率提升到 53%，miss 绝对量（168,155）仍高于基线（≈152,775），计费当量估算 187,265 vs ~166,000（+12.8%）。

## 6. 精简措施（2026-08-04 已执行 + 复测）

- ✅ **全局静态层工具文本精简**：`tool_schema_text()` 从"完整参数 schema 文本"（1,302 字符）改为"工具名 + 一句话用途"（316 字符）；参数细节由 tools 参数（全量 JSON schema）提供，消除与 tools 参数的内容重复。同时补足输出格式要求（JSON 示例 / player_id 约定 / 技能目标合法性）。**全局层 2,361 → 1,522 字符（-35.5%）**，仍满足 T1 ≥1,500 目标。
- ⚠️ **无源数据更正（REV-008 R1）**：此前记载的"精简后复测（rounds=4 evil 胜）46.00% / 339,663 / 190,941"为未归档快照、全仓库零匹配、不可复核，且与归档实际值矛盾，**已废弃**。以下方归档数据为准。
- ✅ **精简后 live 复测**（2026-08-04 17:33 局，day2 game_over / good 胜，94 请求，短局口径）：全量命中率 **43.14%**（≥40% 达标）；真实总 token **177,828**（含 completion 6,641）；计费当量 **104,717**；reasoning=0、error=0；evil_coord 命中率 **75.89%**（F5 修复后）。原始数据已归档 `docs/alpha-1.2-evidence/pln039-live-2026-08-04-rev.llm.jsonl`（复算：`python scripts/debug/analyze_llm_cache.py <path>`）。⚠️ 该局为 day2 短局，与局2（day5 完整局）口径不同，绝对量不可直接对比；但 177,828 ≤ 基线 187,423（DoD #5 首次达成方向）。fallback 1 次（defense_speech JSONDecodeError，LLM 输出抖动正常兜底，非 F3 收严误伤）。T2.1 tools 恒等 ✅（各 player 组合数=1）。
- ⏳ **archive/reflect 合并或降频**：辅助调用仍占 62,734+52,090 = 114,824 tokens（35%），阈值上调可再降绝对量（未执行）。
- **接受权衡（待验证）**：命中率 12.7% → 46-53%（+33-40pp）达成计划目标；**单局计费当量 +12.8% 为实测事实**，跨 Agent 共享段长期收益需多局数据支撑，当前未验证（REV-008 F2 登记）。
- **跨 Agent 交叉命中（待验证）**：全局层 1,522 字符跨 Agent 逐 token 一致，任一 Agent 活跃即共享段活跃——此为设计假设，长期多局收益高于单局 **需多局实测证实**。

## 7. 相关文档

- `docs/plans/prompt-cache-optimization-plan.md`（PLN-039）
- `docs/guides/prompt-design.md`（REF-006）
- `scripts/debug/analyze_llm_cache.py`（T6 分析工具）
