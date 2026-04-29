"""Export an Alpha 1.0 issue package for a single game_id."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.data_collector import GameDataCollector
from src.state.game_record import GameRecordStore


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_log_tail(path: Path, max_lines: int) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "line_count": 0,
            "tail": [],
        }
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "path": str(path),
        "exists": True,
        "line_count": len(lines),
        "tail": lines[-max_lines:],
    }


def _build_metrics_summary(
    game_id: str,
    game_history: dict[str, Any] | None,
    ai_traces: dict[str, Any],
    storyteller_judgements: dict[str, Any] | None,
    log_tails: list[dict[str, Any]],
) -> dict[str, Any]:
    settlement = game_history.get("settlement", {}) if game_history else {}
    trace_stats = ai_traces.get("stats", {}) if isinstance(ai_traces, dict) else {}
    judgement_count = 0
    judgement_categories: list[str] = []
    judgement_buckets: list[str] = []
    if storyteller_judgements:
        judgement_count = int(storyteller_judgements.get("judgement_count", 0) or 0)
        judgement_categories = list(storyteller_judgements.get("categories", []) or [])
        judgement_buckets = list(storyteller_judgements.get("buckets", []) or [])

    return {
        "game_id": game_id,
        "has_game_history": bool(game_history),
        "winning_team": (game_history or {}).get("winning_team") or settlement.get("winning_team"),
        "victory_reason": (game_history or {}).get("victory_reason") or settlement.get("victory_reason"),
        "player_count": (game_history or {}).get("player_count") or settlement.get("statistics", {}).get("player_count"),
        "round_count": (game_history or {}).get("round_count") or settlement.get("duration_rounds"),
        "ai_trace_stats": trace_stats,
        "storyteller_judgement_count": judgement_count,
        "storyteller_judgement_categories": judgement_categories,
        "storyteller_judgement_buckets": judgement_buckets,
        "log_files": [
            {
                "path": item["path"],
                "exists": item["exists"],
                "line_count": item["line_count"],
                "tail_line_count": len(item["tail"]),
            }
            for item in log_tails
        ],
    }


async def export_all_assets(
    game_id: str,
    output_dir: str = "data/exports",
    *,
    db_path: str = "data/games.db",
    sessions_dir: str = "data/sessions",
    log_paths: Iterable[str] = ("storyteller_run.log",),
    log_tail_lines: int = 200,
) -> dict[str, Any]:
    """Export history, AI traces, storyteller judgements, metrics and log snippets."""
    target_dir = Path(output_dir) / game_id
    target_dir.mkdir(parents=True, exist_ok=True)

    store = GameRecordStore(db_path)
    try:
        assets = await store.export_game_assets(game_id, storyteller_agent=None)
    finally:
        await store.close()

    if assets is None:
        return {
            "status": "error",
            "message": f"Game not found: {game_id}",
            "game_id": game_id,
            "output_dir": str(target_dir),
        }

    game_history = assets.get("game_history")
    storyteller_judgements = assets.get("storyteller_judgements")
    ai_traces = GameDataCollector.export_ai_traces(game_id, base_dir=sessions_dir)
    log_tails = [_read_log_tail(Path(path), log_tail_lines) for path in log_paths]
    metrics_summary = _build_metrics_summary(
        game_id,
        game_history,
        ai_traces,
        storyteller_judgements,
        log_tails,
    )

    _write_json(target_dir / "game_history.json", game_history)
    _write_json(target_dir / "ai_traces.json", ai_traces)
    _write_json(target_dir / "storyteller_judgements.json", storyteller_judgements)
    _write_json(target_dir / "metrics_summary.json", metrics_summary)
    for item in log_tails:
        log_name = Path(item["path"]).name or "log.txt"
        (target_dir / "logs").mkdir(parents=True, exist_ok=True)
        (target_dir / "logs" / f"{log_name}.tail.txt").write_text(
            "\n".join(item["tail"]) + ("\n" if item["tail"] else ""),
            encoding="utf-8",
        )

    manifest = {
        "version": "alpha1-issue-package-v1",
        "game_id": game_id,
        "exported_at": datetime.now().isoformat(),
        "output_dir": str(target_dir),
        "assets": [
            "game_history.json",
            "ai_traces.json",
            "storyteller_judgements.json",
            "metrics_summary.json",
            "manifest.json",
            *[f"logs/{Path(item['path']).name}.tail.txt" for item in log_tails],
        ],
        "summary": metrics_summary,
    }
    _write_json(target_dir / "manifest.json", manifest)
    return {"status": "ok", **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_id", help="Target game_id")
    parser.add_argument("--output", default="data/exports", help="Output root directory")
    parser.add_argument("--db-path", default="data/games.db", help="Game record database path")
    parser.add_argument("--sessions-dir", default="data/sessions", help="AI trace directory")
    parser.add_argument(
        "--log-path",
        action="append",
        dest="log_paths",
        help="Log file to include as a tail snippet. Can be passed more than once.",
    )
    parser.add_argument("--log-tail-lines", type=int, default=200)
    args = parser.parse_args()

    payload = asyncio.run(
        export_all_assets(
            args.game_id,
            args.output,
            db_path=args.db_path,
            sessions_dir=args.sessions_dir,
            log_paths=args.log_paths or ["storyteller_run.log"],
            log_tail_lines=args.log_tail_lines,
        )
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
