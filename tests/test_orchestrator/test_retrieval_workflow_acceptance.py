from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_retrieval_workflow_acceptance_script_runs_cleanly():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/acceptance/retrieval_workflow_acceptance.py",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "retrieval_workflow_acceptance: ok" in result.stdout
    assert "[retrieval] GATE PASSED" in result.stdout
    assert "[workflow] GATE PASSED" in result.stdout
