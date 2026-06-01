# 20260503_A11-VERIFY-029_verification_policy

## 任务

- 任务 ID：A11-VERIFY-029
- 任务名称：建立 Alpha 1.1 验证规范
- 改动范围：`docs/alpha-1.1-plan/verification_policy.md`

## 基线

- 基线版本：无（新建文档）
- 基线命令：N/A
- 基线结果：N/A

## 验证

- 验证日期：2026-05-03
- 验证命令：

```powershell
# 验证文档存在且被链接
Test-Path docs\alpha-1.1-plan\verification_policy.md
```

## 结果

- 通过状态：PASS
- 关键指标：文档存在，定义 L0-L5 证据等级、Done 条件、证据文件规范
- 关键观察：
  - 区分了静态检查(L1)、行为验收(L3)和基准测试(L4)
  - 明确"不能把字段存在当成难度生效"
  - 主计划和 README 均链接到该规范

## 回归保护

- 已覆盖的 Alpha 1.0 流程：N/A（纯文档）
- 未覆盖原因：N/A

## 结论

- 是否满足 Done：是
- 残留风险：无
- 后续任务：A11-VERIFY-035 (发布证据索引)
