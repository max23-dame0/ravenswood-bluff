---
name: doc-governance-cleanup-and-hardening
overview: 清理上轮文档治理遗留的临时产物，补入两项增强（证据文件入库索引 + 文档健康 CI 校验脚本），并核对根目录 harness 长期文档（AGENTS/MEMORY/PROGRESS/DECISIONS/CLAUDE）的健康度，消除过时/错误信息。
todos:
  - id: clean-temp-artifacts
    content: 删除 4 个临时产物（.codebuddy/tmp_*.{ps1,py} 与 docs/.gov_body.md）
    status: completed
  - id: enhance-evidence-index
    content: 在 docs/README.md 新增证据索引章节，登记 29 篇 alpha-1.1-evidence 文件名并标注豁免
    status: completed
    dependencies:
      - clean-temp-artifacts
  - id: add-doc-health-ci
    content: 新增 scripts/check_doc_health.py，校验 frontmatter 必填字段与内部链接并作 CI 门禁退出码
    status: completed
    dependencies:
      - clean-temp-artifacts
  - id: verify-fix-harness-docs
    content: 核对并修正 AGENTS/CLAUDE/DECISIONS(D009)/PROGRESS/MEMORY 与根规范文件，补索引指针与治理记录
    status: completed
    dependencies:
      - clean-temp-artifacts
  - id: final-verification
    content: 全仓 grep 陈旧引用 + README 链接解析 + check_doc_health.py 语法自检，确认无污染
    status: completed
    dependencies:
      - enhance-evidence-index
      - add-doc-health-ci
      - verify-fix-harness-docs
---

## 用户需求

用户要求在上轮文档治理（语料根统一到 `docs/`、全量人工文档补 frontmatter、`docs/README.md` 重写为五要素索引）的基础上，完成三件事：

1. **清理临时产物**：删除上轮治理遗留的临时脚本与中间文件。
2. **加入增强**：把上轮承诺的两项增强落地——① 让 `docs/README.md` 索引登记 29 篇自动生成的验收证据文件名；② 新增一个 CI 校验脚本，对任意文档缺 frontmatter / 死链即告警。
3. **保证 harness 长期文档健康**：核对根目录下长期依赖与维护的 harness 文档（AGENTS.md / MEMORY.md / PROGRESS.md / DECISIONS.md / CLAUDE.md，以及 README.md / architecture.md / CHANGELOG.md / VERSION_NOTES.md），确保无过时或错误信息污染，做精准修正与指针补全。

## 核心内容

- 删除 4 个临时文件：`.codebuddy/tmp_build_readme.ps1`、`.codebuddy/tmp_gov_add_fm.ps1`、`.codebuddy/tmp_gov_add_fm.py`、`docs/.gov_body.md`。
- 在 `docs/README.md` 新增「自动生成验收证据」章节，列出 `docs/alpha-1.1-evidence/` 下 29 个文件（相对路径链接），保持它们 frontmatter 豁免。
- 新增 `scripts/check_doc_health.py`（仅用标准库），巡检 `docs/`：frontmatter 必填字段齐全 + 角色合法 + 内部相对链接有效，输出违规清单并以非零退出码作为 CI 门禁。
- 核对并修正 harness 文档：补 `docs/README.md` 与 `docs/tech-traps.md` 指针（AGENTS.md、CLAUDE.md）；DECISIONS.md 补 D009（文档治理决策）；PROGRESS.md 补治理条目与最近会话；MEMORY.md Auto Memory 补治理记录；对根目录规范文件做一次陈旧引用核查，发现即修。
- 最终验证：全仓 grep 无 `documents/` 等陈旧引用、`docs/README.md` 链接可解析、`scripts/check_doc_health.py` 通过语法自检。

## 技术栈

- 文档治理规范：`doc-governance` 技能（五要素索引 + frontmatter 受控词表）。
- CI 脚本语言：Python 3.11+，仅用标准库（`os` / `re` / `sys` / `pathlib`），与项目 `ruff` / `pytest` 约定一致、可接入 CI。
- 本机当前无 Python 运行时（install_binary 被锁），脚本作为 CI 交付物，本地仅做 `py_compile` 语法自检 + 人工评审，不强行运行。

## 实现方案

### 1. 临时产物清理

直接删除上轮遗留的 4 个文件。其中 `docs/.gov_body.md` 为隐藏点文件（list_dir 不显示，但确实存在），必须显式删除，否则会随 `docs/` 一起进入版本库，污染语料。

### 2. 证据索引增强（docs/README.md）

在五要素索引「6. 主题归口」之后新增「7. 自动生成验收证据（alpha-1.1-evidence/）」章节：用一张表格列出 29 个文件名（相对路径链接 + 日期/类型），并标注「脚本自动产出、frontmatter 豁免」。保持证据文件本身零改动、豁免策略不变。

### 3. CI 校验脚本（scripts/check_doc_health.py）

**策略**：单文件、无外部依赖，CI 中以 `python scripts/check_doc_health.py` 调用；发现任一违规即打印 `路径:行号 原因` 并以 `sys.exit(1)` 退出（CI 门禁），全绿则退出 0。

**关键逻辑**：

- 遍历 `docs/`（根可配 `--root`），跳过豁免目录 `alpha-1.1-evidence/`（其下 README 也跳过）与豁免文件清单。
- frontmatter 校验：文件须以 `---\n` 开头；解析 YAML 头部，要求 `doc_id / title / category / role / status / date / author` 七字段齐全；`role` 取值须 ∈ {State, Delta, Cold}；`category` 须 ∈ 受控词表；`status` ∈ {draft, review, published, archived, superseded}。
- 链接校验：正则提取 `[text](target)`；跳过 `http(s)://` 外链与纯 `#anchor`；相对路径按当前文件目录解析，目标须存在；同时校验 `docs/README.md` 内部链接。
- 输出分级汇总（违规数 / 文件数），便于 CI 日志阅读。

**性能**：单次 O(N·M)（N=文件数，M=单文件行数），仅读取语料，无网络/IO 放大；超 100 行单文件可按需截断头部解析，无瓶颈。

**可维护性**：豁免目录/文件、受控词表均在脚本顶部常量集中定义，后续新增豁免（如新证据目录）只改常量。

### 4. harness 文档健康核对与精准修正

遵循「最小但完备、不大幅重写」原则，仅做精准修正：

- **AGENTS.md**（保持 <200 行）：「专题文档索引」补两行 —— `docs/README.md`（文档体系标准索引）与 `docs/tech-traps.md`（技术陷阱速查）。
- **CLAUDE.md**（33KB）：文档索引段轻量补 `docs/README.md` 指针（grep 已确认无 `documents/` 陈旧引用，仅补指针）。
- **DECISIONS.md**：新增 `D009` —— 单一语料根=`docs/` + frontmatter 标准 + 证据目录豁免，记录原因/否决方案/可逆方案，利长期维护。
- **PROGRESS.md**：任务看板补「文档体系治理」条目（状态：已完成，环境说明 pytest/ruff 待装 Python 后闭环）；更新「未提交改动清单」与「最近会话记录」。
- **MEMORY.md**（保持 <200 行）：Auto Memory 区补一条文档治理记录（P0–P3：语料根统一、67 篇 frontmatter、五要素索引、证据豁免）。
- **根目录规范文件**（README.md / architecture.md / CHANGELOG.md / VERSION_NOTES.md）：以 grep `documents/|05-reference` + 链接目标存在性做核查，发现陈旧信息即精准修，无问题则不改。

## 目录结构（变更清单）

```
.codebuddy/
├── tmp_build_readme.ps1     # [DELETE] 临时脚本
├── tmp_gov_add_fm.ps1       # [DELETE] 临时脚本
└── tmp_gov_add_fm.py        # [DELETE] 临时脚本
docs/
├── .gov_body.md             # [DELETE] 中间产物（隐藏点文件）
├── README.md                # [MODIFY] 新增证据索引章节 + 链接自查
└── alpha-1.1-evidence/      # [不变] 29 篇，frontmatter 豁免
scripts/
└── check_doc_health.py      # [NEW] 文档健康 CI 校验（frontmatter + 死链）
AGENTS.md                    # [MODIFY] 补 docs/README.md、docs/tech-traps.md 指针
CLAUDE.md                    # [MODIFY] 文档索引段补指针
DECISIONS.md                 # [MODIFY] 新增 D009
PROGRESS.md                  # [MODIFY] 补治理条目 + 最近会话
.codebuddy/memory/MEMORY.md  # [MODIFY] Auto Memory 补治理记录
```

## 关键代码结构（scripts/check_doc_health.py）

```python
# 顶部常量（集中可维护）
EXEMPT_DIRS = {"alpha-1.1-evidence"}
EXEMPT_FILES = {"README.md"}                 # 仅豁免各证据子目录内的 README；docs/README.md 自身需校验
VALID_ROLES = {"State", "Delta", "Cold"}
VALID_CATEGORIES = {"architecture","planning","review","release","report","reference"}
REQUIRED_FM = ["doc_id","title","category","role","status","date","author"]

def check_frontmatter(path) -> list[str]:  # 返回违规原因列表
def check_links(path, root) -> list[str]:  # 解析相对链接并校验存在性
def main() -> int:                          # 遍历 docs/，汇总违规，sys.exit(1) 当存在违规
```

## Agent Extensions

### Skill

- **doc-governance**
- Purpose: 指导整套文档治理动作（五要素索引、frontmatter 受控词表、证据豁免、根文档健康核对），确保本轮清理/增强/修正符合既有规范。
- Expected outcome: 生成的 `docs/README.md` 索引、frontmatter 分类、harness 文档修正均满足技能标准，语料可被 Agent 结构化检索且无非标准角色/陈旧引用。