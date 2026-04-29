# M2 任务板：真人前端内测流

## 当前定位

- **阶段**：M2
- **状态**：`In Progress`
- **目标**：真人玩家可以不依赖开发者解释完成一局核心流程。
- **总计划**：[alpha-1.0-plan.md](../alpha-1.0-plan.md)
- **关联文档**：
  - [frontend_acceptance.md](../frontend_acceptance.md)
  - [validation_report.md](../validation_report.md)
  - [remediation_backlog.md](../remediation_backlog.md)

## 第一性原则

内测版的前端优先级是“不中断核心动作”。视觉优化可以后置，但加入、看身份、聊天、提名、辩解、投票、结算必须稳定可操作。

## 任务清单

### M2-1：玩家端完整动线

- 优先级：`P0`
- 范围：
  - `public/index.html`
  - API 状态 payload
  - 前端 acceptance
- 任务：
  - [x] 加入游戏流程稳定。
  - [x] 身份与私密信息可见且不泄露魔典。
  - [x] 聊天室与状态页切换不被轮询强制打断。
  - [x] 提名、辩解、投票、结果阶段状态持续可见。
  - [x] 死亡、幽灵票、结算状态可见。
  - [x] 历史详情入口可用。
- 验收：
  - [x] 玩家端无法访问完整魔典。
  - [x] 第一天可见连续多轮提名 / 辩解 / 投票。

### M2-2：说书人端完整动线

- 优先级：`P0`
- 范围：
  - `public/index.html`
  - `/api/game/grimoire`
  - `/api/storyteller/night/next`
  - 历史详情 API
- 任务：
  - [x] 魔典可访问且字段完整。
  - [ ] 夜晚步骤推进可见。
  - [ ] 私密信息发放状态可见。
  - [x] 关键裁量摘要可见。
  - [x] 结算与历史详情可见。
- 验收：
  - [x] 说书人端能访问完整魔典。
  - [x] 说书人端历史详情能看到裁量摘要。

### M2-3：卡局与等待提示

- 优先级：`P1`
- 范围：
  - 前端状态栏
  - `/api/game/metrics`
  - 当前动作上下文
- 任务：
  - [x] 显示当前阶段。
  - [x] 显示等待对象。
  - [x] 显示当前可执行动作。
  - [x] 显示最近错误或重试提示。
  - [x] 区分“等待 AI”“等待真人”“后台推进中”。
- 验收：
  - [x] 卡局时无需看日志也能判断等待点。

### M2-4：浏览器级验收

- 优先级：`P0`
- 范围：
  - Playwright / MCP 浏览器 smoke
  - `docs/frontend_acceptance.md`
- 任务：
  - [x] 玩家模式浏览器 smoke。
  - [x] 说书人模式浏览器 smoke。
  - [x] 记录一次 5 人真人/半真人验收。
  - [x] 将验收步骤回填到 `frontend_acceptance.md`。
- 验收：
  - [x] `scripts/frontend_acceptance.py` 通过。
  - [x] `tests/test_orchestrator/test_frontend_acceptance.py` 通过。

## 阶段完成标准

- [x] 真人/半真人首日多轮提名投票不卡死。
- [x] 私密信息、提名状态、聊天内容互不遮挡。
- [x] 玩家端与说书人端权限边界清晰。
- [x] 浏览器验收记录已落文档。

## 风险记录

- 轮询刷新容易破坏用户当前停留的 tab。
- 真人操作慢于 AI 推进时，阶段同步可能出现竞态。
- 窄屏体验可能阻塞操作，至少要记录为 P2 风险。

## 完成记录

- 2026-04-28：自动化契约已验证通过：`scripts/frontend_acceptance.py` 输出 `frontend acceptance: ok`；`tests/test_orchestrator/test_frontend_acceptance.py` 已随低内存全量 pytest 覆盖，已知输出为 `321 passed`，但外层命令曾因工具超时返回 124。
- 2026-04-29：验证通过：浏览器级真人/半真人 5 人局验收。Game ID: `3ddd4139-945b-4e3c-aa8c-8861b151f857`。覆盖了加入流程、身份查看、私密信息、提名辩解（defense_text）、实时投票统计、夜晚进度卡片、页面刷新持久化以及结算流程。确认达到“不中断核心动作、信息持久、逻辑自洽”标准。
