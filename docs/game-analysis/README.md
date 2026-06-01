# 对局分析目录

本目录存放真实对局的详细分析报告，用于复盘 AI 行为、性能瓶颈和优化方向。

## 报告列表

| 日期 | 文件 | 对局 | 玩家数 | 胜方 | 关键发现 |
|------|------|------|--------|------|---------|
| 2026-05-07 | [efa662a3_8player_live](2026-05-07_efa662a3_8player_live.md) | 8人Live局 | 8 | evil | 间谍伪装调查员操控全场; Token 91万; Speak P50=13.8s; Vote 100% fallback |

## 分析维度

每份报告涵盖以下维度:

1. **对局概览**: 角色配置、时间线、胜负原因
2. **Token 消耗**: 总量、按行动/玩家/回合分布、成本估算
3. **延迟分布**: P50/P90/P95/P99、按行动类型、超时情况
4. **Fallback 分析**: 比率、原因、影响
5. **AI 思维链**: 高质量推理示例、行为模式、关键博弈节点
6. **问题总结**: 性能问题、AI 质量问题
7. **优化计划**: Token/延迟/质量/架构四个维度

## 如何使用

- 对比不同对局的报告，观察优化效果
- 从思维链分析中提取 AI 行为模式，改进 prompt 设计
- 根据延迟和 token 数据调整超时和预算参数
- 从博弈复盘中发现 AI 策略盲区

## 如何生成新报告

```powershell
# 1. 找到目标对局的 session 文件
ls data/sessions/ | Sort-Object LastWriteTime -Descending | Select-Object -First 10

# 2. 用 Python 分析
.\.venv\Scripts\python.exe -c "
import json
with open('data/sessions/<game_id>_<timestamp>.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()
# ... 分析逻辑 ...
"

# 3. 或使用现有脚本
.\.venv\Scripts\python.exe scripts\parse_exact_metrics.py
.\.venv\Scripts\python.exe scripts\export_all_assets.py <game_id>
```
