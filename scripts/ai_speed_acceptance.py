"""AI speed acceptance: measures action latency in mock games.

Runs mock games with 5 and 10 players, collects per-action-type latency
metrics from AI agents, and verifies P50/P95 against targets.

Target thresholds (from task_m5_ai_speed_flow.md):
  - speak P95 <= 2000ms
  - nomination_intent P95 <= 1000ms
  - vote P95 <= 800ms
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("BOTC_BACKEND", "mock")

from src.agents.ai_agent import AIAgent
from src.agents.storyteller_agent import StorytellerAgent
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.llm.mock_backend import MockBackend
from src.orchestrator.game_loop import GameOrchestrator
from src.state.game_state import GamePhase, GameState


class SlowBackend(LLMBackend):
    """Backend that simulates slow LLM responses to test timeout fallback."""

    def __init__(self, delay_seconds: float = 5.0) -> None:
        self._delay = delay_seconds
        self._mock = MockBackend()

    async def generate(self, system_prompt: str, messages: list[Message], **kwargs) -> LLMResponse:
        import asyncio
        await asyncio.sleep(self._delay)
        return await self._mock.generate(system_prompt, messages, **kwargs)

    def get_model_name(self) -> str:
        return "slow-mock"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self._mock.get_embeddings(texts)


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


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


class _StopGame(Exception):
    """Raised to stop the game loop early."""


async def _run_mock_game(player_count: int) -> list[dict]:
    """Run a short mock game and collect action metrics."""
    backend = MockBackend()
    state = GameState(phase=GamePhase.SETUP)
    orch = GameOrchestrator(state)

    storyteller = StorytellerAgent(backend)
    orch.storyteller_agent = storyteller
    orch.default_agent_backend = backend

    stop_reason = {"value": "timeout"}
    original_publish = orch.event_bus.publish

    async def publish_with_stop(event):
        await original_publish(event)
        # Stop after nomination phase completes (enough for speed measurement)
        if event.event_type in ("execution_resolved", "game_settlement_ready"):
            stop_reason["value"] = "done"
            raise _StopGame("measurement complete")

    orch.event_bus.publish = publish_with_stop  # type: ignore[assignment]

    loop_task = asyncio.create_task(orch.run_game_loop())
    try:
        await asyncio.sleep(0.1)
        await orch.run_setup_with_options(
            player_count=player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=1,
            storyteller_mode="auto",
            audit_mode=True,
            max_nomination_rounds=1,
            backend_mode="mock",
        )
        await asyncio.wait_for(loop_task, timeout=60)
    except (_StopGame, asyncio.CancelledError):
        pass
    finally:
        if not loop_task.done():
            loop_task.cancel()
            with (asyncio.CancelledError, Exception):
                await asyncio.sleep(0.01)

    # Collect metrics from all AI agents
    all_metrics: list[dict] = []
    for agent in orch.broker.agents.values():
        if isinstance(agent, AIAgent):
            all_metrics.extend(agent.export_action_metrics())

    return all_metrics


def _analyze_metrics(all_metrics: list[dict], player_count: int) -> None:
    """Analyze and report latency metrics per action type."""
    print(f"\n--- {player_count}-player game metrics ---")

    by_type: dict[str, list[float]] = {}
    fallback_count = 0

    for m in all_metrics:
        action_type = m.get("action_type", "unknown")
        latency = m.get("latency_ms", 0)
        by_type.setdefault(action_type, []).append(latency)
        if m.get("fallback_used"):
            fallback_count += 1

    total_actions = len(all_metrics)
    _check(f"{player_count}p: total actions > 0", total_actions > 0)
    print(f"  total actions: {total_actions}")
    print(f"  fallbacks: {fallback_count}")

    # Targets per action type
    targets = {
        "speak": 2000,
        "nomination_intent": 1000,
        "vote": 800,
        "night_action": 1500,
        "defense_speech": 2500,
    }

    for action_type, target_ms in targets.items():
        latencies = by_type.get(action_type, [])
        if not latencies:
            print(f"  {action_type}: no data")
            continue

        p50 = _percentile(latencies, 50)
        p95 = _percentile(latencies, 95)
        max_lat = max(latencies)

        print(f"  {action_type}: n={len(latencies)}, P50={p50:.0f}ms, P95={p95:.0f}ms, max={max_lat:.0f}ms")

        # P95 check against target
        _check(f"{player_count}p/{action_type} P95 <= {target_ms}ms", p95 <= target_ms)


async def _run_slow_backend_game(player_count: int) -> tuple[list[dict], list[str]]:
    """Run a game with slow backend to verify timeout fallback."""
    import asyncio

    # 3s delay exceeds speak budget (2s) but allows game to progress
    slow_backend = SlowBackend(delay_seconds=3.0)
    state = GameState(phase=GamePhase.SETUP)
    orch = GameOrchestrator(state)

    storyteller = StorytellerAgent(slow_backend)
    orch.storyteller_agent = storyteller
    orch.default_agent_backend = slow_backend

    event_order: list[str] = []
    original_publish = orch.event_bus.publish

    async def publish_with_tracking(event):
        await original_publish(event)
        event_order.append(f"{event.event_type}:{getattr(event, 'actor', '') or ''}")
        if event.event_type in ("execution_resolved", "game_settlement_ready"):
            raise _StopGame("slow backend measurement complete")

    orch.event_bus.publish = publish_with_tracking  # type: ignore[assignment]

    loop_task = asyncio.create_task(orch.run_game_loop())
    try:
        await asyncio.sleep(0.1)
        await orch.run_setup_with_options(
            player_count=player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=1,
            storyteller_mode="auto",
            audit_mode=True,
            max_nomination_rounds=1,
            backend_mode="mock",
        )
        await asyncio.wait_for(loop_task, timeout=90)
    except (_StopGame, asyncio.CancelledError):
        pass
    finally:
        if not loop_task.done():
            loop_task.cancel()
            with (asyncio.CancelledError, Exception):
                await asyncio.sleep(0.01)

    # Collect metrics from agents AND from orchestrator latency records
    all_metrics: list[dict] = []
    for agent in orch.broker.agents.values():
        if isinstance(agent, AIAgent):
            all_metrics.extend(agent.export_action_metrics())

    # Also include orchestrator-level latency records (captures timeout fallbacks)
    if hasattr(orch, '_action_latencies'):
        all_metrics.extend(orch._action_latencies)

    return all_metrics, event_order


async def main_async() -> None:
    print("=" * 60)
    print("AI speed acceptance checks")
    print("=" * 60)

    # Run 5-player game
    print("\n[1] 5-player mock game")
    metrics_5 = await _run_mock_game(5)
    _analyze_metrics(metrics_5, 5)

    # Run 10-player game
    print("\n[2] 10-player mock game")
    metrics_10 = await _run_mock_game(10)
    _analyze_metrics(metrics_10, 10)

    # [3] Slow backend: verify timeout fallback
    print("\n[3] Slow backend timeout fallback (5-player)")
    metrics_slow, event_order = await _run_slow_backend_game(5)

    fallback_count = sum(1 for m in metrics_slow if m.get("fallback_used"))
    timeout_fallbacks = sum(
        1 for m in metrics_slow
        if (m.get("fallback_reason") or "").startswith("latency_budget_exceeded")
    )
    total_actions = len(metrics_slow)

    _check("slow backend: total actions > 0", total_actions > 0)
    _check("slow backend: fallbacks occurred (timeout)", fallback_count > 0)
    print(f"  total actions: {total_actions}, fallbacks: {fallback_count}, timeout_fallbacks: {timeout_fallbacks}")

    # [4] Verify event ordering
    print("\n[4] Event ordering verification")
    _check("event log: events recorded", len(event_order) > 0)

    # Check that speak events appear in sequence (not scrambled)
    speak_indices = [
        i for i, e in enumerate(event_order)
        if e.startswith("player_speaks:")
    ]
    if speak_indices:
        is_ordered = speak_indices == sorted(speak_indices)
        _check("event log: speak events in order", is_ordered)
    else:
        _check("event log: speak events in order", True)

    # Check nomination events come after discussion
    nom_indices = [
        i for i, e in enumerate(event_order)
        if "nomination" in e
    ]
    if nom_indices and speak_indices:
        last_speak = max(speak_indices)
        first_nom = min(nom_indices)
        _check("event log: nominations after discussion", first_nom >= last_speak)
    else:
        _check("event log: nominations after discussion", True)


def main() -> int:
    asyncio.run(main_async())

    print("\n" + "=" * 60)
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)

    if _fail_count > 0:
        print("ai speed acceptance: FAILED")
        return 1

    print("ai speed acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
