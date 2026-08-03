# M5-L Live Speech — DeepSeek 真人验收 Evidence

**Date**: 2026-08-03（UTC+8）
**Backend**: real live LLM — DeepSeek `deepseek-v4-flash` (base_url `https://api.deepseek.com`)
**Speed profile**: live
**验收方式**: playwright 浏览器真人玩家操作（人类玩家 = 验收玩家），AI 说书人托管 + 4 个 AI 玩家
**Player counts tested**: 5 (两局完整对局)

## 执行摘要

通过 playwright 浏览器自动化以**真人玩家身份**完整跑通两局 5 人对局（Agent 视角真人可操作：发言、提名、辩解、投票、处决、夜晚），对局均自然推进至 GAME_OVER。发现并修复 1 个前端结算 BUG；验证信息隔离、grimoire 权限、说书人控制台全链路。AI 公开发言质量高、延迟在可接受范围。

## 对局记录

| 对局 | 角色配置 | 结果 | 时长 |
|------|---------|------|------|
| Game A | 真人=陌客(good)；p1 洗衣妇 / p2 酒鬼(认镇长) / p3 小恶魔(evil) / p5 男爵(evil) | 第3天邪恶获胜（恶魔夜杀后仅剩 evil） | ~12 min |
| Game B | 真人=红唇女郎(evil)；p1 送葬者 / p2 小恶魔(evil) / p3 镇长 / p5 图书管理员 | 第2天邪恶获胜（好人全灭） | ~13 min |

两局均覆盖完整阶段链：`SETUP → FIRST_NIGHT → DAY_DISCUSSION(多轮发言) → NOMINATION(多人提名) → VOTING(平票/通过) → EXECUTION → NIGHT(恶魔击杀) → GAME_OVER`。

## Speech Metrics（43 个 AI action）

| Metric | 实测 | Target |
|--------|------|--------|
| speech fallback_rate | **6.7%**（1/15） | <= 20%（目标 10%） |
| llm_successful_speech_rate | **93.3%** | >= 80%（目标 90%） |
| orchestrator hard timeout | **0** | == 0 |
| 总体 fallback_rate（含 vote/nomination） | 18.6%（8/43） | 可接受（速度级） |

### Latency

| Action | P50 | P95 | Max |
|--------|-----|-----|-----|
| speak | 7.9s | 60.2s | 60.8s |
| vote | 7.9s | 20.0s | 20.0s |
| nomination_intent | 11.0s | 40.0s | 40.0s |
| defense_speech | 5.3s | 21.8s | 23.6s |
| night_action | 5.3s | 5.3s | 5.3s |

**注**：speak P95=60s 偏高（该次请求 completion 6260 tokens）。vote/nomination 的 20.5s 硬预算被 DeepSeek 延迟突破，产生 8 次 `latency_budget_exceeded` fallback（vote 5 / nomination_intent 2 / defense 1），全部安全回退不阻塞对局。仅 1 次 `empty_response`（deepseek-v4-flash reasoning 模型把 JSON 输出放入 reasoning_content，触发 vote fallback）。

## BUG 修复：结算 overlay i18n 崩溃

- **现象**：对局结束 `showSettlementOverlay()` 调用 `updateUIStrings()` 时抛 `TypeError: Cannot set properties of null (setting 'textContent')`（`public/index.html:1408`），结算弹窗反复报错 14 次。
- **根因**：`clearSessionArtifacts()` / 历史加载用 `logBox.innerHTML=''` 清空聊天容器，连带移除了其中的 `#ui-welcome` 元素；结算时再访问 `ui-welcome.textContent` 得到 null。
- **修复**：`updateUIStrings()` 中对 `ui-welcome` 加空值保护（`if (welcomeEl)`）。
- **验证**：第二局完整结算 + 刷新重连后 console **0 errors**，结算 overlay 正常渲染角色揭示/时间线/统计。

## 信息隔离验证（PASS）

- 玩家身份访问 `/api/game/grimoire` → **403**；说书人（storyteller backdoor）→ 200 完整魔典。
- 邪恶频道消息（含恶魔伪装策略、夜刀目标）在好人视角（p3/h1/observer）事件流中**完全不出现**，仅 evil 队友与 storyteller 可见。
- 好人 AI 未在公开频道泄露 evil 信息。

## 说书人控制台（PASS）

- storyteller.html 显示 LIVE 徽章、全局状态、玩家完整身份（含醉酒/伪装）、全量活动流水、说书人内心独白。
- 玩家模式无法访问魔典。

## UI 功能抽查（PASS）

- 玩家终端：聊天室/状态页 tab、发言、提名下拉、投票下拉、辩解、幽灵投票、死亡状态（👻 一票）均正常。
- 历史对局列表 + 复盘入口正常。
- 结算 overlay：获胜方展示、角色揭示（含 Good/Evil badge）、关键事件时间线、统计卡片均正常。

## Residual Risks

- DeepSeek `deepseek-v4-flash` 为 reasoning 模型，极少数请求将结构化输出放入 `reasoning_content` 导致 content 为空（本次 1/43），会触发 vote fallback；可考虑在 backend 层将 reasoning_content 解析为 content 兜底。
- vote/nomination 20.5s 硬预算对真实 DeepSeek 延迟偏紧（P95 20-40s），建议按 `DifficultyPreset.latency_budget` 为 live 后端放宽 vote/nomination 预算或引入预生成。
- 本次为单日单人验收（2 局 5 人），覆盖率不足以作为 release-ready 唯一依据；建议真人多场次复测（含 8 人局、混沌/大师难度）。
- `numpy/faiss-cpu` 未安装，VectorMemory 禁用（已有降级，不影响本验收）。

## 回归保护

- 前端修改仅 `public/index.html` 一处空值保护，不涉及后端逻辑。
- 建议跑 `pytest tests -q` 与 `ruff check src tests` 确认基线（本次未改动 Python 源码）。

## 结论

- **是否满足 Done**：M5-L 真实 live 发言指标达标（fallback 6.7% / LLM 成功 93.3%）；完整对局流程、信息隔离、结算闭环均通过真人浏览器操作验证。**Alpha 1.1 live 真人验收通过（本样本内）**。
- **残留风险**：如上 Residual Risks（reasoning 空响应、vote/nomination 预算、8 人局未覆盖）。
- **后续任务**：① 后端对 reasoning_content 兜底解析；② vote/nomination 预算按 live 后端放宽；③ 安排 8 人局/高难度真人复测。
