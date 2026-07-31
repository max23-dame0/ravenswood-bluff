---
description: FastAPI + WebSocket 服务端模块规则
globs: src/api/**/*.py
alwaysApply: false
---
# API 规则 (api)

> 适用于 `src/api/**`：`server.py` 含全部 REST 端点 + WebSocket 处理器 + 会话管理。

## 核心约束

- **单入口 server**：`server.py`(~1000) 聚合 REST + WS。新增端点在此登记，复杂逻辑委托 `src/orchestrator` / `src/agents`。**why**：统一会话生命周期。
- **WebSocket 为人机通道**：HumanAgent 经 WS 收真人输入；服务端须维护会话与连接映射。
- **配置来自 .env**：LLM 端点/key 经 `python-dotenv` 注入，代码中不写死绝对路径或密钥。**why**：跨环境可移植（见 `tech-traps.md` 路径陷阱）。

## 代码风格

- REST 路由前缀如 `/api/game/*`；指标 `GET /api/game/metrics`。

## 禁止模式

- 在 `server.py` 内写游戏规则/决策逻辑（应委托 orchestrator/agents）。
- 代码硬编码绝对路径或 API key。

## 推荐模式

- 前端 UI 由 FastAPI 从 `public/` 提供（`/ui/index.html`、`/ui/storyteller.html`）。
