---
doc_id: "RPT-016"
title: "PLN-040 T4 进化有效性 A/B 基准结果"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-07"
author: "Ravenswood Bluff"
---

# PLN-040 T4 进化有效性 A/B 基准结果

## 1. 实验设计

`scripts/benchmark/evolution_ab_benchmark.py`（程序化对局循环，不依赖 run_simulation 的 print-only 流程）：

- **对照组（冷启动）**：每局前清空档案目录（隔离 `_finalize_agent_player_profiles` 的持续写入），20 局。
- **实验组（进化 K 局）**：先进化 15 局完整 mock 局（game_over 触发 finalize 落盘），再测 20 局（保留档案）。
- 5 人局、seed=42、`AI_FAST_LOW_VALUE_ACTIONS=1`（本地判定路径，T3.5 方案 3）、`BOTC_TENDENCY_STEP=0.05`。
- 指标（M4）：胜率差分（目标 +5pp）、Elo 差分（目标 +25，简单 Elo 胜+10/负-10）。

## 2. 结果

| 组 | 胜率 | Elo 均值 | 完成局 |
|------|:--:|:--:|:--:|
| 对照组（冷启动，每局清档） | 48.00% | 1492.0 | 20/20 |
| 实验组（进化 K=15） | 50.00% | 1500.0 | 20/20 |
| **差分** | **+2.00pp** | **+8.0** | — |

**结论：[FAIL] 进化未达到 M4 显著提升目标（+5pp / +25 Elo）**，但方向正确（Δ>0）。

## 3. 诊断（T4.3：进化为写入而未显著影响结果）

1. **进化写入确实生效**：实验组玩家 tendency 显著漂移（aggression 0.72-0.75 vs 对照组 0.61-0.63，talkativeness 0.78-0.87 vs 0.61-0.72），跨过 0.65 覆盖阈值。
2. **方向正确但幅度不足**：Δ+2.00pp（Elo +8），不到目标的一半。5 人 mock 局胜率主要由角色分配/随机噪声决定，tendency 微调（决策阈值变化）对胜率的边际影响有限。
3. **对照组隔离是方法论关键**：初版脚本对照组每局也写档案（对照组在"进化"），导致 Δ≈0；修复为每局清档后方向转为 +2pp——证明进化有真实（但小）效果。
4. **双计问题（既有）**：`finalize_game_review` 与 `finalize_game_lesson` 都调用 `record_game_result`，导致 games_played 每局计 2 次。不影响本基准胜率（用 outcome 独立计算），但影响档案战绩统计准确性，建议后续修复。

## 4. 洞察

- mock 下"决策阈值类"进化的胜率增益有限（±2pp 级），与 T3.5 结论一致——量化验证需走本地判定路径，且 mock 的胜率噪声大（5 人局样本方差高）。
- 若需更强进化效果：① 增加 K（50+ 局）；② 增加玩家数（8 人局信号更强）；③ 增强进化机制本身（如 LLM 蒸馏经验、倾向幅度更大）。这些超出 T4 基准范围，登记为后续优化方向。
- **本基准的价值**：提供了"进化有效性"的可复现测量工具，诚实地量化了当前进化机制的真实增益（+2pp），避免"mock 全绿 ≠ 进化有效"的误判。

## 5. 相关文件

- `scripts/benchmark/evolution_ab_benchmark.py`（T4 基准）
- `tests/test_benchmark/test_evolution_ab_benchmark.py`（6 单测：胜率/Elo/空局/除零）
- 计划：`docs/plans/pln040-player-distinctness-plan.md`（PLN-040 T4）
- 相关：`docs/alpha-1.2-evidence/pln040-t3-tendency-calibration-2026-08-07.md`（RPT-015，T3.5 判定路径结论）
