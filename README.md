# 鸦木布拉夫小镇 (Ravenswood Bluff) AI 引擎

![Version](https://img.shields.io/badge/version-alpha--1.2--awakening-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**鸦木布拉夫小镇** 是一个基于多智能体（Multi-Agent）与状态机驱动的《血染钟楼》（Blood on the Clocktower）社交推演引擎。当前版本口径为 **Alpha 1.2「觉醒之鸦」(The Awakening) 内部测试版本**：在前一版本多轴难度系统与速度工程的基础上，将 AI 玩家从「集中式调度 + 单次无状态 LLM 调用」演进为**受控自主 Agent**（行动工具化、世界感知查询化、记忆工具化、策略先行），并落地**跨局玩家/说书人进化机制**（局中反思、局后复盘、学习他人、调整策略）与整套 **token 成本控制**（前缀缓存优化 + 草稿复用 + thinking 分级）。


---

## 核心能力

- **完整主流程**：支持 `SETUP -> FIRST_NIGHT -> DAY_DISCUSSION -> NOMINATION -> VOTING -> EXECUTION -> NIGHT -> GAME_OVER` 主链，覆盖提名、辩解、投票、处决、夜晚行动、结算和 rematch。
- **《暗流涌动》角色规则**：主体角色能力已实现，并通过 `docs/reference/rule_matrix.md` 和专项验收持续追踪高风险角色边界。
- **受控自主 AI 玩家**：AI 玩家以工具调用主导行动（8 个行动 ToolDef）、按需查询世界（4 只读 WorldTools）、工具化维护记忆（append/read/reflect/archive），并以策略先行 loop（think → act）驱动决策；JSON fallback 兜底保证不卡流程。
- **跨局玩家进化**：AI 玩家拥有个人跨局档案（战绩、倾向画像、局中反思、局后复盘、向强者学习、策略调整），新对局自动注入既往经验，行为随对局精进、风格分化，更接近有记忆的人类玩家；说书人同样累积跨局主持经验。
- **AI/人类说书人链路**：说书人裁量、私密信息、夜晚步骤和 judgement ledger 可追踪，玩家视角与说书人视角保持信息边界；说书人工具注册表 + `BOTC_ST_LLM_STRATEGY` 分级 LLM 介入。
- **Token 成本控制**：三层前缀缓存优化（真实命中率 43-63%）、发言草稿复用（有草稿时 0 次 LLM）、thinking 分级与 max_tokens 上限（live 实测 total -62%、fallback 归零）。
- **复盘与数据资产**：对局历史、AI traces、说书人裁量、玩家进化档案和导出脚本为内测问题定位提供证据链。

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

启动后访问链接：

- **游戏客户端（玩家/观战端）**：[http://127.0.0.1:8000](http://127.0.0.1:8000) (或 [http://127.0.0.1:8000/ui/index.html](http://127.0.0.1:8000/ui/index.html))
- **说书人魔典控制台**：[http://127.0.0.1:8000/ui/storyteller.html](http://127.0.0.1:8000/ui/storyteller.html)
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

## 验收入口

发布与验收前，必须执行一键聚合门禁命令以运行全部 9 个 Gate 自动化验收：

```powershell
.\.venv\Scripts\python.exe scripts\alpha1.1_acceptance.py
```

该脚本将自动执行并确保以下门禁全部通过（ok）：
1. **pytest regression**：主流程与角色能力单元测试不回归。
2. **agent reasoning**：AI 玩家的社交推理和博弈逻辑正常。
3. **difficulty acceptance**：4 种难度模式（Casual/Standard/Master/Chaos）配置加载成功。
4. **difficulty comparison**：不同难度之间的行为差异可审计、可感知。
5. **difficulty behavior**：难度行为级断言测试正常。
6. **ai speed**：决策速度优化正常，提名与投票本地判定 P95 ~0ms。
7. **ai conversation quality**：发言质量监测正常，低信息率低，重复发言为 0。
8. **ai live-like speech**：在高延迟 Live 环境下，AI 发言硬超时率 0%，LLM 成功率 100%。
9. **alpha1 backward compatibility**：与上一版本完全兼容。

验收证据输出至 `docs/alpha-1.1-evidence/` 目录。

Agent 原生重构的 token 控制效果由离线基准验证：

```powershell
.\.venv\Scripts\python.exe scripts\benchmark\token_budget_benchmark.py
```

> Alpha 1.2 完整发布门禁与验收记录见 `docs/releases/alpha-1.2-release-checklist.md`。


---

## 项目架构

- `docs/plans/agent-native-redesign-plan.md`：Agent 原生重构（PLN-037/038）总体设计与任务板。
- `docs/plans/prompt-cache-optimization-plan.md`：Prompt 前缀缓存命中率优化（PLN-039）与任务板。
- `docs/releases/alpha-1.2-agent-native-release.md`：Alpha 1.2「觉醒之鸦」发布记录。
- `docs/alpha-1.1-evidence/`：9-gate 验收证据记录；`docs/alpha-1.2-evidence/`：Alpha 1.2 live 验收证据。
- `VERSION_NOTES.md`：Alpha 1.2 内部测试版本说明。
- `CHANGELOG.md`：项目版本迭代变更记录。
- `src/agents/`：AI 玩家（受控自主 Agent）、说书人（工具注册表 + 跨局档案）。
- `src/engine/`：规则引擎、角色能力、阶段控制、数据采集。
- `src/orchestrator/`：对局循环、事件总线、信息分发（信息隔离）。
- `src/state/`：不可变 GameState 快照、事件日志、对局记录。
- `src/api/`：本地 API server 与前端接口。
- `public/`：浏览器 UI。
- `scripts/`：验收门禁、基准、导出、模拟和数据工具。
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
.\.venv\Scripts\python.exe scripts\export\export_all_assets.py <game_id> --output data\exports --log-path storyteller_run.log
```

---

## 版本记录

此分支所有变动追踪至 [CHANGELOG.md](./CHANGELOG.md)。Alpha 1.2「觉醒之鸦」详细发布说明见 [docs/releases/alpha-1.2-agent-native-release.md](./docs/releases/alpha-1.2-agent-native-release.md)，发布门禁见 [docs/releases/alpha-1.2-release-checklist.md](./docs/releases/alpha-1.2-release-checklist.md)。


## 开源协议

本引擎及实现基于 MIT 协议，完全开源。
