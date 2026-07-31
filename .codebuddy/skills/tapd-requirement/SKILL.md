---
name: tapd-requirement
description: Use when the user wants to write structured requirement documents, create/sync requirements to TAPD, update existing TAPD requirements, split acceptance criteria, or manage product requirements. Triggers include "写需求", "创建需求", "同步到TAPD", "发到TAPD", "更新需求", "拆分验收标准", "补充验收条件", or similar intent related to requirement management with TAPD.
---

# TAPD Requirement — 产品侧需求管理

通过 MCP（`mcp-server-tapd`）创建/同步需求。本地文档与 TAPD 以 front-matter 中的 `tapd_story_id` 双向关联。

## 🔴 核心原则：Front-Matter 与正文分离

**YAML front-matter（`---` 之间的元数据）是本地管理信息，不允许推送到 TAPD。**

- `tapd_story_id`、`tapd_url`、`status`、`priority`、`iteration`、`updated_at` 等字段仅在本地 front-matter 中维护
- 推送到 TAPD 的 `description` 内容必须是 front-matter **之后**的正文部分
- 无论是直接传 `description` 字符串还是通过 `description_file` 文件，都必须先剥离 front-matter

### 剥离方式

**方式一（推荐）：传 `description` 时手工剥离**

读取 `.md` 文件，定位第二个 `---`，取其后的正文作为 `description` 传入。

**方式二：传 `description_file` 时使用临时文件**

当内容过大需要 `description_file` 时，**不可直接传入源文件**。必须：
1. 读取源文件，剥离 front-matter，得到纯正文
2. 将纯正文写入临时文件（如 `/tmp/tapd_desc_<story_id>.md`）
3. 将临时文件路径作为 `description_file` 传入
4. 调用完成后删除临时文件

## 场景一：创建新需求

1. **编写需求文档** 使用下方模板，保存为 `.md` 文件

2. **确定项目空间** 调 `get_user_participant_projects` 选项目，得到 `workspace_id`；如需迭代调 `get_iterations`

3. **创建并回写（原子操作，不可拆分）** 🔴

   > **CRITICAL：3A 和 3B 必须在同一批 tool call 中完成，绝不允许只创建不回写！**

   **3A.** 调 `create_story_or_task`：
   ```
   type: "story", workspace_id, name, description, priority, iteration_id(可选)
   ```
   - `description` 必须是剥离 front-matter 后的纯正文（见上方"核心原则"）
   - 若正文过大需使用 `description_file`：先写入剥离 front-matter 后的临时文件，传临时文件路径
   - 从返回提取 `story_id` 和 `workspace_id`

   **3B.** 同一批次用 `replace_in_file` 回写 front-matter：
   ```yaml
   tapd_story_id: "<story_id>"
   tapd_url: "https://www.tapd.cn/<workspace_id>/prong/stories/view/<story_id>"
   status: "in_progress"
   updated_at: "<当天日期>"
   ```

4. **验证 & 输出** 用 `read_file` 确认 `tapd_story_id` 非空 → 输出确认信息含 TAPD 链接

## 场景二：更新已有需求

1. 读本地 front-matter 提取 `tapd_story_id`
2. 若无 tapd_story_id，从对话记录查找并回写
3. 调用 `update_story_or_task` 更新需求
   - `description` / `description_file` 必须剥离 front-matter（同上）
4. `replace_in_file` 更新本地 front-matter
5. `read_file` 验证 → 输出确认

## 场景三：补充验收标准

读取验收标准 → 拆分为独立可验证的 `[ ]` checkbox 项，覆盖正常流程+异常边界 → 更新本地文档（仅正文部分） → 同步 TAPD（剥离 front-matter 后推送）

## 需求文档模板

```markdown
---
tapd_story_id: ""
tapd_url: ""
status: draft
priority: Medium
iteration: ""
updated_at: ""
---

# [需求标题]

## 背景
<!-- 为什么要做？解决什么问题？ -->

## 目标
<!-- 期望效果，可量化目标 -->

## 功能描述
### 核心功能
### 用户操作流程
<!-- 1. → 2. → 3. -->

## 验收标准
- [ ] 标准1：...
- [ ] 标准2：...

## 优先级 & 范围
- **优先级**: High / Medium / Low
- **预计上线时间**: YYYY-MM-DD
```

## 规则

1. 本地文档必须补充 tapd_story_id
2. tapd_story_id 不可删除或随意修改
3. 迭代 ID 通过 `get_iterations` 获取
4. MCP 调用失败时提示用户检查 Token 和网络
5. **🔴 推送到 TAPD 的内容必须剥离 YAML front-matter**，front-matter 元数据是本地管理信息，不可出现在 TAPD 描述中

## 完成检查清单

创建或更新需求后确认：

- [ ] 获得需求 story_id
- [ ] 本地 front-matter 回写 story_id（非空字符串）
- [ ] 用 `read_file` 验证回写生效
- [ ] 确认推送到 TAPD 的内容不包含 front-matter 元数据（tapd_story_id、tapd_url 等）
