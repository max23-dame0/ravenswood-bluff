from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_a3_memory_acceptance_script_passes():
    repo_root = Path(__file__).resolve().parents[2]
    python = sys.executable
    result = subprocess.run(
        [str(python), "scripts/acceptance/a3_memory_acceptance.py"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "a3 memory acceptance: ok" in result.stdout
