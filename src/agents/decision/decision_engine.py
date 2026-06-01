"""
Decision scoring, target selection, normalization, and fallback for AIAgent.

Extracted from AIAgent to reduce god-object size. All methods access agent
state through the injected ``agent`` reference — never import AIAgent itself.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from src.content.trouble_brewing_terms import get_role_name
from src.agents.persona_registry import Archetype
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    Team,
)

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent


class DecisionEngine:
    """Handles scoring, target selection, normalization, and fallback decisions."""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ==================================================================
    #  SCORING
    # ==================================================================

    def target_signal_score(self, target_id: str, visible_state: AgentVisibleState) -> float:
        agent = self._agent
        if not target_id or target_id == agent.player_id:
            return 0.0

        target = next((player for player in visible_state.players if player.player_id == target_id), None)
        if not target:
            return 0.0

        intel = agent.difficulty_preset.nomination_intelligence
        texts = agent._recent_context_texts(visible_state)
        mention_hits = agent._count_mentions(texts, target.name)
        score = 0.16 + min(0.24, mention_hits * 0.06)

        if target_id in visible_state.nominees_today:
            score += 0.12
        if target_id == visible_state.current_nominee:
            score += 0.06
        if visible_state.current_nominator and visible_state.current_nominator == target_id:
            score += 0.03

        profile = agent.social_graph.get_profile(target_id)
        if profile:
            if profile.trust_score < 0:
                score += min(0.20, abs(profile.trust_score) * 0.25)
            elif profile.trust_score > 0:
                score -= min(0.12, profile.trust_score * 0.12)
            if profile.notes:
                score += min(0.08, len(profile.notes) * 0.02)
            claim_signals = agent.social_graph.claim_signal_summary(target_id)
            if claim_signals["conflicts"]:
                score += min(0.20, claim_signals["conflicts"] * 0.10) * intel
            if claim_signals["denial"] and claim_signals["self_claim"]:
                score += min(0.08, claim_signals["denial"] * 0.04) * intel

        confirmed_teammates = "\n".join(
            agent.working_memory.get_objective_memory_summaries("evil_teammates")
            + agent.working_memory.get_private_memory_summaries("evil_teammates")
        )
        if confirmed_teammates and target.name in confirmed_teammates:
            if agent.team == Team.EVIL.value:
                score = max(0.0, score - 0.35 * intel)
            else:
                score += 0.05 * intel

        high_confidence_signals = [
            ("fortune_teller_info", 0.16, ("恶魔", "邪恶", "可疑", "至少一人可能", "之一可能")),
            ("investigator_info", 0.16, ("爪牙", "邪恶", "可疑")),
            ("empath_info", 0.08, ("邪恶邻座", "邪恶", "有", "2")),
            ("chef_info", 0.06, ("邪恶相邻", "邪恶", "有", "2")),
        ]
        for category, weight, keywords in high_confidence_signals:
            for summary in agent.working_memory.get_private_memory_summaries(category):
                if target.name in summary and any(keyword in summary for keyword in keywords):
                    score += weight * intel
                    break

        targeted_private_summaries = [
            *agent.working_memory.get_private_memory_summaries("role_candidate_hint"),
            *agent.working_memory.get_private_memory_summaries("demon_candidate"),
            *agent.working_memory.get_private_memory_summaries("revealed_role"),
        ]
        claimed_role_id = agent._profile_claimed_role_id(profile)
        for summary in targeted_private_summaries:
            if target.name not in summary:
                continue
            mentioned_roles = agent._extract_role_ids_from_text(summary)
            mentioned_teams = {agent._role_team_hint(role_id) for role_id in mentioned_roles if agent._role_team_hint(role_id)}

            if "可能是" in summary and "恶魔" in summary:
                score += 0.14 * intel
            elif "可能是" in summary and mentioned_teams == {Team.EVIL}:
                score += 0.14 * intel
            elif "可能是" in summary and mentioned_teams and mentioned_teams <= {Team.GOOD}:
                score -= 0.06
            elif "身份被高可信信息指出为" in summary and mentioned_roles:
                # Hard evidence from storyteller — not scaled by intel
                if any(agent._role_team_hint(role_id) == Team.EVIL for role_id in mentioned_roles):
                    score += 0.18
                elif all(agent._role_team_hint(role_id) == Team.GOOD for role_id in mentioned_roles):
                    score -= 0.10

            if claimed_role_id and mentioned_roles:
                if claimed_role_id in mentioned_roles:
                    score -= 0.12
                else:
                    score += 0.07

        empath_count = agent._latest_numeric_value("empath_info", (r"邪恶玩家数量：(\d+)",))
        if empath_count is not None:
            neighbor_ids = set(agent._empath_neighbor_ids(visible_state))
            if target_id in neighbor_ids:
                if empath_count == 0:
                    score -= 0.12
                elif empath_count == 1:
                    score += 0.04
                elif empath_count >= 2:
                    score += 0.12

        recent_texts = texts[-8:]
        if any(target.name in text and "可疑" in text for text in recent_texts):
            score += 0.08
        if any(target.name in text and "怀疑" in text for text in recent_texts):
            score += 0.05
        if any(target.name in text and "信任" in text for text in recent_texts):
            score -= 0.06
        if agent.persona_profile.get("social_style") == "从众" and mention_hits > 0:
            score += 0.03

        # Evil: prioritize targeting high-value info roles
        if agent.team == Team.EVIL.value and profile:
            target_claimed_role = agent._profile_claimed_role_id(profile)
            _info_roles = {"fortune_teller", "empath", "investigator", "chef", "undertaker", "monk", "washerwoman", "librarian"}
            if target_claimed_role in _info_roles:
                score += 0.10 * intel

        # Evil coordination: boost score if a confirmed teammate publicly accused this target
        if agent.team == Team.EVIL.value and confirmed_teammates and intel > 0:
            teammate_names = [n.strip() for n in confirmed_teammates.split("\n") if n.strip()]
            for text in recent_texts:
                if target.name in text and any(tn in text for tn in teammate_names):
                    if any(kw in text for kw in ("可疑", "怀疑", "提名", "不对劲")):
                        score += 0.06 * intel
                        break

        return max(0.0, min(1.0, score))

    # ==================================================================
    #  THRESHOLDS
    # ==================================================================

    def nomination_threshold(self, visible_state: AgentVisibleState) -> float:
        agent = self._agent
        threshold = 0.60
        # W3-C: 引入人格原型偏置
        profile = agent.persona_profile or {}
        archetype = profile.get("archetype")
        if isinstance(archetype, Archetype):
            threshold += archetype.nomination_threshold_offset
        # Difficulty override
        threshold += agent._difficulty_threshold_offset("nomination_threshold_offset")

        alive_count = agent._visible_alive_count(visible_state)
        if alive_count <= 5:
            threshold -= 0.03
        elif alive_count >= 8:
            threshold += 0.02

        threshold -= min(0.08, max(0, visible_state.day_number - 1) * 0.02)
        threshold += agent._persona_modifier("risk_tolerance", {"保守": 0.08, "均衡": 0.02, "激进": -0.05})
        threshold += agent._persona_modifier("social_style", {"从众": 0.03, "独立": 0.0, "带节奏": -0.04})
        threshold += agent._persona_modifier("assertiveness", {"温和": 0.04, "中性": 0.0, "强势": -0.04})
        if agent.team == "evil":
            intel = agent.difficulty_preset.nomination_intelligence
            threshold -= 0.02 + 0.03 * intel
        # Decision noise layer
        noise_key = f"nominate_day{getattr(visible_state, 'day_number', 1)}_round{getattr(visible_state, 'round_number', 1)}"
        threshold += agent.decision_noise.threshold_noise(noise_key)
        return max(0.40, min(0.85, threshold))

    def nomination_margin(self) -> float:
        agent = self._agent
        intel = agent.difficulty_preset.nomination_intelligence
        base = 0.09 - 0.07 * intel  # casual(0.2)→0.076, standard(0.5)→0.055, master(0.85)→0.0305
        return max(
            0.03,
            min(
                0.10,
                base
                + agent._persona_modifier("risk_tolerance", {"保守": 0.03, "均衡": 0.01, "激进": -0.01})
                + agent._persona_modifier("assertiveness", {"温和": 0.02, "中性": 0.0, "强势": -0.02}),
            ),
        )

    def vote_threshold(self, visible_state: AgentVisibleState) -> float:
        agent = self._agent
        threshold = 0.54
        # W3-C/D: 引入人格原型偏置
        profile = agent.persona_profile or {}
        archetype = profile.get("archetype")
        if isinstance(archetype, Archetype):
            threshold += archetype.vote_threshold_offset
        # Difficulty override
        threshold += agent._difficulty_threshold_offset("vote_threshold_offset")

        alive_count = agent._visible_alive_count(visible_state)
        if alive_count <= 5:
            threshold -= 0.02
        elif alive_count >= 8:
            threshold += 0.02

        # W3-D: 亡魂投票保护逻辑 (Ghost Vote Protection)
        me = visible_state.self_view
        if me and not me.is_alive:
            # 死亡玩家如果只有一票，门槛大幅提高，倾向于保留至最后
            if me.ghost_votes_remaining <= 1:
                threshold += 0.15
            else:
                threshold += 0.05

        threshold -= min(0.05, max(0, visible_state.day_number - 1) * 0.015)
        threshold += agent._persona_modifier("risk_tolerance", {"保守": 0.04, "均衡": 0.01, "激进": -0.04})
        threshold += agent._persona_modifier("social_style", {"从众": 0.02, "独立": 0.0, "带节奏": -0.03})
        threshold += agent._persona_modifier("assertiveness", {"温和": 0.03, "中性": 0.0, "强势": -0.03})
        if agent.team == "evil":
            threshold -= 0.01
        # Decision noise layer
        noise_key = f"vote_day{getattr(visible_state, 'day_number', 1)}_round{getattr(visible_state, 'round_number', 1)}"
        threshold += agent.decision_noise.threshold_noise(noise_key)
        return max(0.20, min(0.95, threshold))

    def select_nomination_target(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, intent_mode: bool = False) -> tuple[str, float, float] | None:
        agent = self._agent
        legal_targets = list(legal_context.legal_nomination_targets)
        if not legal_targets:
            return None

        intel = agent.difficulty_preset.nomination_intelligence

        # Timing intelligence: high-intel agents wait for more info before nominating
        patience = int(intel * 3)  # casual=0, standard=1, master=2, chaos=1
        nominees_so_far = len(getattr(visible_state, 'nominees_today', ()) or ())
        if nominees_so_far < patience and not intent_mode:
            # Quick scan: only bypass patience if there's a strong signal
            quick_scores = [self.target_signal_score(tid, visible_state) for tid in legal_targets]
            if not quick_scores or max(quick_scores) < 0.60:
                return None

        noise_key = f"nom_target_day{getattr(visible_state, 'day_number', 1)}_round{getattr(visible_state, 'round_number', 1)}"
        base_scores = {tid: self.target_signal_score(tid, visible_state) for tid in legal_targets}
        noisy_scores = {
            tid: score + agent.decision_noise.threshold_noise(f"{noise_key}_{tid}")
            for tid, score in base_scores.items()
        }
        scored_targets = sorted(
            ((noisy_scores[tid], tid) for tid in legal_targets),
            key=lambda item: (-item[0], item[1]),
        )
        best_score, best_target = scored_targets[0]
        runner_up_score = scored_targets[1][0] if len(scored_targets) > 1 else 0.0
        threshold = self.nomination_threshold(visible_state)
        if intent_mode:
            threshold = max(0.25, threshold - 0.30)
            margin = max(0.01, self.nomination_margin() - 0.03)
        else:
            margin = self.nomination_margin()

        # Bold move: occasionally bypass threshold (chaos/casual more likely)
        day = getattr(visible_state, 'day_number', 1)
        round_n = getattr(visible_state, 'round_number', 1)
        bold = agent.decision_noise.should_bold_move(f"nom_bold_day{day}_round{round_n}")
        if bold.triggered:
            threshold = max(0.25, threshold - 0.15)
            margin = max(0.01, margin - 0.02)

        if best_score < threshold:
            return None
        if len(scored_targets) > 1 and (best_score - runner_up_score) < margin:
            return None
        return best_target, best_score, threshold

    def nomination_candidate_band(
        self,
        legal_targets: list[str],
        visible_state: AgentVisibleState,
        tolerance: float = 0.04,
    ) -> tuple[list[str], float]:
        if not legal_targets:
            return [], 0.0
        scored_targets = [
            (self.target_signal_score(target_id, visible_state), target_id)
            for target_id in legal_targets
        ]
        best_score = max(score for score, _ in scored_targets)
        band = sorted(
            [
                target_id
                for score, target_id in scored_targets
                if (best_score - score) <= tolerance
            ]
        )
        return band, best_score

    def choose_nomination_target_from_band(
        self,
        legal_targets: list[str],
        visible_state: AgentVisibleState,
        action_type: str,
        salt: str,
        tolerance: float = 0.04,
    ) -> tuple[str | None, float]:
        agent = self._agent
        candidate_band, best_score = self.nomination_candidate_band(
            legal_targets, visible_state, tolerance=tolerance,
        )
        if not candidate_band:
            return None, 0.0
        if len(candidate_band) == 1:
            return candidate_band[0], best_score
        target = self.stable_choice(
            candidate_band, visible_state.round_number, visible_state.day_number, action_type, salt,
        )
        return target, best_score

    def select_night_targets(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
    ) -> list[str]:
        agent = self._agent
        required_targets = max(1, int(getattr(legal_context, "required_targets", 1) or 1))
        legal_targets = list(legal_context.legal_night_targets)
        if getattr(legal_context, "can_target_self", False) and agent.player_id not in legal_targets:
            legal_targets.append(agent.player_id)

        ordered_targets: list[str] = []
        seen: set[str] = set()
        for candidate in legal_targets:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            ordered_targets.append(candidate)

        if len(ordered_targets) < required_targets:
            return []

        if required_targets == 1 and (agent.perceived_role_id or agent.role_id) == "poisoner":
            poisoner_order = self._rank_poisoner_targets(ordered_targets, visible_state)
            if poisoner_order:
                return [poisoner_order[0]]

        scored_targets = sorted(
            [
                (self.target_signal_score(target_id, visible_state), target_id)
                for target_id in ordered_targets
            ],
            key=lambda item: (-item[0], item[1]),
        )

        selected: list[str] = []
        for _, target_id in scored_targets:
            if target_id in selected:
                continue
            selected.append(target_id)
            if len(selected) >= required_targets:
                break

        if len(selected) < required_targets:
            return []
        return selected[:required_targets]

    def known_evil_teammate_ids(self, visible_state: AgentVisibleState) -> set[str]:
        agent = self._agent
        summaries = agent.working_memory.get_objective_memory_summaries("evil_teammates")
        teammate_ids: set[str] = set()
        for player in visible_state.players:
            if player.player_id == agent.player_id:
                continue
            if any(player.name in summary for summary in summaries):
                teammate_ids.add(player.player_id)
        return teammate_ids

    def poisoner_priority_for_target(self, target_id: str, visible_state: AgentVisibleState) -> float:
        agent = self._agent
        teammate_ids = self.known_evil_teammate_ids(visible_state)
        if target_id in teammate_ids:
            return -1.0

        profile = agent.social_graph.get_profile(target_id)
        claim_role_id = agent._profile_claimed_role_id(profile)
        info_role_weights = {
            "fortune_teller": 0.48,
            "undertaker": 0.42,
            "empath": 0.40,
            "monk": 0.34,
            "investigator": 0.32,
            "washerwoman": 0.30,
            "librarian": 0.30,
            "chef": 0.26,
        }
        score = 0.0
        if claim_role_id:
            score += info_role_weights.get(claim_role_id, 0.0)

        target_name = agent._player_name_from_visible_state(target_id, visible_state)
        for summary in agent.working_memory.get_private_memory_summaries("revealed_role"):
            if target_name in summary:
                role_ids = agent._extract_role_ids_from_text(summary)
                for role_id in role_ids:
                    score += info_role_weights.get(role_id, 0.0) * 0.9

        for summary in agent.working_memory.get_private_memory_summaries("role_candidate_hint"):
            if target_name in summary:
                role_ids = agent._extract_role_ids_from_text(summary)
                for role_id in role_ids:
                    score += info_role_weights.get(role_id, 0.0) * 0.75

        if claim_role_id in {"mayor", "virgin"}:
            score += 0.08

        score += max(0.0, min(0.15, self.target_signal_score(target_id, visible_state) * 0.2))
        return score

    def _rank_poisoner_targets(self, ordered_targets: list[str], visible_state: AgentVisibleState) -> list[str]:
        ranked = sorted(
            ((self.poisoner_priority_for_target(target_id, visible_state), target_id) for target_id in ordered_targets),
            key=lambda item: (-item[0], item[1]),
        )
        viable = [target_id for score, target_id in ranked if score >= 0]
        return viable or [target_id for _, target_id in ranked]

    def coerce_target_values(self, raw_target: Any) -> list[str]:
        """把 LLM/脚本返回的目标字段递归拍平为字符串列表。"""
        flattened: list[str] = []

        def visit(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, str):
                for piece in value.split(","):
                    piece = piece.strip()
                    if piece:
                        flattened.append(piece)
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    visit(item)
                return
            text = str(value).strip()
            if text:
                flattened.append(text)

        visit(raw_target)
        return flattened

    def select_vote_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, model_vote: bool | None = None) -> tuple[bool, float, float]:
        agent = self._agent
        nominee_id = visible_state.current_nominee
        threshold = agent._vote_threshold(visible_state)
        if not nominee_id:
            return False, 0.0, threshold

        suspicion = agent._target_signal_score(nominee_id, visible_state)

        # W3-D: 群体压力与势头感知 (Group Momentum)
        req_votes = legal_context.votes_required
        current_yes = visible_state.yes_votes

        social_style = agent.persona_profile.get("social_style", "独立")
        if social_style == "从众":
            # 如果已经有很多票了，跟票意愿增加（门槛降低）
            if current_yes >= req_votes / 2:
                threshold -= 0.05
        elif social_style == "带节奏":
            # 如果票数还很少，且我是前序位，可能想带节奏，门槛降低
            if current_yes < 2:
                threshold -= 0.03

        # 决定性一票检测 (Deciding Vote Detection)
        # 如果加上我刚好能处决，门槛微降
        if current_yes == req_votes - 1:
            threshold -= 0.02

        margin = 0.06
        if suspicion >= threshold + margin:
            return True, suspicion, threshold
        if suspicion <= threshold - margin:
            return False, suspicion, threshold
        if model_vote is not None:
            return bool(model_vote), suspicion, threshold

        # 兜底：基于人格偏好稳定选择
        return agent._persona_vote_bias(visible_state), suspicion, threshold

    def can_attempt_slayer_shot(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
    ) -> bool:
        agent = self._agent
        me = visible_state.self_view
        perceived_role = (me.perceived_role_id if me else None) or agent.perceived_role_id or agent.role_id
        if perceived_role != "slayer":
            return False
        if not legal_context.can_slayer_shot:
            return False
        return action_type in {"speak", "nomination_intent"}

    def select_slayer_shot_target(self, visible_state: AgentVisibleState) -> tuple[str, float] | None:
        agent = self._agent
        candidates = [
            player.player_id
            for player in visible_state.players
            if player.player_id != agent.player_id and player.is_alive
        ]
        if not candidates:
            return None

        scored = sorted(
            ((self.target_signal_score(player_id, visible_state), player_id) for player_id in candidates),
            key=lambda item: (-item[0], item[1]),
        )
        best_score, best_target = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        score_gap = best_score - second_score
        target_name = agent._player_name_from_visible_state(best_target, visible_state)

        has_hard_evidence = any(
            target_name in summary
            for category in ("revealed_role", "demon_candidate")
            for summary in agent.working_memory.get_private_memory_summaries(category)
        )

        if has_hard_evidence and best_score >= 0.35:
            return best_target, best_score
        if best_score >= 0.74 and score_gap >= 0.10:
            return best_target, best_score
        return None

    # ==================================================================
    #  EVIDENCE & REASONING
    # ==================================================================

    def reasoning_evidence_candidates(self, target_id: str | None, visible_state: AgentVisibleState) -> list[str]:
        agent = self._agent
        if not target_id:
            return []

        target = next((player for player in visible_state.players if player.player_id == target_id), None)
        if not target:
            return []

        target_name = target.name
        profile = agent.social_graph.get_profile(target_id)
        claim_signals = agent.social_graph.claim_signal_summary(target_id)
        candidates: list[str] = []

        objective_candidates = [
            *agent.working_memory.get_objective_memory_summaries("evil_teammates"),
            *agent.working_memory.get_objective_memory_summaries("evil_bluffs"),
        ]
        for summary in objective_candidates:
            if target_name in summary:
                candidates.append(f"客观信息：{summary}")

        targeted_private_summaries = [
            *agent.working_memory.get_private_memory_summaries("revealed_role"),
            *agent.working_memory.get_private_memory_summaries("demon_candidate"),
            *agent.working_memory.get_private_memory_summaries("role_candidate_hint"),
        ]
        claimed_role_id = agent._profile_claimed_role_id(profile)
        for summary in targeted_private_summaries:
            if target_name in summary:
                candidates.append(f"高可信信息：{summary}")
                mentioned_roles = agent._extract_role_ids_from_text(summary)
                if claimed_role_id and mentioned_roles and claimed_role_id not in mentioned_roles:
                    candidates.append(f"高可信信息：{target_name} 的公开自报 {claimed_role_id} 与这条线索冲突")

        if claim_signals["conflicts"] or (claim_signals["self_claim"] and claim_signals["denial"]):
            candidates.append(f"公开信息：{target_name} 的身份说法前后不一致")

        high_confidence_summaries = [
            *agent.working_memory.get_private_memory_summaries("fortune_teller_info"),
            *agent.working_memory.get_private_memory_summaries("investigator_info"),
            *agent.working_memory.get_private_memory_summaries("empath_info"),
            *agent.working_memory.get_private_memory_summaries("chef_info"),
        ]
        for summary in high_confidence_summaries:
            if target_name in summary:
                candidates.append(f"高可信信息：{summary}")

        if profile and profile.claim_history:
            recent_claim = profile.claim_history[-1]
            if recent_claim.claim_type == "self_claim" and recent_claim.role_id:
                candidates.append(f"公开信息：{target_name} 最近自报 {recent_claim.role_id}")
            if recent_claim.claim_type == "denial" and recent_claim.role_id:
                candidates.append(f"公开信息：{target_name} 最近否认自己是 {recent_claim.role_id}")

        public_claims = agent.working_memory.get_public_memory_summaries("role_claim")
        for summary in reversed(public_claims):
            if target_name in summary:
                candidates.append(f"公开信息：{summary}")

        return candidates

    def best_reasoning_evidence(self, target_id: str | None, visible_state: AgentVisibleState) -> str:
        candidates = self.reasoning_evidence_candidates(target_id, visible_state)
        return candidates[0] if candidates else ""

    def augment_reasoning_with_evidence(
        self,
        reasoning: str,
        *,
        action_type: str,
        target_id: str | None,
        visible_state: AgentVisibleState,
        suspicion: float | None = None,
        threshold: float | None = None,
    ) -> str:
        agent = self._agent
        base = reasoning.strip()
        evidence_candidates = self.reasoning_evidence_candidates(target_id, visible_state)
        parts = [base] if base else []
        if evidence_candidates:
            parts.append(f"依据={evidence_candidates[0]}")
            for extra in evidence_candidates[1:3]:
                if not extra.startswith("公开信息："):
                    parts.append(f"补充={extra}")
                elif action_type in {"nominate", "nomination_intent", "vote"} and "前后不一致" in extra:
                    parts.append(f"补充={extra}")
        if suspicion is not None and threshold is not None:
            label = "怀疑度"
            parts.append(f"{label}={suspicion:.2f} 阈值={threshold:.2f}")
        if action_type in {"nominate", "nomination_intent", "vote"}:
            parts.append(f"风格={agent.persona_profile.get('social_style', '独立')}")
        return " | ".join(part for part in parts if part)

    # ==================================================================
    #  PERSONA HELPERS
    # ==================================================================

    def persona_vote_bias(self, visible_state: AgentVisibleState) -> bool:
        agent = self._agent
        profile = agent.persona_profile or {}
        bias = profile.get("decision_style", "")
        nominee = visible_state.current_nominee
        if nominee == agent.player_id:
            return False
        if agent.team == "evil":
            return bias.startswith("谨慎") or bias.startswith("保持") or bias.startswith("会在")
        return not bias.startswith("压迫") and not bias.startswith("果断")

    def find_most_suspicious_player(self, visible_state: AgentVisibleState) -> str | None:
        """从社交图谱中找到最可疑的存活玩家名称，用于兜底发言。"""
        agent = self._agent
        best_name = None
        best_trust = 0.0
        for player in visible_state.players:
            if player.player_id == agent.player_id or not player.is_alive:
                continue
            profile = agent.social_graph.get_profile(player.player_id)
            if profile and profile.trust_score < best_trust:
                best_trust = profile.trust_score
                best_name = player.name
        return best_name if best_trust < -0.1 else None

    # ==================================================================
    #  LOCAL LOW-VALUE DECISION
    # ==================================================================

    def local_low_value_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str) -> dict[str, Any]:
        agent = self._agent
        if action_type == "vote":
            decision, suspicion, threshold = agent._select_vote_decision(visible_state, legal_context)
            if os.getenv("AI_FORCE_PROGRESS_ACTIONS", "0") == "1":
                decision = True
            return {
                "action": "vote",
                "decision": decision,
                "reasoning": (
                    f"本地启发式投票：怀疑度={suspicion:.2f} 阈值={threshold:.2f}，"
                    f"{'赞成' if decision else '反对'}处决。"
                ),
            }

        selected = agent._select_nomination_target(visible_state, legal_context, intent_mode=True)
        if not selected:
            if os.getenv("AI_FORCE_PROGRESS_ACTIONS", "0") == "1" and legal_context.legal_nomination_targets:
                target_id = legal_context.legal_nomination_targets[0]
                return {
                    "action": "nominate",
                    "target": target_id,
                    "reasoning": f"本地审计推进：选择首个合法提名目标 {target_id}。",
                }
            return {
                "action": "none",
                "target": "not_nominating",
                "reasoning": "本地启发式：当前没有足够强的提名目标。",
            }
        target_id, suspicion, threshold = selected
        return {
            "action": "nominate",
            "target": target_id,
            "reasoning": (
                f"本地启发式提名：目标={target_id} 怀疑度={suspicion:.2f} "
                f"阈值={threshold:.2f}。"
            ),
        }

    def normalize_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str, decision: dict[str, Any]) -> dict[str, Any]:
        agent = self._agent
        if not isinstance(decision, dict):
            return agent._fallback_decision(visible_state, legal_context, action_type, reason="non_dict_response")

        reasoning = str(decision.get("reasoning", ""))
        tone = str(decision.get("tone", "calm"))

        if action_type in {"speak", "nomination_intent"} and decision.get("action") == "slayer_shot" and legal_context.can_slayer_shot:
            target = decision.get("target")
            candidate_ids = {player.player_id for player in visible_state.players if player.is_alive and player.player_id != agent.player_id}
            if isinstance(target, str) and target in candidate_ids:
                suspicion = agent._target_signal_score(target, visible_state)
                return {
                    "action": "slayer_shot",
                    "target": target,
                    "reasoning": agent._augment_reasoning_with_evidence(
                        reasoning or "决定发动猎手技能。",
                        action_type="slayer_shot",
                        target_id=target,
                        visible_state=visible_state,
                        suspicion=suspicion,
                        threshold=0.74,
                    ),
                }

        if action_type in {"nominate", "nomination_intent"}:
            target = decision.get("target")
            if decision.get("action") == "none" or str(target).lower() == "none":
                return {"action": "none", "target": None, "reasoning": reasoning or "放弃提名。"}

            legal_targets = list(legal_context.legal_nomination_targets)
            if target in legal_targets:
                suspicion = agent._target_signal_score(target, visible_state)
                threshold = agent._nomination_threshold(visible_state)
                return {
                    "action": "nominate",
                    "target": target,
                    "reasoning": agent._augment_reasoning_with_evidence(
                        reasoning or "决定提名。",
                        action_type=action_type,
                        target_id=target,
                        visible_state=visible_state,
                        suspicion=suspicion,
                        threshold=threshold,
                    ),
                }

            return agent._fallback_decision(visible_state, legal_context, action_type, reason="invalid_nomination_target")


        if action_type == "vote":
            final_vote = decision.get("decision")
            if isinstance(final_vote, bool):
                suspicion, threshold = (0.0, agent._vote_threshold(visible_state))
                if visible_state.current_nominee:
                    suspicion = agent._target_signal_score(visible_state.current_nominee, visible_state)
                return {
                    "action": "vote",
                    "decision": final_vote,
                    "reasoning": agent._augment_reasoning_with_evidence(
                        reasoning or "完成投票。",
                        action_type=action_type,
                        target_id=visible_state.current_nominee,
                        visible_state=visible_state,
                        suspicion=suspicion,
                        threshold=threshold,
                    ),
                }
            return agent._fallback_decision(visible_state, legal_context, action_type, reason="invalid_vote_decision")

        if action_type == "defense_speech":
            content = str(decision.get("content", "")).strip()
            if not content:
                return agent._fallback_decision(visible_state, legal_context, action_type, reason="empty_defense_speech")
            content = agent._stabilize_speech_content_with_memory(content, visible_state, action_type)
            content = agent._sanitize_public_speech_content(content, visible_state)
            return {"action": "speak", "content": content, "tone": tone, "reasoning": reasoning}

        if action_type in {"night_action", "death_trigger"}:
            targets = agent._coerce_target_values(decision.get("targets"))
            if not targets:
                targets = agent._coerce_target_values(decision.get("target"))

            legal_targets = list(legal_context.legal_night_targets)
            # 兼容自选逻辑
            if getattr(legal_context, "can_target_self", False):
                legal_targets.append(agent.player_id)

            required_targets = max(0, int(getattr(legal_context, "required_targets", 1) or 0))
            if not targets:
                if required_targets > 0:
                    return agent._fallback_decision(visible_state, legal_context, action_type, reason="missing_night_target")
                # 某些角色可能没有目标
                return {"action": action_type, "target": None, "targets": [], "reasoning": reasoning}

            if required_targets > 0 and len(targets) != required_targets:
                return agent._fallback_decision(visible_state, legal_context, action_type, reason="invalid_night_target_count")
            if len(set(targets)) != len(targets):
                return agent._fallback_decision(visible_state, legal_context, action_type, reason="duplicate_night_targets")

            # 校验所有目标是否合法
            all_valid = all(t in legal_targets for t in targets)
            if decision.get("action") in {"night_action", "death_trigger"} and all_valid:
                payload: dict[str, Any] = {"action": action_type, "reasoning": reasoning}
                if len(targets) == 1:
                    payload["target"] = targets[0]
                else:
                    payload["target"] = targets[0]
                    payload["targets"] = targets
                return payload

            return agent._fallback_decision(visible_state, legal_context, action_type, reason="illegal_night_target")

        if decision.get("action") == "skip_discussion":
            return {"action": "skip_discussion", "reasoning": reasoning or "我选择暂时结束发言。"}

        content = str(decision.get("content", "")).strip()
        if not content:
            return agent._fallback_decision(visible_state, legal_context, action_type, reason="empty_speech")
        content = agent._stabilize_speech_content_with_memory(content, visible_state, action_type)
        content = agent._sanitize_public_speech_content(content, visible_state)
        return {"action": "speak", "content": content, "tone": tone, "reasoning": reasoning}

    def fallback_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str, reason: str) -> dict[str, Any]:
        agent = self._agent
        agent._pending_fallback_reason = reason
        fallback = agent._persona_fallback_speech(action_type, reason, visible_state, legal_context)
        if action_type in {"nominate", "nomination_intent"}:
            selection = agent._select_nomination_target(visible_state, legal_context, intent_mode=(action_type == "nomination_intent"))
            if selection:
                target, score, threshold = selection
                return {
                    "action": "nominate",
                    "target": target,
                    "reasoning": agent._augment_reasoning_with_evidence(
                        f"兜底提名，按稳定人格选择更可疑的目标。({reason})",
                        action_type=action_type,
                        target_id=target,
                        visible_state=visible_state,
                        suspicion=score,
                        threshold=threshold,
                    ),
                }
            if action_type == "nomination_intent":
                legal_targets = list(legal_context.legal_nomination_targets)
                if legal_targets:
                    target, score = agent._choose_nomination_target_from_band(
                        legal_targets,
                        visible_state,
                        action_type,
                        "intent_band",
                        tolerance=0.05,
                    )
                    if score >= 0.18:
                        return {
                            "action": "nominate",
                            "target": target,
                            "reasoning": agent._augment_reasoning_with_evidence(
                                f"兜底提名，局势足够可疑，主动推动提名。({reason})",
                                action_type=action_type,
                                target_id=target,
                                visible_state=visible_state,
                                suspicion=score,
                                threshold=agent._nomination_threshold(visible_state),
                            ),
                        }
            if action_type == "nominate":
                legal_targets = list(legal_context.legal_nomination_targets)
                if legal_targets:
                    target, score = agent._choose_nomination_target_from_band(
                        legal_targets,
                        visible_state,
                        action_type,
                        "fallback_force_band",
                        tolerance=0.05,
                    )
                    # 只有怀疑度极高(>0.65)且不在pass_bias中的时候才强制提名
                    if (
                        target
                        and score > 0.65
                        and agent._stable_choice(
                            ["yes", "no"],
                            visible_state.round_number,
                            visible_state.day_number,
                            action_type,
                            "fallback_force",
                        ) == "yes"
                    ):
                        return {
                            "action": "nominate",
                            "target": target,
                            "reasoning": agent._augment_reasoning_with_evidence(
                                f"兜底提名，怀疑度极高，强制推动。({reason})",
                                action_type=action_type,
                                target_id=target,
                                visible_state=visible_state,
                                suspicion=score,
                                threshold=agent._nomination_threshold(visible_state),
                            ),
                        }
            return {"action": "none", "target": None, "reasoning": fallback.get("reasoning", f"决定放弃此轮行动。({reason})")}
        if action_type == "vote":
            vote, suspicion, threshold = agent._select_vote_decision(visible_state, legal_context, None)
            return {
                "action": "vote",
                "decision": vote,
                "reasoning": agent._augment_reasoning_with_evidence(
                    fallback.get('reasoning', f'兜底投票决策。({reason})'),
                    action_type=action_type,
                    target_id=visible_state.current_nominee,
                    visible_state=visible_state,
                    suspicion=suspicion,
                    threshold=threshold,
                ),
            }
        if action_type == "defense_speech":
            return fallback
        if action_type in {"night_action", "death_trigger"}:
            required_targets = max(0, int(getattr(legal_context, "required_targets", 1) or 0))
            selected_targets = agent._select_night_targets(visible_state, legal_context)
            if not selected_targets:
                return fallback
            if required_targets > 1 and len(selected_targets) >= required_targets:
                return {
                    "action": action_type,
                    "target": selected_targets[0],
                    "targets": selected_targets[:required_targets],
                    "reasoning": fallback.get("reasoning", f"兜底夜晚行动。({reason})"),
                }
            if len(selected_targets) == 1:
                return {
                    "action": action_type,
                    "target": selected_targets[0],
                    "reasoning": fallback.get("reasoning", f"兜底夜晚行动。({reason})"),
                }
            return {
                "action": action_type,
                "target": None,
                "targets": selected_targets,
                "reasoning": fallback.get("reasoning", f"兜底夜晚行动。({reason})"),
            }
        return fallback

    def persona_fallback_speech(self, action_type: str, reason: str, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext) -> dict[str, Any]:
        agent = self._agent
        profile = agent.persona_profile or {}
        role_name = profile.get("role_name", agent.name)
        stable_line = agent._public_speech_anchor_line(visible_state)
        evil_coordination = agent._evil_coordination_line(visible_state)
        if action_type == "defense_speech":
            if evil_coordination:
                content = evil_coordination
            elif stable_line:
                content = f"先别急着把票压上来，我更相信我已经确认过的线索：{stable_line}"
            else:
                content = agent._stable_choice(
                    [
                        "我觉得现在最重要的是把信息说清楚，而不是急着扣帽子。",
                        "我知道我看起来有点像目标，但我希望大家再给我一点解释的机会。",
                        "先别急着把票压上来，我愿意把我的判断过程说完整。",
                    ],
                    visible_state.round_number,
                    visible_state.day_number,
                    action_type,
                    "defense",
                )
            return {
                "action": "speak",
                "content": content,
                "tone": "defensive",
                "reasoning": f"兜底辩解，保持角色风格 {role_name}。({reason})",
            }
        if action_type == "vote":
            return {
                "action": "vote",
                "decision": agent._persona_vote_bias(visible_state),
                "reasoning": f"兜底投票，保持角色风格 {role_name}。({reason})",
            }
        if action_type in {"nominate", "nomination_intent"}:
            wants_to_pass = agent._stable_choice(["yes", "yes", "no"], visible_state.round_number, visible_state.day_number, action_type, "pass_bias") == "yes"
            legal_targets = list(legal_context.legal_nomination_targets)

            if not legal_targets or wants_to_pass:
                return {"action": "none", "target": None, "reasoning": f"兜底选择放弃提名。({reason})"}

            target, _ = agent._choose_nomination_target_from_band(
                legal_targets,
                visible_state,
                action_type,
                "nominate_band",
                tolerance=0.05,
            )
            return {
                "action": "nominate",
                "target": target,
                "reasoning": f"兜底强行提名目标。({reason})",
            }
        if action_type in {"night_action", "death_trigger"}:
            legal_targets = list(legal_context.legal_night_targets)
            target = agent._stable_choice(legal_targets, visible_state.round_number, visible_state.day_number, action_type, "night") if legal_targets else None
            return {
                "action": action_type,
                "target": target,
                "reasoning": f"兜底夜晚行动，按稳定人格选择目标。({reason})",
            }
        if evil_coordination:
            content = evil_coordination
        elif stable_line:
            content = f"我先说我更信哪条线：{stable_line}。公开场上的说法我会参考，但不会放在这之上。"
        else:
            content = agent._stable_choice(
                [
                    "我先听大家说完，再决定要不要站队。",
                    "我还在观察局势，暂时不想把话说死。",
                    "先别急着下结论，我想再听听更多细节。",
                ],
                visible_state.round_number,
                visible_state.day_number,
                action_type,
                "speech",
            )
        return {
            "action": "speak",
            "content": content,
            "tone": "calm",
            "reasoning": f"兜底发言，保持角色风格 {role_name}。({reason})",
        }

    def stable_choice(self, options: list[str], round_number: int, day_number: int, action_type: str, salt: str = "") -> str:
        agent = self._agent
        if not options:
            return ""
        digest = agent._stable_hash(
            agent.player_id,
            agent.role_id or "unknown",
            round_number,
            day_number,
            action_type,
            salt,
        )
        index = int(digest[:8], 16) % len(options)
        return options[index]

    def track_own_claims_from_decision(self, decision: dict[str, Any], visible_state: AgentVisibleState) -> None:
        """Track evil agent's own public claims for narrative consistency."""
        agent = self._agent
        extracted = decision.get("extracted_claims") or []
        for claim in extracted:
            if not isinstance(claim, dict):
                continue
            if claim.get("claim_type") == "self_claim":
                role_id = claim.get("role_id", "")
                if role_id:
                    agent.deception_tracker.record_self_claim(
                        role_id, visible_state.day_number,
                        context=f"D{visible_state.day_number}R{visible_state.round_number}",
                    )
        content = str(decision.get("content", ""))
        if content and len(content) > 30:
            role_ids = agent._extract_role_ids_from_text(content)
            for rid in role_ids:
                if rid not in agent.deception_tracker.active_claims:
                    agent.deception_tracker.record_fabrication(visible_state.day_number, content)
                    break