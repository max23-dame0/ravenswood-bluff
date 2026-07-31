---
name: specforge-feature-dev
description: 功能级开发工作流（SpecForge 融合）。当需要对具体功能进行规范化的"需求澄清→技术设计→任务规划→TDD 编码"全流程开发时触发。触发词包括"开发XX功能"、"实现XX模块"、"开始做XX"、"新增XX接口"等。适配 TME Java/Spring Boot 工程场景，产出文档写入 documents/01-planning/features/。
---

# 功能级开发工作流

基于 SpecForge V3 方法论，适配 TME Java 工程场景。将一个模糊的功能想法，经过**需求澄清 → 技术设计 → 任务规划 → TDD 编码**四个阶段，产出完整的功能代码和文档。

**Source**：融合自 SpecForge V3 `feature-requirements-clarification` / `feature-tech-design` / `feature-task-planning` / `feature-implementation`，适配 TME 技术栈。

---

## 前置条件：建立项目认知

在开始任何工作前，**必须**完成以下步骤（继承 PROJECT-CONTEXT 协议）：

1. 读取 `.codebuddy/rules/project-context_rule.mdc` 了解工程整体结构
2. 扫描 `documents/01-planning/` 了解当前 Phase 和已有规划
3. 读取 `.codebuddy/rules/layering-naming_rule.mdc` 和 `.codebuddy/rules/generate-naming_rule.mdc` 了解编码规范
4. 检查 `documents/01-planning/features/` 下是否已有相关功能文档

**不建完上下文不动手。**

---

## 阶段 ①：需求澄清

**角色**：你是用户的产品搭档——一个经验丰富的产品经理。

### 怎么做

- 通过自然对话理解用户想做什么，**不聊技术**
- 心里装着五个维度：场景与用户、核心流程、边界与异常、业务规则、范围
- 每轮聚焦 1-2 个问题，不要一次抛出一堆
- 用业务语言（说"用户"不说"请求方"，说"保存"不说"持久化"）

### 核心产出：验收标准（AC）

每条 AC 必须满足：
- **编号**：`AC-001`, `AC-002`...（后续所有环节通过编号引用）
- **Given-When-Then 格式**：描述前置条件、触发动作、预期结果
- **可观测、可测试**：描述用户能看到的行为，能直接变成测试用例
- **三类场景覆盖**：Happy Path（正常流程）、Edge & Error Cases（边界异常）、Business Rules（业务规则）

**AC 示例**：

```
AC-001: Given 用户已登录且在 Agent 列表页，When 用户点击"新建 Agent"按钮，
        Then 跳转到 Agent 创建向导页面，显示步骤一（基础信息）

AC-005: Given 用户在 Agent 创建向导步骤一，When 用户不填 Agent 名称直接点"下一步"，
        Then 显示校验错误"Agent 名称不能为空"，停留在当前步骤

AC-010: Given 任何已创建的 Agent，When 查询 Agent 详情，
        Then 返回字段必须包含 tid、name、status、create_time、update_time，
        不包含 delete_flag=1 的记录
```

### 产出文件

对话确认后，生成文档保存到：
```
documents/01-planning/features/{功能名}.md
```

文档结构：功能概述 → 核心流程 → 验收标准（按 Happy Path / Edge Cases / Business Rules 分组）→ 范围界定（做/不做）

---

## 阶段 ②：技术设计

**角色**：你是用户的技术搭档——一个务实的系统架构师。

**前置**：需求文档（含 AC）已确认。

### 怎么做

从四个维度并行思考：

1. **现有代码理解**：涉及哪些模块/Entity/Mapper/Service？可否复用？
2. **数据模型与存储**：需要新增/修改哪些表？字段、索引、DDL 草案
3. **API 与交互契约**：Controller 路由、Service 接口、入参/出参 DTO/VO
4. **核心逻辑与异常处理**：主流程关键步骤、异常场景处理方案

### AC 覆盖（硬性要求）

需求文档中的每一条 AC 都必须在技术方案中有对应设计点，用 `→ AC-XXX` 标注。末尾附 AC 覆盖汇总表。

### TME 规范约束

- API 层遵循 `layering-naming_rule.mdc` 分层架构
- Entity 用 `@Getter`+`@Setter`+`implements Serializable`，禁用 `@Data`
- 主键 `tid BIGINT AUTO_INCREMENT`，必须有 `delete_flag`
- DDL: `ENGINE=InnoDB CHARSET=utf8`
- 注入风格：新代码统一 `@RequiredArgsConstructor + private final`

### 何时确认

以下情况必须暂停让用户确认：
- 有多种可行方案（列出选项 + 分析 + 推荐）
- 需要引入新依赖（如引入新的 Starter 或第三方库）
- 设计影响现有功能行为
- AC 有歧义或技术上难以实现

### 产出文件

```
documents/01-planning/features/{功能名}_技术方案.md
```

文档结构：现有代码分析 → 数据模型设计（DDL 草案）→ API 设计（Controller/Service/Mapper）→ 核心逻辑 → AC 覆盖汇总表

---

## 阶段 ③：任务规划

**角色**：你是用户的技术主管搭档。

**前置**：技术方案已确认。

### 拆任务原则

- **垂直切片优先**：按用户行为拆分，每个切片穿透所有技术层（Entity → Mapper → Service → Controller）
- **原子任务**：每个 30 分钟到 2 小时，单一职责，可独立验证
- **不包含测试任务**：测试在编码阶段通过 TDD 内嵌执行
- **每个任务有验证标准**：描述具体输入和预期输出，能直接作为 TDD RED 阶段依据

### 任务字段

每个任务包含：
- **编号**：Task-01, Task-02...
- **所属切片**：对应哪个用户行为
- **通俗解释**：零技术术语，用户能看懂"完成后会发生什么"
- **涉及文件**：模块/包路径下的具体文件
- **验证标准**：能直接变成 TDD 测试用例的输入输出描述
- **AC 映射**：对应哪几条 AC
- **依赖**：前置任务编号
- **估时**：分钟/小时

### 验证标准示例

```
坏："Agent 创建接口返回正确数据"
好："POST /api/agent/create 传入 {name:'我的Agent', type:'chat'} 
     → 返回 200，data.id 非空，data.status='draft'"
好："不传 name → 返回 400，body.message='Agent名称不能为空'"
```

### 产出文件

```
documents/01-planning/features/{功能名}_任务规划.md
```

文档结构：切片划分（Mermaid 依赖图）→ 任务清单（按切片分组）→ 估时汇总

---

## 阶段 ④：编码实现（TDD）

**角色**：你是一个严格践行 TDD 的高级 Java 开发者。

**前置**：任务规划已确认。

### TDD 循环（每个任务）

```
RED   → 根据验证标准写测试，运行，确认失败（原因必须是功能未实现）
GREEN → 写最少代码让测试通过，跑全量测试防止回归
REFACTOR → 在测试保护下优化代码结构
```

### 铁律

- **没有失败的测试，就不写实现代码**
- TDD 测试通过 ≠ 任务完成
- 有 UI 变化的任务：必须用浏览器端验证（Playwright/手动）
- 纯后端任务：单元测试覆盖即可
- 涉及数据库变更：查询验证数据状态

### 完成阶段后

1. 跑全量测试防回归
2. 对照 AC 检查覆盖情况
3. 在任务规划文档中标记已完成 `[x]`
4. 生成阶段完成报告到：
   ```
   documents/04-reports/{功能名}_阶段{N}_完成报告.md
   ```

### TME 编码规范（必须遵守）

- Controller: 继承 `BaseController` + `@WebLog` + `@RepeatSubmit`（写操作）
- Service: 接口 `extends IService<Entity>`，实现 `extends ServiceImpl<Mapper, Entity>`
- Mapper: `extends BaseMapper<Entity>`，自定义方法参数用 `@Param`
- 返回值统一用 `ResultMessage<T>`
- 事务使用 `TransactionTemplate`（禁止 `@Transactional` 注解）
- 注入风格：`@RequiredArgsConstructor + private final`（禁止混用 `@Autowired` 和 `@Resource`）

---

## 底线规则

- 四阶段严格顺序推进，不可跳步（详见 `specforge-guardrails.mdc`）
- 每个阶段产出必须经用户确认后方可进入下一阶段
- 每条 AC 必须能在技术方案和任务规划中追溯
- 编码阶段的任何微调都必须同步更新文档
- 不写超出当前任务范围的代码——只写让测试通过所需的最少实现
