# 鸦木布拉夫小镇 (Ravenswood Bluff) AI 引擎

![Version](https://img.shields.io/badge/version-alpha--1.1-orange)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**鸦木布拉夫小镇** 是一个基于多智能体（Multi-Agent）与状态机驱动的《血染钟楼》（Blood on the Clocktower）社交推演引擎。当前版本口径为 **Alpha 1.1 内部测试版本**：在前一版本稳定主流程的基础上，正式引入了多轴 AI 玩家难度系统，实施了深度响应速度与对话质量优化工程，并对底层上帝对象（AIAgent 与 GameOrchestrator）完成了彻底的模块化重构。


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

## Alpha 1.1 验收入口

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


---

## 项目架构

- `docs/alpha-1.1-plan.md`：Alpha 1.1 总体开发计划、Milestone 列表与验收标准。
- `docs/alpha-1.1-plan/`：M5/M6/M7 各阶段具体任务板。
- `docs/alpha-1.1-evidence/`：发布的各项测试与验收证据记录。
- `VERSION_NOTES.md`：Alpha 1.1 内部测试版本说明。
- `CHANGELOG.md`：项目版本迭代变更记录。
- `src/agents/`：AI 玩家（Facade 及其下 9 大重构子模块）、说书人。
- `src/engine/`：规则引擎、角色能力、阶段控制、数据采集。
- `src/orchestrator/`：对局循环（Facade 及其下阶段处理器等重构模块）、信息分发。
- `src/state/`：状态快照、事件日志、对局记录。
- `src/api/`：本地 API server 与前端接口。
- `public/`：浏览器 UI。
- `scripts/`：验收门禁、导出、模拟和数据工具。
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

此分支所有变动追踪至 [CHANGELOG.md](./CHANGELOG.md)。Alpha 1.1 详细开发设计与路线见 [docs/alpha-1.1-plan.md](./docs/alpha-1.1-plan.md)。


## 开源协议

本引擎及实现基于 MIT 协议，完全开源。
