"""
GameOrchestrator 委托 / 辅助方法层（从 game_loop.py facade 抽出）

设计目标（见 `DECISIONS.md` D006）：facade 仅做编排与路由，行为逻辑下沉到子模块
（agents/claims/grimoire/info/metrics/phases/settlement）。本模块承载从
`GameOrchestrator` 抽出的极薄委托包装与辅助方法，由 `GameOrchestrator` 继承。
所有方法仅通过 `self` 访问 orchestrator 实例属性/子模块，调用点保持 `self._x(...)`
不变，故行为完全一致。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from src.agents.base_agent import BaseAgent
from src.orchestrator.metrics import MetricsCollector
from src.orchestrator.phases import DayDiscussionHandler
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GameEvent,
    GamePhase,
    GrimoireInfo,
    PlayerState,
    Visibility,
)

logger = logging.getLogger(__name__)


class GameOrchestratorDelegation:
    """极薄委托包装 + 辅助方法（按关注点分组，均转调子模块）。"""

    # -- MetricsCollector delegation (batch 1) --

    async def _timed_act(
        self,
        agent: BaseAgent,
        visible_state: Any,
        action_type: str,
        legal_context: Any = None,
        player_id: str = "",
        phase: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await self.metrics_collector._timed_act(
            agent, visible_state, action_type, legal_context, player_id, phase, **kwargs
        )

    @staticmethod
    def _should_wait_without_orchestrator_timeout(agent: BaseAgent, action_type: str) -> bool:
        return MetricsCollector._should_wait_without_orchestrator_timeout(agent, action_type)

    def _action_budget_ms(self, agent: BaseAgent, action_type: str) -> int:
        return self.metrics_collector._action_budget_ms(agent, action_type)

    @staticmethod
    def _latest_agent_metric(agent: BaseAgent, action_type: str) -> dict[str, Any] | None:
        return MetricsCollector._latest_agent_metric(agent, action_type)

    def _record_speech_metric_from_action(
        self,
        visible_state: Any,
        action_type: str,
        action: dict[str, Any],
        agent_metric: dict[str, Any] | None,
        orchestrator_fallback: bool,
        orchestrator_reason: str,
    ) -> None:
        self.metrics_collector._record_speech_metric_from_action(
            visible_state,
            action_type,
            action,
            agent_metric,
            orchestrator_fallback,
            orchestrator_reason,
        )

    @staticmethod
    def _latency_fallback(action_type: str, legal_context: Any = None) -> dict[str, Any]:
        return MetricsCollector._latency_fallback(action_type, legal_context)

    @staticmethod
    def _smart_latency_fallback(
        agent: Any,
        action_type: str,
        visible_state: Any,
        legal_context: Any,
        reason: str,
    ) -> dict[str, Any]:
        return MetricsCollector._smart_latency_fallback(
            agent, action_type, visible_state, legal_context, reason
        )

    def get_action_latency_summary(self) -> dict[str, Any]:
        return self.metrics_collector.get_action_latency_summary()

    def _record_recent_exception(self, context: str, exc: Exception) -> None:
        self.metrics_collector._record_recent_exception(context, exc)

    def _human_player_ids(self) -> set[str]:
        return self.metrics_collector._human_player_ids()

    def _ai_discussion_message_limit(self) -> int | None:
        return self.metrics_collector._ai_discussion_message_limit()

    def _record_pace_event(self, event: dict[str, Any]) -> None:
        self.metrics_collector._record_pace_event(event)

    def _collect_ai_action_records(self) -> list[dict[str, Any]]:
        return self.metrics_collector._collect_ai_action_records()

    def _snapshot_ai_action_positions(self) -> dict[str, int]:
        return self.metrics_collector._snapshot_ai_action_positions()

    def _collect_ai_action_records_since(self, positions: dict[str, int]) -> list[dict[str, Any]]:
        return self.metrics_collector._collect_ai_action_records_since(positions)

    # -- MetricsCollector delegation (batch 2) --

    @staticmethod
    def _percentile(sorted_values: list[float], p: float) -> float:
        return MetricsCollector._percentile(sorted_values, p)

    def _latency_stats(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self.metrics_collector._latency_stats(records)

    def _latency_by_action_type(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self.metrics_collector._latency_by_action_type(records)

    def _summarize_ai_action_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        return self.metrics_collector._summarize_ai_action_records(records)

    def collect_ai_action_metrics(self, limit: int = 40) -> dict[str, Any]:
        return self.metrics_collector.collect_ai_action_metrics(limit)

    def collect_runtime_diagnostics(self) -> dict[str, Any]:
        return self.metrics_collector.collect_runtime_diagnostics()

    def _make_trace_id(self, prefix: str) -> str:
        return f"{prefix}-{str(uuid.uuid4())[:8]}"

    def _get_storyteller_client_id(self) -> str | None:
        return self.state.config.storyteller_client_id if self.state.config else None

    def _update_payload(self, **kwargs: Any) -> None:
        payload = dict(self.state.payload)
        payload.update(kwargs)
        self.state = self.state.with_update(payload=payload)

    def _set_nomination_state(self, **kwargs: Any) -> None:
        payload = dict(self.state.payload)
        nomination_state = dict(payload.get("nomination_state", {}))
        nomination_state.update(kwargs)
        payload["nomination_state"] = nomination_state
        self.state = self.state.with_update(payload=payload)

        # 触发状态更新事件，以便前端 fetchGameState
        asyncio.create_task(
            self._publish_event(
                GameEvent(
                    event_type="nomination_state_updated",
                    phase=self.state.phase,
                    round_number=self.state.round_number,
                    payload=nomination_state,
                    visibility=Visibility.PUBLIC,
                )
            )
        )

    def _append_nomination_history(self, entry: dict[str, Any]) -> None:
        payload = dict(self.state.payload)
        day_number = self.state.day_number
        history = [
            item
            for item in payload.get("nomination_history", [])
            if item.get("day_number") == day_number
        ]
        history.append({"day_number": day_number, **entry})
        payload["nomination_history"] = history[-12:]
        self.state = self.state.with_update(payload=payload)

    def _player_label(self, player_id: str | None) -> str:
        player = self.state.get_player(player_id) if player_id else None
        return player.name if player else (player_id or "未知玩家")

    def _should_storyteller_auto_act(self) -> bool:
        """检查说书人是否应由 AI 自动执行逻辑。"""
        if not self.storyteller_agent:
            return False
        # 如果模式是自动，或者人类模式下选择了托管
        return getattr(self.storyteller_agent, "mode", "auto") == "auto" or getattr(
            self.storyteller_agent, "delegated", False
        )

    # -- GrimoireManager delegation --

    def _log_storyteller(self, event: str, **fields: Any) -> None:
        self.grimoire_manager._log_storyteller(event, **fields)

    def _record_storyteller_judgement(
        self, category: str, decision: str, reason: str | None = None, **fields: Any
    ) -> None:
        self.grimoire_manager._record_storyteller_judgement(category, decision, reason, **fields)

    def _normalize_private_info_payload(self, player: PlayerState, payload: dict) -> dict:
        return self.private_info_normalizer._normalize_private_info_payload(player, payload)

    def _record_data_snapshot(self, stage: str, **extra_summary: Any) -> None:
        self.metrics_collector._record_data_snapshot(stage, **extra_summary)

    def _build_ai_data_snapshot_summary(self) -> dict[str, Any]:
        return self.metrics_collector._build_ai_data_snapshot_summary()

    async def _publish_event(self, event: GameEvent) -> None:
        try:
            # 由于 GameEvent 是 frozen 的，我们需要 model_copy 来更新
            updates = {}
            if getattr(event, "day_number", 1) == 1 and self.state.day_number != 1:
                updates["day_number"] = self.state.day_number

            if updates:
                event = event.model_copy(update=updates)
        except Exception as e:
            logger.warning(f"Error updating event before publish: {e}")
        self.state = self.state.with_event(event)
        await self.event_bus.publish(event)
        if (
            event.event_type in {"player_speaks", "defense_started"}
            and "extracted_claims" not in event.payload
        ):
            self._schedule_claim_extraction(event)

    # -- ClaimExtractor delegation --

    def _schedule_claim_extraction(self, event: GameEvent) -> None:
        self.claim_extractor._schedule_claim_extraction(event)

    async def _extract_claims_background(self, event: GameEvent) -> None:
        await self.claim_extractor._extract_claims_background(event)

    async def _extract_claims_via_llm(self, event: GameEvent) -> list[dict[str, Any]]:
        return await self.claim_extractor._extract_claims_via_llm(event)

    # -- AgentManager delegation --

    def register_agent(self, agent: BaseAgent) -> None:
        self.agent_manager.register_agent(agent)

    def _sync_agent(self, player_id: str, trace_id: str) -> None:
        self.agent_manager._sync_agent(player_id, trace_id)

    def _sync_all_agents(self, trace_id: str = "BOTC-FLOW-SYNC") -> None:
        self.agent_manager._sync_all_agents(trace_id)

    async def _batch_reflect_agents(self, phase: GamePhase) -> None:
        await self.agent_manager._batch_reflect_agents(phase)

    def _get_agent_visible_state(self, player_id: str) -> AgentVisibleState | None:
        return self.agent_manager._get_agent_visible_state(player_id)

    def _get_agent_legal_context(
        self,
        player_id: str,
        visible_state: AgentVisibleState | None = None,
    ) -> AgentActionLegalContext:
        return self.agent_manager._get_agent_legal_context(player_id, visible_state)

    def _ensure_player_alive(self, player_id: str, context: str = "action") -> PlayerState:
        return self.agent_manager._ensure_player_alive(player_id, context)

    async def _on_any_event(self, event: GameEvent) -> None:
        self._mark_progress()
        self.event_log.append(event)
        await self.broker.broadcast_event(event, self.state)

    # --------------- 结算报告 ---------------

    def _build_settlement_report(self) -> dict[str, Any]:
        return self.settlement_builder._build_settlement_report()

    def _determine_victory_reason(self) -> str:
        return self.settlement_builder._determine_victory_reason()

    def _summarize_event(self, event: GameEvent) -> str:
        return self.settlement_builder._summarize_event(event)

    # --------------- 具体阶段逻辑 ---------------

    async def _run_setup_phase(self) -> None:
        logger.info("等说书人(h1)配置游戏人数...")

    async def _run_first_night(self) -> None:
        await self.night_phase_handler._run_first_night()

    def get_grimoire_info(self) -> GrimoireInfo:
        return self.grimoire_manager.get_grimoire_info()

    def _update_grimoire(self) -> None:
        self.grimoire_manager._update_grimoire()

    async def _publish_private_info(
        self, phase: GamePhase, target: str, trace_id: str, payload: dict
    ) -> None:
        await self.private_info_normalizer._publish_private_info(phase, target, trace_id, payload)

    async def _run_night(self) -> None:
        await self.night_phase_handler._run_night()

    async def _resolve_on_death_triggers(self, pre_alive: set[str]) -> None:
        await self.night_phase_handler._resolve_on_death_triggers(pre_alive)

    async def _execute_slayer_shot(self, actor_id: str, target_id: str) -> None:
        await self.night_phase_handler._execute_slayer_shot(actor_id, target_id)

    async def _execute_night_actions(self, phase: GamePhase) -> None:
        await self.night_phase_handler._execute_night_actions(phase)

    async def _distribute_night_info(self, phase: GamePhase) -> None:
        await self.night_phase_handler._distribute_night_info(phase)

    def _scramble_info(self, info: dict) -> dict:
        return self.night_phase_handler._scramble_info(info)

    def _clear_transient_statuses(self) -> None:
        self.night_phase_handler._clear_transient_statuses()

    def _compute_discussion_rounds(self) -> int:
        return self.day_discussion_handler._compute_discussion_rounds()

    async def _run_day_discussion(self) -> None:
        await self.day_discussion_handler._run_day_discussion()

    def _dedupe_public_speech_content(
        self, content: str, actor_id: str, discussion_round: int
    ) -> str:
        return self.day_discussion_handler._dedupe_public_speech_content(
            content, actor_id, discussion_round
        )

    @staticmethod
    def _player_name_for_event(player_id: str, visible_state: AgentVisibleState) -> str:
        return DayDiscussionHandler._player_name_for_event(player_id, visible_state)

    def _draft_focus_target(self, self_player_id: str, visible_state: AgentVisibleState) -> str:
        return self.day_discussion_handler._draft_focus_target(self_player_id, visible_state)

    async def handle_chat(self, sender_id: str, content: str, is_private: bool = False) -> None:
        await self.day_discussion_handler.handle_chat(sender_id, content, is_private)

    async def _run_nomination_phase(self) -> None:
        await self.nomination_voting_handler._run_nomination_phase()

    def _select_nomination_intent(
        self, intents: dict[str, dict[str, Any]]
    ) -> tuple[str, str] | None:
        return self.nomination_voting_handler._select_nomination_intent(intents)

    def _select_audit_nomination_fallback(self) -> tuple[str, str] | None:
        return self.nomination_voting_handler._select_audit_nomination_fallback()

    def _can_continue_nomination_rounds(self, nomination_round: int, max_rounds: int) -> bool:
        return self.nomination_voting_handler._can_continue_nomination_rounds(
            nomination_round, max_rounds
        )

    async def _collect_nomination_intents(
        self, nomination_round: int
    ) -> dict[str, dict[str, Any]]:
        return await self.nomination_voting_handler._collect_nomination_intents(nomination_round)

    async def _handle_virgin_trigger(
        self, nominator_id: str, nominee_id: str, trace_id: str
    ) -> bool:
        return await self.nomination_voting_handler._handle_virgin_trigger(
            nominator_id, nominee_id, trace_id
        )

    async def _run_defense_and_voting(self, nominee_id: str, trace_id: str) -> None:
        await self.nomination_voting_handler._run_defense_and_voting(nominee_id, trace_id)
