# Alpha 1.0 内测反馈模板

请每个问题单独提交一份反馈。最重要的是保留 `game_id`，这样开发者可以导出同局历史、AI traces、说书人裁量和日志片段。

## 基本信息

- `game_id`：
- 发生时间：
- 反馈人：
- 版本或 commit：
- 模式：mock / live
- 玩家配置：AI 局 / 真人局 / 真人+AI 混合局
- 说书人模式：AI 自动 / 真人说书人 / 真人托管
- 浏览器与窗口尺寸：

## 问题摘要

- 一句话描述：
- 影响范围：卡局 / 规则错误 / UI 不可操作 / 信息泄露 / AI 行为异常 / 性能慢 / 数据导出问题 / 其他
- 严重程度：P0 阻断 / P1 影响内测 / P2 可接受遗留

## 复现步骤

1. 
2. 
3. 

## 预期行为


## 实际行为


## 定位资产

- 问题包导出命令：

```powershell
.\.venv\Scripts\python.exe scripts\export_all_assets.py <game_id> --output data\exports --log-path storyteller_run.log
```

- 导出包路径：
- 截图或录屏路径：
- 相关日志片段：

## 临时规避

- 是否可继续游戏：
- 当前规避方式：

## 备注

