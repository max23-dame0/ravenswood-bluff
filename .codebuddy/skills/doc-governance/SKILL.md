---
name: doc-governance
description: 平台无关的通用文档治理引擎。为任意 AI 编程工具（CodeBuddy / Claude Code / Cursor / Windsurf / Cline / Aider / Copilot / Codex）管理的项目提供文档体系诊断、文档创建、文档审计、腐败检测与文档体系初始化五维工作流，使项目沉淀可检索、可审计、不易腐坏的 Markdown 文档库。
---

# doc-governance（文档治理）

为项目建立"可检索、可审计、不易腐坏"的文档体系。本 Skill 聚焦治理层，独立于任何功能文档生成或任务管理工作流——当你需要新建/整理/审计项目文档时遵循本规范即可。

## 何时使用

- 项目缺乏统一文档结构，或文档散落、难以检索
- 需要新建架构文档、计划、报告、发布记录、API 文档
- 文档出现"写了没人维护、链接失效、与代码脱节"等腐败迹象
- 在新项目初始化一套符合治理标准的 `documents/` 文档体系
- 对已沉淀文档做质量审计与一致性检查

## 核心模型：三层记忆模型（跨平台抽象）

所有 AI 编程工具共享同一概念，但承载文件不同。不要写死某一平台的路径：

| 层级 | 概念 | 作用 |
|------|------|------|
| **热（Hot）** | 常驻指令文件 | 每次会话自动加载，定义项目命令、规范、硬约束（如 `AGENTS.md` / `CLAUDE.md` / `.cursorrules` / `.codebuddy/rules/*.mdc` 等） |
| **温（Warm）** | 路径作用域规则 | 仅匹配特定路径/语境时激活，约束具体技术栈行为 |
| **冷（Cold）** | 长期记忆与文档语料 | 按需检索的知识库——即本项目治理的 `documents/` 文档体系 |

各平台具体承载文件见 `references/platform-adapter.md`。下文所有工作流产出的都是"冷层"资产（Markdown 文档），并通过"热层"规则文件约束其格式。

## 文档角色体系

每份文档用 frontmatter 的 `role` 标注其一，决定 Agent 的处理策略：

- `[State]` 描述**当前是什么**（架构、规范、API 契约、ADR）→ 修改即更新，始终反映最新状态
- `[Delta]` 描述**做过什么**（计划、审查、报告、发布）→ 完成后不再改动，只新增
- `[Cold]` 外部引入的知识（参考、调研）→ 仅作参考，不与代码同步

## Harness 文件约定（运行态 / 热层）

> 让 AI 编程工具每次会话都能"热启动"并持久化跨会话状态。`documents/` 语料是冷层；本节约定的是根目录**运行态文件**（热层）。详见 `references/documentation-governance.md §8`。
>
> **独立性与并存**：本节约定的命名、角色、结构与主流 harness 工程实践一致——因此本 Skill **可独立使用，也可与任何"harness 搭建类 Skill"并存，但本 Skill 不依赖、也不 require 任何此类 Skill**。

| 文件 | 角色 | 模板 | 是否套用 Frontmatter 受控词表 |
|------|------|------|------------------------------|
| `AGENTS.md` / `CLAUDE.md` | 入口路由器（80–200 行） | `agents-md-template.md` | 否（运行态） |
| `MEMORY.md` | 长期记忆（冷热分层 + Auto Memory） | `memory-template.md` | 否 |
| `PROGRESS.md` | 状态持久化三件套之一（三行摘要） | `progress-template.md` | 否 |
| `DECISIONS.md` | 决策日志 | `decisions-template.md` | 否 |
| `documents/05-reference/tech-traps.md` | 冷记忆落点（坑点库） | `tech-traps-template.md` | **是**（属语料） |

**关键区分**：运行态文件（上表前 4 个）是 Agent 工作台，**不强制** `doc_id`/`category`/`role`；`tech-traps.md` 属 `documents/` 语料，正常套用 §2.1。

**兼容原则**（与 harness 工程实践对齐，详见 §8.8）：仓库即真实来源、渐进式披露、状态持久化三件套（PROGRESS+DECISIONS+Git）、WIP 显式登记（≤3）、清洁状态闭环（含部署后/E2E 验证）、指令与记忆分离、三层文档分工不重复抄写。

## 五维工作流

### 1. 诊断工作流（Diagnose）

对目标项目的文档体系做体检。逐项检查：

1. 是否存在 `documents/README.md` 统一索引，且包含§五要素
2. frontmatter 元数据完整性（§2.1 必填字段）
3. 链接健康度（内部相对链接是否全部有效——重点查 `documents/README.md` 与实际文件的死链）
4. 角色标注一致性（`role` 与所在目录一致）
5. 代码一致性（代码示例/接口签名/配置参数是否与代码库一致）
6. 时效性（超过 30 天未更新或引用的代码已变更的文档）
7. 反模式命中（§6 清单）

输出诊断报告（可用 `references/templates/audit-report-template.md`），给出 Agent 友好度 + 人类可读性双评分（§5）。

### 2. 创建工作流（Create）

新建文档时：

1. 先查 `documents/README.md` 索引，确认无重复主题；有则更新既有文档
2. 按 `references/documentation-governance.md §1.2` 命名规则命名
3. 从 `references/templates/` 选模板，补全 frontmatter 受控词表（§2.1）
4. 按 §2.2 排版标准撰写，代码块标注语言，内部链接用相对路径
5. 在 `documents/README.md` 注册索引条目（§3.3）

### 3. 审计工作流（Audit）

周期性或发布前对文档质量打分：

- 用 §5 的 Agent 友好度六维 + 人类可读性五维评分
- 生成带严重度（🔴P0 / 🟡P1 / 🔵P2）的问题清单
- 输出可跟踪的修复优先级表

### 4. 腐败检测工作流（Corruption Detection）

重点识别"文档已失效但仍在被引用"的幽灵/僵尸文档：

- **幽灵文档**：存在文件但未在 `README.md` 注册
- **僵尸规则**：文档内容与代码不一致却未被标注 `superseded`
- **死链接**：索引或正文指向不存在的文件
- **岛文档**：无任何交叉引用

命中后按 §6 纠正，必要时将 `status` 改为 `archived` 或 `superseded`。

### 5. 初始化工作流（Initialize）

在新项目建立治理就绪的文档体系：

1. 按 `references/documentation-governance.md §3.1` 创建 `documents/` 标准目录
2. 复制 `references/templates/` 六个模板到 `documents/templates/`
3. 创建 `documents/README.md` 索引骨架（§3.3 五要素）
4. 在目标项目根目录建立 harness 运行态文件，从 `references/templates/` 取对应模板：
   - `AGENTS.md` / `CLAUDE.md`（入口路由器，80–200 行）→ `agents-md-template.md`
   - `MEMORY.md`（长期记忆，冷热分层 + Auto Memory）→ `memory-template.md`
   - `PROGRESS.md`（状态看板 + 三行摘要）→ `progress-template.md`
   - `DECISIONS.md`（决策日志）→ `decisions-template.md`
   - `documents/05-reference/tech-traps.md`（坑点库，套用 Frontmatter）→ `tech-traps-template.md`
   （命名与平台映射见 `references/platform-adapter.md`；以上文件**不依赖**任何 harness 搭建类 Skill）
5. 按 `references/platform-adapter.md` 把治理规则接入当前 AI 编程工具的规则机制，并把本文档 §8 要点精简进热层常驻文件（如 `global`）

## 核心速查

**Frontmatter 必填**（完整规范见 `references/documentation-governance.md §2.1`）：

```yaml
---
doc_id: "{category}-{NNN}"
title: "{文档标题}"
category: "{architecture|planning|review|release|report|reference|api|template|spec}"
role: "[State]"            # [State] | [Delta] | [Cold]
status: "published"        # draft | review | published | archived | superseded
date: "YYYY-MM-DD"
author: "{作者/团队}"
---
```

**文档生命周期**：`draft → review → published → archived / superseded`

**README 索引五要素**：①场景查找表 ②目录结构树(带角色标签) ③按目录分类索引 ④ADR 索引区 ⑤模板索引区

**反模式（禁止）**：无 frontmatter、幽灵文档、僵尸规则、巨型单文件(>500行)、死链接、岛文档、裸代码块、空格/特殊字符文件名、硬编码绝对路径。

## 配套资源

| 资源 | 用途 |
|------|------|
| `references/documentation-governance.md` | 完整治理规则（创建/格式/组织/Agent 友好/评分/反模式/接入） |
| `references/platform-adapter.md` | 三层记忆模型与各 AI 编程工具接入详解 |
| `references/templates/` | 6 个文档模板（ADR、通用文档、审计、BUG 修复、验证、发布清单）+ 5 个 harness 运行态模板（入口/MEMORY/PROGRESS/DECISIONS/tech-traps） |

## 平台适配

本 Skill 不绑定任何单一 AI 编程工具。把治理规则与目标项目的 `documents/` 结构接入 CodeBuddy / Claude Code / Cursor / Windsurf / Cline / Aider / GitHub Copilot / OpenAI Codex 的具体步骤，见 `references/platform-adapter.md`。最小可用接入：复制 `documents/` 结构 + 模板 → 根目录 `AGENTS.md` 写一行"编辑 `*.md` 须遵循 frontmatter 与索引规范" → 把 §2.1、§3.3 要点贴入该工具的规则文件。
