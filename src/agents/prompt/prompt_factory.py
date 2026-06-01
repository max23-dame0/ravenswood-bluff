"""
Prompt construction for AIAgent.

Extracted from AIAgent to reduce god-object size. All methods access agent
state through the injected ``agent`` reference — never import AIAgent itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from src.content.trouble_brewing_terms import get_role_description, get_role_name
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GamePhase,
    Team,
)

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent


class PromptFactory:
    """Builds system-prompt blocks for AIAgent actions."""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ------------------------------------------------------------------
    # Public entry points (called by AIAgent.act / orchestrator)
    # ------------------------------------------------------------------

    def build_persona_prompt_block(
        self,
        action_type: str,
        visible_state: Optional[AgentVisibleState] = None,
    ) -> str:
        agent = self._agent
        profile = agent.persona_profile or {}
        strategy_block = ""
        if visible_state and action_type in ["night_action", "nomination_intent", "nominate"]:
            strategy_block = agent._get_evil_strategic_summary(visible_state)
            if strategy_block:
                strategy_block = f"\n\n{strategy_block}\n"

        action_hints = {
            "speak": "口语化发言，直接表达观点或质疑。",
            "nominate": "你的任务是决定是否提名。如果不确定或不想提名，请果断输出 {\"action\": \"none\"} 放弃提名，不要勉强。",
            "nomination_intent": "你的任务是先判断是否提名。不要像规则机器，先想清楚再说。不确信可直接不提名。",
            "vote": "你的任务是投票。请从性格角度出发，不一定要投给可疑分最高的人；不要像算分机器一样刻板。",
            "defense_speech": "你是被提名者。请像真人一样辩解，语气要贴合你的性格。",
            "night_action": "你在夜晚执行角色能力。请选择符合角色和局势的目标，语气保持自然。",
            "death_trigger": "你刚刚因为夜晚死亡而触发角色能力。请选择合适目标并自然表达。",
        }
        block = f"""【稳定人格锚点】
- 角色名: {profile.get('role_name', get_role_name(agent.role_id or 'unknown'))}
- 角色说明: {profile.get('role_description', get_role_description(agent.role_id or 'unknown'))}
- 个性提示: {agent.persona.description}
- 说话风格: {agent.persona.speaking_style}{strategy_block}
- 人格签名: {profile.get('signature', agent.persona_signature or 'unknown')}
- 角色气质: {profile.get('role_hint', '保持自然、连贯且像真人。')}
- 表达锚点: {profile.get('voice_anchor', '先说结论再补理由')}
- 决策风格: {profile.get('decision_style', '保持谨慎但自然')}
- 语句节奏: {profile.get('speech_rhythm', '短句、自然、不过度模板化')}
- 风险偏好: {profile.get('risk_tolerance', '均衡')}
- 社交倾向: {profile.get('social_style', '独立')}
- 压力方式: {profile.get('assertiveness', '中性')}
- 行为约束: {profile.get('posture', '保持像真人一样思考')}
- 当前动作风格: {action_hints.get(action_type, '保持自然、像人类一样反应。')}
"""
        # Append difficulty modifiers
        preset = agent.difficulty_preset
        if preset.prompt_modifier:
            block += f"\n【难度风格】{preset.prompt_modifier}"
        if preset.speech_style_prompt:
            block += f"\n【发言指导】{preset.speech_style_prompt}"
        if agent.team == Team.EVIL.value and preset.evil_strategy_prompt:
            block += f"\n【邪恶策略】{preset.evil_strategy_prompt}"
            consistency = agent.deception_tracker.get_consistency_guidance()
            if consistency:
                block += f"\n【叙事一致性】{consistency}"
        elif agent.team == Team.GOOD.value and preset.good_strategy_prompt:
            block += f"\n【正义策略】{preset.good_strategy_prompt}"
        return block

    def build_action_context(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext,
        action_type: str,
    ) -> str:
        agent = self._agent
        memory_brief = self.build_memory_signal_brief(visible_state, action_type)
        if action_type in {"nominate", "nomination_intent"}:
            legal_targets = list(legal_context.legal_nomination_targets)
            if legal_targets:
                threshold = agent._nomination_threshold(visible_state)
                base = (
                    f"你可以合法提名的目标只有这些：{', '.join(legal_targets)}。"
                    f"只有当怀疑度明显高于 {threshold:.2f} 时才提名；"
                    "如果没有足够理由，请返回 action=none。"
                )
                if agent._can_attempt_slayer_shot(visible_state, legal_context, action_type):
                    base += " 如果你是猎手且已经对某人形成极强恶魔判断，也可以改为返回 action=slayer_shot 并指定 target。"
                return f"{base}\n{memory_brief}" if memory_brief else base
            base = "当前没有合法提名目标，请返回 action=none。"
            return f"{base}\n{memory_brief}" if memory_brief else base
        if action_type == "vote":
            nominee = agent._player_name_from_visible_state(visible_state.current_nominee, visible_state) if visible_state.current_nominee else "无"
            threshold = legal_context.votes_required
            current_yes = visible_state.yes_votes
            remaining_voters = list(legal_context.remaining_voters)

            me = visible_state.self_view
            ghost_context = ""
            if me and not me.is_alive:
                ghost_context = f"\n- **注意**：你已经死亡，仅剩 {me.ghost_votes_remaining} 票可能决定胜利，请非常慎重地使用。"

            status_context = (
                f"\n- 当前已举手人数：{current_yes} 人"
                f"\n- 处决所需总票数：{threshold} 人"
                f"\n- 尚未表态的人员名单：{', '.join(remaining_voters)}"
            )

            base = (
                f"当前投票对象是：{nominee}。"
                f"{status_context}{ghost_context}"
                "\n只有在你认为目标确认为邪恶阵营，或者你认为这一票是决定性的一票（帮助正义方翻盘或帮助邪恶方处决关键好人）时才投赞成票。"
            )
            return f"{base}\n{memory_brief}" if memory_brief else base
        if action_type == "defense_speech":
            speech_priority = self.build_speech_priority_brief(visible_state)
            base = (
                "你是被提名者，需要进行简短辩解。请返回 action=speak 和一段自然中文。"
                " 辩解时以你的私密信息和高可信线索作为推理基础，但不要直接引用或复述私密信息原文。"
                " 用你自己的话表达推理结论，通过逻辑推理和场上观察到的矛盾来说服其他人。"
                " 不要出现'根据我的信息'、'我的私密信息显示'等暴露底牌的表述。"
            )
            if speech_priority:
                base = f"{base}\n{speech_priority}"
            return f"{base}\n{memory_brief}" if memory_brief else base
        if action_type in {"night_action", "death_trigger"}:
            legal_targets = list(legal_context.legal_night_targets)
            target_count = getattr(legal_context, "required_targets", 1)
            can_self = getattr(legal_context, "can_target_self", False)
            context_msg = f"优先从这些玩家里选择：{', '.join(legal_targets)}。"
            if target_count > 1:
                context_msg += f" 本次行动必须选择正好 {target_count} 个目标。"
            if can_self:
                context_msg += " 你可以选择你自己。"
            return f"{context_msg}\n{memory_brief}" if memory_brief else context_msg
        # First-speaker hint: if no prior discussion speeches exist in this phase
        first_speaker_hint = ""
        has_prior_speeches = any(
            e.event_type == "player_speaks" and e.phase == visible_state.phase
            for e in visible_state.visible_event_log
        )
        if not has_prior_speeches and action_type in {"speak", "defense_speech"}:
            first_speaker_hint = (
                "这是本回合首次发言，场上尚无公开讨论内容。"
                "请基于你的角色信息和夜间结果自然开场，不要引用不存在的先前发言。\n"
            )

        speech_priority = self.build_speech_priority_brief(visible_state)
        if agent.team == "evil":
            base = (
                "作为邪恶阵营，你必须伪装身份并给出虚假推导。**绝不能**泄露你的真实身份、队友、或任何私密底牌。"
                " 发言时应当'假装'依赖某些伪造的事实或逻辑，引导好人互踩。"
            )
        else:
            base = (
                "作为正义阵营，请自然发言。如果你没有确切信息，可以简短表达。 "
                "发言时以你的私密信息和高可信线索作为推理基础，但不要直接复述私密信息原文，"
                "用你自己的话表达推理结论。公开声明可作辅助参考。"
            )
        if agent._can_attempt_slayer_shot(visible_state, legal_context, action_type):
            base += " 如果你是猎手且已经锁定高价值恶魔候选，也可以直接返回 action=slayer_shot 并指定 target。"
        if speech_priority:
            base = f"{base}\n{speech_priority}"
        if first_speaker_hint:
            base = f"{first_speaker_hint}{base}"
        return f"{base}\n{memory_brief}" if memory_brief else base

    def build_memory_signal_brief(self, visible_state: AgentVisibleState, action_type: str = "") -> str:
        agent = self._agent
        lines: list[str] = []

        # Skip private info for speak/defense — already in tiered memory section
        if action_type not in {"speak", "defense_speech"}:
            private_summaries = agent.working_memory.get_private_memory_summaries()
            if private_summaries:
                lines.append("【高可信私密信息】")
                lines.extend(f"- {summary}" for summary in private_summaries[-4:])

        public_summaries = agent.working_memory.get_public_memory_summaries()
        if public_summaries:
            lines.append("【公开信息】")
            lines.extend(f"- {summary}" for summary in public_summaries[-4:])

        empath_hint = agent._empath_neighbor_signal_summary(visible_state)
        if empath_hint:
            lines.append(empath_hint)
        chef_hint = agent._chef_signal_summary()
        if chef_hint:
            lines.append(chef_hint)
        return "\n".join(lines)

    def build_speech_priority_brief(self, visible_state: AgentVisibleState) -> str:
        agent = self._agent
        lines: list[str] = []

        conflict_lines: list[str] = []
        for profile in agent.social_graph.profiles.values():
            claimed_role_id = agent._profile_claimed_role_id(profile)
            if not claimed_role_id:
                continue
            claim_name = get_role_name(claimed_role_id)
            for summary in agent.working_memory.get_private_memory_summaries("role_candidate_hint"):
                if profile.name in summary and "可能是" in summary:
                    mentioned_roles = agent._extract_role_ids_from_text(summary)
                    if mentioned_roles and claimed_role_id not in mentioned_roles:
                        conflict_lines.append(
                            f"- {profile.name} 公开跳 {claim_name}，但你的高可信信息更像在指向别的身份：{summary}"
                        )
                        break
            for summary in agent.working_memory.get_private_memory_summaries("demon_candidate"):
                if profile.name in summary:
                    conflict_lines.append(
                        f"- {profile.name} 的公开说法需要谨慎对待，因为你的高可信信息把他卷入了恶魔候选：{summary}"
                    )
                    break
            for summary in agent.working_memory.get_private_memory_summaries("revealed_role"):
                if profile.name in summary:
                    mentioned_roles = agent._extract_role_ids_from_text(summary)
                    if mentioned_roles and claimed_role_id not in mentioned_roles:
                        conflict_lines.append(
                            f"- {profile.name} 公开跳 {claim_name}，但你的高可信结果直接揭示了另一种身份：{summary}"
                        )
                        break

        if conflict_lines:
            lines.append("【逻辑焦点】公开说法与高可信信息的冲突，可作为重点质问或抗推的线索：")
            lines.extend(conflict_lines[:3])

        return "\n".join(lines)

    def build_visible_state_summary(self, visible_state: AgentVisibleState) -> str:
        player_count = len(visible_state.players)
        alive_count = sum(1 for p in visible_state.players if p.is_alive)

        from src.engine.scripts import get_role_counts
        counts = get_role_counts(player_count)
        board_setup = f"{counts['townsfolk']}镇民, {counts['outsider']}外来者, {counts['minion']}爪牙, {counts['demon']}恶魔"

        player_list = ", ".join(
            f"{p.name}({p.player_id},{'存活' if p.is_alive else '死亡'})"
            for p in visible_state.players
        )
        lines = [
            f"- 公开阶段：{visible_state.phase}，第 {visible_state.day_number} 天，第 {visible_state.round_number} 轮",
            f"- 存活人数：{alive_count}/{player_count}",
            f"- 玩家列表：{player_list}",
            f"- 剧本默认配置（{player_count}人局）：{board_setup}",
        ]
        if visible_state.self_view:
            lines.append(
                f"- 你的认知身份：{visible_state.self_view.perceived_role_id} / {visible_state.self_view.current_team.value} 阵营"
            )
        if visible_state.current_nominator or visible_state.current_nominee:
            lines.append(
                f"- 当前提名链：{visible_state.current_nominator or '无'} -> {visible_state.current_nominee or '无'}"
            )
        if visible_state.nominees_today:
            nominees = ", ".join(visible_state.nominees_today)
            lines.append(f"- 今日被提名过的玩家：{nominees}")
        if visible_state.nominations_today:
            nominators = ", ".join(visible_state.nominations_today)
            lines.append(f"- 今日已提名过的玩家：{nominators}")
        if visible_state.yes_votes:
            lines.append(f"- 今日已投赞成票数：{visible_state.yes_votes}")
        return "\n".join(lines)

    def deception_budget_prompt(self, visible_state: AgentVisibleState) -> str:
        """Return deception budget guidance for evil agents."""
        agent = self._agent
        if agent.team != Team.EVIL.value:
            return ""
        tracker = agent.deception_tracker
        day = visible_state.day_number
        remaining = tracker.max_fabrications_per_day - tracker._daily_fabrication_count.get(day, 0)
        if remaining <= 0:
            return "【虚构预算】你今天的虚构额度已用完。不要再编造新信息，继续沿用你已有的身份和叙事线。"
        if remaining == 1:
            return "【虚构预算】你今天只剩最后一次虚构机会。谨慎使用，优先保持已有叙事的一致性。"
        return ""
