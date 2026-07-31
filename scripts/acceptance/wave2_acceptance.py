"""Wave 2 aggregate acceptance runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_script(script_name: str) -> None:
    """Run a sibling script; ``script_name`` is relative to the ``scripts/`` root."""
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / script_name),
        ],
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
    run_script("acceptance/storyteller_acceptance.py")
    run_script("acceptance/storyteller_balance_acceptance.py")
    run_script("acceptance/role_acceptance.py")
    print("wave2 acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
