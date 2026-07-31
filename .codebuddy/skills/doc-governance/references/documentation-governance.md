# 通用文档治理规则（Documentation Governance）

> **适用范围**：所有 `*.md` 文档，跨项目、跨 AI 编程工具可迁移。
> **角色**：定义"怎么创建文档、写成什么样、放哪里、如何让 Agent 读懂"四维约束。
> **配套**：`doc-governance` Skill（工作流引导）、`references/templates/`（模板）、`references/platform-adapter.md`（各平台接入方式）。

本文档是平台无关的纯 Markdown 规范。不同 AI 编程工具（CodeBuddy / Claude Code / Cursor / Windsurf / Cline / Aider / GitHub Copilot / OpenAI Codex）对"常驻指令文件 / 路径作用域规则 / 长期记忆"的承载文件各不相同，但治理逻辑一致。如何把本规则接入具体平台，见 `references/platform-adapter.md`。

---

## §1 文档创建规范

### §1.1 创建决策树

```
需要新建文档吗？
├─ 是 → 检查是否已有覆盖该主题的文档（查 documents/README.md 索引）
│   ├─ 已有 → 更新现有文档，不新建
│   └─ 没有 → 确定文档角色
│       ├─ [State] → 放入 00-architecture/ 或 api/ 或根目录规范类
│       ├─ [Delta] → 放入 01-planning/、02-review/、03-releases/、04-reports/
│       └─ [Cold]  → 放入 05-reference/
└─ 否 → 不创建
```

### §1.2 命名规则

| 文档类型 | 命名格式 | 示例 |
|---------|---------|------|
| **ADR** | `NNN-{kebab-case}.md` | `001-containerization-strategy.md` |
| **Sprint Backlog** | `sprint-backlog_{PhaseN}_{主题}.md` | `sprint-backlog_Phase5_自定义Agent体系.md` |
| **审计/审查报告** | `{类型}_{范围}_{日期}.md` | `全项目综合审计_v2_2026-07-01.md` |
| **验证/测试报告** | `{Phase}{范围}_{验证类型}_{日期}.md` | `Phase3b_种子化端到端验证_2026-07-01.md` |
| **调研/参考** | `{主题关键词}_{日期}.md` | `AI编程Agent文档管理最佳实践调研报告_2026-07-06.md` |
| **设计文档** | `{主题}_{文档类型}.md` | `系统设计文档_SDD.md` |
| **模板文件** | `{用途}-template.md` | `adr-template.md` |

**通用规则**：
- 文件名使用**中文或英文**，同一项目保持一致
- 日期格式 `YYYY-MM-DD`（可排序）
- 禁止空格和特殊字符（`()` `&` `#` 等）
- 编号用三位零填充（`001`、`002`…`099`）

### §1.3 文档生命周期

```
draft（草稿）→ review（评审中）→ published（已发布）→ archived（已归档）
                                                    → superseded（已被替代）
```

- 每次状态变更更新 frontmatter `status` 字段
- 归档文档移入 `documents/archive/` 目录
- 被替代文档保留原位置，frontmatter 标注 `superseded_by: [新文档路径]`

---

## §2 格式与内容要求

### §2.1 Frontmatter 元数据（Agent 解析入口）

**每份文档必须包含 YAML frontmatter**，放在文件最顶部，用 `---` 包裹：

```yaml
---
# 必填字段
doc_id: "{category}-{NNN}"           # 文档编号，如 "ADR-001"、"RPT-2026-0706-001"
title: "{文档标题}"                    # 与一级标题一致
category: "{分类}"                     # 从受控词汇中选择（见 §2.1.1）
role: "[State]"                       # [State] | [Delta] | [Cold]
status: "published"                   # draft | review | published | archived | superseded
date: "YYYY-MM-DD"                    # 创建日期
author: "{作者/团队}"

# 推荐字段
tags: ["tag1", "tag2"]                # 检索标签（小写英文或中文关键词）
related:                              # 关联文档（相对路径）
  - "00-architecture/系统设计文档_SDD.md"
  - "architecture-decisions/001-documentation-architecture.md"

# 可选字段
version: "v1.0"                       # 文档版本
superseded_by: ""                     # 被哪个文档替代
reviewers: ["审核人1", "审核人2"]       # 审核人列表
---
```

#### §2.1.1 受控词汇（category）

| 分类 | 说明 | 对应目录 |
|------|------|---------|
| `architecture` | 架构设计、技术方案 | `00-architecture/` |
| `planning` | 改进计划、Sprint Backlog | `01-planning/` |
| `review` | 审查报告、审计、BUG 报告 | `02-review/` |
| `release` | 发布版本、DDL | `03-releases/` |
| `report` | 项目报告、验证报告 | `04-reports/` |
| `reference` | 外部参考、调研 | `05-reference/` |
| `api` | API 接口文档 | `api/` |
| `template` | 文档模板 | `templates/` |
| `spec` | 规范/标准 | 根目录（如 `AGENTS.md`） |

### §2.2 通用排版标准

| 元素 | 规范 | 示例 |
|------|------|------|
| **标题层级** | `#` → `##` → `###` → `####`，不超过 4 级 | `## §1 文档创建规范` |
| **代码块** | 必须标注语言类型 | ` ```java ` 而非 ` ``` ` |
| **表格** | 对齐线使用 `:--`、`:--:`、`--:` | 见本文所有表格 |
| **列表** | 无序用 `-`，有序用 `1.`，嵌套缩进 2 空格 | — |
| **链接** | 使用**相对路径**，不用绝对路径 | `[设计文档](00-architecture/系统设计文档_SDD.md)` |
| **图片** | 存放于 `documents/images/`，相对路径引用 | `![架构图](images/architecture.png)` |
| **换行** | 段落间空一行，章节间空一行 + `---` 分隔线 | — |

### §2.3 内容质量规范

#### 必检项（文档创建/修改时逐项通过）

- [ ] **Frontmatter 完整**：§2.1 中"必填字段"全部填写
- [ ] **标题一致**：frontmatter `title` = 文档一级标题 `# xxx`
- [ ] **角色标注**：`role` 字段已填，且与目录角色一致
- [ ] **TOC 目录**：超过 3 个 `##` 章节的文档，在标题下方提供目录
- [ ] **代码一致性**：所有代码示例/接口签名/配置参数与当前代码库一致
- [ ] **链接有效性**：所有内部链接指向存在的文件（相对路径）
- [ ] **无占位符**：不允许 `TODO`、`FIXME`、`xxx` 等占位符（除非标记为 `draft` 状态）
- [ ] **索引注册**：在 `documents/README.md` 中注册了索引条目

#### 时效性检查

| 条件 | 操作 |
|------|------|
| 文档超过 30 天未更新 | 检查内容是否仍准确 |
| 文档引用的代码已变更 | 更新文档或标注 `status: superseded` |
| 状态为 `draft` 超过 14 天 | 催促完成或降级为 `archived` |

---

## §3 文档组织规范

### §3.1 标准目录结构

```
documents/
├── README.md                     ← [必需] 统一索引入口（Agent 检索起点）
├── images/                       ← [可选] 文档内嵌图片
│
├── 00-architecture/              ← [State] 架构与设计（权威真源）
│   ├── architecture-decisions/   ← [State] ADR 决策记录
│   ├── 系统设计文档_SDD.md
│   ├── 测试策略与质量门禁.md
│   └── ...
│
├── 01-planning/                  ← [Delta] 计划与 Backlog
│   └── sprint-backlog_*.md
│
├── 02-review/                    ← [Delta] 审查与一致性分析
│   ├── audit/                    ← 审计专项报告
│   └── bugfix/                   ← BUG 报告
│
├── 03-releases/                  ← [Delta] 版本化交付物（含 baseline/ 与版本化 DDL）
│
├── 04-reports/                   ← [Delta] 项目报告（验收/进度/验证）
│
├── 05-reference/                 ← [Cold] 外部参考与调研（含 tech-traps 技术陷阱库）
│
├── api/                          ← [State] API 接口文档
│
├── archive/                      ← 历史归档（只读）
│
└── templates/                    ← [State] 文档模板
```

### §3.2 角色标注体系

```
[State]  — 描述"当前是什么"（架构、规范、API 契约、ADR）
           → 修改即更新，始终反映最新状态

[Delta]  — 描述"做过什么"（计划、审查、报告、发布记录）
           → 完成后不再修改，只新增

[Cold]   — 外部引入的知识（参考文档、调研报告、第三方文档）
           → 仅作参考，不与项目代码同步
```

### §3.3 索引维护规则

`documents/README.md` 必须包含：

1. **场景查找表**：`| 我想... | 先看这个 | 再看这个 |` 格式
2. **目录结构图**：ASCII 树形图，含角色标签
3. **按目录分类索引**：表格，含 `| 文档 | 角色 | 日期 | 状态 |` 列
4. **ADR 索引区**：`| ADR | 标题 | 状态 | 日期 | 关联 |`
5. **模板索引区**：`| 模板 | 用途 |`

---

## §4 Agent 友好标记体系

### §4.1 结构化标记（Agent 解析元数据）

| 标记 | 位置 | 格式 | 作用 |
|------|------|------|------|
| **YAML frontmatter** | 文件顶部 | `---\nkey: value\n---` | Agent 读取元数据入口 |
| **角色标签** | frontmatter `role` | `[State]` / `[Delta]` / `[Cold]` | 决定 Agent 的处理策略 |
| **文档编号** | frontmatter `doc_id` | `{category}-{NNN}` | 全局唯一标识 |
| **标签** | frontmatter `tags` | `["k8s", "container", "lifecycle"]` | 语义检索关键词 |
| **关联链接** | frontmatter `related` | 相对路径数组 | 构建文档间知识图谱 |

### §4.2 检索优化约定

| 约定 | 说明 | 示例 |
|------|------|------|
| **可排序日期** | 文件名含 `YYYY-MM-DD` | `验证报告_2026-07-06.md` |
| **固定命名模式** | 同类型文档用相同前缀 | `sprint-backlog_Phase*` |
| **编号递增** | 用三位数字 | `001`、`002`… |
| **英文 Tag** | tags 字段用小写英文便于跨境项目 | `tags: ["k8s", "container"]` |
| **索引表可 grep** | README.md 中的表用标准 Markdown 表格 | `| 文档 | 角色 | 日期 |` |

### §4.3 解析约定（Agent 消费）

| 约定 | 说明 |
|------|------|
| **代码块语言标注** | ` ```java `、` ```yaml `、` ```sql ` — 未标注语言视为纯文本 |
| **任务列表** | `- [ ] 待完成` / `- [x] 已完成` — Agent 可识别并跟踪完成度 |
| **章节编号** | `§` 前缀（如 `§1.1`）— Agent 交叉引用时可精确定位 |
| **相对链接** | 所有内部链接用相对路径 — Agent 可直接通过 workspace 解析 |
| **语义化表格** | 表格第一行为列名，Agent 可解析为键值对 |

---

## §5 质量评分标准

### §5.1 Agent 友好度评分

| 维度 | 满分 | 评分标准 |
|------|:--:|------|
| **元数据完整性** | 25 | frontmatter 全部必填字段（5 分/字段） |
| **角色标注** | 15 | `role` 正确且与目录一致 |
| **链接健康度** | 20 | 内部链接全部有效（每发现 1 个死链 -5） |
| **代码一致性** | 20 | 代码示例与当前代码库一致 |
| **可检索性** | 10 | 含 `tags` + `doc_id` + 已在 README.md 注册 |
| **时效性** | 10 | 30 天内更新过，或内容仍准确 |
| **总计** | 100 | ≥ 80 → 优秀，60~79 → 合格，< 60 → 需改进 |

### §5.2 人类可读性评分

| 维度 | 满分 | 评分标准 |
|------|:--:|------|
| **排版规范** | 25 | 满足 §2.2 所有排版标准 |
| **TOC 目录** | 15 | 超过 3 节的有 TOC |
| **示例丰富** | 20 | 关键概念有代码/配置示例 |
| **图表辅助** | 20 | 架构图/流程图/时序图（Mermaid 或图片） |
| **语言清晰** | 20 | 无歧义、无过度缩写、中文自然流畅 |
| **总计** | 100 | ≥ 80 → 优秀，60~79 → 合格，< 60 → 需改进 |

---

## §6 禁止模式（Anti-Patterns）

| 反模式 | 说明 | 纠正 |
|--------|------|------|
| 🔥 **无 frontmatter** | 文档缺少 YAML 元数据头 | 补充 frontmatter |
| 🔥 **幽灵文档** | 存在但未在 README.md 注册 | 注册到索引 |
| 🔥 **僵尸规则** | 文档内容与代码不一致 | 更新或标注 `superseded` |
| 🔥 **巨型单文件** | 超过 500 行的单 Markdown 文件 | 拆分为多文件 |
| ⚠️ **死链接** | 内部链接指向不存在的文件 | 修复或移除 |
| ⚠️ **岛文档** | 没有任何交叉引用 | 添加 `related` 关联 |
| ⚠️ **裸代码块** | 代码块无语言标注 | 添加语言标签 |
| ⚠️ **空格/特殊字符文件名** | `文档 (v2).md` | 规范化为 `文档_v2.md` |
| ⚠️ **硬编码绝对路径** | `/home/user/project/docs/x.md` | 改为相对路径 |

---

## §7 接入各平台

本规则是平台无关的纯 Markdown。如何把它接入具体的 AI 编程工具（常驻指令文件、路径作用域规则、长期记忆机制），见 `references/platform-adapter.md`。

文档创建时只需遵循本规范；本 Skill 聚焦"治理层"（诊断、创建、审计、腐败检测、初始化），独立于任何功能文档生成或任务管理工作流。

---

## §8 Harness 文件治理

> **目的**：在目标项目根目录建立一组 Agent 运行态文件（入口路由器、长期记忆、进度看板、决策日志、分层规则），让 AI 编程工具在每次会话都能"热启动"，并支持多会话状态持久化。
>
> **与本文档其他章节的关系**：§1~§7 约束的是 `documents/` **语料**（冷层）；本节约束的是**热层运行态文件**。两者命名、角色、结构刻意与主流 harness 工程实践对齐，因此**本 Skill 既可独立使用，也可与任何"harness 搭建类 Skill"并存——但本 Skill 不依赖、也不 require 任何此类 Skill**。

### §8.1 运行态文件 vs 语料文件（关键区分）

| 维度 | 语料文件（`documents/`） | 运行态 Harness 文件（根目录） |
|------|------------------------|------------------------------|
| 层级 | 冷层（按需检索） | 热层（每次会话加载） |
| 受 §2.1 Frontmatter 约束 | **是**（需 `doc_id`/`category`/`role` 等） | **否**（不要求 Frontmatter 受控词表） |
| 生命周期 | draft→review→published→… | 随项目状态持续演进 |
| 角色 | `[State]`/`[Delta]`/`[Cold]` | 入口=手册（人写）、MEMORY=笔记（AI 写） |
| 是否计入质量评分 | 是 | 仅做"是否存在/是否过期"健康度检查 |

> **为什么运行态文件不套用 Frontmatter 受控词表**：它们是 Agent 的"工作台"，不是知识库语料。强制 `doc_id`/`category` 会增加无谓摩擦，反而降低被维护的意愿。其格式由本节 §8.2~§8.6 单独约定。

### §8.2 入口文件（路由器 / Hot）

**命名**（按平台，见 `references/platform-adapter.md`）：`AGENTS.md`（CodeBuddy / Cursor / Codex / 通用标准）或 `CLAUDE.md`（Claude Code）。

**篇幅**：80–200 行（渐进式披露，细节外链到 `documents/`）。

**必含区块**：

1. **Setup & Commands**：环境准备、构建/测试/启动/部署命令
2. **会话工作流**：标准执行步骤
3. **清洁状态检查**：硬性"做完"定义，含**部署后/E2E 验证闭环**（详见 §8.9）
4. **分层规则加载指引**：如何引用 `documents/` 与分层规则文件
5. **上下文预算声明**：入口 ≤200 行、MEMORY ≤200 行
6. **硬约束清单**（建议 ≤15 条）：每条标注 `why` / `when` / `when-remove`
7. **专题文档索引**：指向 `documents/README.md`
8. **临时产物纪律**：中间文件放哪、何时清理

**模板**：`references/templates/agents-md-template.md`

### §8.3 MEMORY.md（长期记忆，冷热分层 / Cold→Hot 桥）

**命名**：`MEMORY.md`（或平台等价记忆文件）。**篇幅**：50–200 行（硬上限 200）。

**区块**：启动链、项目定位、模块速查、核心基础设施、关键状态枚举、硬约束、禁止事项、🤖 **Auto Memory 区域**（AI 追加的项目认知）。

**冷热分层**：高频/稳定知识留在本文件（热）；坑点、已废弃的旧约束、长尾细节**外链**到 `documents/05-reference/tech-traps.md`（冷）——既控制 MEMORY 体积，又让陷阱可检索。

**模板**：`references/templates/memory-template.md`

### §8.4 PROGRESS.md（状态持久化三件套之一）

根目录文件，承载"现在进行到哪"。必含：

- **活跃任务看板**：显式登记并行任务（建议 ≤3），每条标状态
- **未提交改动清单**：每条须有对应 commit（✅ 已提交 / 🚧 待提交）
- **测试基线**：具名基线（如 `baseline-v1.6.0`），供回归对比
- **整体进度** / **阻塞项** / **最近会话记录**：三行摘要（**禁止抄写过程**）

**模板**：`references/templates/progress-template.md`

### §8.5 DECISIONS.md（决策日志）

根目录文件，承载"为什么这么做"。每条格式：

```
## D{NNN} {一句话决策}
- 日期：YYYY-MM-DD
- 决策：……
- 原因：……
- 否决方案：……（及为何否决）
- 约束：……
```

**模板**：`references/templates/decisions-template.md`

### §8.6 分层规则（热层常驻 / 温层作用域）

- **热层**：`global.md`（或等价常驻文件，`alwaysApply: true`）——项目通用规范
- **温层**：按检测到的分层架构生成对应文件（如 `api.md` / `service.md` / `data.md`），用 `globs` 限定作用域，仅匹配路径时激活

平台无关的承载方式见 `references/platform-adapter.md`；把本文档 §1~§7 要点精简进 `global.md` 即可完成治理规则的常驻化。

### §8.7 冷记忆落点：技术陷阱库

`documents/05-reference/tech-traps.md` 沉淀踩坑记录（可检索、可审计、可演进）。MEMORY 中只留一行指针，细节入此库。

**模板**：`references/templates/tech-traps-template.md`

### §8.8 与 harness 工程实践兼容的 12 条原则

1. **仓库即唯一真实来源**：harness 文件与 `documents/` 互补，代码优先于文档
2. **渐进式披露**：入口 80–200 行，细节按需加载
3. **每个约束标注来源 + 过期条件**（why / when / when-remove）
4. **状态持久化三件套**：PROGRESS + DECISIONS + Git
5. **WIP 显式登记**（建议 ≤3），避免"中间迷失"
6. **清洁状态 = 硬性"做完"定义**（含部署后/E2E 验证闭环）
7. **重要规则放文件首尾**（中等长度注意力的注意力陷阱）
8. **分层规则**：global → 模块 → 文件级
9. **上下文预算**：入口 ≤200 行，MEMORY ≤200 行
10. **指令与记忆分离**：入口=手册（人写），MEMORY=笔记（AI 写）
11. **三层文档分工**：daily memory / PROGRESS（三行摘要）/ handoff 禁止重复抄写
12. **清洁状态须含部署后/E2E 验证闭环**

### §8.9 清洁状态闭环（Clean-State Closure）

"做完"的硬性定义，至少覆盖：

- [ ] 功能/文档改动已完成并自测通过
- [ ] 关联 `documents/` 已更新（frontmatter + 索引）
- [ ] `PROGRESS.md` 未提交清单已清零（或已 commit）
- [ ] 若涉及部署：**部署后**已验证（E2E / 健康检查 / 关键链路回归）
- [ ] 无残留临时产物（中间文件已清理）
