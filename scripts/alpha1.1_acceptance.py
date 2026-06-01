"""Alpha 1.1 aggregate release gate runner.

Runs the difficulty-system acceptance gates plus backward-compatibility and
regression checks introduced for Alpha 1.1.
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


def _script_exists(path: str) -> bool:
    return (REPO_ROOT / path).is_file()


def build_gates(args: argparse.Namespace) -> list[Gate]:
    gates: list[Gate] = [
        Gate(
            "existing tests regression",
            [
                "-m", "pytest",
                "tests/test_difficulty.py",
                "tests/test_state/",
                "tests/test_engine/",
                "tests/test_orchestrator/test_game_loop.py",
                "tests/test_orchestrator/test_api_server.py",
                "tests/test_orchestrator/test_information_broker.py",
                "tests/test_orchestrator/test_event_bus.py",
                "tests/test_agents/test_ai_persona.py",
                "tests/test_agents/test_memory.py",
                "-q",
            ],
            args.gate_timeout_seconds,
        ),
        Gate(
            "agent reasoning tests",
            [
                "-m", "pytest",
                "tests/test_agents/test_agent_reasoning.py",
                "-q",
            ],
            args.gate_timeout_seconds,
        ),
        Gate(
            "difficulty acceptance",
            ["scripts/difficulty_acceptance.py"],
            args.gate_timeout_seconds,
        ),
        Gate(
            "difficulty comparison",
            ["scripts/difficulty_comparison.py"],
            args.gate_timeout_seconds,
            skip_reason=None if _script_exists("scripts/difficulty_comparison.py") else "script not yet implemented",
        ),
        Gate(
            "difficulty behavior acceptance",
            ["scripts/difficulty_behavior_acceptance.py"],
            args.gate_timeout_seconds,
            skip_reason=None if _script_exists("scripts/difficulty_behavior_acceptance.py") else "script not yet implemented",
        ),
        Gate(
            "ai speed acceptance",
            ["scripts/ai_speed_acceptance.py"],
            args.gate_timeout_seconds,
            skip_reason=None if _script_exists("scripts/ai_speed_acceptance.py") else "script not yet implemented",
        ),
        Gate(
            "ai conversation quality",
            ["scripts/ai_conversation_quality_acceptance.py"],
            args.gate_timeout_seconds,
            skip_reason=None if _script_exists("scripts/ai_conversation_quality_acceptance.py") else "script not yet implemented",
        ),
        Gate(
            "ai live-like speech",
            ["scripts/ai_live_speech_acceptance.py"],
            max(args.gate_timeout_seconds, 360),
            skip_reason=None if _script_exists("scripts/ai_live_speech_acceptance.py") else "script not yet implemented",
        ),
        Gate(
            "alpha1 backward compatibility",
            ["scripts/alpha1_rules_acceptance.py"],
            args.gate_timeout_seconds,
        ),
    ]
    return gates


def print_summary(results: Sequence[GateResult]) -> None:
    print("\nalpha1.1 acceptance summary")
    print("=" * 72)
    for result in results:
        elapsed = format_seconds(result.elapsed_seconds)
        detail = f" - {result.reason}" if result.reason else ""
        print(f"{result.status:4} {result.name:<30} {elapsed:>9}{detail}")
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
        help="Timeout for each gate. Defaults to 180 seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not PYTHON.exists():
        print(f"alpha1.1 acceptance: missing Python interpreter: {PYTHON}")
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
    print("\nalpha1.1 acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
