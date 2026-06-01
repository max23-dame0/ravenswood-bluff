"""AgentManager — agent lifecycle: registration, sync, reflection."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.agents.base_agent import BaseAgent
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GamePhase,
    PlayerState,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class AgentManager:
    """Agent lifecycle management extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    def register_agent(self, agent: BaseAgent) -> None:
        self._o.broker.register_agent(agent)
        self._sync_agent(agent.player_id, "BOTC-FLOW-SYNC")

    def _sync_agent(self, player_id: str, trace_id: str) -> None:
        if player_id not in self._o.broker.agents:
            return
        private_view = self._o.broker.get_private_view(player_id, self._o.state)
        if not private_view:
            return
        self._o.broker.agents[player_id].synchronize_role(private_view)
        p_state = self._o.state.get_player(player_id)
        logger.info(
            "[role_sync][%s] %s true_role=%s perceived_role=%s current_team=%s",
            trace_id,
            player_id,
            p_state.true_role_id if p_state else "unknown",
            private_view.perceived_role_id,
            private_view.current_team.value,
        )

    def _sync_all_agents(self, trace_id: str = "BOTC-FLOW-SYNC") -> None:
        for player_id in self._o.broker.agents:
            self._sync_agent(player_id, trace_id)

    async def _batch_reflect_agents(self, phase: GamePhase) -> None:
        """Batch reflect for all AI agents at phase boundaries.

        Runs reflect_if_needed() concurrently for all living AI agents,
        allowing them to consolidate working memory into impressions.
        Failures are logged but never block game progression.
        """
        human_ids = self._o._human_player_ids()
        reflect_tasks: list[asyncio.Task] = []
        for player in self._o.state.players:
            if player.player_id in human_ids:
                continue
            if not player.is_alive:
                continue
            agent = self._o.broker.agents.get(player.player_id)
            if not agent:
                continue
            visible_state = self._get_agent_visible_state(player.player_id)
            if not visible_state:
                continue
            if hasattr(agent, "reflect_if_needed"):
                reflect_tasks.append(
                    asyncio.create_task(agent.reflect_if_needed(visible_state))
                )

        if reflect_tasks:
            results = await asyncio.gather(*reflect_tasks, return_exceptions=True)
            reflected = sum(1 for r in results if r is True)
            if reflected:
                logger.info(
                    "[batch_reflect] phase=%s reflected=%d/%d",
                    phase.value, reflected, len(reflect_tasks),
                )

    def _get_agent_visible_state(self, player_id: str) -> AgentVisibleState | None:
        return self._o.broker.get_visible_state(player_id, self._o.state)

    def _get_agent_legal_context(
        self,
        player_id: str,
        visible_state: AgentVisibleState | None = None,
    ) -> AgentActionLegalContext:
        return self._o.broker.get_action_legal_context(player_id, self._o.state, visible_state)

    def _ensure_player_alive(self, player_id: str, context: str = "action") -> PlayerState:
        """[GAME-1.2] 统一存活检查。若玩家不存在或已死亡则抛出 ValueError。"""
        player = self._o.state.get_player(player_id)
        if not player:
            raise ValueError(f"[{context}] 玩家 {player_id} 不存在")
        if not player.is_alive:
            raise ValueError(f"[{context}] 玩家 {player_id} ({player.name}) 已死亡，无法执行操作")
        return player
