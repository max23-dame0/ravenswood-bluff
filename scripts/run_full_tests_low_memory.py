"""Run the full pytest suite with conservative process and thread settings."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


LOW_MEMORY_ENV = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "HF_ENABLE_PARALLEL_LOADING": "false",
    # Prevent inherited pytest-xdist options such as "-n auto" from spawning workers.
    "PYTEST_ADDOPTS": "",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=1800,
        help="Upper bound for the full test run. Defaults to 30 minutes.",
    )
    args, pytest_args = parser.parse_known_args()

    repo_root = Path(__file__).resolve().parents[1]
    python = repo_root / ".venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env.update(LOW_MEMORY_ENV)

    command = [
        str(python),
        "-m",
        "pytest",
        "tests",
        "-q",
        "--tb=short",
        "--durations=20",
        *pytest_args,
    ]
    result = subprocess.run(
        command,
        cwd=repo_root,
        env=env,
        check=False,
        timeout=args.timeout_seconds,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
