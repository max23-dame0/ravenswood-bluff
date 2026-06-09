# 鸦木布拉夫小镇 — 文档目录索引与归属整理

为了方便在不同开发阶段快速检索、维护以及规范文档结构，现将 `docs/` 目录下现存的所有文档归类整理如下。

---

## 1. 开发计划与任务看板 (Development Plans & Sprints)
本类别包含各个开发阶段的总体设计方案与具体实施的子任务看板。

* **[Alpha 1.2 主开发计划](alpha-1.2-plan.md)**: 本阶段（多人联机与局域网部署）的总体方案与验收标准。
* **[Alpha 1.2 任务看板目录](alpha-1.2-plan/README.md)**: Alpha 1.2 阶段的详细任务列表目录。
  * **[M8：多人联机与局域网部署服务](alpha-1.2-plan/task_m8_network_hosting.md)**: 端口绑定、动态 IP 检测、启动脚本与 Docker 部署任务。
* **[Alpha 1.1 主开发计划](alpha-1.1-plan.md)**: 难度预设、博弈噪声以及 AI 速度/发言质量的总体改造方案。
* **[Alpha 1.1 任务看板目录](alpha-1.1-plan/README.md)**: Alpha 1.1 阶段任务细分目录。
  * **[M5：AI 响应速度与流畅体验](alpha-1.1-plan/task_m5_ai_speed_flow.md)**: 响应等待与分层决策优化。
  * **[M5-R：AI 发言质量回归与并行纠偏](alpha-1.1-plan/task_m5r_ai_speech_quality_repair.md)**: 顺序发言与 fallback 策略重构。
  * **[M6：难度系统校准与架构补丁](alpha-1.1-plan/task_m6_difficulty_system_refactor.md)**: 难度五轴模型升级与欺诈一致性。
  * **[M7：验证规范与增量证据](alpha-1.1-plan/task_m7_validation_evidence.md)**: 性能与差异度行为级验收指标。
  * **[验证规范：证明改进真实存在](alpha-1.1-plan/verification_policy.md)**: 增量行为与自动化基线验证的规范定义。
* **[Alpha 1.0 主开发计划](alpha-1.0-plan.md)**: 完成首个测试候选版（规则封板、说书人控制台、真人前端内测流）的主开发计划。
* **[Alpha 1.0 任务看板目录](alpha-1.0-plan/)**: 归档的 1.0 各子任务板（魔典、说书人裁量、AI 情绪等）。
* **[Alpha 0.3 主开发计划](alpha-0.3-plan.md)**: 包含 AI 说书人内心独白、三层记忆架构（RAG）和猎手/圣女规则实现的主计划。
* **[Alpha 0.3 任务看板目录](alpha-0.3-plan/)**: 归档的 0.3 各任务模块。
* **[Alpha 0.2 任务看板目录](alpha-0.2-plan/)**: 归档的早期 0.2 开发路线与看板。

---

## 2. 发布说明与已知限制 (Release Notes & Checklists)
记录各版本正式对外发布前的验收检查单、发布日志及已知的问题清单。

* **[Alpha 1.0 发布清单](alpha-1.0-release-checklist.md)**: 1.0 阶段的上线门禁与上线测试检查单。
* **[Alpha 1.0 已知问题](alpha-1.0-known-issues.md)**: 1.0 阶段遗留的问题、限制以及临时变通方案（Workarounds）。
* **[Alpha 0.3 发布总结](alpha-0.3-release-summary.md)**: 0.3 阶段的交付特性、修复内容和已知局限。
* **[Alpha 0.2 发布总结](alpha-0.2-release-summary.md)**: 0.2 阶段的合并特性与回归校验记录。
* **[Alpha 0.1 发布说明](alpha-0.1-release-notes.md)**: 早期 0.1 版本的流程框架发布说明。

---

## 3. 技术分析、规则与架构文档 (Architecture & System Design)
系统整体设计理念、核心机制、重构规划与游戏规则边界定义。

* **[规则判定矩阵 (Rule Matrix)](rule_matrix.md)**: 记录 Troubling Brewing 剧本中高风险角色（如酒鬼、中毒、隐士、间谍等）的行为期望与裁断逻辑。
* **[测试套件与工程分析 (Harness Engineering)](harness-engineering-analysis.md)**: 全量测试套件的高阶设计分析，涵盖时序、Mock 环境及通信断言。
* **[项目瘦身计划 (Slimming Plan)](project-slimming-plan.md)**: 项目代码规模瘦身、上帝对象拆解以及重构规划指南。

---

## 4. 测试与质量验收报告 (Verification & Test Reports)
自动化门禁运行结果报告、数据证据文件与接口通信契约验证。

* **[Alpha 1.1 验收证据目录 (alpha-1.1-evidence/)](alpha-1.1-evidence/)**: 存放自动化验收脚本生成的真实日志、性能指标和证据摘要。
* **[前端接口契约验证报告](frontend_acceptance.md)**: 前后端 WebSocket 连接、事件模型及 HTTP 契约通信验收记录。
* **[系统验证报告](validation_report.md)**: 自动化测试套件在特定里程碑的综合通过报告。

---

## 5. 交接与历史遗留 Backlog (Handovers & Remediations)
跨开发周期、跨大语言模型或不同 AI 助手接力开发时的交接文档和待解决历史债务。

* **[Gemini 接手整治 Backlog (2026-04-18)](GEMINI_REMEDIATION_BACKLOG.md)**: 早期对于代码质量、并发错误与规则缺陷的全面修复清单。
* **[Remediation Backlog 摘要](remediation_backlog.md)**: 精简版的待整改缺陷清单。
* **[Gemini 接手评审报告](GEMINI_HANDOFF_REVIEW_2026-04-18.md)**: 评估现有引擎主循环、记忆系统与前后端通信的交接报告。
* **[Claude 接手工作交接 (CLAUDE_HANDOFF)](CLAUDE_HANDOFF.md)**: 记录从上一阶段团队向新开发助手的技术上下文交接。
* **[Alpha 0.2 工作交接报告](HANDOVER_ALPHA_0.2.md)**: 早期 0.2 阶段版本的开发与部署交接指南。

---

## 6. 对局资产与数据操作规范 (Data Management & Testing Samples)
对局产生的中间数据（Traces、Logs）的读写、清理规范，以及基准测试的行为样本。

* **[Alpha 1.0 数据操作指南](alpha-1.0-data-operations.md)**: 针对大体积对局日志、Trace 资产的持久化、清理与故障排查包导出指南。
* **[Alpha 1.0 AI 行为样本](alpha-1.0-ai-behavior-sample.md)**: 各种难度及性格参数下，AI 产生的高真实感公开发言样本对照。
* **[Alpha 1.0 基准测试结果](alpha-1.0-benchmark-results.md)**: 早期 1.0 后端并发与性能压测基准数据。
* **[用户反馈模板](alpha-1.0-feedback-template.md)**: 测试玩家在体验对局后反馈问题的统一问卷/文档结构。

---

## 7. 对局复盘与日志分析 (Game Session Analysis)
真实或高延迟模拟对局的追溯记录与博弈逻辑演进分析。

* **[对局分析目录 (game-analysis/)](game-analysis/)**: 存放典型完整对局的深度分析报告，用于定位 AI 博弈合理性与说书人裁量质量。
  * **[2026-05-07 8人Live对局分析](game-analysis/2026-05-07_efa662a3_8player_live.md)**: 记录在真实延迟或兼容模型下，各轮次 AI 行为、超时 fallback 与 Token 消耗表现。

---

## 8. 部署与联机指引 (Deployment & Multiplayer Guides)
提供本地、局域网及云端服务器部署和联机游玩的详细配置指引。

* **[局域网联机配置指南](lan_play_guide.md)**: Windows 端口开放、局域网 IP 分享与玩家连接步骤说明。
* **[云端服务器部署指南](cloud_deployment_guide.md)**: 容器云平台（如 Railway）及云服务器 Docker Compose 的部署教程。
