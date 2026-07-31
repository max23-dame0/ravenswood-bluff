---
name: harness-setup
description: 专供 coding agent 安装与调用的即插即用 Harness 环境搭建 Skill。语言/框架无关，自动适配任意技术栈（Java/Python/Go/Node/前端等）。支持 CodeBuddy（AGENTS.md）和 Claude Code（CLAUDE.md）等多种 Agent 平台。当用户需要为项目初始化或重建 coding agent 的 harness 工作环境时触发。触发词包括"搭建harness"、"初始化harness"、"harness环境搭建"、"setup harness"、"重新搭建harness"、"harness治理"、"agent工作环境"、"空项目搭建"、"从零搭建"。基于 Learn Harness Engineering 13 讲体系，自动扫描项目、检测平台和分层架构、生成全套自适应 harness 文件，支持增量更新与退化检测；并支持空项目（Greenfield）模式：通过对话澄清需求、搭建最小测试框架脚手架，并在后续开发中持续自适应，让 coding agent 免去繁琐的环境配置步骤。
---

# Harness Setup — 即插即用 Harness 环境搭建 Skill

## 定位与边界

### 本 Skill 是什么

一个 **专供 coding agent 安装与调用的 meta-skill**。**语言/框架无关**，支持任意技术栈（Java/Spring、Python/Django、Go/Gin、Node/Express、Vue/React 前端等）。目标项目的 coding agent 加载本 Skill 后，通过一句触发词即可自动检测项目架构并完成全套 Harness 环境搭建。核心价值：**即插即用，零手工配置**。

### 核心原则

- **即插即用**：安装到项目后，一句"搭建 harness"即可触发全自动搭建
- **可持续适应**：支持增量更新（项目变化时只更新变动部分）和退化检测（过时文件自动标记）
- **仓库即真实来源**：所有生成文件落地到项目仓库，受 Git 版本管理

### 严格边界：本 Skill 不做什么

本 Skill **仅聚焦 Harness 环境配置**，严格遵守以下边界：

**✅ 本 Skill 做的事（允许）**：
- 创建、更新、增量维护 `AGENTS.md` / `CLAUDE.md` / `MEMORY.md` / `PROGRESS.md` / `DECISIONS.md` 等 Markdown 配置文件
- 分析项目结构（技术栈、构建工具、模块划分）
- 从现有配置文件中提取编码规范（Checkstyle、ESLint、ruff 等）
- 生成分层规则文件（`.codebuddy/rules/*.md`）
- 创建上下文治理配置（大小预算、加载策略）
- 生成辅助文件（tech-traps.md、session-handoff.md）
- 执行全新会话验证测试

**❌ 本 Skill 不做的事（禁止）**：
- 编写、修改、删除任何业务代码文件（`.java`、`.ts`、`.vue`、`.py` 等）
- 执行 `git commit` / `git push`（Harness 文件创建后由 coding agent 自行决定是否提交）
- 修改项目依赖配置（`package.json`、`pom.xml`、`requirements.txt` 等）
- 实现任何功能逻辑或业务特性
- 运行编译/测试命令（那是 coding agent 的工作，不是 harness 搭建者的工作）

**一句话边界**：本 Skill 是"装修队"——负责铺好地板、接好水电（harness 环境），但绝不碰业主的家具和电器（业务代码）。

### 空项目（Greenfield）模式的边界放宽

当目标项目为**空项目**（无源码、无构建配置、README 为空或缺失）时，本 Skill 进入 Greenfield 模式。此时"接好水电"本身包含**搭建测试框架**这项基础设施——因为空房间里没有任何可运行的环境，coding agent 连 `pytest`/`jest` 都无处可跑。因此 Greenfield 模式允许本 Skill 在用户确认后：

- ✅ 创建最小项目骨架与**测试框架脚手架**（如 `package.json`/`pyproject.toml` 的 dev 依赖、`tests/` 目录、一个 smoke test）
- ✅ 将需求澄清结果（技术栈、模块结构、测试框架选型、状态枚举、编码规范）写入 harness 文件
- ❌ 仍**不编写任何业务功能代码**（不含领域逻辑、不含真实业务用例）
- ❌ 仍**不执行** `git commit` / 不运行测试命令（脚手架创建后由 coding agent 跑）

> 一句话：Greenfield 模式下"装修队"不仅铺地板，还会把**水电总闸（测试框架）**一并装好，但绝不会替业主买家具（业务功能）。

## 触发条件

当用户提到以下场景时触发：

- "搭建 harness"、"初始化 harness"、"harness 环境搭建"、"setup harness"
- "重新搭建 harness"、"重建 harness"
- "harness 治理"、"agent 工作环境"
- "给这个项目配 harness"、"为项目搭建编码 agent 环境"
- "检查 harness 退化"、"更新 harness"
- "空项目搭建"、"从零搭建"、"初始化空项目"、"greenfield harness"（空项目引导模式）

## 工作流

### Phase 0：模式判定（首次搭建 vs 增量更新 vs 退化修复）

根据传入指令（如"搭建"、"更新"、"检查退化"）和目标项目现状，判定当前使用的模式：

| 模式 | 触发方式 | 行为 |
|------|---------|------|
| 首次搭建 | "搭建harness" / "初始化harness" | 全量生成所有文件 |
| 增量更新 | "更新harness" | 仅更新与项目现状不一致的文件 |
| 退化修复 | "检查harness退化" / "harness治理" | 扫描已有文件，标记过期/过时项 |
| 空项目引导（Greenfield） | "空项目搭建" / "从零搭建" / 检测到空项目 | 先需求澄清对话，再脚手架测试框架，最后生成 harness 文件（见 Phase 1B） |

### Phase 1B：空项目模式（需求澄清 + 测试框架脚手架）

> 仅当 Phase 0 判定为「空项目引导」模式时执行本阶段。**空项目无可扫描**，因此本阶段先把"项目该长什么样"通过对话澄清出来，再搭好测试框架这块"水电总闸"，最后才生成 harness 文件。

#### 1B.1 需求澄清对话（Agent 主导，用户回答）

Agent 主动发起结构化澄清，**不要一次性抛出所有问题**，按以下模块分轮询问，每轮 1-3 个问题，用户已说明的跳过。答案实时写入 `DECISIONS.md` 与 `MEMORY.md`（见 1B.3）。

| 模块 | 澄清要点 | 若用户不确定，Agent 的默认建议 |
|------|---------|-------------------------------|
| 项目目标 | 做什么系统？核心用户/场景？MVP 范围？ | 先定一个最小可用闭环 |
| 语言/技术栈 | 用哪种语言/框架？ | 按团队熟悉度或生态成熟度给 1-2 个选项 |
| 模块结构 | 预期分层（如 controller/service/repo）？ | 给出该语言的主流分层建议 |
| 测试框架 | 单元/集成测试用什么？ | 按语言给主流选型（见 1B.2） |
| 状态枚举 | 有哪些关键状态/术语？ | 待 coding agent 开发时补充 |
| 编码规范 | 命名/格式/错误处理偏好？ | 采用该语言社区默认约定 |
| CI/质量门 | 是否需要 CI、覆盖率门槛？ | 先留空，后续再加 |

澄清完成后，Agent 用一句话**复述需求要点**请用户确认，避免方向错误。

#### 1B.2 测试框架脚手架（Greenfield 专属，环境基础设施）

经用户确认技术栈后，Agent 创建**最小测试框架脚手架**。这是本 Skill 对"不修改依赖配置"边界的唯一例外——空项目无环境可运行，必须先装好"水电"。**仅脚手架，不含业务代码**：

| 技术栈 | 创建内容（示例） |
|--------|----------------|
| Python | `pyproject.toml`/`requirements.txt`（含 `pytest` 等 dev 依赖）、`tests/` 目录、一个 `test_smoke.py`（断言 `True`，证明框架可跑） |
| Node/TS | `package.json`（含 `jest`/`vitest` devDependency + `test` script）、`__tests__/` 或 `tests/`、`smoke.test.ts` |
| Go | `go.mod`（若无）、`<pkg>_test.go` 的最小 `TestSmoke` |
| Java | `pom.xml`/`build.gradle`（含 JUnit 等 test 依赖）、`src/test/` 骨架 |
| 前端 | 沿用 Node 方案，测试目录指向组件/逻辑层 |

> 脚手架只验证"框架能跑起来"，**不写任何真实业务用例**。真实用例由后续 coding agent 按需求补充。

#### 1B.3 将澄清结果固化进 harness 文件

- `DECISIONS.md` 追加：`D00X 测试框架选型 = {框架}`（含原因、否决方案），`D00Y 模块分层 = {结构}`
- `MEMORY.md`：`项目定位` 由澄清结果填充；`技术栈`/`模块速查`/`关键状态` 先用已知项，未知项标注 `（待开发补充）`
- `AGENTS.md` 的 `Setup & Commands` 的 `{{TEST_CMD}}` 填为脚手架对应命令（如 `pytest` / `npm test`）
- 可选：将澄清结论与脚手架方案写入 `documents/05-reference/greenfield-plan.md`（模板 `assets/greenfield.md.tmpl`），作为项目蓝图存档

#### 1B.4 与常规 Phase 的衔接

完成 1B.1–1B.3 后，**继续走 Phase 2（平台检测）→ Phase 3（文件生成）→ Phase 4（验证）→ Phase 5（报告）**，此时项目已从"空"变为"有测试框架的最小骨架"，后续生成逻辑与常规搭建一致。

---

### Phase 1：项目扫描

分析目标项目，收集 Harness 生成所需的所有信息。**本阶段只读，不写任何文件**。

#### 1.1 项目身份

- 项目名称和一句话定位：从 `README.md`、根 `package.json`、根 `pom.xml` 提取
- Git 仓库信息：`git remote -v`、当前分支

#### 1.2 技术栈

- 语言/运行时版本（从 `package.json`、`pom.xml`、`go.mod`、`Cargo.toml`、`.python-version` 等提取）
- 框架（Spring Boot、Vue、React、Express 等）
- 构建工具（Maven、Gradle、npm、yarn、pnpm、Make 等）
- 数据库/中间件（从 `application.yml`、`.env`、`docker-compose.yml` 等提取）

#### 1.3 运行命令

从 `package.json` scripts、`Makefile`、`pom.xml` 等提取：
- 编译命令
- 测试命令
- 启动命令

#### 1.4 编码规范

从现有配置文件中提取（**语言无关**，有什么提取什么）：
- **代码风格**：`.eslintrc.*` / `.prettierrc` / `checkstyle.xml` / `pyproject.toml [tool.ruff]` / `.editorconfig` / `.clang-format` / `rustfmt.toml` 等
- **分层架构**：分析 `src/` 下的目录/包（如 Java 的 controller-service-repository、Python 的 views-services-models、Go 的 handler-service-repo、Node 的 routes-controllers-services、前端 SPA 的 components-stores-views 等），**按项目实际结构描述，不预设固定分层**
- **编码约定**：从现有代码中归纳命名规范、错误处理模式、依赖注入方式等

#### 1.5 模块结构

- 单仓库：分析 `src/` 目录结构
- Monorepo：分析 `packages/`、`modules/`、`apps/`、多构建模块（`pom.xml`、`Cargo.toml`、`go.mod`、`package.json` workspaces 等）
- 生成模块速查表

#### 1.6 已有 Harness 文件

检查以下文件是否已存在，记录内容和行数：

| 文件 | 路径 |
|------|------|
| 入口文件 | `AGENTS.md` / `CLAUDE.md` / `CURSOR.md` |
| 长期记忆 | `.codebuddy/memory/MEMORY.md` |
| 进度 | `PROGRESS.md` |
| 决策 | `DECISIONS.md` |
| 规则 | `.codebuddy/rules/*.md` |
| 技术陷阱 | `documents/05-reference/tech-traps.md` |
| 会话交接 | `.codebuddy/harness/session-handoff.md` |

### Phase 2：平台检测

判断目标项目使用的 Agent 平台：

| 信号 | 判定平台 | 入口文件名 |
|------|---------|-----------|
| 存在 `.codebuddy/` 目录 | CodeBuddy | `AGENTS.md` |
| 存在 `.claude/` 目录或 `CLAUDE.md` | Claude Code | `CLAUDE.md` |
| 存在 `.cursor/` 目录或 `.cursorrules` | Cursor | `AGENTS.md` |
| 存在 `.codex/` 目录或 `.codex.toml` | Codex CLI | `AGENTS.md` |
| 无明确信号 | 默认 | `AGENTS.md` |

### Phase 3：文件生成

按顺序执行。**每步使用 `assets/` 目录下的模板**，填充 Phase 1 扫描结果。

#### 步骤 1：入口文件（`AGENTS.md` / `CLAUDE.md`）——根目录

- **模板**：`assets/entry.md.tmpl`
- **目标行数**：80-200 行
- **角色**：路由器，不写详细规范
- **必含内容**：
  - Setup & Commands
  - 会话工作流（上班读记忆 → WIP 显式登记看板 → 下班记进度 + 填交接 + 对齐 git）
  - 清洁状态检查（L12 六项，含「部署后/E2E 验证闭环」第 6 项）
  - 分层规则加载指引（指向 `.codebuddy/rules/`）
  - 上下文预算声明（最大加载量）
  - 硬约束（≤15 条，标注 why/when/when-remove）
  - 专题文档索引
  - 临时产物纪律（调试 `*.txt` / `*_trace.txt` / 临时 `*.log` 不污染仓库，下班前清理或进 `.gitignore`）

#### 步骤 2：长期记忆 `MEMORY.md`（`.codebuddy/memory/` 或平台对应目录）

- **模板**：`assets/MEMORY.md.tmpl`
- **目标行数**：50-80 行（**硬上限 200 行**，超出部分 AI 需自行精简）
- **角色**：项目认知 + Auto Memory 指令
- **必含内容**：
  - ⚠️ 启动链（依次读取顺序）
  - 项目定位（1 段）
  - 模块速查表
  - 核心基础设施
  - 关键状态枚举
  - 硬约束
  - 禁止事项
  - 🤖 **Auto Memory 区域**：AI 在会话中自动将重要发现追加到此区域
- **冷热分层（主动）**：坑点/旧约束/过期风险等"冷记忆"外链到 `documents/05-reference/tech-traps.md`，MEMORY.md 仅保留「热认知」（模块/中间件/状态枚举/硬约束/纪律）+ 一行索引。超过 120 行即触发精简，不等到 200 行退化告警。

#### 步骤 3：`PROGRESS.md`（根目录）

- **模板**：`assets/PROGRESS.md.tmpl`
- **目标行数**：40-60 行
- **必含内容**：
  - 活跃任务看板（显式登记当前并行任务：任务名/阶段/状态/下一步/阻塞，**禁止只写单行 WIP**）
  - 未提交改动清单（标记 ✅ 的任务必须有对应 commit；仅本地验证未提交的一律登记状态 + 计划 commit，禁止"文档写完成、git 无 commit"）
  - 测试基线（具名：pass 数 + 每条已知失败须写明用例名 + 根因 + 关联 issue，**禁止模糊写"known failure"**）
  - 整体进度（阶段表格）
  - 阻塞项
  - 最近会话记录（**三行摘要**：做了什么 / 验证 / 下一步 + 链接 daily memory 日期，禁止把完整过程再抄一遍）

#### 步骤 4：`DECISIONS.md`（根目录）

- **模板**：`assets/DECISIONS.md.tmpl`
- **目标行数**：50-80 行
- **必含内容**：
  - D001：Harness 采用五子系统架构
  - 从已有文档中提取的架构决策（如有）
  - 格式：日期 + 决策 + 原因 + 否决方案 + 约束

#### 步骤 5：分层规则文件（`.codebuddy/rules/`）

- **模板**：`assets/rule.md.tmpl`（MDC 风格 YAML frontmatter）
- **核心原则**：**根据 Phase 1.4 分析出的实际分层架构生成规则文件**，不预设任何语言/框架的分层模式
- **始终生成**：
  - `global.md`（`alwaysApply: true`）— 全项目通用约束（语言/框架无关的通用规范）

- **按检测到的分层架构自动生成对应的规则文件**，globs 与目录结构一一对应。示例：

| 检测到的架构 | 生成的规则文件 |
|-------------|--------------|
| Java Spring (controller/service/repository) | `api.md` (globs: `**/controller/**`)、`service.md`、`data.md` (globs: `**/repository/**`) |
| Python Django (views/services/models) | `views.md` (globs: `**/views/**`)、`services.md`、`models.md` (globs: `**/models/**`) |
| Go (handler/service/repo) | `handler.md` (globs: `**/handler/**`)、`service.md`、`repo.md` (globs: `**/repo/**`) |
| Node Express (routes/controllers/services) | `routes.md` (globs: `**/routes/**`)、`controllers.md`、`services.md` |
| 前端 SPA (components/stores/views) | `components.md` (globs: `**/*.vue, **/*.tsx`)、`stores.md` (globs: `**/stores/**`)、`views.md` |
| Clean Architecture (domain/use-cases/adapters) | `domain.md` (globs: `**/domain/**`)、`usecases.md`、`adapters.md` |
| 单文件脚本项目（无分层） | 仅保留 `global.md`，不强行拆分层 |

- 如果项目已有 lint 配置文件（`.eslintrc`、`checkstyle.xml`、`pyproject.toml` 等），将关键规则提取到对应文件的"代码风格"区域
- 无现成规范时，生成结构骨架（带注释引导用户补全）

#### 步骤 6：辅助文件

- **`documents/05-reference/tech-traps.md`**（如存在 `documents/` 目录）→ `assets/tech-traps.md.tmpl`
- **`.codebuddy/harness/session-handoff.md`** → `assets/session-handoff.md.tmpl`
- **`.codebuddy/harness/context-budget.md`** → `assets/context-budget.md.tmpl`（上下文预算声明）
- **`documents/README.md`** 索引更新（如已有索引文件）

### Phase 4：验证（全新会话测试）

对照 L03 标准，确认新 Agent 只读仓库就能回答 5 个问题：

| # | 问题 | 答案应来自 | 状态 |
|:--|------|------|:--:|
| 1 | 这是什么系统？ | MEMORY.md §1 项目定位 | ✅/❌ |
| 2 | 它怎么组织的？ | 入口文件 Project Structure | ✅/❌ |
| 3 | 怎么运行？ | 入口文件 Setup & Commands | ✅/❌ |
| 4 | 怎么验证正确性？ | 入口文件 清洁状态检查 | ✅/❌ |
| 5 | 现在的进度如何？ | PROGRESS.md | ✅/❌ |

### Phase 5：输出搭建报告

```markdown
# Harness 搭建报告 — {date}

## 搭建模式
{首次搭建 / 增量更新 / 退化修复}

## 项目识别
- 项目: {name} | 技术栈: {stack} | 构建: {build}
- Agent 平台: {CodeBuddy / Claude Code / ...}

## 已生成/更新文件
| 文件 | 操作 | 行数 |
|------|:--:|:--:|
| 入口文件（AGENTS.md / CLAUDE.md） | 🆕/🔄 | XX |
| MEMORY.md | 🆕/🔄 | XX |
| PROGRESS.md | 🆕/🔄 | XX |
| DECISIONS.md | 🆕/🔄 | XX |
| .codebuddy/rules/global.md | 🆕/🔄 | XX |
| .codebuddy/rules/{category}.md | 🆕/🔄 | XX |
| tech-traps.md | 🆕/🔄 | XX |
| session-handoff.md | 🆕/🔄 | XX |
| context-budget.md | 🆕/🔄 | XX |

## 验证结果
| # | 问题 | 状态 |
|:--|------|:--:|
| 1-5 | (同上) | ✅/❌ |

## 后续建议
- （增量模式）注意：XXX.md 已存在，仅更新 YYY 部分
- （退化修复）发现过时信息：XXX
```

---

## 自适应维护

### 增量更新检测

当触发"更新 harness"，在 Phase 1 扫描时对比：

- `package.json` / `pom.xml` 中的依赖是否变化 → 更新技术栈描述
- `src/` 下是否新增模块/包 → 更新模块速查、分层规则
- 是否新增了 lint 配置文件 → 更新 Coding Standards
- `.gitignore` 是否变化 → 更新上下文治理策略

### 退化检测信号

| 信号 | 诊断 | 操作 |
|------|------|------|
| 入口文件 > 200 行 | 违背渐进式披露 | 拆分详细规范到 rules/ |
| MEMORY.md > 200 行（或含冷记忆未外链） | 可能超出上下文预算 / 未冷热分层 | 精简或把坑点外链到 tech-traps.md |
| 规则文件无 frontmatter | 缺少元数据 | 自动补齐 YAML 头 |
| 入口文件的命令与 package.json 不一致 | 已过时 | 用当前值更新 |
| PROGRESS.md 日期 > 7 天未更新 | 进度信息陈旧 | 标记 ⚠️，提示用户 |
| 根目录散落调试产物（`*_trace.txt` / `test_*.txt` / 临时 `*.log`） | 违反临时产物纪律 | 清理或加入 `.gitignore` |
| PROGRESS 标记 ✅ 但 git 无对应 commit | 文档与 git 状态脱节 | 对齐：要么 commit，要么改标"已验证待提交"并登记未提交清单 |
| session-handoff.md 仅占位符（无真实内容） | 跨会话交接机制失效 | 下班流程强制填写 4 行交接摘要 |

### Greenfield 持续优化（开发测试过程中的自适应）

空项目搭好测试框架后，真正的开发由 coding agent 进行。本 Skill 通过"更新 harness"在后续持续优化：

- **测试框架扩张检测**：扫描新增的测试依赖（如 `requirements.txt` 加了 `pytest-cov`）或新测试目录，自动把新命令同步进 `AGENTS.md` 的 `Setup & Commands` 与 `MEMORY.md` 的 `技术栈`。
- **增量需求澄清**：开发中出现原澄清未覆盖的边界（新状态枚举、新模块），Agent 可在"更新 harness"时**补问**并写入 `DECISIONS.md`/`MEMORY.md`，不必重走 1B 全流程。
- **脚手架升级建议**：当业务测试变多，提示把 smoke test 目录结构规范化、补充覆盖率配置（仍由 coding agent 执行，本 Skill 只建议并记录决策）。

---

## 原则速查

| # | 原则 | 来源 |
|:--|------|:--:|
| 1 | 仓库即唯一真实来源 | L03 |
| 2 | 渐进式披露：入口 80-200 行，按需加载 | L04 |
| 3 | 每个约束标注来源+过期条件 | L04 |
| 4 | 状态持久化三件套：PROGRESS + DECISIONS + Git | L05 |
| 5 | WIP 显式登记：允许多任务并行，但必须登记活跃任务看板（建议 ≤3），切换前写回状态 | L07（实测纯 WIP=1 在重载下难遵守，登记制更稳） |
| 6 | 清洁状态 = 硬性"做完"定义 | L12 |
| 7 | 中间迷失效应：重要规则放文件首尾 | L04 |
| 8 | 分层规则：global → 模块 → 文件级 | L04 扩展 |
| 9 | 上下文预算：入口 ≤200 行，MEMORY ≤200 行 | 行业实践 |
| 10 | 指令与记忆分离：入口 = 手册（人写），MEMORY = 笔记（AI 写） | Claude Code 实践 |
| 11 | 三层文档分工：daily memory（过程细节）/ PROGRESS（三行摘要）/ handoff（交接）禁止重复抄写 | 实战复盘（ai-platform-server） |
| 12 | 清洁状态须含「部署后/E2E 验证闭环」：本地 ✅ ≠ 生产 ✅，未验证须显式记录原因 | 实战复盘（ai-platform-server） |

---

## 模板占位符说明

所有模板使用 `{{PLACEHOLDER}}` 标记，Phase 3 生成时替换：

| 占位符 | 含义 | 来源 |
|------|------|------|
| `{{PROJECT_NAME}}` | 项目名称 | Phase 1.1 |
| `{{PROJECT_DESCRIPTION}}` | 项目一句话定位 | Phase 1.1 |
| `{{BUILD_CMD}}` | 编译命令 | Phase 1.3 |
| `{{TEST_CMD}}` | 测试命令 | Phase 1.3 |
| `{{START_CMD}}` | 启动命令 | Phase 1.3 |
| `{{TECH_STACK}}` | 技术栈 | Phase 1.2 |
| `{{LANG_VERSION}}` | 语言版本 | Phase 1.2 |
| `{{MODULE_LIST}}` | 模块列表（表格） | Phase 1.5 |
| `{{MIDDLEWARE_LIST}}` | 中间件列表 | Phase 1.2 |
| `{{STATE_ENUMS}}` | 关键状态枚举 | Phase 1.2 分析 |
| `{{ARCHITECTURE_CONSTRAINTS}}` | 架构约束列表 | Phase 1.4 + 1.5 |
| `{{CODING_STANDARDS}}` | 编码规范 | Phase 1.4 |
| `{{DO_NOT_LIST}}` | 禁止事项列表 | Phase 1 推断 |
| `{{REFERENCE_DOCS}}` | 专题文档索引 | Phase 1.6 检测 |
| `{{ENTRY_FILE}}` | 入口文件名 | Phase 2 平台检测 |
| `{{CONTEXT_BUDGET}}` | 上下文预算总字节数 | 默认 32768 (32 KiB) |
| `{{DATE}}` | 搭建日期 | 当前日期 |
| `{{REPO_PATH}}` | Git 仓库路径 | Phase 1.1 |
| `{{BRANCH}}` | 当前分支 | Phase 1.1 |
| `{{GREENFIELD_MODE}}` | 是否空项目（Greenfield）模式 | Phase 0 判定 |
| `{{TEST_FRAMEWORK}}` | 选型的测试框架 | Phase 1B.2 |
| `{{REQUIREMENT_SUMMARY}}` | 需求澄清要点摘要 | Phase 1B.1 |
