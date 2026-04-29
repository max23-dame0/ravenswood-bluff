# Alpha 1.0 内测候选版本说明

当前版本口径：`alpha1.0-candidate`。

Alpha 1.0 是《鸦木布拉夫小镇》的首个正式内测候选版本。这个版本的重点是把已有能力收束成可组织小范围内测的包：规则主链可验收，真人玩家可以进入浏览器流程，AI 玩家不会阻塞主线，说书人裁量可追踪，问题可以按 `game_id` 导出定位资产。

## 面向内测者的变化

- 可以通过本地 API server 进入玩家 UI 和说书人 UI。
- 支持 mock 模式快速演示，也支持 live 模式调用兼容 OpenAI 接口的模型服务。
- 对局结束后可以查看结算、历史和复盘信息。
- 玩家视角和说书人视角已分离：玩家端不展示完整魔典和幕后裁量；说书人端保留完整诊断信息。
- 反馈问题时，请优先提供 `game_id`，并按 `docs/alpha-1.0-feedback-template.md` 填写。

## 面向开发者的变化

- `scripts/alpha1_acceptance.py` 作为发布前聚合门禁，默认运行本地可重复检查；full pytest 和 live smoke 需要显式开关。
- `scripts/export_all_assets.py` 可生成单局问题定位包，包含历史、AI traces、说书人裁量、metrics 摘要和日志尾片段。
- `docs/alpha-1.0-release-checklist.md` 是打 `alpha1.0` 标签前的主 checklist。
- `docs/alpha-1.0-known-issues.md` 记录允许带出的遗留风险。
- `docs/alpha-1.0-data-operations.md` 说明数据目录、可清理生成物和保留策略。

## 保守说明

Alpha 1.0 仍是内测候选，不承诺生产级稳定或完整覆盖所有《血染钟楼》变体。首轮内测建议使用小范围、短时长、明确记录 `game_id` 的方式推进。

发布前必须确认：

- README、CHANGELOG、VERSION_NOTES、known issues 和 release checklist 口径一致。
- Alpha1 聚合门禁通过或明确记录跳过项。
- 至少一局 mock 或 live 候选局能按 `game_id` 导出问题包。
- 浏览器级真人/半真人 smoke 已在 checklist 中记录。
