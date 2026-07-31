---
description: LLM 后端抽象模块规则
globs: src/llm/**/*.py
alwaysApply: false
---
# LLM 后端规则 (llm)

> 适用于 `src/llm/**`：`LLMBackend` 抽象与 OpenAI / Mock 实现。

## 核心约束

- **统一抽象**：所有 LLM 调用经 `LLMBackend`（`generate` / `get_embeddings`）。Agent 行为须后端无关。**why**：可离线测试 + 可切换模型。**when_remove**：废除抽象层时。
- **后端选择**：`BOTC_BACKEND=mock|openai|auto`；`auto` = 有 key 用 openai 否则 mock。Agent 不得假设具体后端。
- **MockBackend 仅模式匹配、零网络**：用于测试与离线演示；其返回毫秒级，不能代表 live 延迟。

## 代码风格

- 新增后端实现 `base_backend.py` 抽象接口，注册到后端工厂。

## 禁止模式

- 在 Agent 代码里直接 `import openai` / 硬编码 API 调用（应走 `LLMBackend`）。
- 用 MockBackend 的毫秒延迟推断 live 性能（见 `CLAUDE.md` §9.9）。

## 推荐模式

- 调试真实 prompt：`scripts/debug/dump_ai_prompt.py`；live 性能须用慢/真实后端验证。
