# Harness Setup

**即插即用的 Coding Agent Harness 环境搭建 Skill**。专供 coding agent 安装与调用，让 coding agent 免去繁琐的环境配置步骤。

## 定位

本 Skill 是一个 **meta-skill**——它不写业务代码，只负责为目标项目搭建 Agent 工作环境。一句"搭建 harness"，全自动完成。

**严格边界**：
- ✅ 创建/更新 Markdown 配置文件（AGENTS.md、PROGRESS.md、MEMORY.md 等）
- ✅ 分析项目结构并生成分层规则
- ❌ 不编写、修改、删除任何业务代码
- ❌ 不修改项目依赖配置

## 支持平台

- CodeBuddy（AGENTS.md）
- Claude Code（CLAUDE.md）
- Cursor（AGENTS.md）
- OpenAI Codex CLI（AGENTS.md）
- 以上平台的规则文件格式互通

## 一次搭建，生成什么

```
目标项目/
├── AGENTS.md (或 CLAUDE.md)        # 入口文件 — Agent 着陆页
├── PROGRESS.md                      # 项目进度 — 当前状态（含活跃任务看板 / 未提交改动清单）
├── DECISIONS.md                     # 架构决策 — 不推翻已有决定
├── .codebuddy/
│   ├── memory/
│   │   └── MEMORY.md               # 长期记忆 + Auto Memory
│   ├── rules/                       # 分层规则（MDC 格式，按项目架构自适应生成）
│   │   ├── global.md               #   alwaysApply: true
│   │   └── {layer}.md              #   按检测到的分层自动创建
│   └── harness/
│       ├── session-handoff.md      # 会话交接模板
│       └── context-budget.md       # 上下文预算配置
└── documents/
    └── 05-reference/
        └── tech-traps.md           # 技术陷阱冷记忆
```

## 使用方式

1. 将本 Skill 放到目标项目 agent 的 skill 目录，或让 agent 安装此 skill
2. 向 Agent 说：**"搭建 harness"**
3. Skill 自动完成：扫描项目 → 检测平台 → 生成所有文件 → 验证

## 三种模式

| 模式 | 命令 | 说明 |
|------|------|------|
| 首次搭建 | "搭建 harness" | 全量生成所有文件 |
| 增量更新 | "更新 harness" | 仅更新与项目现状不一致的文件 |
| 退化修复 | "检查 harness 退化" | 扫描已有文件，标记过时项 |

## 核心工作约定（Agent 工作契约）

Skill 生成的 harness 默认贯彻以下契约（详情见 `USER-GUIDE.md`）：

- **WIP 显式登记**：允许多任务并行，但每个活跃任务必须在 `PROGRESS.md` 的「活跃任务看板」登记一行（任务/阶段/状态/下一步/阻塞），切换前写回状态，不靠脑子记。
- **清洁状态 6 项**：编译 / 测试（基线一致、已知失败具名）/ lint / git（clean 或已登记未提交清单）/ `PROGRESS.md` 已更新 / **部署后验证闭环**（本地 ✅ ≠ 生产 ✅，未验证须显式记录原因）。
- **三层文档分工**：`.codebuddy/memory/YYYY-MM-DD.md`（过程细节）/ `PROGRESS.md`（三行摘要）/ `session-handoff.md`（4 行交接）——禁止重复抄写。
- **决策含回退方案**：`DECISIONS.md` 每条决策须写明可逆/回退路径（如保留旧链路做 fallback），避免不可逆改动。
- **MEMORY 冷热分层**：热认知留在 `MEMORY.md`，坑点/旧约束等冷记忆外链 `documents/05-reference/tech-traps.md`。

> 以上约定源自多个真实项目的复盘（见 `USER-GUIDE.md` §6.2 案例 9–13），目标是让 harness 的"体系与执行"保持一致，而非只写给人看。

## 触发词

- 搭建 harness / 初始化 harness / harness 环境搭建
- setup harness / 重新搭建 harness
- harness 治理 / agent 工作环境
- 检查 harness 退化 / 更新 harness

## 理论基础

基于 [Learn Harness Engineering 13 讲](https://walkinglabs.github.io/learn-harness-engineering/zh/)，融合 Claude Code、Codex、Cursor 等行业最佳实践。
