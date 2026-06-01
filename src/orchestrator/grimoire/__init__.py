"""GrimoireManager — grimoire snapshot and storyteller logging."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.state.game_state import (
    GrimoireInfo,
    PlayerGrimoireInfo,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)
storyteller_logger = logging.getLogger("storyteller")


class GrimoireManager:
    """Grimoire snapshot and storyteller logging extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    def get_grimoire_info(self) -> GrimoireInfo:
        """生成当前的魔典快照（实时计算）。"""
        state = self._o.state
        ordered_player_ids = state.seat_order if state.seat_order else tuple(p.player_id for p in state.players)
        grimoire_players = []
        for pid in ordered_player_ids:
            player = state.get_player(pid)
            if not player:
                continue
            grimoire_players.append(PlayerGrimoireInfo(
                player_id=player.player_id,
                name=player.name,
                role_id=player.role_id,
                true_role_id=player.true_role_id,
                perceived_role_id=player.perceived_role_id,
                public_claim_role_id=player.public_claim_role_id,
                fake_role=player.fake_role,
                team=player.team,
                current_team=player.current_team,
                is_alive=player.is_alive,
                is_poisoned=player.is_poisoned,
                is_drunk=player.is_drunk,
                storyteller_notes=player.storyteller_notes,
                ongoing_effects=player.ongoing_effects,
            ))

        # 收集夜晚行动记录
        night_actions = tuple(
            {"event_type": event.event_type, "actor": event.actor, "target": event.target, "payload": event.payload, "trace_id": event.trace_id}
            for event in state.event_log
            if event.event_type in {"night_action_requested", "night_action_resolved", "private_info_delivered", "role_transfer"}
        )
        return GrimoireInfo(
            players=tuple(grimoire_players),
            night_actions=night_actions,
            reminders=tuple(state.payload.get("reminders", []))
        )

    def _update_grimoire(self) -> None:
        """更新状态中的魔典快照（用于存档和持久化）。"""
        grimoire = self.get_grimoire_info()
        self._o.state = self._o.state.with_update(grimoire=grimoire)
        self._log_storyteller(
            "grimoire_update",
            players=len(grimoire.players),
            night_actions=len(grimoire.night_actions),
        )

    def _log_storyteller(self, event: str, **fields: Any) -> None:
        parts = [f"{key}={value}" for key, value in fields.items() if value is not None]
        storyteller_logger.info("[%s] %s", event, " ".join(parts) if parts else "")

    def _record_storyteller_judgement(self, category: str, decision: str, reason: str | None = None, **fields: Any) -> None:
        fields.setdefault("phase", self._o.state.phase.value)
        fields.setdefault("day_number", self._o.state.day_number)
        fields.setdefault("round_number", self._o.state.round_number)
        if self._o.storyteller_agent and hasattr(self._o.storyteller_agent, "record_judgement"):
            self._o.storyteller_agent.record_judgement(category, decision, reason, **fields)
            return
        parts = [f"decision={decision}"]
        if reason:
            parts.append(f"reason={reason}")
        parts.extend(f"{key}={value}" for key, value in fields.items() if value is not None)
        storyteller_logger.info("[judgement][%s] %s", category, " ".join(parts))
