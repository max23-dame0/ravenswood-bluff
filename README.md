# 鸦木布拉夫小镇 (Ravenswood Bluff) AI 引擎

![Version](https://img.shields.io/badge/version-alpha--1.0--candidate-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**鸦木布拉夫小镇** 是一个基于多智能体（Multi-Agent）与状态机驱动的《血染钟楼》（Blood on the Clocktower）社交推演引擎。当前版本口径为 **Alpha 1.0 内测候选**：面向真实内测局收束《暗流涌动》（Trouble Brewing）主流程、AI 玩家、AI 说书人、真人混合对局、结算历史和复盘导出。

Alpha 1.0 仍是内测版本，重点是稳定、可验收、可定位问题；规则边界、live 模型耗时、浏览器真人体验和数据体积控制仍会持续打磨。

---

## 核心能力

- **完整主流程**：支持 `SETUP -> FIRST_NIGHT -> DAY_DISCUSSION -> NOMINATION -> VOTING -> EXECUTION -> NIGHT -> GAME_OVER` 主链，覆盖提名、辩解、投票、处决、夜晚行动、结算和 rematch。
- **《暗流涌动》角色规则**：主体角色能力已实现，并通过 `docs/rule_matrix.md` 和专项验收持续追踪高风险角色边界。
- **AI 玩家与真人混合局**：AI 玩家具备结构化记忆、身份声明账本、社交图谱和 persona 差异；真人玩家可通过浏览器参与核心流程。
- **AI/人类说书人链路**：说书人裁量、私密信息、夜晚步骤和 judgement ledger 可追踪，玩家视角与说书人视角保持信息边界。
- **复盘与数据资产**：对局历史、AI traces、说书人裁量和导出脚本为内测问题定位提供证据链。

---

## 快速开始

### 1. 环境准备

推荐使用 **Python 3.11+**。

```powershell
cd d:\鸦木布拉夫小镇
.\.venv\Scripts\activate
pip install -e "."
```

### 2. Mock 模式启动

Mock 模式适合本地验收和不依赖外部模型的内测演示。

```powershell
.\.venv\Scripts\python.exe -m src.api.server
```

启动后访问：

- 玩家/说书人 UI：`http://127.0.0.1:8000`
- 静态 UI 入口：`http://127.0.0.1:8000/ui/index.html`
- 常用真人 host id：`h1`

### 3. Live 模式启动

Live 模式会调用兼容 OpenAI 接口的模型服务，耗时和稳定性取决于模型、网络和并发设置。发布前需要记录 live smoke 结果。

```powershell
$env:OPENAI_API_KEY="your_api_key"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
.\.venv\Scripts\python.exe -m src.api.server
```

若本地配置了其他兼容 OpenAI 的 backend，请使用对应的 `OPENAI_BASE_URL` 和模型配置。

---

## Alpha 1.0 验收入口

发布前优先执行当前仓库已有的门禁命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe scripts\alpha3_acceptance.py
.\.venv\Scripts\python.exe scripts\alpha1_rules_acceptance.py
.\.venv\Scripts\python.exe scripts\frontend_acceptance.py
.\.venv\Scripts\python.exe scripts\storyteller_acceptance.py
.\.venv\Scripts\python.exe scripts\role_acceptance.py
.\.venv\Scripts\python.exe -m pytest tests\test_orchestrator\test_frontend_acceptance.py -q
```

若 `scripts\alpha1_acceptance.py` 已在当前分支落地，可作为发布前聚合门禁：

```powershell
.\.venv\Scripts\python.exe scripts\alpha1_acceptance.py
```

浏览器级真人/半真人 smoke 需要单独记录，至少覆盖：

- 玩家加入、身份查看、私密信息、聊天、提名、辩解、投票、死亡、结算、历史。
- 说书人魔典、夜晚步骤、私密信息确认、裁量记录、结算复盘。
- 玩家端无法访问完整魔典或说书人内部裁量。
- 5 人 live 短局至少完成一次处决；mock 7-10 人局稳定完成整局。

详细发布门槛见 [Alpha 1.0 Release Checklist](./docs/alpha-1.0-release-checklist.md)，遗留风险见 [Alpha 1.0 Known Issues](./docs/alpha-1.0-known-issues.md)。
内测问题反馈可直接使用 [Alpha 1.0 Feedback Template](./docs/alpha-1.0-feedback-template.md)，数据保留和清理策略见 [Alpha 1.0 Data Operations](./docs/alpha-1.0-data-operations.md)。

---

## 项目架构

- `docs/alpha-1.0-plan.md`：Alpha 1.0 总体发布计划、P0/P1/P2 任务板和冻结标准。
- `docs/alpha-1.0-plan/`：M1-M6 阶段任务板。
- `docs/alpha-1.0-release-checklist.md`：发布前 checklist。
- `docs/alpha-1.0-known-issues.md`：内测候选已知问题。
- `docs/alpha-1.0-feedback-template.md`：内测问题反馈模板。
- `docs/alpha-1.0-data-operations.md`：数据目录、导出包和清理说明。
- `src/agents/`：AI 玩家、说书人、认知层、记忆组件。
- `src/engine/`：规则引擎、角色能力、阶段控制、数据采集。
- `src/orchestrator/`：对局循环、信息分发、说书人裁量链路。
- `src/state/`：状态快照、事件日志、对局记录。
- `src/api/`：本地 API server 与前端接口。
- `public/`：浏览器 UI。
- `scripts/`：验收、导出、模拟和数据工具。
- `tests/`：单元、集成与验收测试。

---

## 内测反馈信息

提交内测问题时，请尽量附上：

- `game_id`
- 发生时间
- mock/live 模式
- 玩家模式：真人、AI、混合、人类说书人或 AI 说书人
- 复现步骤
- 预期行为与实际行为
- 导出包或相关 `data/`、日志路径

推荐先生成问题包：

```powershell
.\.venv\Scripts\python.exe scripts\export_all_assets.py <game_id> --output data\exports --log-path storyteller_run.log
```

---

## 版本记录

此分支所有变动追踪至 [CHANGELOG.md](./CHANGELOG.md)。Alpha 1.0 发布计划见 [docs/alpha-1.0-plan.md](./docs/alpha-1.0-plan.md)。

## 开源协议

本引擎及实现基于 MIT 协议，完全开源。
