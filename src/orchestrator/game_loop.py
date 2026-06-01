"""游戏主循环 (Game Orchestrator)。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from typing import Any

from src.agents.base_agent import BaseAgent
from src.content.trouble_brewing_terms import get_role_name
from src.engine.nomination import NominationManager
from src.engine.phase_manager import PhaseManager
from src.engine.rule_engine import RuleEngine
from src.engine.roles.base_role import get_role_class
from src.engine.victory_checker import VictoryChecker
from src.engine.data_collector import GameDataCollector
from src.debug.game_debug_logger import game_debug_logger
from src.orchestrator.agents import AgentManager
from src.orchestrator.claims import ClaimExtractor
from src.orchestrator.event_bus import EventBus
from src.orchestrator.grimoire import GrimoireManager
from src.orchestrator.info import PrivateInfoNormalizer
from src.orchestrator.information_broker import InformationBroker
from src.orchestrator.metrics import MetricsCollector
from src.orchestrator.phases import DayDiscussionHandler, NightPhaseHandler, NominationVotingHandler
from src.orchestrator.settlement import SettlementBuilder
from src.orchestrator.speech_cache import SpeechPreGenCache
from src.state.event_log import EventLog
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    AbilityTrigger,
    ChatMessage,
    DifficultyLevel,
    GameConfig,
    GameEvent,
    GamePhase,
    GameState,
    GrimoireInfo,
    PlayerGrimoireInfo,
    PlayerState,
    PlayerStatus,
    RoleType,
    Team,
    Visibility,
)
from src.state.game_record import GameRecordStore
from src.state.snapshot import SnapshotManager

logger = logging.getLogger(__name__)
storyteller_logger = logging.getLogger("storyteller")


class GameOrchestrator:
    """顶级容器，协调规则、Agent 和状态。"""

    MAX_AGENT_RETRIES = 5  # 最大重试次数，防止 AI/人类玩家意图异常导致卡死

    def __init__(self, initial_state: GameState):
        self.state = initial_state
        self.phase_manager = PhaseManager()
        self.event_bus = EventBus()
        self.event_log = EventLog()
        self.snapshot_manager = SnapshotManager()
        self.broker = InformationBroker()
        self.storyteller_agent = None
        self.default_agent_backend = None
        self.winner: Team | None = None
        self.settlement_report: dict[str, Any] | None = None
        self.record_store = GameRecordStore()
        self.data_collector = GameDataCollector()
        self._setup_done: asyncio.Future | None = None
        self._setup_started = False
        self._pending_night_action: dict[str, Any] | None = None  # { "player_id": str, "action_type": str, "legal_context": dict }
        self._loop_started_at: float | None = None
        self._last_progress_at: float | None = None
        self._current_waiting_for: str | None = None
        self._recent_exception: dict[str, Any] | None = None
        self._current_night_steps: list[dict[str, Any]] | None = None
        self._current_night_step_index: int = -1
        self._phase_started_at: float | None = None
        self._phase_started_action_positions: dict[str, int] = {}
        self._phase_duration_history: list[dict[str, Any]] = []
        self._action_latencies: list[dict[str, Any]] = []
        # Orchestrator 预算必须大于 agent 内部预算，让 agent 的智能 fallback 优先执行。
        # Agent 预算: speak=2.0s, defense_speech=2.5s, vote=0.8s, nomination_intent=1.0s, night_action=1.5s
        # vote/nomination_intent 预算提高到 2500ms，确保 agent 的智能 fallback 有足够时间执行。
        self._action_latency_budgets: dict[str, int] = {
            "vote": 2500,
            "nomination_intent": 2500,
            "night_action": 2500,
            "speak": 3500,
            "defense_speech": 4000,
        }
        # Speech pre-generation cache: created per round in _run_day_discussion
        self._claim_extraction_tasks: set[asyncio.Task] = set()
        self._claim_extraction_failures: dict[str, int] = {}
        self.agent_manager = AgentManager(self)
        self.claim_extractor = ClaimExtractor(self)
        self.grimoire_manager = GrimoireManager(self)
        self.metrics_collector = MetricsCollector(self)
        self.private_info_normalizer = PrivateInfoNormalizer(self)
        self.settlement_builder = SettlementBuilder(self)
        self.night_phase_handler = NightPhaseHandler(self)
        self.day_discussion_handler = DayDiscussionHandler(self)
        self.nomination_voting_handler = NominationVotingHandler(self)
        self.event_bus.subscribe("*", self._on_any_event, priority=0)

    def _mark_progress(self, waiting_for: str | None = None) -> None:
        self._last_progress_at = time.time()
        self._current_waiting_for = waiting_for

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
        return await self.metrics_collector._timed_act(agent, visible_state, action_type, legal_context, player_id, phase, **kwargs)

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
        self.metrics_collector._record_speech_metric_from_action(visible_state, action_type, action, agent_metric, orchestrator_fallback, orchestrator_reason)

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
        return MetricsCollector._smart_latency_fallback(agent, action_type, visible_state, legal_context, reason)

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
        asyncio.create_task(self._publish_event(GameEvent(
            event_type="nomination_state_updated",
            phase=self.state.phase,
            round_number=self.state.round_number,
            payload=nomination_state,
            visibility=Visibility.PUBLIC
        )))

    def _append_nomination_history(self, entry: dict[str, Any]) -> None:
        payload = dict(self.state.payload)
        day_number = self.state.day_number
        history = [
            item for item in payload.get("nomination_history", [])
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
        return (
            getattr(self.storyteller_agent, "mode", "auto") == "auto"
            or getattr(self.storyteller_agent, "delegated", False)
        )

    # -- GrimoireManager delegation --

    def _log_storyteller(self, event: str, **fields: Any) -> None:
        self.grimoire_manager._log_storyteller(event, **fields)

    def _record_storyteller_judgement(self, category: str, decision: str, reason: str | None = None, **fields: Any) -> None:
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
            if getattr(event, 'day_number', 1) == 1 and self.state.day_number != 1:
                updates["day_number"] = self.state.day_number
                
            if updates:
                event = event.model_copy(update=updates)
        except Exception as e:
            logger.warning(f"Error updating event before publish: {e}")
        self.state = self.state.with_event(event)
        await self.event_bus.publish(event)
        if event.event_type in {"player_speaks", "defense_started"} and "extracted_claims" not in event.payload:
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

    async def run_setup(self, player_count: int, host_id: str, is_human: bool = True):
        if self._setup_started or self.phase_manager.current_phase != GamePhase.SETUP:
            raise RuntimeError("BOTC-FLOW-SETUP: 当前对局已开始或已配置，不能重复 setup")
        await self.run_setup_with_options(player_count, host_id, is_human)

    async def run_setup_with_options(
        self,
        player_count: int,
        host_id: str,
        is_human: bool = True,
        discussion_rounds: int | None = None,
        storyteller_mode: str | None = None,
        audit_mode: bool = False,
        max_nomination_rounds: int | None = None,
        ai_discussion_message_limit: int | None = None,
        backend_mode: str = "auto",
        human_mode: str | None = None,
        human_client_id: str | None = None,
        storyteller_client_id: str | None = None,
        storyteller_delegated: bool = False,
        difficulty: str = "standard",
    ) -> None:
        logger.info(f"[run_setup_with_options] Starting setup for {player_count} players. host_id={host_id} mode={human_mode}")
        if self._setup_started or self.phase_manager.current_phase != GamePhase.SETUP:
            logger.warning("[run_setup_with_options] Setup already started or not in SETUP phase. phase=%s", self.phase_manager.current_phase)
            raise RuntimeError("BOTC-FLOW-SETUP: 当前对局已开始或已配置，不能重复 setup")

        self._setup_started = True
        debug_dir = game_debug_logger.start_game(
            self.state.game_id,
            {
                "player_count": player_count,
                "host_id": host_id,
                "human_mode": human_mode or ("player" if is_human else "none"),
                "backend_mode": backend_mode,
                "difficulty": difficulty,
            },
        )
        if debug_dir:
            logger.info("[run_setup_with_options] Debug logs for this game: %s", debug_dir)
        from src.engine.scripts import SCRIPTS, distribute_roles

        script = SCRIPTS["trouble_brewing"]
        role_ids, bluffs = distribute_roles(script, player_count)
        resolved_human_mode = human_mode or ("player" if is_human else "none")
        resolved_human_client_id = human_client_id or (host_id if resolved_human_mode == "player" else None)
        resolved_storyteller_client_id = storyteller_client_id or (host_id if resolved_human_mode == "storyteller" else None)
        human_seat = random.randint(0, player_count - 1) if resolved_human_mode == "player" and resolved_human_client_id else -1
        players: list[PlayerState] = []
        seat_order: list[str] = []

        for seat_index, role_id in enumerate(role_ids):
            player_id = resolved_human_client_id if seat_index == human_seat else f"p{seat_index + 1}"
            role_cls = get_role_class(role_id)
            team = role_cls.get_definition().team if role_cls else Team.GOOD
            fake_role = None
            statuses = (PlayerStatus.ALIVE,)
            if role_id == "drunken":
                fake_role = await self.storyteller_agent.decide_drunk_role(script, role_ids) if self._should_storyteller_auto_act() else "washerwoman"
                statuses = (PlayerStatus.ALIVE, PlayerStatus.DRUNK)
            players.append(
                PlayerState(
                    player_id=player_id,
                    name="Human Player" if player_id == resolved_human_client_id else f"Player {seat_index + 1}",
                    role_id=role_id,
                    team=team,
                    true_role_id=role_id,
                    perceived_role_id=fake_role or role_id,
                    current_team=team,
                    fake_role=fake_role,
                    statuses=statuses,
                )
            )
            seat_order.append(player_id)

        payload = dict(self.state.payload)
        if "fortune_teller" in role_ids:
            goods = [p for p in players if p.current_team == Team.GOOD and p.true_role_id != "fortune_teller"]
            if goods:
                payload["fortune_teller_red_herring"] = random.choice(goods).player_id

        self.state = self.state.with_update(
            players=tuple(players),
            seat_order=tuple(seat_order),
            bluffs=tuple(bluffs),
            payload=payload,
            config=GameConfig(
                player_count=player_count,
                script=script,
                script_id=script.script_id,
                human_client_id=resolved_human_client_id,
                human_mode=resolved_human_mode,
                storyteller_client_id=resolved_storyteller_client_id,
                human_player_ids=[resolved_human_client_id] if resolved_human_mode == "player" and resolved_human_client_id else [],
                is_human_participant=resolved_human_mode == "player",
                storyteller_mode=storyteller_mode or ("human" if resolved_human_mode == "storyteller" else getattr(self.storyteller_agent, "mode", "auto")),
                storyteller_delegated=storyteller_delegated,
                backend_mode=backend_mode,
                audit_mode=audit_mode,
                discussion_rounds=discussion_rounds or 3,
                ai_discussion_message_limit=ai_discussion_message_limit,
                max_nomination_rounds=max_nomination_rounds,
                difficulty=DifficultyLevel(difficulty),
            ),
        )
        if self.storyteller_agent:
            new_mode = self.state.config.storyteller_mode
            logger.info(f"[run_setup_with_options] Updating storyteller_agent mode to {new_mode}, delegated={storyteller_delegated}")
            self.storyteller_agent.mode = new_mode
            if hasattr(self.storyteller_agent, "delegated"):
                self.storyteller_agent.delegated = storyteller_delegated
        self._update_payload(nomination_state={"stage": "idle"}, nomination_history=[])
        self._update_grimoire()

        from src.agents.ai_agent import AIAgent, Persona
        from src.agents.persona_registry import ARCHETYPES
        from src.llm.openai_backend import OpenAIBackend

        backend = self.default_agent_backend or (getattr(self.storyteller_agent, "backend", None)) or OpenAIBackend()
        player_count = len(self.state.players)
        archetype_keys = list(ARCHETYPES.keys())
        rng = random.Random(self.state.game_id)
        rng.shuffle(archetype_keys)

        self.data_collector.start_game(self.state.game_id)
        for i, player in enumerate(self.state.players):
            if player.player_id not in self.broker.agents:
                # 轮询分配不同的性格原型
                arch_key = archetype_keys[i % len(archetype_keys)]
                arch = ARCHETYPES[arch_key]
                persona = Persona(
                    description=arch.description,
                    speaking_style=arch.speaking_style,
                    archetype=arch_key
                )
                
                difficulty = self.state.config.difficulty.value if self.state.config else "standard"
                self.register_agent(AIAgent(
                    player.player_id,
                    player.name,
                    backend,
                    persona,
                    player_count=player_count,
                    data_collector=self.data_collector,
                    difficulty=difficulty,
                ))

        logger.info("[run_setup_with_options] Syncing all agents")
        self._sync_all_agents("BOTC-FLOW-SETUP")
        if not self._setup_done:
            self._setup_done = asyncio.get_running_loop().create_future()
        if not self._setup_done.done():
            logger.info("[run_setup_with_options] Setting _setup_done result to True")
            self._setup_done.set_result(True)
        logger.info("[run_setup_with_options] Setup completed successfully")

    async def run_game_loop(self) -> Team | None:
        try:
            if not self._setup_done:
                self._setup_done = asyncio.get_running_loop().create_future()
            self._loop_started_at = time.time()
            self._mark_progress("setup")
            logger.info("=== 游戏开始 ===")
            self.snapshot_manager.take_snapshot(self.state)
            await self._transition_and_run(GamePhase.SETUP)

            while not self.winner:
                self.winner = self.state.winning_team or VictoryChecker.check_victory(self.state)
                if self.winner:
                    await self._transition_and_run(GamePhase.GAME_OVER)
                    break

                phase = self.phase_manager.current_phase
                if phase == GamePhase.SETUP:
                    self._mark_progress("setup_done")
                    logger.info("[run_game_loop] Waiting for _setup_done...")
                    await self._setup_done
                    logger.info("[run_game_loop] _setup_done received. Transitioning to FIRST_NIGHT")
                    await self._transition_and_run(GamePhase.FIRST_NIGHT)
                elif phase in (GamePhase.FIRST_NIGHT, GamePhase.NIGHT):
                    await self._transition_and_run(GamePhase.DAY_DISCUSSION)
                elif phase == GamePhase.DAY_DISCUSSION:
                    await self._transition_and_run(GamePhase.NOMINATION)
                elif phase in (GamePhase.NOMINATION, GamePhase.EXECUTION):
                    await self._transition_and_run(GamePhase.NIGHT)
                else:
                    break
            return self.winner
        finally:
            if game_debug_logger.game_id == self.state.game_id:
                logger.info("Ending debug logs for game %s", self.state.game_id)
                game_debug_logger.end_game()

    async def _transition_and_run(self, target_phase: GamePhase) -> None:
        phase_start = time.perf_counter()
        self._phase_started_at = time.time()
        self._phase_started_action_positions = self._snapshot_ai_action_positions()
        self._mark_progress(f"phase:{target_phase.value}")
        if target_phase != self.phase_manager.current_phase:
            await self._archive_agent_phase_memories()
        if target_phase != self.phase_manager.current_phase or target_phase == GamePhase.SETUP:
            self.phase_manager.transition_to(target_phase)
        self.state = self.state.with_update(
            phase=target_phase,
            round_number=self.phase_manager.round_number,
            day_number=self.phase_manager.day_number,
        )
        if target_phase == GamePhase.GAME_OVER:
            self._set_nomination_state(
                stage="idle",
                result_phase="game_over",
                current_nominator=None,
                current_nominee=None,
                votes_cast=0,
                yes_votes=0,
                threshold=(self.state.alive_count // 2) + 1 if self.state.alive_count else 0,
                votes={},
                defense_text=None,
                last_result=None,
            )
            # 结算报告生成与持久化
            self.settlement_report = self._build_settlement_report()
            self.state = self.state.with_update(winning_team=self.winner)
            await self._publish_event(GameEvent(
                event_type="game_settlement",
                phase=GamePhase.GAME_OVER,
                round_number=self.phase_manager.round_number,
                trace_id=self._make_trace_id("BOTC-SETTLEMENT"),
                visibility=Visibility.PUBLIC,
                payload=self.settlement_report,
            ))
            try:
                await self.record_store.save_game(
                    self.state.game_id, self.state, self.settlement_report
                )
            except Exception as exc:
                logger.error("Failed to persist game record: %s", exc)
            self._record_data_snapshot(
                "game_settlement_ready",
                winning_team=self.winner.value if self.winner else None,
                timeline_items=len(self.settlement_report.get("timeline", [])) if self.settlement_report else 0,
            )
        phase_event = GameEvent(
            event_type="phase_changed",
            phase=target_phase,
            round_number=self.phase_manager.round_number,
            trace_id=self._make_trace_id("BOTC-FLOW-PHASE"),
            visibility=Visibility.PUBLIC,
            payload={"day_number": self.phase_manager.day_number},
        )
        await self._publish_event(phase_event)
        self.snapshot_manager.take_snapshot(self.state)

        if self._should_storyteller_auto_act():
            narration = await self.storyteller_agent.narrate_phase(self.state)
            if narration:
                self.state = self.state.with_message(ChatMessage(
                    speaker="storyteller",
                    content=narration,
                    phase=target_phase,
                    round_number=self.phase_manager.round_number,
                ))

        # [A3-ST-6] 如果开启了 AI 说书人自动动作，在每个阶段开始时进行局势分析
        if self.storyteller_agent and self._should_storyteller_auto_act():
            try:
                await self.storyteller_agent.analyze_game_situation(self.state)
            except Exception as exc:
                logger.warning("Storyteller analysis failed: %s", exc)

        if target_phase == GamePhase.SETUP:
            await self._run_setup_phase()
        elif target_phase == GamePhase.FIRST_NIGHT:
            await self._run_first_night()
        elif target_phase == GamePhase.NIGHT:
            await self._run_night()
        elif target_phase == GamePhase.DAY_DISCUSSION:
            await self._run_day_discussion()
        elif target_phase == GamePhase.NOMINATION:
            await self._run_nomination_phase()
        duration_ms = int((time.perf_counter() - phase_start) * 1000)
        phase_action_summary = self._summarize_ai_action_records(
            self._collect_ai_action_records_since(self._phase_started_action_positions)
        )
        self._phase_duration_history.append(
            {
                "phase": target_phase.value,
                "day_number": self.state.day_number,
                "round_number": self.state.round_number,
                "duration_ms": duration_ms,
                "ai_action_count": phase_action_summary["action_count"],
                "ai_total_tokens": phase_action_summary["total_tokens"],
                "ai_average_tokens_per_action": phase_action_summary["average_tokens_per_action"],
                "ai_fallback_count": phase_action_summary["fallback_count"],
                "ai_fallback_token_share": phase_action_summary["fallback_token_share"],
                "ai_top_token_action": phase_action_summary["top_token_actions"][0] if phase_action_summary["top_token_actions"] else None,
                "ai_tokens_by_action_type": phase_action_summary["tokens_by_action_type"],
                "ai_fallback_by_action_type": phase_action_summary["fallback_by_action_type"],
            }
        )
        self._phase_duration_history = self._phase_duration_history[-50:]
        self._mark_progress(None)

    async def _archive_agent_phase_memories(self) -> None:
        tasks = []
        for player_id, agent in self.broker.agents.items():
            try:
                visible_state = self._get_agent_visible_state(player_id)
                if visible_state:
                    tasks.append(agent.archive_phase_memory(visible_state))
            except Exception as exc:
                logger.warning("archive_phase_memory setup failed for %s: %s", player_id, exc)
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("[archive] phase memory archiving timed out after 10s")

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

    async def _publish_private_info(self, phase: GamePhase, target: str, trace_id: str, payload: dict) -> None:
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

    def _dedupe_public_speech_content(self, content: str, actor_id: str, discussion_round: int) -> str:
        return self.day_discussion_handler._dedupe_public_speech_content(content, actor_id, discussion_round)

    @staticmethod
    def _player_name_for_event(player_id: str, visible_state: AgentVisibleState) -> str:
        return DayDiscussionHandler._player_name_for_event(player_id, visible_state)

    def _draft_focus_target(self, self_player_id: str, visible_state: AgentVisibleState) -> str:
        return self.day_discussion_handler._draft_focus_target(self_player_id, visible_state)

    async def handle_chat(self, sender_id: str, content: str, is_private: bool = False) -> None:
        await self.day_discussion_handler.handle_chat(sender_id, content, is_private)

    async def _run_nomination_phase(self) -> None:
        await self.nomination_voting_handler._run_nomination_phase()

    def _select_nomination_intent(self, intents: dict[str, dict[str, Any]]) -> tuple[str, str] | None:
        return self.nomination_voting_handler._select_nomination_intent(intents)

    def _select_audit_nomination_fallback(self) -> tuple[str, str] | None:
        return self.nomination_voting_handler._select_audit_nomination_fallback()

    def _can_continue_nomination_rounds(self, nomination_round: int, max_rounds: int) -> bool:
        return self.nomination_voting_handler._can_continue_nomination_rounds(nomination_round, max_rounds)

    async def _collect_nomination_intents(self, nomination_round: int) -> dict[str, dict[str, Any]]:
        return await self.nomination_voting_handler._collect_nomination_intents(nomination_round)

    async def _handle_virgin_trigger(self, nominator_id: str, nominee_id: str, trace_id: str) -> bool:
        return await self.nomination_voting_handler._handle_virgin_trigger(nominator_id, nominee_id, trace_id)

    async def _run_defense_and_voting(self, nominee_id: str, trace_id: str) -> None:
        await self.nomination_voting_handler._run_defense_and_voting(nominee_id, trace_id)

    def export_game_record(self, export_dir: str) -> None:
        """持久化输出事件日志和系统快照到外部文件系统，用于前端回放或调试"""
        import os
        import json
        
        os.makedirs(export_dir, exist_ok=True)
        # 导出快照
        snapshot_path = os.path.join(export_dir, "snapshots.json")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(self.snapshot_manager.export_to_json())
            
        # 导出事件
        event_path = os.path.join(export_dir, "events.json")
        events_data = [e.model_dump(mode="json") for e in self.event_log.events]
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"游戏记录已持久化到目录: {export_dir}")
