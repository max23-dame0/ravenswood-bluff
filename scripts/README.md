# scripts/ 目录约定

> 2026-07-31 规范化整理后的组织方式。新增脚本请按下表归位。

## 分层原则

- **顶层 `scripts/*.py`**：用户/CI 直接调用的**入口**（聚合门禁、维护工具）。路径稳定，不随整理移动。
- **子目录**：被入口调用或按用途分类的**实现脚本**。

| 目录 | 用途 | 说明 |
|------|------|------|
| `scripts/` | 入口 | `alpha1.1_acceptance.py`（9 gate 发布 blocker）、`alpha1_acceptance.py`、`alpha3_acceptance.py`、`check_doc_health.py` |
| `scripts/acceptance/` | 验收门禁 | 每个脚本实现 `main() -> int`（0=通过），被聚合入口以子进程调用 |
| `scripts/benchmark/` | 性能基准 | 延迟/吞吐基准与结果解析（`parse_*_metrics.py`） |
| `scripts/export/` | 数据导出 | 对局资产、AI trace、平衡性样本导出与生成 |
| `scripts/debug/` | 调试辅助 | prompt 抽取、单点行为验证等人工调试工具 |

## 新增脚本须知

1. **REPO_ROOT 计算**：子目录内脚本深度为 2，必须写
   `REPO_ROOT = Path(__file__).resolve().parents[2]`（顶层入口用 `parents[1]`），
   随后 `sys.path.insert(0, str(REPO_ROOT))` 才能 `import src.*`。
2. **新增 gate**：脚本放 `scripts/acceptance/`，并在 `scripts/alpha1.1_acceptance.py`
   的 `Gate(...)` 列表登记完整路径 `scripts/acceptance/xxx.py`。
3. **跨脚本 import**：使用完整包路径，如 `from scripts.acceptance.ai_evaluation import ...`
   （依赖 `pyproject.toml` 的 `pythonpath = ["."]`）。
4. **默认离线**：脚本应默认走 `BOTC_BACKEND=mock`，live 模式作为显式开关。

## 运行

```bash
python scripts/alpha1.1_acceptance.py          # 9 gate 聚合验收（发布 blocker）
python scripts/acceptance/role_acceptance.py   # 单个 gate
python scripts/debug/dump_ai_prompt.py         # 抽取发给 LLM 的真实 prompt
```

> 入口脚本内部统一使用 `sys.executable`（当前解释器）调用子脚本，跨平台通用：用哪个 python 启动入口，子脚本就用哪个。
> 请勿再硬编码 `.venv\Scripts\python.exe`（Windows-only，会在 Linux CI 上 `FileNotFoundError`）。
