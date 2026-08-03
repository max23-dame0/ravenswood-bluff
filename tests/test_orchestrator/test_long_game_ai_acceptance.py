from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.slow
def test_long_game_ai_acceptance_script_runs_and_reports_metrics():
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/acceptance/long_game_ai_acceptance.py",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines[-1] == "long game ai acceptance: ok"
    payload = json.loads("\n".join(lines[:-1]))
    assert payload["long_game_persona_diversity_score"] >= 0.6
    assert payload["long_game_stability_score"] >= 0.75
    assert payload["long_game_retention_rate"] == 1.0
    assert payload["long_game_social_consistency_rate"] >= 0.8
    assert payload["aggressive_nomination_rate"] > payload["silent_nomination_rate"]
