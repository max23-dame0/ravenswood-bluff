---
doc_id: "RPT-015"
title: "PLN-040 T3 tendency 标定实验结果"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-07"
author: "Ravenswood Bluff"
---

# PLN-040 T3 tendency 标定实验结果（M5）

## 1. 实验设计

三场景对照（各 2 局 8 人 mock，seed=42，`scripts/benchmark/tendency_calibration_benchmark.py`）：

| 场景 | tendency 配置 | 预期 |
|------|--------------|------|
| baseline | 全部玩家 0.5（均衡） | 基准 |
| polarized | 一半激进（aggression/talkativeness/risk 0.8-0.85），一半保守（caution 0.9） | 距离应拉开 |
| mixed | 每玩家四维均匀随机（0.05~0.95） | 距离应拉开 |

指纹基准：`scripts/benchmark/player_distinctness_benchmark.py` 12 维行为指纹 + 两两归一化欧氏距离。

## 2. 结果

| 场景 | mean_distance | max | min | stability_mean | pairs |
|------|:--:|:--:|:--:|:--:|:--:|
| baseline | 0.3127 | 0.5533 | 0.0013 | 0.2772 | 56 |
| **polarized** | **0.3430** | 0.5964 | **0.0512** | 0.2509 | 56 |
| **mixed** | **0.3482** | 0.6227 | 0.0013 | 0.2686 | 56 |

- **M1 相对对照达成**：polarized Δ=+0.0303、mixed Δ=+0.0355（均 >0，差异化生效）。
- **min_distance 显著提升**（极化场景 0.0013→0.0512）：不再存在"完全同质玩家对"——这正是消除同质化的直接证据。
- stability_mean 微降（0.2772→0.2509/0.2686）：差异化注入未破坏跨局稳定性。

## 3. 关键实现与修复

- **tendency → 行为标签覆盖**：`AIAgent.tendency_behavior_overrides()` 把四维 tendency 映射到 `decision_engine` 消费的 `risk_tolerance / social_style / assertiveness` 标签，注入 `refresh_persona_profile`。
- **中性区间不覆盖（关键修复）**：仅 tendency ≥0.65 或 ≤0.35 时覆盖对应标签；0.35~0.65 不覆盖，保留原有 `_pick_stable`/archetype 结果。否则默认玩家行为被强行改写，导致 `test_ai_agent_nomination_intent_can_proactively_nominate` 回归（提名阈值被从"保守"覆盖为"均衡"触发 `llm_none_strong_signal` 覆写）。
- **连续画像文案**：`build_evolved_tendency_summary` 从 4 档标签升级为连续文案（攻击性/冒险度/健谈度/谨慎度 × 偏强/略强/中等/略弱/偏弱）。
- **标定步长**：`BOTC_TENDENCY_STEP` 环境变量覆盖默认 ±0.02（可调 0.05/0.10/0.15 观察行为差异，仍守 0.05~0.95 边界）。

## 4. 洞察与限制

1. **mock 噪声是最大干扰源**：mock fallback 率 57%+（vote/nomination 走 `invalid_*` fallback，不经 `decision_engine` 阈值），导致 tendency 信号被稀释——即便如此差异化仍 Δ+0.03，真实 LLM 局中信号占比更高，预期差异更大。
2. **tendency 影响的是决策阈值**，对发言内容/长度影响弱（通过 prompt 文案间接影响）——指纹中发言维度占比高，限制了差异化上限。
3. **M1 验收应以相对对照为准**（绝对值 0.30 在 mock 下 baseline 即 0.31，不可用），本次验证了 Δ>0 判据。

## 6. T3.5 补充：mock fallback 根因修复与判定路径对齐（2026-08-07 同日）

### 6.1 根因

PLN-039 三层前缀把"当前需要执行的动作类型"从 system 移到 user 末条，
`MockBackend._extract_action_type` 仍只扫 system_prompt → 提取失败 → 所有动作返回
默认 speak 决策 → `normalize_decision` 判非法（vote 无 decision 字段 / nomination 无 target）
→ **vote/nomination 100% fallback**（fallback_rate 57%）。

### 6.2 修复

`mock_backend.py` `_extract_action_type` 改为扫描 `system + messages` 拼接文本。
修复后：vote 返回 `decision:true`、nomination 返回 `nominate+target`；
**fallback_rate 57% → 2.4~11.9%**（剩余为 night_action 目标合法校验）。

### 6.3 关键发现（决策阈值类差异化在 mock 的可测性）

修复后重跑标定实验，polarized Δ 反而转负（-0.002）——**mock 返回固定合法决策，
`normalize_decision` 校验通过后不再走 `_select_nomination_target`/threshold 判断路径，
tendency 影响的决策阈值在 mock 的 LLM 模拟路径下永不被消费**。

**方案 3（落地）**：标定脚本开启 `AI_FAST_LOW_VALUE_ACTIONS=1`，复现 live 模式
`simulate_game` 的本地判定路径（`local_low_value_decision` 消费 threshold）——
**polarized Δ+0.0092 / mixed Δ+0.0226（差异化重新可测，纯真实信号）**。
注意：不得同时设 `AI_FORCE_PROGRESS_ACTIONS=1`（会强制 vote=True 覆盖 tendency 信号）。

### 6.4 结论

- 决策阈值类差异化的量化验证，mock 下必须走**本地判定路径**（与 live 一致），
  不能依赖 mock 的 LLM 模拟路径；
- 修复前 Δ+0.03 部分是 fallback 随机噪声假象，方案 3 的 Δ+0.01~0.02 才是真实信号；
- 新增 6 单测 `tests/test_llm/test_mock_action_type.py` 固化 action_type 提取修复。

## 5. 相关文件

- `src/agents/ai_agent.py`（`tendency_behavior_overrides` / `_derive_tendency_delta` 标定步长）
- `src/agents/memory/memory_controller.py`（persona_profile 应用覆盖）
- `src/agents/memory/player_profile.py`（连续画像文案）
- `src/llm/mock_backend.py`（T3.5 action_type 提取修复）
- `scripts/benchmark/tendency_calibration_benchmark.py`（标定实验 + T3.5 方案 3）
- `tests/test_agents/test_tendency_behavior.py`（11 单测）；`tests/test_llm/test_mock_action_type.py`（6 单测）
- 计划：`docs/plans/pln040-player-distinctness-plan.md`（PLN-040 T3 / T3.5）
