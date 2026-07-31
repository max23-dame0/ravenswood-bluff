"""Wave 3 aggregate acceptance runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_script(script_name: str) -> None:
    """Run a sibling script; ``script_name`` is relative to the ``scripts/`` root."""
    repo_root = Path(__file__).resolve().parents[2]
    python = sys.executable
    result = subprocess.run(
        [str(python), str(repo_root / "scripts" / script_name)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    print(result.stdout.strip())


def main() -> int:
    run_script("acceptance/long_loop_memory_acceptance.py")
    run_script("acceptance/long_game_ai_acceptance.py")
    run_script("acceptance/player_knowledge_acceptance.py")
    run_script("debug/persona_divergence_test.py")
    run_script("acceptance/ai_eval_acceptance.py")
    print("wave3 acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
