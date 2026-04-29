# Alpha 1.0 任务板目录

本目录用于承接 [alpha-1.0-plan.md](../alpha-1.0-plan.md) 的执行层任务拆分。

`alpha 1.0` 的核心目标不是继续扩大功能面，而是把当前项目收束成可正式内测的版本：规则稳定、真人可玩、AI 不阻塞、说书人可追踪、问题可复盘、发布有门禁。

## 阶段任务板

| 阶段 | 文件 | 目标 |
|---|---|---|
| M1 | [task_m1_rules_flow.md](./task_m1_rules_flow.md) | 规则与流程封板 |
| M2 | [task_m2_frontend_human_flow.md](./task_m2_frontend_human_flow.md) | 真人前端内测流 |
| M3 | [task_m3_live_backend.md](./task_m3_live_backend.md) | Live Backend 性能与可靠性 |
| M4 | [task_m4_storyteller_replay.md](./task_m4_storyteller_replay.md) | 说书人真相源与复盘封板 |
| M5 | [task_m5_ai_player_experience.md](./task_m5_ai_player_experience.md) | AI 玩家内测体验 |
| M6 | [task_m6_release_package.md](./task_m6_release_package.md) | 发布工程与内测包 |

## 状态约定

- `Planned`：已规划，尚未开始。
- `In Progress`：正在实现或验证。
- `Blocked`：存在阻塞，需要先处理依赖。
- `Done`：主链完成，且有验收保护。
- `Deferred`：明确延期，不阻塞 alpha1.0 内测。

## 优先级约定

- `P0`：不完成不得进入正式内测。
- `P1`：强烈建议进入 alpha1.0。
- `P2`：可延期，但必须记录。

## 更新原则

1. 每个任务完成时同步填写“完成记录”。
2. 如果任务被延期，必须写清楚延期原因与风险。
3. 如果代码实现和文档计划不一致，以最新验收结果为准，并回填任务板。
4. 所有 alpha1.0 发布口径保持保守，不使用“完美”“零遗忘”“生产级”等绝对描述。
