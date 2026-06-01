"""LLM-backed speech pre-generation cache.

Generates real LLM drafts in the background while other players are acting,
so when it's your turn the draft is already ready. This converts wall-clock
wait time from N × LLM_latency to ~1 × LLM_latency + small_refinement.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.state.game_state import AgentActionLegalContext, AgentVisibleState

logger = logging.getLogger(__name__)


@dataclass
class CachedDraft:
    """A pre-generated speech draft."""
    content: str
    tone: str
    reasoning: str
    generated_at: float
    event_count_at_gen: int
    player_id: str
    action_type: str = "speak"
    source: str = "pregen_llm"  # pregen_llm | pregen_refined | inline_llm


class SpeechPreGenCache:
    """LLM-backed speech pre-generation cache.

    Lifecycle:
    1. pregenerate_batch() — kick off background LLM drafts for all AI players
    2. get_or_wait() — when it's a player's turn, get draft (wait if still generating)
    3. on_player_spoke() — after each speech, invalidate remaining players' stale drafts
    4. cancel_all() — cancel any pending tasks at end of round
    """

    def __init__(self) -> None:
        # Cache keyed by player_id (one draft per player per round)
        self._cache: dict[str, CachedDraft] = {}
        # Background generation tasks keyed by player_id
        self._tasks: dict[str, asyncio.Task[CachedDraft | None]] = {}
        # Players who haven't spoken yet in this round
        self._pending_players: set[str] = set()
        # Event count at the time of batch pregeneration
        self._batch_event_count: int = 0
        # Stats
        self.stats = {
            "pregen_count": 0,
            "pregen_hit_count": 0,
            "pregen_miss_count": 0,
            "refine_count": 0,
            "inline_count": 0,
        }

    async def pregenerate_batch(
        self,
        agents: dict[str, Any],
        visible_states: dict[str, AgentVisibleState],
        legal_contexts: dict[str, AgentActionLegalContext],
        event_count: int,
    ) -> None:
        """Kick off background LLM drafts for all AI players.

        Each player gets a background task that calls agent.generate_draft_speech().
        Tasks run concurrently — the LLM calls happen in parallel.
        """
        self._batch_event_count = event_count
        self._pending_players = set(visible_states.keys())

        for player_id, vs in visible_states.items():
            agent = agents.get(player_id)
            if not agent:
                continue
            lc = legal_contexts.get(player_id, AgentActionLegalContext())

            # Skip if we already have a fresh draft for this player
            existing = self._cache.get(player_id)
            if existing and existing.event_count_at_gen == event_count:
                self.stats["pregen_hit_count"] += 1
                continue

            # Cancel any existing task for this player
            old_task = self._tasks.get(player_id)
            if old_task and not old_task.done():
                old_task.cancel()

            # Start background generation
            self.stats["pregen_count"] += 1
            task = asyncio.create_task(
                self._generate_draft(player_id, agent, vs, lc, event_count)
            )
            self._tasks[player_id] = task
            task.add_done_callback(lambda t, pid=player_id: self._on_task_done(pid, t))

    async def _generate_draft(
        self,
        player_id: str,
        agent: Any,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        event_count: int,
    ) -> CachedDraft | None:
        """Generate a single draft via the agent's lightweight method."""
        try:
            action = await agent.generate_draft_speech(visible_state, legal_context)
            if not action or not action.get("content"):
                return None
            return CachedDraft(
                content=str(action["content"]),
                tone=action.get("tone", "calm"),
                reasoning=action.get("reasoning", ""),
                generated_at=time.time(),
                event_count_at_gen=event_count,
                player_id=player_id,
                source="pregen_llm",
            )
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            logger.warning("[SpeechPreGen] draft generation failed for %s: %s", player_id, exc)
            return None

    def _on_task_done(self, player_id: str, task: asyncio.Task) -> None:
        """Callback when a background draft task completes."""
        self._tasks.pop(player_id, None)
        try:
            result = task.result()
            if result:
                self._cache[player_id] = result
        except (asyncio.CancelledError, Exception):
            pass

    async def get_or_wait(
        self,
        player_id: str,
    ) -> CachedDraft | None:
        """Get the pre-generated draft for a player, waiting if still generating.

        Waits for the background task to complete (no artificial timeout).
        The orchestrator's _timed_act handles the overall hard timeout.
        Returns None only if generation failed or was cancelled.
        """
        # Check cache first
        cached = self._cache.get(player_id)
        if cached:
            self.stats["pregen_hit_count"] += 1
            return cached

        # Wait for pending task to complete
        task = self._tasks.get(player_id)
        if task and not task.done():
            try:
                result = await asyncio.shield(task)
                if result:
                    self.stats["pregen_hit_count"] += 1
                    return result
            except asyncio.CancelledError:
                self.stats["pregen_miss_count"] += 1
                return None
            except Exception:
                self.stats["pregen_miss_count"] += 1
                return None

        self.stats["pregen_miss_count"] += 1
        return None

    def on_player_spoke(self, player_id: str, event_count: int) -> None:
        """Called after a player speaks. Removes their draft and marks others stale."""
        # Remove the speaker's draft
        self._cache.pop(player_id, None)
        self._pending_players.discard(player_id)

        # Cancel the speaker's task if still running
        task = self._tasks.pop(player_id, None)
        if task and not task.done():
            task.cancel()

        # Update batch event count so remaining drafts are considered stale
        self._batch_event_count = event_count

    def cancel_all(self) -> None:
        """Cancel all pending tasks. Call at end of round or game."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._cache.clear()
        self._pending_players.clear()

    def get_stats(self) -> dict[str, int]:
        """Return cache statistics."""
        return dict(self.stats)
