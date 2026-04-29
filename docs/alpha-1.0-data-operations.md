# Alpha 1.0 数据与日志目录说明

本文件用于内测前后的数据保留和清理。原则：真实内测局按 `game_id` 保留定位资产；测试、probe、corrupt 备份和缓存不作为发布资产提交。

## 关键目录

| 路径 | 内容 | 是否保留 | 说明 |
|---|---|---|---|
| `data/games.db` | SQLite 对局历史 | 保留 | 主历史库，按 `game_id` 查询。 |
| `data/games.records.json` | JSON fallback 历史 | 视情况保留 | SQLite 不可写时的 fallback，若包含内测局需保留。 |
| `data/sessions/` | AI trace JSONL | 按需保留 | `GameDataCollector` 输出，问题定位时通过 `game_id_*.jsonl` 查找。 |
| `data/exports/<game_id>/` | 问题定位包 | 保留相关局 | 由 `scripts/export_all_assets.py` 生成。 |
| `storyteller_run.log` | 说书人运行日志 | 保留尾部或随问题包导出 | 导出包默认可附带 tail 片段。 |
| `logs/` | 运行日志目录 | 按需保留 | 若存在，按同一 `game_id` 和时间筛选。 |
| `tests/test_runs/` | 测试运行产物 | 可清理 | 不进入发布资产。 |
| `data/_pytest*/` | pytest 临时数据 | 可清理 | 不进入发布资产。 |
| `data/_probe*` | 手动探针文件 | 可清理 | 不进入发布资产。 |
| `data/*.corrupt_*` | SQLite 恢复备份 | 可清理或归档 | 若不再需要恢复，可移出发布工作区。 |
| `.pytest_cache/` | pytest 缓存 | 可清理 | 不影响运行。 |

## 生成问题包

```powershell
.\.venv\Scripts\python.exe scripts\export_all_assets.py <game_id> --output data\exports --log-path storyteller_run.log
```

导出包包含：

- `game_history.json`
- `ai_traces.json`
- `storyteller_judgements.json`
- `metrics_summary.json`
- `logs/*.tail.txt`
- `manifest.json`

## 内测前清理建议

在清理前，确认没有需要保留的真实内测局。不要删除仍需复盘的 `data/games.db`、`data/games.records.json`、`data/sessions/` 或 `data/exports/<game_id>/`。

可清理目标：

```powershell
Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force tests\test_runs -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force data\_pytest* -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force data\_probe* -ErrorAction SilentlyContinue
Remove-Item -Force data\*.corrupt_* -ErrorAction SilentlyContinue
Remove-Item -Force data\*-journal.corrupt_* -ErrorAction SilentlyContinue
```

若 Windows 返回 `Access denied`，通常是文件 ACL 或进程占用问题。先关闭正在运行的 API server、pytest 或编辑器预览，再重试；不要为了清理临时文件而改动真实对局数据库权限。

## 体积控制

- 小范围内测前记录 `data/` 初始大小。
- 每次正式内测局记录 `game_id` 和导出包路径。
- 长局结束后优先保留 `data/exports/<game_id>/`，再按需要归档原始 `data/sessions/<game_id>_*.jsonl`。
- 发布包不应夹带无关测试数据、probe 文件或旧 corrupt 备份。
