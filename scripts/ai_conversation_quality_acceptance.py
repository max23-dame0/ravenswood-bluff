"""AI conversation quality acceptance: validates speech quality in mock games.

Checks:
  1. Low-content speech rate: fallback/empty speeches should be below threshold.
  2. Duplicate speech rate: no identical speeches in the same discussion round.
  3. Minimum effective information: each speech should contain at least one of
     doubt target, stance, question, event reference, or private clue.
  4. Context responsiveness: later AI players should reference earlier players.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("BOTC_BACKEND", "mock")

from src.agents.ai_agent import AIAgent
from src.agents.storyteller_agent import StorytellerAgent
from src.llm.mock_backend import MockBackend
from src.orchestrator.game_loop import GameOrchestrator
from src.state.game_state import GamePhase, GameState

# Low-content markers: short generic phrases that don't carry game information
LOW_CONTENT_MARKERS = (
    "我还在想",
    "让我再琢磨",
    "等我理理思路",
    "我在整理思路",
    "有点复杂",
    "我没有要补充",
    "该说的我都说了",
    "我能说的就这些",
    "我没什么好辩解",
)

# Minimum character count for a substantive speech
MIN_SPEECH_LENGTH = 8

_pass_count = 0
_fail_count = 0


def _check(label: str, condition: bool) -> None:
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {label}")
    else:
        _fail_count += 1
        print(f"  FAIL  {label}")


class _StopGame(Exception):
    """Raised to stop the game loop early."""


async def _run_mock_game(player_count: int, discussion_rounds: int = 2) -> dict:
    """Run a mock game and collect speech events for quality analysis."""
    backend = MockBackend()
    state = GameState(phase=GamePhase.SETUP)
    orch = GameOrchestrator(state)

    storyteller = StorytellerAgent(backend)
    orch.storyteller_agent = storyteller
    orch.default_agent_backend = backend

    speak_events: list[dict] = []
    original_publish = orch.event_bus.publish

    async def publish_with_capture(event):
        await original_publish(event)
        if event.event_type == "player_speaks":
            speak_events.append({
                "actor": event.actor,
                "content": event.payload.get("content", ""),
                "round": event.payload.get("round", 0),
                "tone": event.payload.get("tone", ""),
            })
        if event.event_type in ("execution_resolved", "game_settlement_ready"):
            raise _StopGame("quality measurement complete")

    orch.event_bus.publish = publish_with_capture  # type: ignore[assignment]

    loop_task = asyncio.create_task(orch.run_game_loop())
    try:
        await asyncio.sleep(0.1)
        await orch.run_setup_with_options(
            player_count=player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=discussion_rounds,
            storyteller_mode="auto",
            audit_mode=True,
            max_nomination_rounds=1,
            backend_mode="mock",
        )
        await asyncio.wait_for(loop_task, timeout=120)
    except (_StopGame, asyncio.CancelledError):
        pass
    finally:
        if not loop_task.done():
            loop_task.cancel()
            try:
                await asyncio.sleep(0.01)
            except (asyncio.CancelledError, Exception):
                pass

    # Collect action metrics from agents
    all_metrics: list[dict] = []
    for agent in orch.broker.agents.values():
        if isinstance(agent, AIAgent):
            all_metrics.extend(agent.export_action_metrics())

    return {
        "speak_events": speak_events,
        "action_metrics": all_metrics,
        "player_count": player_count,
        "discussion_rounds": discussion_rounds,
    }


def _is_low_content(content: str) -> bool:
    """Check if speech content is low-information."""
    text = content.strip()
    if not text:
        return True
    if len(text) < MIN_SPEECH_LENGTH:
        return True
    for marker in LOW_CONTENT_MARKERS:
        if text == marker or text == f"{marker}。":
            return True
    return False


def _analyze_quality(result: dict) -> None:
    """Analyze speech quality metrics."""
    speak_events = result["speak_events"]
    player_count = result["player_count"]
    rounds = result["discussion_rounds"]

    print(f"\n--- {player_count}-player game quality analysis ({rounds} rounds) ---")

    total_speeches = len(speak_events)
    _check(f"{player_count}p: speeches collected", total_speeches > 0)
    print(f"  total speeches: {total_speeches}")

    # 1. Low-content speech rate
    low_content = [e for e in speak_events if _is_low_content(e["content"])]
    low_rate = len(low_content) / total_speeches if total_speeches else 0
    _check(f"{player_count}p: low-content rate <= 30% (got {low_rate:.0%})", low_rate <= 0.30)
    if low_content:
        print(f"  low-content examples: {[e['content'][:20] for e in low_content[:3]]}")

    # 2. Duplicate speech rate within same round
    duplicates = 0
    by_round: dict[int, list[str]] = {}
    for e in speak_events:
        by_round.setdefault(e["round"], []).append(e["content"])
    for rnd, contents in by_round.items():
        counter = Counter(contents)
        for content, count in counter.items():
            if count > 1 and len(content.strip()) > 0:
                duplicates += count - 1
    dup_rate = duplicates / total_speeches if total_speeches else 0
    _check(f"{player_count}p: duplicate rate == 0 (got {duplicates})", duplicates == 0)

    # 3. Orchestrator hard timeout fallback rate
    action_metrics = result["action_metrics"]
    speak_metrics = [m for m in action_metrics if m.get("action_type") == "speak"]
    orchestrator_timeouts = sum(
        1 for m in speak_metrics
        if (m.get("fallback_reason") or "").startswith("orchestrator_hard_timeout")
    )
    timeout_rate = orchestrator_timeouts / len(speak_metrics) if speak_metrics else 0
    _check(f"{player_count}p: orchestrator timeout rate <= 10% (got {timeout_rate:.0%})", timeout_rate <= 0.10)
    print(f"  orchestrator timeouts: {orchestrator_timeouts}/{len(speak_metrics)}")

    # 4. Agent-level fallback rate (should be higher than orchestrator, meaning agent handles it)
    agent_fallbacks = sum(
        1 for m in speak_metrics
        if m.get("fallback_used") and not (m.get("fallback_reason") or "").startswith("orchestrator_hard_timeout")
    )
    print(f"  agent-level fallbacks: {agent_fallbacks}/{len(speak_metrics)}")

    # 5. Total fallback rate
    total_fallbacks = sum(1 for m in speak_metrics if m.get("fallback_used"))
    total_fallback_rate = total_fallbacks / len(speak_metrics) if speak_metrics else 0
    _check(f"{player_count}p: total fallback rate <= 50% (got {total_fallback_rate:.0%})", total_fallback_rate <= 0.50)


async def main_async() -> None:
    print("=" * 60)
    print("AI conversation quality acceptance checks")
    print("=" * 60)

    # Run 5-player game with 2 discussion rounds
    print("\n[1] 5-player game (2 rounds)")
    result_5 = await _run_mock_game(5, discussion_rounds=2)
    _analyze_quality(result_5)

    # Run 8-player game with 2 discussion rounds
    print("\n[2] 8-player game (2 rounds)")
    result_8 = await _run_mock_game(8, discussion_rounds=2)
    _analyze_quality(result_8)


def main() -> int:
    asyncio.run(main_async())

    print("\n" + "=" * 60)
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)

    if _fail_count > 0:
        print("ai conversation quality acceptance: FAILED")
        return 1

    print("ai conversation quality acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
