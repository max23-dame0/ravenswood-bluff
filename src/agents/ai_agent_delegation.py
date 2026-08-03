"""
AIAgent 委托 / 辅助方法层（从 ai_agent.py facade 抽出）

设计目标（见 `DECISIONS.md` D006）：facade 仅做路由与编排，行为逻辑下沉到子模块。
本模块承载从 `AIAgent` 抽出的委托包装与辅助方法，按关注点分成若干 Mixin，
由 `AIAgent` 多重继承。所有方法仅通过 `self` 访问 agent 实例属性/子模块，
调用点保持 `self._x(...)` 不变，故行为完全一致。

后续可进一步将各 Mixin 下沉到对应子模块包（decision/prompt/memory/...）。
"""

from __future__ import annotations

import re
from typing import Any

from src.agents.persona.persona import ParsedRoleStatement
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GameEvent,
    GameState,
    PrivatePlayerView,
    Team,
    Visibility,
    VisiblePlayerInfo,
)


class DecisionDelegationMixin:
    """提名 / 投票 / 夜间目标等决策逻辑委托给 DecisionEngine。"""

    def _nomination_threshold(self, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.nomination_threshold(visible_state)

    def _nomination_margin(self) -> float:
        return self._decision_engine.nomination_margin()

    def _vote_threshold(self, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.vote_threshold(visible_state)

    def _target_signal_score(self, target_id: str, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.target_signal_score(target_id, visible_state)

    def _select_nomination_target(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        intent_mode: bool = False,
    ) -> tuple[str, float, float] | None:
        return self._decision_engine.select_nomination_target(
            visible_state, legal_context, intent_mode
        )

    def _nomination_candidate_band(
        self, legal_targets: list[str], visible_state: AgentVisibleState, tolerance: float = 0.04
    ) -> tuple[list[str], float]:
        return self._decision_engine.nomination_candidate_band(
            legal_targets, visible_state, tolerance
        )

    def _choose_nomination_target_from_band(
        self,
        legal_targets: list[str],
        visible_state: AgentVisibleState,
        action_type: str,
        salt: str,
        tolerance: float = 0.04,
    ) -> tuple[str | None, float]:
        return self._decision_engine.choose_nomination_target_from_band(
            legal_targets, visible_state, action_type, salt, tolerance
        )

    def _select_night_targets(
        self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext
    ) -> list[str]:
        return self._decision_engine.select_night_targets(visible_state, legal_context)

    def _known_evil_teammate_ids(self, visible_state: AgentVisibleState) -> set[str]:
        return self._decision_engine.known_evil_teammate_ids(visible_state)

    def _poisoner_priority_for_target(
        self, target_id: str, visible_state: AgentVisibleState
    ) -> float:
        return self._decision_engine.poisoner_priority_for_target(target_id, visible_state)

    def _rank_poisoner_targets(
        self, ordered_targets: list[str], visible_state: AgentVisibleState
    ) -> list[str]:
        return self._decision_engine._rank_poisoner_targets(ordered_targets, visible_state)

    def _coerce_target_values(self, raw_target: Any) -> list[str]:
        return self._decision_engine.coerce_target_values(raw_target)

    def _select_vote_decision(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        model_vote: bool | None = None,
    ) -> tuple[bool, float, float]:
        return self._decision_engine.select_vote_decision(visible_state, legal_context, model_vote)

    def _can_attempt_slayer_shot(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
    ) -> bool:
        return self._decision_engine.can_attempt_slayer_shot(
            visible_state, legal_context, action_type
        )

    def _select_slayer_shot_target(
        self, visible_state: AgentVisibleState
    ) -> tuple[str, float] | None:
        return self._decision_engine.select_slayer_shot_target(visible_state)

    def _reasoning_evidence_candidates(
        self, target_id: str | None, visible_state: AgentVisibleState
    ) -> list[str]:
        return self._decision_engine.reasoning_evidence_candidates(target_id, visible_state)

    def _best_reasoning_evidence(
        self, target_id: str | None, visible_state: AgentVisibleState
    ) -> str:
        return self._decision_engine.best_reasoning_evidence(target_id, visible_state)

    def _augment_reasoning_with_evidence(
        self,
        reasoning: str,
        *,
        action_type: str,
        target_id: str | None,
        visible_state: AgentVisibleState,
        suspicion: float | None = None,
        threshold: float | None = None,
    ) -> str:
        return self._decision_engine.augment_reasoning_with_evidence(
            reasoning,
            action_type=action_type,
            target_id=target_id,
            visible_state=visible_state,
            suspicion=suspicion,
            threshold=threshold,
        )

    def _stable_choice(
        self,
        options: list[str],
        round_number: int,
        day_number: int,
        action_type: str,
        salt: str = "",
    ) -> str:
        return self._decision_engine.stable_choice(
            options, round_number, day_number, action_type, salt
        )

    def _persona_vote_bias(self, visible_state: AgentVisibleState) -> bool:
        return self._decision_engine.persona_vote_bias(visible_state)

    def _persona_fallback_speech(
        self,
        action_type: str,
        reason: str,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
    ) -> dict[str, Any]:
        return self._decision_engine.persona_fallback_speech(
            action_type, reason, visible_state, legal_context
        )

    def _find_most_suspicious_player(self, visible_state: AgentVisibleState) -> str | None:
        return self._decision_engine.find_most_suspicious_player(visible_state)

    def _local_low_value_decision(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
    ) -> dict[str, Any]:
        return self._decision_engine.local_low_value_decision(
            visible_state, legal_context, action_type
        )

    def _track_own_claims_from_decision(
        self, decision: dict[str, Any], visible_state: AgentVisibleState
    ) -> None:
        return self._decision_engine.track_own_claims_from_decision(decision, visible_state)

    def _normalize_decision(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        return self._decision_engine.normalize_decision(
            visible_state, legal_context, action_type, decision
        )

    def _fallback_decision(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._decision_engine.fallback_decision(
            visible_state, legal_context, action_type, reason
        )


class PromptDelegationMixin:
    """提示词构建委托给 PromptFactory。"""

    def _build_persona_prompt_block(
        self, action_type: str, visible_state: AgentVisibleState | None = None
    ) -> str:
        return self._prompt_factory.build_persona_prompt_block(action_type, visible_state)

    def _build_action_context(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
    ) -> str:
        return self._prompt_factory.build_action_context(visible_state, legal_context, action_type)

    def _build_memory_signal_brief(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_memory_signal_brief(visible_state)

    def _build_speech_priority_brief(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_speech_priority_brief(visible_state)

    def _build_visible_state_summary(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_visible_state_summary(visible_state)

    def _deception_budget_prompt(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.deception_budget_prompt(visible_state)

    def _json_schema_for_action(self, action_type: str) -> str:
        schemas = {
            "speak": (
                "{\n"
                '  "action": "speak",\n'
                '  "content": "你的中文发言内容",\n'
                '  "tone": "calm/passionate/accusatory/defensive",\n'
                '  "reasoning": "你的内部推理（不公开）",\n'
                f'  "extracted_claims": [ // 可选：声明身份时提取，格式如 {{"role_id": "mayor", "claim_type": "self_claim", "subject_player_ids": ["{self.player_id}"]}}'
                "\n  ]\n"
                "}"
            ),
            "defense_speech": (
                "{\n"
                '  "action": "speak",\n'
                '  "content": "你的辩解内容",\n'
                '  "tone": "calm/passionate/defensive",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
            "vote": (
                "{\n"
                '  "action": "vote",\n'
                '  "decision": true/false,\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
            "nominate": (
                "{\n"
                '  "action": "nominate/none",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
            "nomination_intent": (
                "{\n"
                '  "action": "nominate/none",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
            "night_action": (
                "{\n"
                '  "action": "night_action",\n'
                '  "target": "player_id 或 [id1, id2]",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
            "slayer_shot": (
                "{\n"
                '  "action": "slayer_shot",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
        }
        return schemas.get(
            action_type,
            (
                "{\n"
                '  "action": "speak/nominate/vote/night_action/slayer_shot/skip_discussion/none",\n'
                '  "content": "发言内容（仅 speak 时）",\n'
                '  "target": "player_id（提名/射击时）",\n'
                '  "decision": true/false（仅 vote 时）,\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                "}"
            ),
        )


class MemoryDelegationMixin:
    """记忆 / 社交图谱 / 角色同步委托给 MemoryController / EventObserver。"""

    def _refresh_persona_profile(self) -> None:
        return self._memory_controller.refresh_persona_profile()

    def _process_event_for_social_graph(self, event: GameEvent) -> None:
        return self._event_observer.process_event_for_social_graph(event)

    async def observe_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        return await self._event_observer.observe_event(event, visible_state)

    async def _ingest_visible_event_to_vector_memory(self, event: GameEvent) -> None:
        return await self._event_observer.ingest_visible_event_to_vector_memory(event)

    def _remember_critical_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        return self._event_observer.remember_critical_event(event, visible_state)

    def _store_private_info_memory(
        self, info_type: str, summary: str, visible_state: AgentVisibleState
    ) -> None:
        return self._event_observer.store_private_info_memory(info_type, summary, visible_state)

    def _store_targeted_private_hints(
        self, info_type: str, payload: dict[str, Any], visible_state: AgentVisibleState
    ) -> None:
        return self._event_observer.store_targeted_private_hints(info_type, payload, visible_state)

    async def _reflect(self, visible_state: AgentVisibleState) -> None:
        return await self._memory_controller.reflect(visible_state)

    async def reflect_if_needed(self, visible_state: AgentVisibleState) -> bool:
        return await self._memory_controller.reflect_if_needed(visible_state)

    async def think(self, prompt: str, visible_state: AgentVisibleState) -> str:
        return await self._memory_controller.think(prompt, visible_state)

    async def archive_phase_memory(self, visible_state: AgentVisibleState) -> None:
        return await self._memory_controller.archive_phase_memory(visible_state)

    def build_data_snapshot_summary(self) -> dict[str, Any]:
        return self._memory_controller.build_data_snapshot_summary()

    def _sync_social_graph(self, game_state: GameState) -> None:
        return self._memory_controller.sync_social_graph(game_state)

    def _prime_social_graph_from_state(self, visible_state: AgentVisibleState) -> None:
        return self._memory_controller.prime_social_graph_from_state(visible_state)

    def _extract_role_ids_from_text(self, text: str) -> list[str]:
        haystack = (text or "").lower()
        found: set[str] = set()
        for role_id, zh_name, en_name in self._iter_role_terms():
            if zh_name in haystack or en_name.lower() in haystack or role_id in haystack:
                found.add(role_id)
        return list(found)

    def _role_team_hint(self, role_id: str) -> Team | None:
        from src.engine.roles.base_role import get_role_class

        role_cls = get_role_class(role_id)
        if not role_cls:
            return None
        try:
            return role_cls.get_definition().team
        except Exception:
            return None


class ObserverDelegationMixin:
    """事件观测 / 可见状态构建。"""

    def _format_event_to_text(self, event: GameEvent, visible_state: AgentVisibleState) -> str:
        return self._event_observer.format_event_to_text(event, visible_state)

    def _iter_role_terms(self) -> list[tuple[str, str, str]]:
        return self._event_observer._iter_role_terms()

    def _extract_role_statements(
        self, content: str, speaker_id: str, visible_state: AgentVisibleState
    ) -> list[ParsedRoleStatement]:
        return self._event_observer.extract_role_statements(content, speaker_id, visible_state)

    def _is_event_visible_to_self(self, event: GameEvent) -> bool:
        if event.visibility == Visibility.PUBLIC:
            return True
        if event.visibility == Visibility.STORYTELLER_ONLY:
            return self.player_id in {event.actor, event.target}
        if event.visibility == Visibility.PRIVATE:
            return event.actor == self.player_id or event.target == self.player_id
        if event.visibility == Visibility.TEAM_EVIL:
            return self.team == Team.EVIL.value
        if event.visibility == Visibility.TEAM_GOOD:
            return self.team == Team.GOOD.value
        return False

    def _is_chat_visible_to_self(self, message) -> bool:
        if message.speaker == self.player_id:
            return True
        recipients = getattr(message, "recipient_ids", None)
        if not recipients:
            return True
        return self.player_id in recipients

    def _build_visible_state(self, game_state: GameState) -> AgentVisibleState:
        return AgentVisibleState(
            game_id=game_state.game_id,
            phase=game_state.phase,
            round_number=game_state.round_number,
            day_number=game_state.day_number,
            self_view=self.private_view
            if isinstance(self.private_view, PrivatePlayerView)
            else None,
            players=tuple(
                VisiblePlayerInfo(
                    player_id=player.player_id,
                    name=player.name,
                    is_alive=player.is_alive,
                )
                for player in game_state.players
            ),
            current_nominee=game_state.current_nominee,
            current_nominator=game_state.current_nominator,
            seat_order=game_state.seat_order
            or tuple(player.player_id for player in game_state.players),
            nominations_today=game_state.nominations_today,
            nominees_today=game_state.nominees_today,
            yes_votes=sum(1 for vote in game_state.votes_today.values() if vote is True),
            voted_player_ids=tuple(game_state.votes_today.keys()),
            public_chat_history=tuple(
                message
                for message in game_state.chat_history
                if self._is_chat_visible_to_self(message)
            ),
            visible_event_log=tuple(
                event for event in game_state.event_log if self._is_event_visible_to_self(event)
            ),
        )


class SpeechDelegationMixin:
    """公开发言净化 / 锚点委托给 SpeechSanitizer。"""

    def _evil_coordination_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer._evil_coordination_line(visible_state)

    def _mentioned_visible_names(self, summary: str, visible_state: AgentVisibleState) -> list[str]:
        return self._speech_sanitizer._mentioned_visible_names(summary, visible_state)

    def _private_info_public_paraphrase(
        self, summary: str, visible_state: AgentVisibleState
    ) -> str:
        return self._speech_sanitizer._private_info_public_paraphrase(summary, visible_state)

    def _public_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer.public_speech_anchor_line(visible_state)

    def _preferred_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer.preferred_speech_anchor_line(visible_state)

    def _hidden_memory_summaries_for_public_filter(self) -> list[str]:
        return self._speech_sanitizer._hidden_memory_summaries_for_public_filter()

    def _sanitize_public_speech_content(
        self, content: str, visible_state: AgentVisibleState
    ) -> str:
        return self._speech_sanitizer.sanitize_public_speech_content(content, visible_state)

    def _stabilize_speech_content_with_memory(
        self,
        content: str,
        visible_state: AgentVisibleState,
        action_type: str,
    ) -> str:
        return self._speech_sanitizer.stabilize_speech_content_with_memory(
            content, visible_state, action_type
        )


class EvilDelegationMixin:
    """邪恶协同委托给 EvilStrategy。"""

    def _get_evil_strategic_summary(self, visible_state: AgentVisibleState) -> str:
        return self._evil_strategy.get_evil_strategic_summary(visible_state)

    async def build_evil_night_coordination_message(
        self,
        action: dict[str, Any],
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext | None = None,
    ) -> str:
        return await self._evil_strategy.build_evil_night_coordination_message(
            action, visible_state, legal_context
        )

    async def generate_first_night_coordination(self, visible_state: AgentVisibleState) -> str:
        return await self._evil_strategy.generate_first_night_coordination(visible_state)


class SignalSummaryMixin:
    """角色信号摘要 / 合法上下文 / 近期上下文等辅助计算。"""

    def _player_name_from_visible_state(
        self, player_id: str | None, visible_state: AgentVisibleState
    ) -> str:
        if not player_id:
            return "某个目标"
        if visible_state.self_view and player_id == visible_state.self_view.player_id:
            return visible_state.self_view.name
        for player in visible_state.players:
            if player.player_id == player_id:
                return player.name
        return player_id

    def _empath_neighbor_ids(self, visible_state: AgentVisibleState) -> tuple[str, ...]:
        me = visible_state.self_view
        if not me or me.perceived_role_id != "empath":
            return ()
        seat_order = list(
            visible_state.seat_order or tuple(player.player_id for player in visible_state.players)
        )
        if me.player_id not in seat_order:
            return ()
        alive_lookup = {player.player_id: player.is_alive for player in visible_state.players}
        my_idx = seat_order.index(me.player_id)
        n = len(seat_order)
        if n <= 1:
            return ()

        def find_neighbor(step: int) -> str | None:
            idx = my_idx
            for _ in range(n - 1):
                idx = (idx + step) % n
                pid = seat_order[idx]
                if alive_lookup.get(pid, True):
                    return pid
            return None

        left = find_neighbor(-1)
        right = find_neighbor(1)
        result: list[str] = []
        for pid in (left, right):
            if pid and pid not in result:
                result.append(pid)
        return tuple(result)

    def _empath_neighbor_signal_summary(self, visible_state: AgentVisibleState) -> str:
        if not visible_state.self_view or visible_state.self_view.perceived_role_id != "empath":
            return ""
        summaries = self.working_memory.get_private_memory_summaries("empath_info")
        if not summaries:
            return ""
        latest = summaries[-1]
        neighbor_names = [
            self._player_name_from_visible_state(pid, visible_state)
            for pid in self._empath_neighbor_ids(visible_state)
        ]
        if neighbor_names:
            return (
                f"作为共情者，你当前活着的邻座是：{', '.join(neighbor_names)}。最近结果：{latest}"
            )
        return f"作为共情者，你最近的结果是：{latest}"

    def _chef_signal_summary(self) -> str:
        summaries = self.working_memory.get_private_memory_summaries("chef_info")
        if not summaries:
            return ""
        return f"作为厨师，你的高可信首夜结果是：{summaries[-1]}"

    def _latest_numeric_value(self, category: str, patterns: tuple[str, ...]) -> int | None:
        summaries = self.working_memory.get_private_memory_summaries(category)
        if not summaries:
            return None
        summary = summaries[-1]
        for pattern in patterns:
            match = re.search(pattern, summary)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return None
        return None

    def _visible_alive_count(self, visible_state: AgentVisibleState) -> int:
        return sum(1 for player in visible_state.players if player.is_alive)

    def _recent_context_texts(self, visible_state: AgentVisibleState, limit: int = 12) -> list[str]:
        texts: list[str] = []
        for obs in self.working_memory.observations[-limit:]:
            if obs.content:
                texts.append(obs.content)
        for message in visible_state.public_chat_history[-limit:]:
            speaker = next(
                (player for player in visible_state.players if player.player_id == message.speaker),
                None,
            )
            speaker_name = speaker.name if speaker else message.speaker
            target_name = ""
            if message.target_player:
                target_player = next(
                    (
                        player
                        for player in visible_state.players
                        if player.player_id == message.target_player
                    ),
                    None,
                )
                target_name = (
                    f" -> {target_player.name}" if target_player else f" -> {message.target_player}"
                )
            texts.append(f"{speaker_name}{target_name}: {message.content}")
        for event in visible_state.visible_event_log[-limit:]:
            if event.event_type in {
                "player_speaks",
                "nomination_started",
                "vote_cast",
                "voting_resolved",
                "execution_resolved",
                "player_death",
                "private_info_delivered",
            }:
                texts.append(self._format_event_to_text(event, visible_state))
        return texts

    def _count_mentions(self, texts: list[str], keyword: str) -> int:
        if not keyword:
            return 0
        lowered = keyword.lower()
        count = 0
        for text in texts:
            haystack = text.lower()
            if lowered in haystack:
                count += haystack.count(lowered)
        return count

    def _persona_modifier(self, key: str, mapping: dict[str, float], default: float = 0.0) -> float:
        profile = self.persona_profile or {}
        return mapping.get(str(profile.get(key, "")), default)

    def _build_legal_action_context(
        self, game_state: GameState, visible_state: AgentVisibleState
    ) -> AgentActionLegalContext:
        from src.engine.roles.base_role import get_role_class
        from src.engine.rule_engine import RuleEngine

        nomination_targets: list[str] = []
        for player in game_state.players:
            if player.player_id == self.player_id:
                continue
            can_nominate, _ = RuleEngine.can_nominate(game_state, self.player_id, player.player_id)
            if can_nominate:
                nomination_targets.append(player.player_id)

        night_targets = [
            player.player_id
            for player in game_state.get_alive_players()
            if player.player_id != self.player_id
        ]
        voters_so_far = set(game_state.votes_today.keys())
        seat_order = visible_state.seat_order or tuple(
            player.player_id for player in visible_state.players
        )
        remaining_voters = [pid for pid in seat_order if pid not in voters_so_far]
        required_targets = 1
        can_target_self = False
        player = game_state.get_player(self.player_id)
        if player:
            role_cls = get_role_class(player.true_role_id or player.role_id)
            if role_cls:
                role_instance = role_cls()
                try:
                    required_targets = max(
                        0,
                        int(role_instance.get_required_targets(game_state, game_state.phase) or 0),
                    )
                except Exception:
                    required_targets = 1
                try:
                    can_target_self = bool(role_instance.can_target_self())
                except Exception:
                    can_target_self = False
        return AgentActionLegalContext(
            legal_nomination_targets=tuple(nomination_targets),
            legal_night_targets=tuple(night_targets),
            votes_required=RuleEngine.votes_required(game_state),
            remaining_voters=tuple(remaining_voters),
            required_targets=required_targets,
            can_target_self=can_target_self,
        )
