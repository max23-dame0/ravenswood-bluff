"""DayDiscussionHandler — discussion rounds, speech dedup, chat handling."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.orchestrator.speech_cache import SpeechPreGenCache
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    ChatMessage,
    GameEvent,
    GamePhase,
    PlayerState,
    Team,
    Visibility,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class DayDiscussionHandler:
    """Day discussion logic extracted from GameOrchestrator."""

    # Daytime evil whisper budget: max whispers per evil player per day
    _MAX_DAY_WHISPERS = 3

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator
        self._speech_round_stats: dict[tuple[int, int], dict[str, int]] = {}
        self._day_whisper_counts: dict[str, dict[int, int]] = {}  # sender_id -> {day -> count}

    def _compute_discussion_rounds(self) -> int:
        """Dynamic discussion rounds based on alive player count and game progress."""
        configured = self._o.state.config.discussion_rounds if self._o.state.config else 3
        alive_count = sum(1 for p in self._o.state.players if p.is_alive)

        if alive_count <= 3:
            base = 1
        elif alive_count <= 5:
            base = 2
        else:
            base = configured

        # Day 1 with many players: fewer rounds (not much happened yet)
        if self._o.state.day_number == 1 and alive_count > 5:
            base = min(base, 2)

        return min(base, configured)

    async def _run_day_discussion(self) -> None:
        # 进入白天讨论时，清空昨晚的进度卡片
        self._o._current_night_steps = None
        self._o._current_night_step_index = -1

        self._o.state = self._o.state.with_update(
            nominations_today=(),
            nominees_today=(),
            votes_today={},
            current_nominee=None,
            current_nominator=None,
            execution_candidates=(),
        )
        self._o._update_payload(nomination_history=[])
        rounds = self._compute_discussion_rounds()
        human_ids = self._o._human_player_ids()
        ai_message_limit = self._o._ai_discussion_message_limit()

        for discussion_round in range(1, rounds + 1):
            # Step 1: Identify AI players and prepare visible states upfront
            ai_players: list[PlayerState] = []
            agents_map: dict[str, Any] = {}
            vs_map: dict[str, AgentVisibleState] = {}
            lc_map: dict[str, AgentActionLegalContext] = {}
            for player in self._o.state.players:
                agent = self._o.broker.agents.get(player.player_id)
                if not agent:
                    continue
                if player.player_id not in human_ids:
                    if ai_message_limit is not None and len(ai_players) >= ai_message_limit:
                        self._o._record_pace_event({
                            "kind": "ai_discussion_throttled",
                            "player_id": player.player_id,
                            "discussion_round": discussion_round,
                            "ai_message_limit": ai_message_limit,
                        })
                        continue
                    ai_players.append(player)
                    self._o._mark_progress(f"ai_action:{player.player_id}:speak")
                    vs = self._o._get_agent_visible_state(player.player_id)
                    if vs:
                        lc = self._o._get_agent_legal_context(player.player_id, vs)
                        agents_map[player.player_id] = agent
                        vs_map[player.player_id] = vs
                        lc_map[player.player_id] = lc

            # Step 2: Kick off AI pre-generation BEFORE human loop
            # Background LLM tasks run concurrently while humans speak.
            pregen_cache = SpeechPreGenCache()
            if agents_map:
                event_count = len(self._o.event_log.events)
                await pregen_cache.pregenerate_batch(agents_map, vs_map, lc_map, event_count)

            # Step 3: Process human players (pregen runs in background)
            for player in self._o.state.players:
                agent = self._o.broker.agents.get(player.player_id)
                if not agent:
                    continue
                if player.player_id in human_ids:
                    visible_state = self._o._get_agent_visible_state(player.player_id)
                    if not visible_state:
                        continue
                    legal_context = self._o._get_agent_legal_context(player.player_id, visible_state)
                    self._o._mark_progress(f"human_action:{player.player_id}:speak")
                    action = await self._o._timed_act(
                        agent, visible_state, "speak",
                        legal_context=legal_context,
                        player_id=player.player_id,
                        phase="day_discussion",
                    )
                    if action.get("action") == "skip_discussion":
                        pregen_cache.cancel_all()
                        self._o._record_data_snapshot("day_discussion_complete", discussion_round=discussion_round)
                        return
                    if action.get("action") == "speak" and action.get("content"):
                        content = self._dedupe_public_speech_content(str(action["content"]), player.player_id, discussion_round)
                        payload = {"content": content, "tone": action.get("tone", "calm"), "round": discussion_round}
                        if "extracted_claims" in action:
                            payload["extracted_claims"] = action["extracted_claims"]
                        await self._o._publish_event(GameEvent(
                            event_type="player_speaks",
                            phase=GamePhase.DAY_DISCUSSION,
                            round_number=self._o.state.round_number,
                            trace_id=self._o._make_trace_id("BOTC-FLOW-SPEAK"),
                            actor=player.player_id,
                            visibility=Visibility.PUBLIC,
                            payload=payload,
                        ))
                    if action.get("action") == "slayer_shot":
                        target_id = action.get("target")
                        if target_id:
                            await self._o._execute_slayer_shot(player.player_id, target_id)

            # Step 4: Process AI speeches sequentially
            # Each AI sees the latest state including human speeches from this round.
            for idx, p in enumerate(ai_players):
                speak_agent = self._o.broker.agents.get(p.player_id)
                if not speak_agent:
                    continue
                visible_state = self._o._get_agent_visible_state(p.player_id)
                if not visible_state:
                    continue
                legal_context = self._o._get_agent_legal_context(p.player_id, visible_state)

                # Get pre-generated LLM draft (waits for background task)
                draft = await pregen_cache.get_or_wait(p.player_id)

                try:
                    if draft and draft.content:
                        action = await self._o._timed_act(
                            speak_agent, visible_state, "speak",
                            legal_context=legal_context,
                            player_id=p.player_id,
                            phase="day_discussion",
                            cached_speech_draft=draft.content,
                            refinement_mode=True,
                        )
                        if action:
                            action["speech_source"] = "cache_refined"
                    else:
                        action = await self._o._timed_act(
                            speak_agent, visible_state, "speak",
                            legal_context=legal_context,
                            player_id=p.player_id,
                            phase="day_discussion",
                        )
                        if action:
                            action["speech_source"] = "live_llm"
                except Exception as exc:
                    self._o._record_recent_exception(f"speak:{p.player_id}", exc)
                    continue

                pregen_cache.on_player_spoke(p.player_id, len(self._o.event_log.events))

                if not action:
                    continue
                if action.get("action") == "skip_discussion":
                    pregen_cache.cancel_all()
                    self._o._record_data_snapshot("day_discussion_complete", discussion_round=discussion_round)
                    return
                if action.get("action") == "speak" and action.get("content"):
                    content = self._dedupe_public_speech_content(str(action["content"]), p.player_id, discussion_round)
                    payload = {"content": content, "tone": action.get("tone", "calm"), "round": discussion_round}
                    if "extracted_claims" in action:
                        payload["extracted_claims"] = action["extracted_claims"]
                    await self._o._publish_event(GameEvent(
                        event_type="player_speaks",
                        phase=GamePhase.DAY_DISCUSSION,
                        round_number=self._o.state.round_number,
                        trace_id=self._o._make_trace_id("BOTC-FLOW-SPEAK"),
                        actor=p.player_id,
                        visibility=Visibility.PUBLIC,
                        payload=payload,
                    ))
                if action.get("action") == "slayer_shot":
                    target_id = action.get("target")
                    if target_id:
                        await self._o._execute_slayer_shot(p.player_id, target_id)

            pregen_cache.cancel_all()

        await self._o._batch_reflect_agents(GamePhase.DAY_DISCUSSION)
        self._o._record_data_snapshot("day_discussion_complete", discussion_round=rounds)

    def _dedupe_public_speech_content(self, content: str, actor_id: str, discussion_round: int) -> str:
        text = content.strip()
        if not text:
            return text
        existing = {
            str(event.payload.get("content", "")).strip()
            for event in self._o.event_log.events
            if event.event_type == "player_speaks" and event.payload.get("round") == discussion_round
        }
        if text not in existing:
            return text
        visible_state = self._o._get_agent_visible_state(actor_id)
        target = self._draft_focus_target(actor_id, visible_state) if visible_state else ""
        if target:
            return f"{text} 我想特别听听 {target} 怎么补这条线。"
        return f"{text} 这个点我先记下来，后面看投票和提名能不能对上。"

    @staticmethod
    def _player_name_for_event(player_id: str, visible_state: AgentVisibleState) -> str:
        for player in visible_state.players:
            if player.player_id == player_id:
                return player.name
        return player_id

    def _draft_focus_target(self, self_player_id: str, visible_state: AgentVisibleState) -> str:
        candidates = [p for p in visible_state.players if p.player_id != self_player_id and p.is_alive]
        if not candidates:
            return ""
        index = (visible_state.day_number + visible_state.round_number + len(self._o.event_log.events)) % len(candidates)
        return candidates[index].name

    async def handle_chat(self, sender_id: str, content: str, is_private: bool = False) -> None:
        sender = self._o.state.get_player(sender_id)
        # 允许说书人发消息，即使他不在玩家列表中
        is_storyteller = sender_id in ["h1", "storyteller", "admin"] or (self._o.state.config and sender_id == self._o.state.config.storyteller_client_id)

        if not sender and not is_storyteller:
            return

        current_phase = self._o.state.phase if self._o.state.phase != GamePhase.SETUP else self._o.phase_manager.current_phase
        private_window_open = current_phase in {GamePhase.FIRST_NIGHT, GamePhase.NIGHT, GamePhase.DAY_DISCUSSION}

        can_use_evil_chat = False
        if is_private and private_window_open and sender and (sender.current_team or sender.team) == Team.EVIL:
            if current_phase == GamePhase.DAY_DISCUSSION:
                # Enforce whisper budget during day
                day = self._o.state.day_number or 1
                sender_counts = self._day_whisper_counts.get(sender_id, {})
                used = sender_counts.get(day, 0)
                if used < self._MAX_DAY_WHISPERS:
                    can_use_evil_chat = True
                    self._day_whisper_counts.setdefault(sender_id, {})[day] = used + 1
                # else: budget exhausted, falls through to public
            else:
                can_use_evil_chat = True

        visibility = Visibility.TEAM_EVIL if can_use_evil_chat else Visibility.PUBLIC
        recipient_ids = tuple(p.player_id for p in self._o.state.players if (p.current_team or p.team) == Team.EVIL) if visibility == Visibility.TEAM_EVIL else None
        self._o.state = self._o.state.with_message(ChatMessage(
            speaker=sender_id,
            content=content,
            phase=current_phase,
            round_number=self._o.state.round_number or self._o.phase_manager.round_number,
            recipient_ids=recipient_ids,
        ))
        await self._o._publish_event(GameEvent(
            event_type="player_speaks",
            phase=current_phase,
            round_number=self._o.state.round_number or self._o.phase_manager.round_number,
            trace_id=self._o._make_trace_id("BOTC-FLOW-CHAT"),
            actor=sender_id,
            visibility=visibility,
            payload={"content": content, "is_private": can_use_evil_chat},
        ))
