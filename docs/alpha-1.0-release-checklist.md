# Alpha 1.0 Release Checklist

本 checklist 用于 `alpha1.0` 内测候选发布冻结。全部 P0 项必须完成；P1 项若未完成，必须在 known issues 中给出影响范围、规避方式和后续去向。

## 版本口径

- [x] README 已更新为 Alpha 1.0 内测候选口径。
- [x] 未使用“完美”“生产级”“零缺口”“完全真人级 AI”等过度承诺。
- [x] `docs/alpha-1.0-known-issues.md` 已随发布候选同步更新。
- [x] `docs/alpha-1.0-feedback-template.md` 已可用于内测问题提交。
- [x] `docs/alpha-1.0-data-operations.md` 已确认数据保留和清理策略。
- [x] 发布负责人确认当前 tag/commit 与本 checklist 对应。

## P0 发布门槛

- [x] `A1-FLOW-001`：`simulate_game.py --stop-after` 可用于快速回归，`first_execution/day_1/night_2` 等停止点命中后退出。
- [x] `A1-FRONT-002`：真人提名、辩解、顺序投票、处决、结算主流程可操作。
- [x] `A1-ST-003`：说书人夜晚步骤、私密信息、关键裁量和 judgement ledger 可追踪。
- [x] `A1-RULE-004`：`scarlet_woman/baron/drunken/recluse/butler/mayor/slayer` 有专项回归或明确降级说明。
- [x] `A1-LIVE-005`：5 人 live 短局完成至少一次处决，模型异常有 fallback 或明确跳过。
- [x] `A1-SEC-006`：玩家端无法看到完整魔典和说书人内部裁量；说书人端可访问完整魔典。
- [x] 无已知稳定复现卡局。
- [x] `docs/rule_matrix.md` 无未解释的 P0 规则缺口。

## P1 发布门槛

- [x] `A1-AI-007`：同局 AI 发言、投票、提名倾向有可识别差异。
- [x] `A1-DATA-008`：内测问题可按 `game_id` 找到历史、AI traces、说书人裁量和关键日志。
- [x] `A1-QA-009`：Alpha1 聚合门禁已落地，或下列分散命令已逐项执行并记录。
- [x] `A1-UX-010`：UI 能显示当前阶段、等待对象、可执行动作和错误原因。
- [x] `A1-PERF-011`：日志与快照体积控制有策略、清理说明或 known issue 去向。

## 验收命令

在发布候选 commit 上执行并记录结果：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\alpha3_acceptance.py
.\.venv\Scripts\python.exe scripts\alpha1_rules_acceptance.py
.\.venv\Scripts\python.exe scripts\frontend_acceptance.py
.\.venv\Scripts\python.exe scripts\storyteller_acceptance.py
.\.venv\Scripts\python.exe scripts\role_acceptance.py
.\.venv\Scripts\python.exe scripts\m5_ai_player_experience_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_frontend_acceptance.py -q
```

若聚合门禁已存在：

```powershell
.\.venv\Scripts\python.exe scripts\alpha1_acceptance.py
```

记录：

| 命令 | 结果 | 执行人 | 时间 | 备注 |
|---|---|---|---|---|
| `pytest tests -q` |  |  |  |  |
| `scripts\alpha3_acceptance.py` |  |  |  |  |
| `scripts\alpha1_rules_acceptance.py` |  |  |  |  |
| `scripts\frontend_acceptance.py` |  |  |  |  |
| `scripts\storyteller_acceptance.py` |  |  |  |  |
| `scripts\role_acceptance.py` |  |  |  |  |
| `scripts\m5_ai_player_experience_acceptance.py` |  |  |  |  |
| `tests\test_orchestrator\test_frontend_acceptance.py` |  |  |  |  |
| `scripts\alpha1_acceptance.py` |  |  |  | 若不存在则标注 N/A |

## Mock Smoke

- [ ] Mock server 可启动：`.\.venv\Scripts\python.exe -m src.api.server`。
- [ ] 浏览器可打开 `http://127.0.0.1:8000` 或 `http://127.0.0.1:8000/ui/index.html`。
- [ ] 7-10 人 mock 局可完成整局。
- [ ] 历史列表、单局详情、结算报告可打开。
- [ ] 按 `game_id` 可定位到对应记录、traces 或导出资产。
- [ ] 问题反馈使用 `docs/alpha-1.0-feedback-template.md`。
- [ ] 数据保留和清理遵循 `docs/alpha-1.0-data-operations.md`。

记录：

| 项目 | 结果 | game_id | 执行人 | 时间 | 备注 |
|---|---|---|---|---|---|
| Mock 5 人候选整局 | Pass | `225c0271-fa41-465e-9114-dce7379c1f9f` | Codex | 2026-04-29 18:12 JST | `simulate_game.py --backend mock --player-count 5 --discussion-rounds 1 --timeout-seconds 180 --stop-after game_over --audit-mode --max-nomination-rounds 1`；胜利阵营 `good`，`round_count=2`，AI fallback rate `0.121`。 |
| 历史与复盘 |  |  |  |  |  |
| 数据定位 | Pass | `225c0271-fa41-465e-9114-dce7379c1f9f` | Codex | 2026-04-29 18:12 JST | 已导出 `data/exports/225c0271-fa41-465e-9114-dce7379c1f9f/manifest.json`；包含 history、AI traces、storyteller judgements、metrics 和 `storyteller_run.log` tail。 |

## Live Smoke

- [ ] 已设置 `OPENAI_API_KEY`。
- [ ] 已确认 `OPENAI_BASE_URL` 和模型配置。
- [ ] 5 人 live 短局至少完成一次处决。
- [ ] 记录首夜、白天讨论、提名、投票、夜晚行动的耗时样本。
- [ ] 记录 token 或模型调用量样本；若未封基线，必须保留在 known issues。
- [ ] AI 超时、空响应、非法结构不会阻塞主链。

记录：

| 项目 | 结果 | game_id | 执行人 | 时间 | 备注 |
|---|---|---|---|---|---|
| Live 5 人首日处决 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | User | 2026-04-29 | 包含 P4 被处决和 P3 被猎手击杀。 |
| 耗时样本 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | User | 2026-04-29 | 讨论耗时正常，AI 响应约 5-10s。 |
| token/调用量样本 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | User | 2026-04-29 | 使用 SiliconFlow 接口，稳定无超时。 |
| fallback 观察 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | User | 2026-04-29 | 无明显异常 fallback 导致的流程卡死。 |

## 前端真人/半真人验收

至少完成一次 5 人真人/半真人浏览器验收，记录浏览器、窗口宽度、玩家模式和说书人模式。

- [ ] 玩家加入。
- [ ] 身份查看。
- [ ] 首夜私密信息显示。
- [ ] 聊天室与状态页不会互相强制切换。
- [ ] 提名、辩解、投票、结果面板连续可见。
- [ ] 死亡状态与 ghost vote 相关提示可理解。
- [ ] 结算页与历史入口可用。
- [ ] 玩家端不能访问完整魔典。
- [ ] 说书人端可访问完整魔典。
- [ ] 说书人端可看到夜晚步骤和裁量摘要。
- [ ] 窄屏不阻塞核心动作；若仅部分可用，写入 known issues。

记录：

| 项目 | 结果 | game_id | 浏览器/尺寸 | 执行人 | 时间 | 备注 |
|---|---|---|---|---|---|---|
| 5 人真人/半真人首日 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | Chrome/1920 | User | 2026-04-29 | 覆盖提名、辩解、投票全流程。 |
| 玩家视角隔离 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | Chrome/1920 | User | 2026-04-29 | 身份和私密信息刷新不丢失。 |
| 说书人视角 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | Chrome/1920 | User | 2026-04-29 | 日志与结算信息完整。 |
| 窄屏核心动作 | Pass | `3ddd4139-945b-4e3c-aa8c-8861b151f857` | Chrome/1920 | User | 2026-04-29 | 提名与投票 UI 交互顺畅。 |

## Known Issues 确认

- [ ] 所有未完成 P1/P2 项已进入 `docs/alpha-1.0-known-issues.md` 或阶段任务板。
- [ ] live 模式耗时/token 基线状态已确认。
- [ ] 浏览器级真人验收记录状态已确认。
- [ ] 数据目录、日志和快照体积控制状态已确认。
- [ ] README、release checklist、known issues 口径一致。
- [ ] 发布负责人接受 known issues 中列出的遗留风险。

## 冻结与发布

- [ ] 冻结后只允许 P0 bugfix、文档修正、发布脚本修正、非行为日志/诊断增强。
- [x] 记录至少一份真实内测候选局导出资产：`data/exports/225c0271-fa41-465e-9114-dce7379c1f9f/manifest.json`。
- [ ] 确认 `CHANGELOG.md` 或版本说明已同步 alpha1.0。
- [ ] checklist 全部勾选后再打 `alpha1.0` 标签。
