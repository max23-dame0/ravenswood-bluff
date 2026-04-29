# Alpha 1.0 正式内测发布开发计划

## 1. 版本定位

`alpha 1.0` 是《鸦木布拉夫小镇》的第一个正式内测发布版本。

它不再以“新增更多能力”为核心目标，而是把 `alpha 0.1` 到 `alpha 0.3` 已经建立的能力收束成一个可以稳定交付给内测玩家的版本：

- `alpha 0.1`：打通完整对局骨架，支持 AI / 真人 / 说书人基础协作。
- `alpha 0.2`：稳定规则主链、提名投票、结算历史、AI 认知与说书人裁量记录。
- `alpha 0.3`：建立数据资产、向量记忆、导演级说书人、特殊规则与战略智能。
- `alpha 1.0`：面向真人内测，把规则正确性、操作体验、性能稳定、复盘可用、发布门禁全部封住。

一句话目标：

**让一组真实内测玩家可以完整、稳定、可复盘地玩完《暗流涌动》对局，并让开发者能定位每个异常。**

---

## 2. 当前项目梳理

### 2.1 已经具备的核心资产

#### 游戏主链

当前系统已经具备完整的 `SETUP -> FIRST_NIGHT -> DAY_DISCUSSION -> NOMINATION -> VOTING -> EXECUTION -> NIGHT -> GAME_OVER` 状态机主链。

已完成或基本完成：

- 多轮提名、辩解、顺序投票、处决结算。
- 首夜 / 普通夜切换。
- 死亡、保护、市长转移、圣徒胜负、守鸦人死亡触发等关键链路。
- Rematch、历史列表、单局详情、结算报告。

#### 角色与规则

`Trouble Brewing / 暗流涌动` 的主体角色能力已经实现，且建立了 `rule_matrix.md` 作为规则-实现-测试映射。

高风险区域仍需在 `alpha 1.0` 继续钉实：

- `scarlet_woman` 接管链路。
- `baron` 对 setup 角色分布的影响。
- `drunken` 的虚假身份、信息失真与说书人视角联动。
- `recluse` 的误判注册链路。
- `butler` 投票约束。
- `mayor` 夜晚转移与白天胜利边界。
- `slayer` 一次性消耗与 UI / AI 双链路一致性。

#### AI 玩家

AI 玩家已经从“返回动作 JSON”推进到具备结构化认知：

- 玩家视角隔离。
- `OBJECTIVE / HIGH_CONFIDENCE / PUBLIC` 三层记忆。
- 结构化身份声明账本。
- 社交图谱与怀疑分。
- 向量记忆摄入、降级、统计与检索。
- 高可信信息已开始影响发言、提名、投票理由。

`alpha 1.0` 的重点不是让 AI 更聪明，而是让 AI 更像“可内测的玩家”：

- 行为节奏稳定。
- 发言有差异。
- 不因 LLM 返回异常卡死流程。
- 不泄露上帝视角。
- 真实 backend 下耗时可接受。

#### AI 说书人

说书人已经具备：

- `StorytellerDecisionContext`。
- judgement ledger。
- 固定信息、特殊信息、失真、误报、平衡干预记录。
- 战略平衡与内心独白。
- 说书人裁量摘要进入历史详情。
- 样本导出和 acceptance 门槛。

`alpha 1.0` 的重点是将其封成“稳定裁定与日志源”：

- 玩家端不泄露内部裁量。
- 所有私密信息来源可追踪。
- 中毒 / 醉酒 / 隐士 / 间谍 / 红鲱鱼等弹性规则可复盘。
- 人类说书人模式与 AI 说书人模式都能走完整流程。

#### 数据与可观测性

`alpha 0.3` 已经建立：

- `GameRecordStore` 对局历史。
- `GameDataCollector` AI 行为日志。
- thought trace、memory snapshot、social graph snapshot、retrieval summary。
- `scripts/export_all_assets.py` 一键导出。
- `game_id` 关联历史、AI traces、storyteller judgements。

`alpha 1.0` 需要补的是发布级运营能力：

- 日志体积控制。
- 内测问题包导出。
- 崩溃 / 卡局 / 超时定位。
- 基础指标看板或命令行诊断。

#### 前端与真人体验

前端已经具备玩家端、说书人端、聊天室、状态页、私密信息、魔典权限、结算与历史入口。

但内测发布最容易翻车的仍是这里：

- 真人提名 / 辩解 / 投票连续操作。
- 聊天室与状态页不互相打断。
- 私密信息、提名状态、投票控件不遮挡。
- 说书人魔典、夜晚推进、裁量摘要可用。
- 移动端或窄屏至少不阻塞核心操作。

---

## 3. Alpha 1.0 发布原则

### 3.1 先稳定，后增强

所有新增能力都必须服务于内测稳定性。除非直接解决 P0/P1 问题，否则不在 `alpha 1.0` 阶段引入大型新系统。

### 3.2 先真人流程，后 AI 花活

AI 智能增强已经在 `alpha 0.3` 完成关键跃迁。`alpha 1.0` 优先保证真人玩家、AI 玩家、人类/AI 说书人混合对局都能稳定玩完。

### 3.3 所有关键路径必须可复盘

内测版本允许出现 bug，但不允许出现“无法定位为什么发生”的 bug。提名、投票、处决、夜晚信息、说书人裁量、AI 决策都必须有可导出的证据链。

### 3.4 发布口径保持保守

对外不使用以下表述：

- 完美还原
- 零遗忘
- 完全真人级 AI
- 生产可用
- 全规则无缺口

推荐口径：

- 正式内测版
- 完整支持《暗流涌动》主流程
- 具备 AI 玩家与 AI 说书人
- 支持对局复盘与数据导出
- 仍在持续打磨规则边界与真人体验

---

## 4. 里程碑计划

### M1：规则与流程封板

目标：确保《暗流涌动》规则主链在自动局、真人局、混合局中都稳定。

任务：

- 修复 `simulate_game.py --stop-after` 停止条件，使其重新承担快速回归职责。
- 补齐 `scarlet_woman / baron / drunken / recluse / butler / mayor / slayer` 专项测试。
- 对 `rule_matrix.md` 中所有 `部分` / `缺口` 项补测试或明确降级说明。
- 审计夜晚行动顺序、死亡跳过、ON_DEATH、保护、转移、处决、胜负判定。
- 固化 `max_nomination_rounds` 与真人流程下的阶段退出条件。

完成标准：

- [x] `pytest tests -q` 通过。
- [x] `scripts/alpha3_acceptance.py` 通过。
- [x] 新增 `scripts/alpha1_rules_acceptance.py` 通过。
- [x] `rule_matrix.md` 中不得存在未说明的 P0 规则缺口。

### M2：真人前端内测流

目标：真人玩家可以不依赖开发者解释完成一局核心流程。

任务：

- 固定玩家端内测动线：加入、身份查看、私密信息、聊天、提名、辩解、投票、死亡、结算、历史。
- 固定说书人端动线：魔典、夜晚步骤、私密信息确认、裁量记录、结算复盘。
- 补齐浏览器级 Playwright 冒烟：玩家模式与说书人模式至少各一条。
- 改善卡局提示：当前阶段、等待谁、可执行动作、错误原因必须清晰。
- 防止聊天室 / 状态页 / 私密信息 / 提名面板互相遮挡或强制切换。

完成标准：

- `scripts/frontend_acceptance.py` 通过。
- `tests/test_orchestrator/test_frontend_acceptance.py` 通过。
- 完成一次 5 人真人/半真人浏览器验收记录。
- 玩家端不能访问完整魔典。
- 说书人端能访问完整魔典并看到裁量摘要。

### M3：Live Backend 性能与可靠性

目标：真实模型驱动下，短局和标准局不会因为耗时、非法动作或并发推进导致体验崩坏。

任务：

- 建立 live 模式耗时基线：首夜、白天讨论、提名、投票、夜晚行动分别统计耗时。
- 优化顺序投票和白天行动的 LLM 调用数量。
- 为 AI 动作保持本地兜底：非法结构、超时、空响应都必须转为合法动作或明确跳过。
- 防止 `/api/game/start`、rematch、重连导致重复推进同一局。
- 增加后台任务状态诊断：当前 game loop 是否运行、最近阶段、最近异常。

完成标准：

- 5 人 live 短局能在可接受时间内完成至少一次处决。
- Mock 7-10 人局稳定完成整局。
- 所有 AI 行动超时都有 fallback。
- 卡局时 `/api/game/metrics` 或诊断接口能定位等待点。

### M4：说书人真相源与复盘封板

目标：说书人成为内测版本中稳定、可解释、可导出的裁定源。

任务：

- 审计所有固定信息角色的信息来源，确保通过说书人链路发放或可追踪。
- 强化中毒 / 醉酒 / 误报 / 红鲱鱼 / 隐士 / 间谍的 judgement 记录。
- 历史详情中展示关键裁量摘要，但玩家视角不得泄露未公开真相。
- 增加内测问题导出包：game history、AI traces、storyteller judgements、metrics、关键日志。
- 建立说书人模式专项验收脚本。

完成标准：

- `storyteller_acceptance.py` 通过并纳入 alpha1 聚合门禁。
- 每局结束后能导出完整裁量摘要。
- 玩家历史详情与说书人历史详情的信息边界不同且可测试。

### M5：AI 玩家内测体验

目标：AI 玩家足够稳定、可区分、可一起玩，而不是只在技术演示中成立。

任务：

- 强化 persona 差异：发言风格、提名倾向、投票偏好、风险偏好。
- 限制同质化高频行为：连续积极提名、无意义跟票、重复模板发言。
- 让高可信信息更自然地进入公开表达，但避免泄露不该公开的上帝视角。
- 增加 AI 行为节奏控制，避免长时间连续刷屏或卡住真人玩家。
- 建立 AI 行为回放审计样本。

完成标准：

- 同一局中不同 AI 的发言与投票倾向可识别。
- AI 非法动作率可统计并低于内测阈值。
- AI 不会因为模型异常阻塞对局。
- AI 公开发言不泄露隐藏真相。

### M6：发布工程与内测包

目标：让内测发布不是“开发者本机能跑”，而是有明确启动、诊断、回滚和反馈流程。

任务：

- 更新 README 到 `alpha 1.0` 口径。
- 增加 `docs/alpha-1.0-release-checklist.md`。
- 增加 `docs/alpha-1.0-known-issues.md`。
- 固化启动命令、环境变量、mock/live 模式说明。
- 增加内测反馈模板：game_id、时间、玩家模式、复现步骤、导出包路径。
- 整理日志与数据目录，避免内测几局后磁盘暴涨。

完成标准：

- 新人按 README 可以启动并进入 UI。
- 内测问题能通过 `game_id` 找到对应数据资产。
- 发布 checklist 全部勾选后才能打 `alpha1.0` 标签。

---

## 5. 优先级任务板

### P0：不完成不得内测

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A1-FLOW-001 | 修复模拟停止条件 | `simulate_game.py` | `--stop-after first_execution/day_1/night_2` 命中后立即退出 |
| A1-FRONT-002 | 真人提名/投票全流程可操作 | `public/index.html`, API, acceptance | 5 人真人/半真人首日多轮提名投票不卡死 |
| A1-ST-003 | 说书人稳定裁定与日志源 | `storyteller_agent.py`, `game_loop.py` | 夜晚顺序、私密信息、关键裁量均可追踪 |
| A1-RULE-004 | 高风险角色封板 | roles, nomination, setup tests | `scarlet_woman/baron/drunken/recluse/butler/mayor/slayer` 有专项回归 |
| A1-LIVE-005 | Live 模式不卡主链 | AI backend, fallback, metrics | 5 人 live 短局完成至少一次处决 |
| A1-SEC-006 | 玩家视角隔离封板 | API, frontend, history | 玩家端无法看到魔典和说书人内部裁量 |

### P1：强烈建议进入 alpha1.0

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A1-AI-007 | AI persona 差异增强 | `ai_agent.py`, persona config | 同局 AI 发言/投票/提名倾向有可识别差异 |
| A1-DATA-008 | 内测问题导出包 | scripts, data exports | 单命令按 `game_id` 导出问题定位包 |
| A1-QA-009 | Alpha1 聚合门禁 | `scripts/alpha1_acceptance.py` | rules/frontend/storyteller/data/live-smoke 聚合 |
| A1-UX-010 | 卡局与等待提示 | frontend, metrics API | UI 显示当前阶段、等待对象、错误原因 |
| A1-PERF-011 | 日志与快照体积控制 | data collector, logs | 长局数据体积有上限策略或清理说明 |

### P2：可延期但需要记录

| ID | 任务 | 范围 | 验收 |
|---|---|---|---|
| A1-MOBILE-012 | 窄屏可用性优化 | frontend CSS | 手机/窄屏不阻塞核心动作 |
| A1-EVAL-013 | 说书人裁量质量评分 | eval scripts | 形成可重复样本评分报告 |
| A1-REPLAY-014 | 更完整复盘页面 | history UI | 可按阶段查看事件、裁量、投票 |
| A1-BALANCE-015 | 多局平衡统计 | exported assets | 输出阵营胜率、天数、处决分布 |

---

## 6. 建议时间切片

### Week 1：规则与卡局风险清零

- 修复 `simulate_game.py` 停止条件。
- 补高风险角色专项测试。
- 跑通 mock 标准局。
- 建立 `alpha1_rules_acceptance.py`。

### Week 2：真人前端与说书人流

- 完成玩家端、说书人端浏览器验收。
- 修复提名 / 投票 / 私密信息 / 聊天室遮挡与切页问题。
- 完成说书人裁量日志源审计。

### Week 3：Live backend 与 AI 体验

- 建立 live 耗时基线。
- 优化白天行动与投票耗时。
- 强化 AI fallback 与 persona 差异。
- 建立内测问题导出包。

### Week 4：发布冻结与内测包

- 新增 alpha1 聚合门禁。
- 更新 README、release checklist、known issues。
- 完成 1 次 mock 全局、1 次 live 短局、1 次真人/半真人验收。
- 打 `alpha1.0` 内测标签。

---

## 7. Alpha 1.0 聚合验收门禁

建议新增：

```powershell
.\.venv\Scripts\python.exe scripts\alpha1_acceptance.py
```

聚合内容：

- `pytest tests -q`
- `scripts/alpha3_acceptance.py`
- `scripts/frontend_acceptance.py`
- `scripts/storyteller_acceptance.py`
- `scripts/role_acceptance.py`
- `scripts/alpha1_rules_acceptance.py`
- mock 全局模拟
- live 短局 smoke（允许手动开关，避免 CI 强依赖 API Key）

通过标准：

- 所有 P0 测试通过。
- 无未解释的规则矩阵缺口。
- 无玩家视角泄露。
- 无已知稳定复现卡局。
- 数据导出可按 `game_id` 完成。

---

## 8. 发布冻结标准

进入发布冻结前必须满足：

- P0 全部完成。
- P1 至少完成 `A1-DATA-008 / A1-QA-009 / A1-UX-010`。
- `CHANGELOG.md` 与 README 更新到 alpha1.0。
- `docs/alpha-1.0-known-issues.md` 已列出可接受遗留问题。
- 至少保留一份真实内测候选局的导出资产。
- 所有新增接口、脚本、验收命令有文档入口。

冻结后只允许：

- P0 bugfix。
- 文档修正。
- 发布脚本修正。
- 不改变行为的日志与诊断增强。

---

## 9. Alpha 1.0 对外发布摘要草案

`alpha 1.0` 是《鸦木布拉夫小镇》的首个正式内测版本，支持《暗流涌动》完整主流程、AI 玩家、AI 说书人、真人玩家混合对局、结算历史与对局复盘。这个版本重点强化了真人可玩性、规则一致性、说书人裁量追踪、AI 行为稳定性与内测问题诊断能力。

仍需诚实说明：

- 当前仍是内测版本，不承诺所有边界规则完全无误。
- Live 模型模式受模型速度和稳定性影响。
- 前端体验以功能可用为主，视觉与移动端体验会继续迭代。
- AI 玩家已经具备结构化记忆和人格差异，但仍会持续优化真人感。

---

## 10. 下一步落地顺序

建议立即从以下 5 件事开始：

1. 建立 `docs/alpha-1.0-release-checklist.md`。
2. 修复 `simulate_game.py --stop-after` 并补测试。
3. 补齐高风险角色专项回归。
4. 跑一次玩家端 + 说书人端浏览器验收，并更新 `frontend_acceptance.md`。
5. 新增 `scripts/alpha1_acceptance.py`，先聚合已有门禁，再逐步收严。

---

## 11. 阶段任务板目录

执行层任务板已拆分到 [alpha-1.0-plan/](./alpha-1.0-plan/)：

- [M1：规则与流程封板](./alpha-1.0-plan/task_m1_rules_flow.md)
- [M2：真人前端内测流](./alpha-1.0-plan/task_m2_frontend_human_flow.md)
- [M3：Live Backend 性能与可靠性](./alpha-1.0-plan/task_m3_live_backend.md)
- [M4：说书人真相源与复盘封板](./alpha-1.0-plan/task_m4_storyteller_replay.md)
- [M5：AI 玩家内测体验](./alpha-1.0-plan/task_m5_ai_player_experience.md)
- [M6：发布工程与内测包](./alpha-1.0-plan/task_m6_release_package.md)
