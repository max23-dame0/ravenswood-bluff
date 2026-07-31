# 项目入口（AGENTS.md / CLAUDE.md）

> 本文件是 Agent 的**路由器 / 操作手册**，80–200 行。细节外链到 `documents/`。
> 对应 `doc-governance` 治理规则 §8.2。本模板为运行态文件，**不套用** `documents/` 的 Frontmatter 受控词表。

## Setup & Commands

```bash
# 环境准备
# （填写：依赖安装、环境变量、初始化命令）

# 构建
# （填写：build 命令）

# 测试
# （填写：test 命令）

# 启动
# （填写：run / dev 命令）

# 部署
# （填写：deploy 命令）
```

## 会话工作流

1. 读取本文件与 `documents/README.md` 索引
2. 读取 `MEMORY.md` 获取项目认知
3. 登记任务到 `PROGRESS.md`（WIP ≤3）
4. 执行改动，遵循 `documents/` 治理规范
5. 收尾前执行**清洁状态检查**（见下）

## 清洁状态检查（Clean-State Closure）

- [ ] 功能/文档改动已完成并自测通过
- [ ] 关联 `documents/` 已更新（frontmatter + 索引）
- [ ] `PROGRESS.md` 未提交清单已清零（或已 commit）
- [ ] 若涉及部署：**部署后**已验证（E2E / 健康检查 / 关键链路回归）
- [ ] 无残留临时产物

## 分层规则加载

- 通用规范：见 `documents/`（根目录 `documents/README.md` 为检索起点）
- 分层规则：热层常驻（`global`），温层按 `globs` 作用域激活

## 上下文预算

- 本文件 ≤200 行；`MEMORY.md` ≤200 行；细节外链，不内联。

## 硬约束（建议 ≤15，每条标 why / when / when-remove）

1. **约束一** — why: … / when: 始终 / when-remove: …
2. **约束二** — why: … / when: … / when-remove: …

## 专题文档索引

- 文档体系入口：[`documents/README.md`](../documents/README.md)
- 治理规范：`doc-governance` Skill（见 `references/documentation-governance.md` §8）

## 临时产物纪律

- 中间文件统一放 `<临时目录>/`，会话收尾前清理
- 不向仓库提交构建产物、日志、缓存
