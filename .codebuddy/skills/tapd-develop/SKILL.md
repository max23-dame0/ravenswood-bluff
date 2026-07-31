---
name: tapd-develop
description: Use when the developer needs to write technical design documents, decompose requirements into TAPD subtasks, upload tech design to story comments, or manage technical solutions linked to TAPD stories. Triggers include "写技术方案", "拆解任务", "创建子任务", "上传技术方案", "技术设计", "方案评审", or similar intent related to technical design and task decomposition with TAPD.
---

# TAPD Dev Flow — 研发侧技术方案拆解

通过 MCP（`mcp-server-tapd`）将技术方案拆解为 TAPD 子任务，并上传完整方案到需求评论区。本地文档与 TAPD 以 front-matter 双向关联。

## 🔴 核心原则：Front-Matter 与正文分离

**YAML front-matter（`---` 之间的元数据）是本地管理信息，绝不允许推送到 TAPD。**

- `tapd_story_id`、`tapd_story_url`、`tasks`、`status`、`updated_at` 等字段仅在本地 front-matter 中维护
- 推送到 TAPD 任务 `description` 或评论 `content` 时，必须剥离 front-matter
- 无论是直接传字符串还是通过 `description_file`，都必须先剥离 front-matter

### 剥离方式

**方式一（推荐）：传内容时手工剥离**

读取 `.md` 文件，定位第二个 `---`，取其后的正文作为内容传入。

**方式二：传 `description_file` 时使用临时文件**

当内容过大需要 `description_file` 时，**不可直接传入源文件**。必须：
1. 读取源文件，剥离 front-matter，得到纯正文
2. 将纯正文写入临时文件（如 `/tmp/tapd_task_<task_id>.md`）
3. 将临时文件路径作为 `description_file` 传入
4. 调用完成后删除临时文件

---

## 场景一：新建技术方案 → 拆解任务 → 上传

### 步骤 1：获取关联需求

- 调 `get_stories_or_tasks` 获取需求详情，确认需求存在
- 从本地需求文档 front-matter 或用户输入获取 `workspace_id` 和 `story_id`

### 步骤 2：编写技术方案文档

使用下方模板，保存为 `.md` 文件，核心包含：
- **整体方案**：架构思路、技术选型、模块划分
- **接口设计**：每个 API 的路由、入参、出参、数据模型
- **数据库变更**：新增/修改的表、字段、索引、迁移脚本
- **任务拆解**：每个任务的详细研发方案（技术方案、文件路径、接口设计、依赖、估时、验收）

### 步骤 3：逐任务创建 TAPD 子任务

对每个任务，调 `create_story_or_task`：

```
workspace_id: <项目ID>
name: "<任务标题>"
options:
  entity_type: "tasks"
  parent_id: "<story_id>"       # 🔴 必填：关联到父需求
  story_id: "<story_id>"        # 🔴 必填：关联到需求（与 parent_id 相同）
  priority_label: "High|Medium|Low"
  description: "<任务描述>"       # 🔴 必须剥离 front-matter
```

> **🔴 关键：`story_id` 和 `parent_id` 必须同时传入**，缺一不可。仅传 `parent_id` 不会自动关联需求，任务会在 TAPD 中显示为"未关联需求"。

每个任务的 `description` 必须包含以下信息（剥离 front-matter 后传入）：

```markdown
## 技术方案
<该任务的具体实现思路、关键算法、设计模式>

## 涉及文件/模块
<代码文件路径>

## 接口设计
<API 入参/出参/数据模型定义>

## 依赖关系
<前置任务ID、外部服务依赖>

## 估时
<X 小时>

## 验收标准
- [ ] <可验证的完成条件>
```

### 步骤 4：回写任务链接到本地 front-matter（原子操作）🔴

> **CRITICAL：创建任务和回写 front-matter 必须在同一批 tool call 中完成！**

每创建一个任务后，立即用 `replace_in_file` 更新本地文档 front-matter 中的 `tasks` 列表：

```yaml
tasks:
  - id: "<task_id>"
    url: "https://www.tapd.cn/<workspace_id>/prong/tasks/view/<task_id>"
    title: "<任务标题>"
```

### 步骤 5：上传完整技术方案到需求评论区

调 `create_comments`：

```
entry_type: "stories"
entry_id: <story_id>
description: |
  ## 技术方案: <方案标题>
  <完整技术方案正文，剥离 front-matter 后传入>
```

> **为什么传到评论区？** Review 阶段需要获取技术方案作为对照依据。

### 步骤 6：输出确认

```
✅ 技术方案已拆解并同步到 TAPD

| 项目 | 内容 |
|------|------|
| 关联需求 | #1001234 - 需求标题 |
| 创建任务数 | N 个 |
| 任务1 | #xxx - 标题 (Xh) |
| 任务2 | #xxx - 标题 (Xh) |
| 方案评论 | 已上传到需求 #1001234 评论区 |
| 本地文档 | docs/tech-design/xxx.md |
```

---

## 场景二：更新已有技术方案

1. 读本地 front-matter 提取 `tapd_story_id` 和 `tasks` 列表
2. 若无 tapd_story_id，从对话记录查找并回写
3. 批量调 `update_story_or_task` 更新每个子任务的 description（剥离 front-matter）
4. 调 `create_comments`（新增评论）更新方案评论（剥离 front-matter）
5. `replace_in_file` 更新 front-matter 中的 `updated_at`
6. `read_file` 验证 → 输出确认

---

## 技术方案文档模板

```markdown
---
tapd_story_id: ""
tapd_story_url: ""
tasks:
  - id: ""
    url: ""
    title: ""
status: draft
updated_at: ""
---

# [技术方案标题]

## 整体方案
<!-- 架构思路、技术选型、模块划分、关键流程图 -->

## 接口设计

### API 1: [接口名称]
- **方法**: POST /api/xxx
- **入参**:
  ```json
  { "field1": "string", "field2": 123 }
  ```
- **出参**:
  ```json
  { "code": 0, "data": {} }
  ```
- **说明**: ...

## 数据库变更

### 新增表: xxx
```sql
CREATE TABLE xxx (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ...
);
```

### 修改表: yyy
```sql
ALTER TABLE yyy ADD COLUMN zzz VARCHAR(64);
```

## 任务拆解

### 任务1：[任务名称]
- **技术方案**: 具体实现思路、关键算法、设计模式
- **涉及文件/模块**: src/api/xxx.go, src/model/xxx.go
- **接口设计**: POST /api/xxx { ... }
- **依赖**: 无 / 前置任务: 任务0
- **估时**: 2h
- **验收标准**:
    - [ ] 接口参数校验正确
    - [ ] 异常情况有对应错误码
    - [ ] 单元测试覆盖核心逻辑

### 任务2：[任务名称]
- ...

## 风险 & 注意事项
<!-- 潜在的技术风险、兼容性问题、性能瓶颈 -->
```

---

## 任务 Description 规范

每个 TAPD 子任务的 description 将作为 AI Review 的核心输入之一，必须包含：

| 字段 | 必填 | 说明 |
|------|------|------|
| 技术方案 | ✅ | 具体实现思路、关键算法、设计模式 |
| 涉及文件/模块 | ✅ | 代码文件路径（Review 阶段对照 diff 验证） |
| 接口设计 | ✅ | API 路由、入参、出参、数据模型 |
| 依赖关系 | ✅ | 前置任务 ID、外部服务依赖 |
| 估时 | ✅ | 预计工时（小时） |
| 验收标准 | ✅ | 可验证的完成条件 |

---

## 规则

1. 本地文档必须补充 `tapd_story_id` 和 `tasks` 列表
2. `tapd_story_id` 和 `tasks` 不可删除或随意修改
3. **🔴 推送到 TAPD 的所有内容必须剥离 YAML front-matter**
4. **🔴 创建子任务时必须同时传入 `story_id` 和 `parent_id`**，缺一不可，否则任务不会关联到需求
5. 每个任务的 description 必须详尽 —— 这是 AI Review "实现准确度"维度的对照基准
6. 接口设计要写清楚入参出参，AI 会对比代码实现与方案描述是否一致
7. 涉及文件路径要准确，方便 Review 阶段定位代码
8. 技术方案必须传到需求评论区，不可漏掉这一步
9. 任务拆解粒度建议 2-8 小时一个任务
10. 方案更新时，同步更新 TAPD 任务描述和评论区方案
11. MCP 调用失败时提示用户检查 Token 和网络

---

## 完成检查清单

创建或更新技术方案后确认：

- [ ] 获得关联需求 story_id
- [ ] 所有子任务已创建，且同时传入了 `story_id` 和 `parent_id`
- [ ] 用 `get_stories_or_tasks` 验证所有子任务的 `story_id` 不为 `"0"`（确认已关联需求）
- [ ] 所有子任务已回写 task_id 到本地 front-matter
- [ ] 完整技术方案已上传到需求评论区
- [ ] 用 `read_file` 验证 front-matter 回写生效
- [ ] 确认推送到 TAPD 的任务描述和评论不包含 front-matter 元数据
