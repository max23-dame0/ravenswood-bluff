import subprocess
import sys
from pathlib import Path


def test_a3_data_acceptance_script_runs_cleanly():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/acceptance/a3_data_acceptance.py",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "a3 data acceptance: ok" in result.stdout
