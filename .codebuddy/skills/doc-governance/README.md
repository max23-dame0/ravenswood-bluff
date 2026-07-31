# doc-governance

> **平台无关的通用文档治理 Skill** —— 让任意 AI 编程工具管理的项目，都能沉淀一套可检索、可审计、不易腐坏的 Markdown 文档体系。

本仓库是一个**自包含的 skill 包**：复制到任意 AI 编程工具（CodeBuddy / Claude Code / Cursor / Windsurf / Cline / Aider / GitHub Copilot / OpenAI Codex）的项目中即可启用，不依赖任何单一平台或外部文件。

## 特性

- **平台无关**：抽象"三层记忆模型（热/温/冷）"，附各 AI 编程工具接入映射，不写死 `.codebuddy/` 等专属路径。
- **五维工作流**：文档体系诊断、文档创建、文档审计、腐败检测、文档体系初始化。
- **完整 Frontmatter 受控词表**：`doc_id`/`title`/`category`/`role`/`status`/`date`/`author` 必填，`category` 与目录强映射。
- **索引五要素**：`documents/README.md` 作为 Agent 检索起点，含场景查找表、目录树、分类索引、ADR 索引、模板索引。
- **反模式清单 + 质量评分**：固化链接健康度、索引注册、代码一致性等必检项。
- **Harness 文件治理**：内置根目录运行态文件约定（`AGENTS`/`MEMORY`/`PROGRESS`/`DECISIONS`/技术陷阱库）与 5 个模板，让 AI 工具每次会话热启动、跨会话状态持久化。
- **自包含分发**：内置治理规则、11 个模板（6 文档 + 5 harness），开箱即用。

## 支持的 AI 编程工具

| 工具 | 常驻指令文件（热层） | 路径作用域规则（温层） |
|------|---------------------|---------------------|
| CodeBuddy | `.codebuddy/rules/*.mdc` | `.codebuddy/rules/*.mdc`（`globs:`） |
| Claude Code | `CLAUDE.md` | `CLAUDE.md` `@import` 子文件 |
| Cursor | `.cursorrules` / `.cursor/rules/*.mdc` | `.cursor/rules/*.mdc` |
| Windsurf | `.windsurfrules` | 记忆文件 |
| Cline | `CLAUDE.md` / `.clinerules` | `.clinerules` 分段 |
| Aider | `CONVENTIONS.md` | 子模块 `CONVENTIONS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` | 仓库内 `**/*.md` 自然检索 |
| OpenAI Codex | `AGENTS.md` | `AGENTS.md` 分节 |
| 通用 | `AGENTS.md`（多工具已支持） | `documents/05-reference/` |

完整映射与接入步骤见 [`references/platform-adapter.md`](references/platform-adapter.md)。

## 安装到目标项目

**最小可用接入：**

1. 复制本仓库的 `references/templates/` 到目标项目的 `documents/templates/`。
2. 按 [`references/documentation-governance.md` §3.1](references/documentation-governance.md) 在目标项目创建 `documents/` 标准目录结构。
3. 在目标项目根目录新建/补充 `AGENTS.md`（或对应工具的常驻指令文件），写入一行约束：*"编辑 `*.md` 须遵循 frontmatter 受控词表（`documents/README.md` 索引与 [`references/documentation-governance.md` §2.1](references/documentation-governance.md)）。"*
4. 把 [`references/documentation-governance.md` §2.1、§3.3](references/documentation-governance.md) 的要点贴入该工具的"常驻指令/规则"文件。

**完整接入：** 按 [`references/platform-adapter.md`](references/platform-adapter.md) 第三节，建立 harness 文件（`AGENTS.md` / `PROGRESS.md` / `DECISIONS.md` / `MEMORY.md`）并补全温层规则。

## 仓库目录结构

```
doc-governance/
├── SKILL.md                                   # 入口与工作流定义（平台无关）
├── README.md                                  # 本文件
├── LICENSE
└── references/
    ├── documentation-governance.md            # 完整治理规则（平台无关纯 Markdown）
    ├── platform-adapter.md                    # 各 AI 编程工具接入详解
    └── templates/
        ├── adr-template.md                    # ADR 模板（六段式）
        ├── universal-doc-template.md          # 通用文档模板
        ├── audit-report-template.md           # 审计报告模板
        ├── bugfix-report-template.md          # BUG 修复报告模板
        ├── verification-report-template.md     # 验证报告模板
        ├── release-checklist-template.md      # 发布检查清单模板
        ├── agents-md-template.md              # Harness 入口/路由器模板
        ├── memory-template.md                 # MEMORY 长期记忆模板
        ├── progress-template.md               # PROGRESS 状态看板模板
        ├── decisions-template.md              # DECISIONS 决策日志模板
        └── tech-traps-template.md             # 技术陷阱库模板（冷记忆落点）
```

## 设计理念

文档会腐坏——不复盘的文档比没有文档更危险。本 Skill 把"可检索（索引 + frontmatter）、可审计（双维度评分 + 反模式）、可演进（生命周期 + 角色分层）"固化为可执行的约束，并刻意与具体 AI 编程工具解耦，使同一套治理逻辑可跨 CodeBuddy、Claude Code、Cursor、Windsurf、Cline、Aider、Copilot、Codex 复用。

治理规则本身（`references/documentation-governance.md`）与平台接入说明（`references/platform-adapter.md`）分离：前者是稳定知识，后者随工具演进而更新。

### 与 harness 搭建类 Skill 的关系

本 Skill 的 harness 文件命名、角色、结构与主流 harness 工程实践一致，**可与任何"harness 搭建类 Skill"在同一项目并存且不冲突**；但本 Skill **不依赖、也不 require 任何此类 Skill**——独立复制即可完整工作。运行态文件（`AGENTS`/`PROGRESS`/`DECISIONS`/`MEMORY`）不套用 `documents/` 的 Frontmatter 受控词表，避免重复摩擦。
