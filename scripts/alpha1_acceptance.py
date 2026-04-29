"""Alpha 1.0 aggregate release gate runner.

The default gate only runs local, repeatable checks. Full pytest and live smoke
remain explicit so CI and local release dry-runs do not require real API keys.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


@dataclass(frozen=True)
class Gate:
    name: str
    command: Sequence[str]
    timeout_seconds: int
    skip_reason: str | None = None


@dataclass(frozen=True)
class GateResult:
    name: str
    status: str
    elapsed_seconds: float
    command: Sequence[str]
    reason: str = ""
    output: str = ""


def format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.1f}s"


def command_text(command: Sequence[str]) -> str:
    return " ".join(str(part) for part in command)


def output_tail(output: str, max_lines: int = 30) -> str:
    lines = [line.rstrip() for line in output.splitlines() if line.rstrip()]
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(["... output truncated ...", *lines[-max_lines:]])


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("BOTC_BACKEND", "mock")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def run_gate(gate: Gate) -> GateResult:
    start = time.perf_counter()
    if gate.skip_reason:
        return GateResult(
            name=gate.name,
            status="SKIP",
            elapsed_seconds=0.0,
            command=gate.command,
            reason=gate.skip_reason,
        )

    try:
        result = subprocess.run(
            [str(PYTHON), *gate.command],
            cwd=REPO_ROOT,
            env=base_env(),
            capture_output=True,
            text=True,
            check=False,
            timeout=gate.timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - start
        output = "\n".join(part for part in (exc.stdout, exc.stderr) if part)
        return GateResult(
            name=gate.name,
            status="FAIL",
            elapsed_seconds=elapsed,
            command=gate.command,
            reason=f"timed out after {gate.timeout_seconds}s",
            output=output_tail(output),
        )

    elapsed = time.perf_counter() - start
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode == 0:
        return GateResult(
            name=gate.name,
            status="PASS",
            elapsed_seconds=elapsed,
            command=gate.command,
            output=output_tail(output, max_lines=8),
        )
    return GateResult(
        name=gate.name,
        status="FAIL",
        elapsed_seconds=elapsed,
        command=gate.command,
        reason=f"exit code {result.returncode}",
        output=output_tail(output),
    )


def build_gates(args: argparse.Namespace) -> list[Gate]:
    gates = [
        Gate("alpha1 rules", ["scripts/alpha1_rules_acceptance.py"], args.gate_timeout_seconds),
        Gate("frontend", ["scripts/frontend_acceptance.py", "--backend", "mock"], args.gate_timeout_seconds),
        Gate("storyteller", ["scripts/storyteller_acceptance.py"], args.gate_timeout_seconds),
        Gate("role", ["scripts/role_acceptance.py"], args.gate_timeout_seconds),
        Gate("m5 ai experience", ["scripts/m5_ai_player_experience_acceptance.py"], args.gate_timeout_seconds),
        Gate("alpha3", ["scripts/alpha3_acceptance.py"], args.gate_timeout_seconds),
    ]

    full_pytest_reason = None
    if not args.include_full_pytest:
        full_pytest_reason = "not requested; pass --include-full-pytest to run"
    gates.append(
        Gate(
            "full pytest",
            ["scripts/run_full_tests_low_memory.py", "--timeout-seconds", str(args.full_pytest_timeout_seconds)],
            args.full_pytest_timeout_seconds + 30,
            full_pytest_reason,
        )
    )

    live_smoke_reason = None
    if not args.include_live_smoke:
        live_smoke_reason = "not requested; pass --include-live-smoke to run"
    gates.append(
        Gate(
            "live smoke",
            [
                "simulate_game.py",
                "--backend",
                "live",
                "--player-count",
                str(args.live_player_count),
                "--discussion-rounds",
                str(args.live_discussion_rounds),
                "--timeout-seconds",
                str(args.live_timeout_seconds),
                "--stop-after",
                args.live_stop_after,
                "--audit-mode",
                "--max-nomination-rounds",
                str(args.live_max_nomination_rounds),
            ],
            args.live_timeout_seconds + 60,
            live_smoke_reason,
        )
    )
    return gates


def print_summary(results: Sequence[GateResult]) -> None:
    print("\nalpha1.0 acceptance summary")
    print("=" * 72)
    for result in results:
        elapsed = format_seconds(result.elapsed_seconds)
        detail = f" - {result.reason}" if result.reason else ""
        print(f"{result.status:4} {result.name:<18} {elapsed:>9}{detail}")
    print("=" * 72)

    failed = [result for result in results if result.status == "FAIL"]
    skipped = [result for result in results if result.status == "SKIP"]
    print(f"passed: {sum(result.status == 'PASS' for result in results)}")
    print(f"failed: {len(failed)}")
    print(f"skipped: {len(skipped)}")

    if skipped:
        print("\nskipped gates")
        for result in skipped:
            print(f"- {result.name}: {result.reason}")

    if failed:
        print("\nfailed gate details")
        for result in failed:
            print(f"\n[{result.name}] {result.reason}")
            print(f"command: {command_text([str(PYTHON), *result.command])}")
            if result.output:
                print(result.output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-timeout-seconds",
        type=int,
        default=180,
        help="Timeout for each default local gate. Defaults to 180 seconds.",
    )
    parser.add_argument(
        "--include-full-pytest",
        action="store_true",
        help="Also run scripts/run_full_tests_low_memory.py.",
    )
    parser.add_argument(
        "--full-pytest-timeout-seconds",
        type=int,
        default=1800,
        help="Timeout passed to the full pytest runner. Defaults to 30 minutes.",
    )
    parser.add_argument(
        "--include-live-smoke",
        action="store_true",
        help="Also run a live short-game smoke with simulate_game.py.",
    )
    parser.add_argument("--live-player-count", type=int, default=5)
    parser.add_argument("--live-discussion-rounds", type=int, default=1)
    parser.add_argument("--live-timeout-seconds", type=int, default=240)
    parser.add_argument(
        "--live-stop-after",
        choices=("first_execution", "day_1", "night_2", "game_over"),
        default="first_execution",
    )
    parser.add_argument("--live-max-nomination-rounds", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not PYTHON.exists():
        print(f"alpha1 acceptance: missing Python interpreter: {PYTHON}")
        return 2

    results: list[GateResult] = []
    for gate in build_gates(args):
        print(f"\n>>> {gate.name}")
        if gate.skip_reason:
            print(f"skip: {gate.skip_reason}")
        else:
            print(f"command: {command_text([str(PYTHON), *gate.command])}")
        result = run_gate(gate)
        results.append(result)
        print(f"{result.status.lower()}: {gate.name} ({format_seconds(result.elapsed_seconds)})")

    print_summary(results)
    if any(result.status == "FAIL" for result in results):
        return 1
    print("\nalpha1 acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
