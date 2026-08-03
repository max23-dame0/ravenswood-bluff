import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_alpha3_acceptance_script_runs_cleanly():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/alpha3_acceptance.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "alpha3 acceptance: ok" in result.stdout
