"""Alpha 1.0 M1 rules and flow acceptance runner."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(*args: str, timeout: int = 120) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    python = repo_root / ".venv" / "Scripts" / "python.exe"
    result = subprocess.run(
        [str(python), *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        raise SystemExit(output)
    if result.stdout.strip():
        print(result.stdout.strip())


def main() -> int:
    run_command(
        "-m",
        "pytest",
        "tests/test_simulate_game.py",
        "tests/test_engine/test_high_risk_roles.py",
        "tests/test_engine/test_role_skill_audit.py",
        "tests/test_engine/test_nomination_rules.py",
        "tests/test_engine/test_roles_victory.py",
        "-q",
    )
    print("alpha1 rules acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
