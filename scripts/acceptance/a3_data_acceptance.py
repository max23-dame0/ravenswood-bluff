"""Alpha 0.3 / A3-DATA aggregate acceptance runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_pytest(*args: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    python = sys.executable
    result = subprocess.run(
        [str(python), "-m", "pytest", *args, "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    print(result.stdout.strip())


def main() -> int:
    run_pytest(
        "tests/test_engine/test_data_collector.py",
        "tests/test_state/test_game_record.py",
        "tests/test_agents/test_storyteller_export.py",
        "tests/test_agents/test_vector_memory.py",
        "tests/test_agents/test_agent_reasoning.py",
        "-k",
        "export or vector_stats or data_collector_records_snapshots_for_key_flow_checkpoints",
    )
    run_pytest(
        "tests/test_orchestrator/test_gameover_api.py",
        "-k",
        "history_endpoints_read_persisted_games or export_endpoint_returns_history_traces_and_judgement_summary",
    )
    print("a3 data acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
