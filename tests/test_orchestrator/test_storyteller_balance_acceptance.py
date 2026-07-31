from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_storyteller_balance_acceptance_script_runs() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "acceptance" / "storyteller_balance_acceptance.py"),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        # 验收脚本跑完整 mock 对局，全量测试并发时耗时抖动大，统一给 300s 上限
        timeout=300,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "storyteller balance acceptance: ok" in result.stdout
    assert "night_info=" in result.stdout
    assert "suppressed=" in result.stdout
    assert "distorted=" in result.stdout
    assert "legacy_fallback=" in result.stdout
