# Harness Setup 用户使用指南

> 面向开发者的完整上手手册。读完本指南，你将掌握：如何安装本 Skill、如何一句命令搭建项目 Harness 环境、日常开发的标准工作流，以及遇到问题时如何排查。

---

## 0. 适用对象与文档目的

本指南适用于**任何使用 Coding Agent 进行开发的工程师**（无论你用 CodeBuddy、Claude Code、Cursor 还是 Codex）。

你不需要理解 Harness Engineering 的全部理论，只需要知道三件事：

1. **本 Skill 是"装修队"**：安装它之后，它会自动为你的项目铺好 Coding Agent 的工作环境（一系列 Markdown 配置文件）。
2. **它不碰你的代码**：搭建过程只创建配置文档，绝不修改、编写、删除任何业务代码，也不改动 `package.json` / `pom.xml` 等依赖文件。*唯一例外*：当项目是**空项目**时，Skill 会额外搭建最小**测试框架脚手架**（仅"水电"，不含业务代码），详见 §3.5。
3. **一次搭建，长期受益**：搭建完成后，你的 Coding Agent 每次新会话都会自动读取这套环境，省去反复解释项目背景的麻烦。

---

## 1. 核心概念速览

### 1.1 什么是 Harness

Harness（意为"马具/装备"）在这里指 **Coding Agent 的工作环境配置**。它把"项目背景、运行命令、编码规范、进度、决策"等信息结构化地放进仓库，让 Agent 一上手就"懂"你的项目。

### 1.2 搭建后会生成什么

Skill 会在你的项目仓库里生成如下文件结构（**全部受 Git 管理，是你的项目资产**）：

```
目标项目/
├── AGENTS.md  (或 CLAUDE.md，取决于平台)   # 入口文件 — Agent 着陆页/操作手册
├── PROGRESS.md                             # 项目进度 — 当前状态快照
├── DECISIONS.md                            # 架构决策 — 记录重要决定，避免反复推翻
├── .codebuddy/
│   ├── memory/
│   │   └── MEMORY.md                       # 长期记忆 + Auto Memory（AI 自主维护）
│   ├── rules/                              # 分层规则（按项目架构自适应的 .md 文件）
│   │   ├── global.md                       #   始终生效的全局规则
│   │   └── {layer}.md                      #   按检测到的分层自动创建（如 api.md/service.md）
│   └── harness/
│       ├── session-handoff.md              # 会话交接模板（跨会话恢复上下文）
│       └── context-budget.md               # 上下文预算配置（窗口分配策略）
└── documents/
    └── 05-reference/
        └── tech-traps.md                   # 技术陷阱冷记忆（踩坑记录）
```

> 不同平台入口文件名不同：CodeBuddy/Cursor/Codex → `AGENTS.md`；Claude Code → `CLAUDE.md`。规则文件（`rules/`）格式在所有平台间互通。

### 1.3 各文件职责（一句话）

| 文件 | 一句话 | 谁维护 |
|------|--------|--------|
| `AGENTS.md` / `CLAUDE.md` | Agent 的"操作手册"：命令、工作流、硬约束 | 人 + Skill |
| `MEMORY.md` | 项目的"长期记忆"：认知、模块、状态枚举 | AI 自动追加 |
| `PROGRESS.md` | "今日进度板"：验证状态、WIP、阻塞项 | 每次会话结束更新 |
| `DECISIONS.md` | "决策档案"：为什么这样设计 | 有新决策时追加 |
| `.codebuddy/rules/*.md` | "分层规则"：不同模块的具体编码约束 | 规范变更时更新 |
| `tech-traps.md` | "踩坑笔记"：已知陷阱与正确做法 | 踩新坑时追加 |

---

## 2. 安装 Skill

### 2.1 前置条件

- 本 Skill **零运行时依赖**：它只生成 Markdown 文件，不需要 Node、Python、JDK 等任何环境。
- 你的项目**应当是一个 Git 仓库**（推荐，便于 Harness 文件的版本管理）。
- 你使用的 Coding Agent 需支持"安装/加载 Skill"或"S kill 目录"机制。

### 2.2 安装方式

**方式一：放到 Agent 的 Skill 目录**

将本 `harness-setup/` 目录整体复制到你的 Agent 的 skills 存放位置。不同平台的典型路径：

| 平台 | Skill 目录 |
|------|-----------|
| CodeBuddy | 项目或全局的 `.codebuddy/skills/` |
| Claude Code | `~/.claude/skills/` 或项目 `.claude/skills/` |
| Cursor | 项目 `.cursor/skills/` 或规则目录 |
| Codex CLI | 项目 `.codex/skills/` |

> 关键点：把本目录放进 Agent 能识别的 **skill 文件夹**下即可，无需修改项目业务代码。

**方式二：让 Agent 自行安装**

若你的 Agent 支持"从仓库/链接安装 Skill"，直接把本 Skill 的仓库地址交给它安装。

### 2.3 验证安装

向 Agent 输入触发词（见第 3 节），若 Agent 开始"扫描项目→检测平台→生成文件"，说明安装成功。

---

## 3. 项目初始化：搭建 Harness 环境

### 3.1 触发搭建

在已安装本 Skill 的项目中，向 Agent 说出以下任一触发词：

- **"搭建 harness"** / **"初始化 harness"** / **"harness 环境搭建"**
- "setup harness" / "给这个项目配 harness"
- "为项目搭建编码 agent 环境"

Skill 会自动进入 **首次搭建模式**。

### 3.2 搭建流程（全自动）

Skill 按以下顺序执行，全程无需人工干预：

| 阶段 | 动作 | 说明 |
|------|------|------|
| Phase 0 模式判定 | 判定首次/增量/退化 | 首次搭建走全量生成 |
| Phase 1 项目扫描 | **只读**分析项目 | 提取项目名、技术栈、构建/测试/启动命令、编码规范、模块结构 |
| Phase 2 平台检测 | 判断 Agent 平台 | 决定入口文件名（AGENTS.md / CLAUDE.md） |
| Phase 3 文件生成 | 套用模板填值 | 按顺序生成入口文件、MEMORY、PROGRESS、DECISIONS、分层规则、辅助文件 |
| Phase 4 验证 | 全新会话测试 | 模拟"新 Agent 只读仓库能否回答 5 个问题" |
| Phase 5 报告 | 输出搭建报告 | 列出生成了哪些文件、行数、验证结果 |

> **关于"依赖配置"**：Skill 不会为你安装项目自身的语言依赖（那是你自己的事，例如 `npm install` / `mvn dependency:resolve`）。它的职责是**扫描并读取**你项目中已有的依赖声明文件（`package.json`、`pom.xml`、`go.mod` 等），提取出正确的 `build` / `test` / `start` 命令并写入 Harness 文件，让 Agent 以后知道怎么构建和验证你的项目。*例外*：空项目（Greenfield）模式下，Skill 会**创建**最小测试框架的 `package.json`/`pyproject.toml` 等依赖声明（仅 dev/test 依赖，无业务代码），把"跑测试"的环境先搭起来。详见 §3.5。

### 3.3 生成的命令从哪来

| 命令类型 | Skill 提取来源 |
|---------|---------------|
| 编译/构建 | `package.json` 的 `scripts.build`、`Makefile`、`pom.xml`、`.gradle` |
| 测试 | `scripts.test`、`pytest.ini`、`go test` 约定、`mvn test` |
| 启动 | `scripts.start`、容器启动脚本、`docker-compose` |
| 代码风格 | `.eslintrc` / `.prettierrc` / `checkstyle.xml` / `pyproject.toml` / `.editorconfig` |

### 3.4 验证搭建结果

搭建完成后，请抽查以下几点确认成功：

1. 根目录出现 `AGENTS.md`（或 `CLAUDE.md`）
2. `.codebuddy/memory/MEMORY.md` 存在且含"启动链"
3. `PROGRESS.md`、`DECISIONS.md` 已生成
4. `.codebuddy/rules/` 下有 `global.md`（及按你项目架构生成的若干规则文件）
5. 打开 `AGENTS.md`，其中的 `build` / `test` / `start` 命令与你本地一致

若一切正常，你可以（但非必须）将这些文件提交到 Git：

```bash
git add AGENTS.md PROGRESS.md DECISIONS.md .codebuddy documents
git commit -m "chore: add agent harness environment"
```

> 注意：Skill 本身**不会**执行 `git commit`，是否提交由你决定。

### 3.5 空项目（从零开始）的特殊流程

如果你的项目是**空的**（没有源码、没有 `package.json`/`pom.xml`/`go.mod`、README 为空或缺失）——也就是"从零开始"，Skill 会自动进入 **Greenfield（空项目引导）模式**，流程与普通搭建不同：

| 阶段 | 空项目模式下的动作 |
|------|------------------|
| 需求澄清 | Agent **主动发起对话**，分轮问你：项目目标、语言/技术栈、模块结构、测试框架、关键状态、编码规范、CI。你回答，Agent 复述确认 |
| 搭建测试框架 | 经你确认技术栈后，Agent 创建**最小测试脚手架**（如 `pyproject.toml` + `pytest` + `tests/test_smoke.py`），让 `pytest`/`jest` 能跑起来 |
| 固化需求 | 澄清结论写入 `DECISIONS.md` / `MEMORY.md`；`AGENTS.md` 的 `test` 命令填为脚手架命令 |
| 衔接常规 | 继续走平台检测 → 生成 harness 文件 → 验证 → 报告 |

> **为什么测试框架要 Skill 搭？** 空项目里 coding agent 连"跑测试"的环境都没有。Greenfield 模式下 Skill 把"水电总闸（测试框架）"一并装好——这是本 Skill 对"不碰依赖文件"边界的**唯一例外**，且**只搭脚手架、不写任何业务代码**。

> **后续持续优化**：开发过程中测试依赖/用例变多时，说"更新 harness"，Skill 会自动把新增命令同步进 `AGENTS.md`；出现原澄清未覆盖的边界，Agent 会增量补问并写入决策/记忆，不必重走全流程。

---

## 4. 日常开发工作流

搭建完成后，你的 Agent 每次新会话都会自动"装载"这套环境。标准开发循环如下。

> **角色澄清（重要）**：
> - 本节描述的「代码编写、调试、构建、测试」动作，**由 coding agent 在你下达自然语言指令后执行**——例如你说"实现并本地验证优惠券接口"，Agent 会调用终端工具运行 `uvicorn` / `pytest`、读取输出、自行修复。
> - **你（用户）在开发流程里的主动职责**（详见 §4.8）：
>   1. **需求澄清**：用自然语言把"要做什么、输入输出、边界"讲清楚；复杂需求先让 Agent 复述确认，避免误解。
>   2. **下达开发指令**：如"实现并本地验证 X 接口"。
>   3. **人工验收与决策**：review Agent 的结果，决定通过/打回；必要时自己照 `AGENTS.md` 的命令手动验收。
>   4. **维护 harness**：项目大变更后跑"更新 harness"。
> - **关于"初步测试命令"**：你**不需要手写**测试命令。Agent 跑测试依赖的是 `AGENTS.md` 里搭建时提取好的 `test` 命令（如 `pytest`）；想做针对性验证，给指令让 Agent 写用例即可。若你亲自验收，直接抄 `AGENTS.md` 的 `Setup & Commands` 里的命令。
> - **harness-setup 这个搭建 Skill 不参与日常开发**，它只负责在初始化时把正确的命令和规则写进仓库，供 Agent 在开发时取用。当然，你也可以随时自己手动跑同样的命令。

### 4.1 上班（每次新会话开始，强制顺序）

Agent 会按以下顺序读取环境文件，**你无需手动操作**，但了解它有助于排查：

1. 读取 `.codebuddy/memory/MEMORY.md`（项目认知 + 上次记忆）
2. 读取 `AGENTS.md`（操作手册 + 硬约束 + 上下文预算）
3. 读取 `PROGRESS.md`（进度、WIP、blocker）
4. 读取 `DECISIONS.md`（已有决策，**不要推翻**）
5. 根据当前任务模块，加载 `.codebuddy/rules/` 下对应规则

### 4.2 代码编写

- **WIP 显式登记**：允许并行推进多个任务，但每个活跃任务必须在 `PROGRESS.md` 的「活跃任务看板」登记一行（任务/阶段/状态/下一步/阻塞）。任务切换前必须写回状态，不允许靠脑子记；建议同时进行的任务 ≤3，过多说明粒度太粗需拆分。
- **按需加载规则**：修改某个模块时，Agent 会自动加载 `rules/` 下 `globs` 命中的规则文件。例如改 `src/api/` 会加载 `api.md` 的规则。
- **遵循 Do Not 硬约束**：`AGENTS.md` 中的"硬约束"是红线，每条都标注了 why/when/when_remove，请遵守。

### 4.3 调试

> 调试由 **Agent** 执行：你给出"启动服务并验证"之类的指令，Agent 调用工具运行命令、读日志、定位问题并修复。你也可以自行手动调试。

- 调试前先读 `tech-traps.md`，确认是否踩中已知陷阱（如空值安全、硬编码路径等）。
- 若遇到新陷阱，调试解决后让 Agent 把经验追加到 `tech-traps.md`（触发条件 + 错误做法 + 正确做法）。
- 跨会话的"为什么这样改"应记录在 `MEMORY.md` 的 Auto Memory 区域，方便下次续上上下文。

### 4.4 构建与测试（清洁状态检查）

**"做完"有硬性定义**。在认为任务完成前，必须让以下 6 项全部通过（来自 `AGENTS.md` 的清洁状态检查表）：

| # | 检查项 | 方式 |
|:--|--------|------|
| 1 | 编译通过 | 运行 `AGENTS.md` 中的 build 命令 |
| 2 | 测试通过（基线一致，已知失败须具名） | 运行 test 命令 |
| 3 | 无 lint 告警 | 各模块 lint 检查 |
| 4 | git status clean 或已登记未提交清单 | `git status`（或已在 PROGRESS 登记） |
| 5 | PROGRESS.md 已更新（看板+未提交清单同步） | 检查更新日期 |
| 6 | **部署后验证闭环** | 已部署并冒烟/E2E，或显式记录未验证原因 + 预计时间 |

> 只要有一项 ❌，任务就不算完成。第 6 项专门杜绝"本地 ✅ 但生产没验证"的早停（详见 §6.2 案例 X）。

### 4.5 下班（每次会话结束前，缺一不可）

1. 更新 `PROGRESS.md`（完成内容、剩余问题、下一步）
2. 若有新决策 → 记录到 `DECISIONS.md`（含回退/可逆方案）
3. 将重要发现写入 `MEMORY.md` 的 Auto Memory 区域（冷记忆外链 tech-traps）
4. 填写 `.codebuddy/harness/session-handoff.md`（**禁止留空占位符**）
5. 检查 `git status`：清洁，或登记到「未提交改动清单」
6. **WIP 显式登记**：把并行任务写回「活跃任务看板」

### 4.6 会话交接

当你中断工作后重新开会话，Agent 会先读 `session-handoff.md` 快速恢复上下文，再走 4.1 的"上班"流程。你只需在重新开工时简单说明"继续上次的任务"即可。

---

## 4.7 完整示例：一次功能开发的全流程

> 场景设定：以**语言无关**为前提，这里用一个 Python FastAPI 商城后端项目 `shop-api` 作示例（你也可以替换为 Java/Go/Node 项目，流程完全一致）。假设 Harness 已搭建好，现在你让 Agent 新增"优惠券校验接口"。

### 步骤 0 — 需求澄清（用户侧，Agent 不动手）

在 Agent 开工前，**你**先用自然语言把需求讲清。例如你给 Agent 的指令可以是：

> "给商城加一个优惠券校验接口：输入优惠码，返回是否有效、折扣类型、折扣值；过期券返回 410；优惠码大小写不敏感。"

Agent 若不确定，会反问澄清（如"折扣类型有哪些枚举？"）。**建议复杂需求先让 Agent 复述一遍需求要点确认无误，再进入开发**，避免做错方向。这一步完全由你提供信息，Agent 只做理解与共情确认，不写代码。

### 步骤 1 — 上班（自动装载环境）

你开启新会话，对 Agent 说："帮我实现优惠券校验接口"。Agent 自动执行：

1. 读 `MEMORY.md` → 得知：这是 FastAPI 商城，`modules: api/ service/ models/`，关键状态 `OrderStatus(PENDING/PAID/...)`。
2. 读 `AGENTS.md` → 得知命令：`build=uv sync`、`test=pytest`、`start=uv run uvicorn shop_api.main:app`。
3. 读 `PROGRESS.md` → 当前无活跃任务、无 blocker。
4. 读 `DECISIONS.md` → 已知 D001（五子系统）、D002（MDC 分层规则），**不推翻已有决定**。
5. 因要改 `src/api/coupon.py` 和 `src/service/coupon_service.py`，自动加载 `rules/api.md`（`globs: **/api/**`）和 `rules/service.md`（`globs: **/service/**`）。

### 步骤 2 — 显式登记 WIP 看板

Agent 在 `PROGRESS.md` 的「活跃任务看板」登记一行：

```
| 1 | 实现优惠券校验接口 | 编码 | 🟡 | 联调验证 | — |
```

允许并行，但每个任务都要登记；切换任务前写回状态与下一步，不靠脑子记。

### 步骤 3 — 编写代码（遵循分层规则）

Agent 按 `api.md` 写路由、按 `service.md` 写业务逻辑。过程中 `tech-traps.md` 提示：

> "空值/空引用陷阱：对可能返回 None 的查询函数要做空值检查。"

Agent 据此在 `coupon_service.validate(code)` 中加了 `if coupon is None: raise CouponNotFound()`，避免 `None.code` 崩溃。

### 步骤 4 — 调试（由 Agent 执行）

> 这里的"调试"由 **coding agent** 完成：你下达指令（如"本地启动并验证接口"），Agent 调用终端运行下面的命令、读取返回结果、若出错则自行定位并修复。它**不是** harness-setup 搭建 Skill 来做——搭建 Skill 只在初始化时把 `uv run uvicorn ...` 这条正确命令写进了 `AGENTS.md`，开发时 Agent 直接拿来用。你也可以自己手动跑同样的命令。

本地启动验证：

```bash
uv run uvicorn shop_api.main:app --reload
curl -X POST localhost:8000/api/coupon/validate -d '{"code":"SAVE10"}'
```

Agent 读取返回结果：200 + 校验结果，说明接口基本可用；若返回 500，Agent 会回到代码定位并修复。

### 步骤 5 — 构建与测试（清洁状态 6 项）

Agent 逐项核对 `AGENTS.md` 的清洁检查表：

| # | 检查项 | 结果 |
|:--|--------|------|
| 1 | `uv sync`（编译/依赖） | ✅ |
| 2 | `pytest` | ❌ 1 个用例失败（边界：过期券未返回 410） |
| 3 | lint（ruff） | ✅ |
| 4 | git status / 未提交清单 | clean |
| 5 | PROGRESS.md 已更新（看板+未提交清单同步） | ⬜ |
| 6 | 部署后验证闭环 | ⬜ 本地过，待联调环境冒烟 |

发现测试失败 → 回到步骤 3 修复"过期券"边界逻辑 → 重跑 `pytest` → ✅ 12/12 通过 → 补更新 PROGRESS。

### 步骤 6 — 下班（固化上下文）

1. 更新 `PROGRESS.md`：完成内容、验证结果（pytest 12/12 通过）、下一步。
2. 无新架构决策，跳过 `DECISIONS.md`。
3. 写 `MEMORY.md` Auto Memory：
   ```
   - 2026-07-24 优惠券码需大写归一化后再查库（用户输入可能小写）
   ```
4. 填 `session-handoff.md`：本轮做了什么、清洁状态、下一步（"前端联调优惠券校验"）。
5. `git status` clean → 你可以决定是否 `git commit`。
6. 把本任务在看板标记完成（或清空该行）。

### 步骤 7 — 下次会话恢复

第二天你开新会话说"继续优惠券联调"。Agent 先读 `session-handoff.md` 快速恢复，再走上班流程，无需你重新解释项目背景。

> 这个示例展示了 Harness 如何把"背景认知、运行命令、编码规范、进度"沉淀进仓库，让 Agent 跨会话连续工作，而你几乎不需要重复解释。

---

## 4.8 用户在开发流程中的职责清单

为方便对照，把"你需要做什么、不需要做什么"列清楚：

| 事项 | 谁来做 | 你需要做的 |
|------|--------|-----------|
| **需求澄清** | 你提供，Agent 理解 | 用自然语言讲清功能、输入输出、边界；复杂需求先让 Agent 复述确认 |
| 写代码 | Agent | 下达"实现 X"指令，无需手写 |
| 调试/定位 | Agent | 下达"启动并验证"指令；必要时你手动 review |
| 跑测试 | Agent | **无需手写测试命令**；想针对性验证就下指令让 Agent 加用例 |
| 人工验收 | 你 | 照 `AGENTS.md` 的 `Setup & Commands` 手动跑，或看 Agent 的验证报告 |
| 决策通过/打回 | 你 | review 结果后决定 |
| 维护 harness | 你触发 | 项目大变更后说"更新 harness" |

**常见疑问**

- **Q：我需要自己准备测试脚本吗？**
  A：不需要。Agent 用 `AGENTS.md` 里搭建时提取的 `test` 命令（如 `pytest`、`mvn test`、`go test`）跑；针对性用例由 Agent 按你的指令生成并执行。

- **Q：需求说不清楚怎么办？**
  A：先给要点，让 Agent 复述确认；Agent 也会在不确定处主动反问（如枚举值、异常分支）。

- **Q：我想自己验收，命令从哪来？**
  A：直接抄 `AGENTS.md` 的 `Setup & Commands` 区块里的 `build` / `test` / `start` 命令。

- **Q：harness-setup 搭建 Skill 会帮我跑测试吗？**
  A：不会。它只在初始化时把正确的 `test` 命令写进 `AGENTS.md`，日常跑测试的是 coding agent（或你自己）。

---

## 5. 自适应维护

项目在演进，Harness 也需跟着变。本 Skill 提供两种维护模式。

### 5.1 增量更新

当项目发生变化（新增模块、升级依赖、新增 lint 配置），向 Agent 说 **"更新 harness"**。Skill 会：

- 对比 `package.json` / `pom.xml` 依赖是否变化 → 更新技术栈描述
- 检查 `src/` 是否新增模块 → 更新模块速查表与分层规则
- 检测新增 lint 配置 → 更新编码规范
- **只更新变动部分**，不重写整个文件

### 5.2 退化检测与修复

当你感觉 Agent "越来越不懂项目"或"频繁违反规范"，说 **"检查 harness 退化"** / **"harness 治理"**。Skill 会扫描并标记以下退化信号：

| 信号 | 诊断 | 操作 |
|------|------|------|
| 入口文件 > 200 行 | 违背渐进式披露 | 拆分详细规范到 `rules/` |
| MEMORY.md > 200 行 | 可能超出上下文预算 | 精简或拆分子文件 |
| 规则文件无 frontmatter | 缺少元数据 | 自动补齐 YAML 头 |
| 入口文件的命令与 `package.json` 不一致 | 已过时 | 用当前值更新 |
| PROGRESS.md 日期 > 7 天未更新 | 进度陈旧 | 标记 ⚠️ 提示 |

---

## 6. 常见问题排查（FAQ）

| # | 问题 | 可能原因 | 解决方案 |
|---|------|---------|---------|
| 白屏/无反应 | Agent 没触发 Skill | Skill 未放入正确目录，或触发词不匹配 | 确认 Skill 在 Agent 的 skills 目录下；换用"搭建 harness"等标准触发词 |
| 1 | 搭建后 `AGENTS.md` 命令是错的 | 项目没有标准脚本，Skill 用了默认值 | 手动编辑 `AGENTS.md` 的 `Setup & Commands` 为正确命令，或说"更新 harness"重扫 |
| 2 | 入口文件名不对（要 `CLAUDE.md` 却生成 `AGENTS.md`） | 平台检测信号缺失 | 确认项目存在 `.claude/` 目录或 `CLAUDE.md`；或手动重命名 |
| 3 | Agent 不读我的分层规则 | `globs` 没匹配到文件路径 | 检查 `rules/*.md` 的 `globs` 是否覆盖目标目录；详见 6.1 |
| 4 | `MEMORY.md` 越写越长 | Auto Memory 未精简 | 超 50 行让 Agent 自行精简；超 200 行触发退化告警 |
| 5 | "更新 harness" 没变化 | 项目结构未变，属正常 | 无实质变化则 Skill 不会重写；可强制"重新搭建 harness" |
| 6 | 误改了业务代码 | 误用本 Skill 做开发 | 本 Skill 边界是"只配环境不写代码"；代码编写请用正常开发指令 |
| 7 | 规则与代码实际不符 | 规范变更后未同步 | 说"更新 harness"或手动改 `rules/` 对应文件 |

### 6.1 规则 globs 不生效的排查

`rules/*.md` 头部有 YAML frontmatter：

```yaml
---
description: API 层规范
globs: **/api/**, **/controller/**
alwaysApply: false
---
```

- `alwaysApply: true` → 每次会话都加载（如 `global.md`）
- `alwaysApply: false` → 仅当编辑的文件路径匹配 `globs` 时才加载
- 若规则不生效，先确认你编辑的文件路径是否落在 `globs` 模式内；必要时放宽或调整模式。

### 6.2 真实踩坑案例集

以下案例来自实际落地经验，每条给出"现象 → 根因 → 解决"。

**案例 1：规则文件"写了却没生效"**
- **现象**：改 `src/controller/OrderController.java` 时，期望的 `api.md` 规则没被加载。
- **根因**：`api.md` 的 globs 写成 `**/controllers/**`（复数），但项目目录是单数 `controller`。
- **解决**：把 globs 改为 `**/controller/**`；或设 `alwaysApply: true` 让该规则始终加载（适合通用性强的约束）。

**案例 2：MEMORY.md 越写越长，Agent 开始"健忘"**
- **现象**：项目跑几周后，Agent 回答质量下降，像忘了早期约定。
- **根因**：Auto Memory 区域无限制追加，文件超过 200 行硬上限，超出部分在上下文窗口被截断丢弃。
- **解决**：区域 > 50 行时让 Agent 自行精简（合并同类、删过时）；> 200 行触发退化告警，把旧条目移入 `documents/` 子文件，MEMORY 仅留索引。

**案例 3：Agent 改了代码却没同步文档（腐败）**
- **现象**："检查 harness 退化"提示入口文件的命令与项目不一致。
- **根因**：你（或 Agent）换了构建工具（如 Maven → Gradle），但 `AGENTS.md` 的 `build` 命令还是旧的 `mvn package`。
- **解决**：说"更新 harness"让 Skill 重扫；或手动把 `AGENTS.md` 的 `Setup & Commands` 改成 `./gradlew build`。

**案例 4：WIP 不登记导致上下文丢失**
- **现象**：Agent 同时在做 A、B、C 多个功能，会话中断后重开，忘了 B 做到哪、C 的下一步是什么，只能从头翻聊天记录。
- **根因**：并行任务但只在脑子里记，没登记到 `PROGRESS.md` 的活跃任务看板，违反 WIP 显式登记。
- **解决**：承认并行现实，但每个任务必须在看板登记一行（阶段/状态/下一步/阻塞）；切换前写回。这样既允许多开，又能跨会话无损恢复（参考 §6.2 案例 W 的真实复盘）。

**案例 5：触发词没认出来，Skill 没启动**
- **现象**：说"配置一下 agent 环境"，Agent 没反应或当成普通对话。
- **根因**：Skill 没放进 Agent 可识别的 skills 目录，或表述偏离标准触发词。
- **解决**：确认 Skill 在 `.codebuddy/skills/`（或对应平台）下；改用"搭建 harness"等标准词。

**案例 6：平台检测错位**
- **现象**：Claude Code 项目里却生成了 `AGENTS.md`。
- **根因**：项目里同时存在 `.codebuddy/` 和 `.claude/`，Skill 优先匹配到 `.codebuddy/`。
- **解决**：删掉不需要的目录信号，或手动把 `AGENTS.md` 重命名为 `CLAUDE.md`。

**案例 7：Auto Memory 把已明确信息反复复制**
- **现象**：MEMORY 里既有模板生成的"项目是 FastAPI 商城"，又有 Auto Memory 追加"项目用 FastAPI"——冗余膨胀。
- **根因**：Agent 未遵守"不要把本文件已明确的信息再重复写入"的管理规则。
- **解决**：清理重复条目；在 Auto Memory 管理规则中强调只追加"新发现/新偏好"。

**案例 8："git status 不干净"却宣布完成**
- **现象**：Agent 说功能完成，但你 `git status` 发现一堆未提交改动，且测试其实没全过。
- **根因**：跳过了清洁状态检查第 4、5 项，过早宣布完成（L09 早停问题）。
- **解决**：强制 Agent 走完 6 项清洁检查再交付；可在 `AGENTS.md` 的 Do Not 加一条"未完成清洁状态 6 项前不得宣布任务完成"。

**案例 9：WIP 显式登记（真实复盘 · ai-platform-server）**
- **背景**：某后端项目单日并行推进 6 项大改动（容器改造、Redis 缓冲、流式方案编码、健康检查诊断、Token 持久化、提交）。纯 WIP=1 根本不现实。
- **做法**：在 `PROGRESS.md` 建「活跃任务看板」表格，T1–T3 各一行（阶段/状态/下一步/阻塞）；切换任务前写回状态。
- **收益**：跨会话无需重读聊天记录即可恢复；审计时一眼看清在跑哪些任务。

**案例 10：清洁状态第 6 项修复"本地 ✅ 但生产未验证"**
- **现象**：功能本地 `mvn test` 全过，Agent 宣布完成，结果部署测试环境后网关 6 分钟掐断长连接，用户侧全失败。
- **根因**：清洁状态只有"编译/测试/lint/git/进度"5 项，缺"部署后验证"闭环，早停在生产前。
- **解决**：清洁状态加第 6 项「部署后/E2E 验证闭环」——已部署冒烟通过，或显式记录未验证原因+预计时间，才允许标 ✅。

**案例 11：测试基线失败"具名化"**
- **现象**：`PROGRESS` 长期写「bff 2 known failure」，无人处理也无从下手。
- **根因**：模糊的"known failure"没有责任人、没有根因，等于技术债合法化。
- **解决**：把失败具名——实测是 `bff ExecutionServiceImplTest` 因 `triggerRun` 签名漂移导致**编译失败**，写明用例名+根因+立 issue+月度回顾日期，从"挂着"变"有 owner"。

**案例 12：三层文档去重（停止重复抄写）**
- **现象**：同一天工作既写进 `.codebuddy/memory/2026-07-27.md`，又原样抄进 `PROGRESS.md` 的会话记录，两份还不一致。
- **根因**：没界定 daily memory / PROGRESS / handoff 的分工，导致重复劳动 + 一致性负担。
- **解决**：明确分工——daily memory 记过程细节与证据链；PROGRESS 只留「三行摘要」（做了什么/验证/下一步）+ 链接日期；handoff 提炼 4 行交接。禁止同段内容两处抄写。

**案例 13：session-handoff 从空占位到真实填写**
- **现象**：交接模板通篇 `<!-- 占位 -->`，下一个会话根本没法恢复，实际靠 PROGRESS + daily memory 兜底。
- **根因**：下班流程把"填 handoff"当可选项，模板又全是占位符，等于没机制。
- **解决**：下班流程强制第 4 步填写 handoff（4 行：做了/验证/未完成/下一步），删除模板占位符改为必填，每个会话结束必须有真实交接内容。

---

## 7. 最佳实践

### 7.1 给使用者

- **搭建后立刻提交一次**：把初始 Harness 文件纳入 Git，作为环境基线。
- **重大项目变更后跑一次"更新 harness"**：新增模块、换框架、加中间件时同步更新。
- **定期"检查 harness 退化"**：建议每 1-2 周或每个大版本后执行。
- **不要手改入口文件超过 200 行**：细节应下沉到 `rules/` 或专题文档（渐进式披露）。
- **尊重 WIP 显式登记**：并行任务必须写进「活跃任务看板」，切换前写回状态；不要只靠脑子记。

### 7.2 给 Harness 文件维护者

- 每条 `Do Not` 硬约束都写清 why/when/when_remove，避免"僵尸约束"。
- `rules/*.md` 单文件 < 80 行，过长就拆。
- `tech-traps.md` 用统一格式（触发条件 + 错误做法 + 根因 + 正确做法 + 检测方法）追加。
- 利用 `MEMORY.md` 的 Auto Memory 区域让 Agent 自主沉淀经验，减少人工维护。

### 7.3 边界红线（务必牢记）

✅ 本 Skill / 本 Harness **做**：创建配置文档、分析结构、提取规范、生成规则、做验证测试。
❌ 本 Skill / 本 Harness **不做**：编写/修改业务代码、改依赖文件、执行 `git commit/push`、运行编译测试（那是 Agent 开发工作，不是"装修"工作）。

> **空项目例外**：仅当项目为空时，本 Skill 可创建最小测试框架脚手架（依赖声明 + 测试目录 + smoke test），但**依旧不写业务代码、不执行 git/测试命令**。

---

## 8. 三种模式速查表

| 模式 | 触发词 | 行为 | 何时用 |
|------|--------|------|--------|
| 首次搭建 | "搭建 harness" | 全量生成所有文件 | 已有项目接入 Harness |
| 空项目引导 | "空项目搭建" / "从零搭建" | 需求澄清 → 搭建测试框架脚手架 → 生成 harness 文件 | **空项目**从零开始 |
| 增量更新 | "更新 harness" | 仅更新与现状不一致的文件 | 项目演进后同步 |
| 退化修复 | "检查 harness 退化" | 扫描标记过时/超标的项 | 感觉 Agent 变笨或规范失效 |

---

> 本指南对应 Skill 版本：v2（语言/框架无关、支持多平台、分层规则 + Auto Memory + 上下文预算）。
> 理论基础：Learn Harness Engineering 13 讲，融合 Claude Code / Codex / Cursor / OpenCode 最佳实践。
