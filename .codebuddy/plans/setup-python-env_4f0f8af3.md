---
name: setup-python-env
overview: 为 Ravenswood Bluff 项目安装 Python 3.11+ 运行时，创建项目根 .venv 虚拟环境，安装项目依赖（含 dev 测试依赖），并通过 mock 后端跑通测试与 ruff lint 完成环境验收。
todos:
  - id: install-python
    content: 探测并安装 Python 3.12，确保 PATH 中 python 可用
    status: completed
  - id: create-venv
    content: 在根目录创建 .venv 虚拟环境并激活
    status: completed
    dependencies:
      - install-python
  - id: install-deps
    content: 用 pip install -e ".[dev]" 安装全部依赖（必要时切镜像源）
    status: completed
    dependencies:
      - create-venv
  - id: run-tests
    content: 运行 pytest tests -q 验证 mock 测试环境通过
    status: completed
    dependencies:
      - install-deps
  - id: run-lint
    content: 运行 ruff check src tests 验证零 lint 告警
    status: completed
    dependencies:
      - install-deps
  - id: verify-server
    content: 以 mock 后端启动服务确认运行环境可达后停止
    status: completed
    dependencies:
      - install-deps
---

## 用户需求

为 Ravenswood Bluff 项目安装所需 Python 依赖，并搭建可用的运行环境与测试环境，使项目能够在本机（Windows）正常运行与测试。

## 产品概述

本任务为纯环境搭建，不涉及业务代码改动。目标是让本机具备一套隔离的 Python 虚拟环境，正确安装 `pyproject.toml` 声明的全部运行时与开发（dev）依赖，并跑通测试与 lint 验收门禁。

## 核心要求

- 安装 Python 3.11+ 运行时（当前系统 PATH 中无 Python，且项目根目录无 `.venv`）。
- 在项目根目录 `d:\ravenswood-bluff` 创建并激活虚拟环境 `.venv`。
- 通过 `pip install -e ".[dev]"` 安装全部依赖（可编辑安装，便于源码改动即时生效）。
- 校验运行环境：以 mock 后端启动 FastAPI 服务可达。
- 校验测试环境：`pytest tests -q` 全量测试通过（默认 MockBackend，离线）。
- 校验 lint：`ruff check src tests` 零告警。
- 内网环境若访问默认 PyPI 受限，需启用公司/可用镜像源，避免安装失败。

## 技术栈选择

- 运行时：Python 3.12（满足 `requires-python >=3.11`，且对 `target-version=py311` 的 ruff 解析完全兼容）。
- 包管理：pip + venv（标准库，零额外依赖）。
- 依赖来源：`pyproject.toml` 唯一真相源（无 requirements.txt / lock 文件）。
- 运行时依赖：pydantic>=2.0、openai>=1.0、httpx>=0.25、fastapi>=0.100.0、uvicorn[standard]、websockets、python-dotenv、aiosqlite>=0.19。
- dev 依赖：pytest>=7.0、pytest-asyncio>=0.21、pytest-cov>=4.0、ruff>=0.5。

## 实现方案

采用「系统 Python 安装 → 项目级 venv 隔离 → 可编辑安装 dev 全量依赖 → 门禁验收」四步走策略：

1. **先探测再安装**：先搜索系统是否已有 Python（Program Files/AppData/常用路径），无则在 PATH 安装 3.12，确保 `python --version` 可用。
2. **venv 隔离**：在 `d:\ravenswood-bluff\.venv` 建虚拟环境，避免污染全局包，且被 `.gitignore` 忽略（若未忽略则补加）。
3. **可编辑安装**：`pip install -e ".[dev]"` 一次装全运行时 + 测试 + lint 工具，保证 `src` 直接可 import。
4. **验收闭环**：`pytest tests -q` + `ruff check src tests` 双门禁，并短启 mock 服务确认运行环境。

## 镜像与网络处理

- 执行前先检查现有 pip 配置：`pip config list` 及 `%APPDATA%\pip\pip.ini`、`C:\ProgramData\pip\pip.ini` 是否已有内网索引。
- 若已配置则沿用；若默认源安装超时/403，则临时使用 `PIP_INDEX_URL` 指向可用镜像（具体地址执行时若失败再向用户索取），不写死进仓库。

## 执行要点

- PowerShell 激活方式：`.\.venv\Scripts\Activate.ps1`（需 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 或 `-ExecutionPolicy Bypass`）。
- 测试默认即 MockBackend（AGENTS.md 确认），无需任何 API Key 即可离线跑通。
- 启动服务（验证运行环境）：`$env:BOTC_BACKEND="mock"; python -m src.api.server`，确认 `http://127.0.0.1:8000` 可达后停止。
- 不修改任何业务源码与 `pyproject.toml`；仅新增 `.venv`（及必要时补 `.gitignore` 条目）。

## 架构/目录影响

```
d:\ravenswood-bluff\
├── .venv/                  # [NEW] 虚拟环境（自动忽略，不入库）
└── .gitignore              # [MODIFY] 若未含 .venv 则追加忽略（避免误提交）
```