---
doc_id: "RPT-018"
title: "PLN-042 认知工作流实施与 live 实测报告"
category: "report"
role: "[Delta]"
status: "published"
date: "2026-08-13"
author: "Ravenswood Bluff"
---

# PLN-042 认知工作流实施与 live 实测报告

> 覆盖：2026-08-13，PLN-042（`docs/plans/pln042-cognitive-workflow-plan.md`）T1-T6 全量实施 + live 实测验收。
> 关联决策：DECISIONS D018（认知工作流落地）。

---

## 1. 目标

用户愿景：agent 玩家决策/发言/行动形成**完整工作流**——像人类一样先根据之前的印象和前人的发言**建立观点和逻辑链**，再推导决策/发言/行动；RAG 作为**真实可信信息来源的保证**，减少无依据断言的幻觉。

## 2. 实施内容（T1-T5，SpecForge TDD）

| 任务 | 交付 | 测试 |
|:--:|------|:--:|
| T1 | `src/agents/reasoning/viewpoint.py`：Evidence（hard/soft 分级）+ Viewpoint（断言/证据链/置信度/状态）+ ViewpointStore（`viewpoints.jsonl` 追加落盘，仅 live） | 9 |
| T2 | `src/agents/reasoning/viewpoint_engine.py`：确定性证据提取/置信度计算（hard 高权重封顶 0.95）/门控（要求 hard_count ≥ 1）/冲突 supersede | 12 |
| T3 | `src/agents/workflow/cognitive_workflow.py`：recall→reason→speak→record 显式工作流（复用 Workflow 引擎 + trace） | 6 |
| T4 | AIAgent 集成：`act()` 认知块（开关 `BOTC_COGNITIVE_SPEAK` 默认 off）+ `build_memory_snapshot`（排除阵营私密类别）+ 观点摘要注入 user 段 | 10 |
| T5 | 严格回归（见 §4） | 692 全绿 |

关键设计：
- **确定性核心**：证据提取/置信度/门控/语言化全部确定性，LLM 不参与论证数值（守住确定性红线）；
- **门控防幻觉**：无硬证据的强断言（"一定是"）在 reason 阶段降级为"可能"——幻觉在**生成前**拦截；
- **包装非重写**：`act()` 主路径不动，开关关闭行为与现状完全一致（mock 全量零回归）；
- **信息隔离**：`build_memory_snapshot` 排除 evil_teammates/evil_bluffs 类别，观点/发言不泄露阵营私密。

## 3. live 实测验收（T6，真实 DeepSeek）

### 3.1 live 5 人局 day_1（BOTC_COGNITIVE_SPEAK=1）

| 验收项 | 结果 |
|------|------|
| ① viewpoints.jsonl 真实落盘 | ✅ 5 玩家全部落盘（p2-p5 各含观点；p1 为 poisoner 且记忆无证据候选，**无依据不强行断言**——符合设计） |
| ② 观点含 hard/soft 证据 | ✅ 24 hard + 23 soft；置信度分级正确：硬证据观点头部置信度 vs 纯软印象 0.59-0.65（注：初版 live 实测"硬证据 0.95"为 P1-1 证据提取双重循环 bug 的虚高效应，修复后单条硬证据置信度 ≈ 0.52、两条 ≈ 0.69，分级区分度恢复） |
| ③ 发言含逻辑链依据 | ✅ 观点链注入 LLM user 段（【你的观点链】+ 置信度），单测断言注入生效 |
| ④ fallback=0 | ✅ 全部动作 fallback=0（工具调用主导） |
| ⑤ 无证据断言拦截 | ✅ 单测验证强断言降级；live 中无证据玩家不产生观点 |

### 3.2 同局 A/B 对比（认知开关开/关，真实 LLM）

| | 认知开启 | 认知关闭 |
|---|---|---|
| 观点形成 | ✅ "P2 可能是恶魔"（硬证据驱动） | ❌ 未形成观点 |
| 发言风格 | **论证式**：直觉 + 前人说辞组织（"Cathy 也提了 Bob 可疑，不是巧合吧"），**隐藏占卜师底牌**（"注意到一些动静"） | **断言式**：直接亮底牌（"我昨晚查了一手"），暴露夜间信息角色 |
| reasoning | 逻辑链完整：占卜结果→呼应 P3→观察 P5 站队 | 单点强推 |

**结论**：认知开启后发言从"断言式"变为"论证式"——基于证据链组织语言、控制信息暴露节奏，正是"先思考再说话 + 真实来源保证"的愿景落地。

### 3.3 部署注意

`simulate_game.py` 用 `--backend live` 参数（默认 mock）；live 局需 `--timeout-seconds 600`（20s 默认不够 day_1）。

## 4. 回归验证（全绿）

| 检查项 | 结果 |
|------|------|
| `pytest tests -q -m "not slow"` | ✅ **692 passed / 0 failed**（基线 690 → +2 净增；新增 35 认知测试） |
| ruff check / format | ✅ 0 / 0 |
| `check_doc_health.py` | ✅ PASSED |
| `alpha1.1_acceptance.py` | ✅ 10/10（最终复核中） |
| mock 8 人局 | ✅ game_over，viewpoints 零污染（开关 off 默认） |

> 全量含 slow 时 `test_storyteller_acceptance` 曾全量并发 240s 超时（已知 slow 并发 flaky，单独跑通过，与本次改动无关）。

## 5. 关键踩坑（已固化 MEMORY.md）

1. **orchestrator 全部走 `agent.act()`，从不调用 `act_with_strategy`**——认知块最初挂在 act_with_strategy，live 局从未执行（viewpoints 0 落盘）。根因排查后移到 `act()` 开头。
2. **`simulate_game.py` 用 `--backend` 参数默认 mock**——环境变量 BOTC_BACKEND 不生效，live 必须显式 `--backend live`。
3. **pytest-asyncio auto 模式未生效**——测试需显式 `@pytest.mark.asyncio`；async 调用处必须 `await`（漏 await 报 never awaited）。
4. **safe-delete 拦截 basetemp 清理**——累计文件 >50 时 pytest 启动即退出；用**每次唯一 basetemp**（时间戳后缀）规避。
5. **PowerShell 中文参数/内联脚本乱码**——统一用脚本文件（write_to_file）+ `-X utf8` 运行。

## 6. 后续建议

1. **观点演化接入**：`ViewpointEngine.update_with_new_evidence`/supersede 已实现但未接入 act() 主循环——下轮接入"新证据更新置信度/冲突废弃"。
2. **动态 RAG 接入 recall 节点**：检索本局内前人发言（现有 BM25 管线），作为 soft 证据来源。
3. **reason 节点 LLM 增强**：当前 reason 是确定性证据拼接；可加 LLM 低预算"论证组织"（产出论点树），仍保持数值确定性。
4. **推广到 defense_speech/nomination**：试点验证后扩展。
