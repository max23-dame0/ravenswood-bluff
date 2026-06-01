from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.content.trouble_brewing_terms import get_role_name
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GamePhase,
    Team,
)

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent


class EvilStrategy:
    """Evil team strategic analysis and night coordination messaging."""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ------------------------------------------------------------------
    # Strategic summary for evil team decision-making
    # ------------------------------------------------------------------

    def get_evil_strategic_summary(self, visible_state: AgentVisibleState) -> str:
        """为邪恶阵营提供战略分析建议。"""
        agent = self._agent
        if agent.team != Team.EVIL.value:
            return ""

        claims = agent.social_graph.get_all_self_claims()
        monk_players = [pid for pid, role in claims.items() if role == "monk"]
        soldier_players = [pid for pid, role in claims.items() if role == "soldier"]
        mayor_players = [pid for pid, role in claims.items() if role == "mayor"]

        summary_parts = ["【邪恶阵营决策建议】"]

        # 1. 防御角色风险 (GAME-3.1)
        if monk_players:
            summary_parts.append(f"- **僧侣风险**: 玩家 {', '.join(monk_players)} 申明了僧侣。注意他们可能保护了核心信息位。")
        if soldier_players:
            summary_parts.append(f"- **士兵风险**: 玩家 {', '.join(soldier_players)} 申明了士兵。恶魔刀他们将无效。")
        if mayor_players:
            summary_parts.append(f"- **市长风险**: 玩家 {', '.join(mayor_players)} 申明了市长。攻击他们可能导致【杀戮转移】。")

        # 2. 哑刀与失败回溯分析 (GAME-3.2)
        kill_events = [e for e in visible_state.visible_event_log if e.event_type == "night_kill"]
        death_events = [e for e in visible_state.visible_event_log if e.event_type == "player_death"]

        if kill_events:
            failures_per_target: dict[str, int] = {}
            redirections: list[str] = []

            for e in kill_events:
                intended_target = e.target or "unknown"
                # 检查该次攻击后是否有对应的死亡事件
                actual_deaths = [
                    de for de in death_events
                    if de.timestamp > e.timestamp and de.phase == e.phase and de.round_number == e.round_number
                ]

                target_died = any(de.target == intended_target for de in actual_deaths)
                if not target_died or e.payload.get("failed"):
                    failures_per_target[intended_target] = failures_per_target.get(intended_target, 0) + 1

                    # [GAME-3.2] 市长转位分析：如果目标没死但其他人死了
                    if actual_deaths and not target_died:
                        other_dead = ", ".join([de.target for de in actual_deaths])
                        redirections.append(f"针对 {intended_target} 的攻击似乎被【转移】到了 {other_dead}")

            last_kill = kill_events[-1]
            last_target = last_kill.target
            last_failures = failures_per_target.get(last_target, 0) if last_target else 0
            is_last_failed = last_failures > 0

            if is_last_failed:
                target_name = agent._player_name_from_visible_state(last_target, visible_state)
                if last_failures >= 2:
                    summary_parts.append(f"- **高危警报**: 你已经连续 {last_failures} 次尝试击杀 {target_name} 失败！这极大概率意味着该目标受到【隐形僧侣】的长期保护，或者是【士兵】。**请务必立即更换目标**。")
                elif redirections:
                    summary_parts.append(f"- **转位警示**: {redirections[-1]}。这高度疑似【市长】在场导致的转位，请谨慎处理。")
                else:
                    summary_parts.append(f"- **哑刀警示**: 昨晚对 {target_name} 的击杀尝试失败了。可能是僧侣保护、士兵或隐形成员。")

        # 3. [GAME-3.1] 隐性保护推断：连续平安夜分析
        night_death_counts: dict[int, int] = {}
        for de in death_events:
            if de.phase == GamePhase.NIGHT:
                night_death_counts[de.round_number] = night_death_counts.get(de.round_number, 0) + 1

        current_round = visible_state.round_number
        peaceful_nights = 0
        for r in range(1, current_round):
            if night_death_counts.get(r, 0) == 0:
                peaceful_nights += 1

        if peaceful_nights >= 2 and not monk_players:
             summary_parts.append(f"- **隐性防御推断**: 本局已出现 {peaceful_nights} 次夜晚无死亡且无人申明僧侣。场上极大概率存在【隐形僧侣】或【士兵/市长】。建议优先刀掉那些表现活跃但一直没死的“稳坐”玩家。")

        # 4. 战术建议
        if agent.role_id == "imp":
            my_trust = agent.social_graph.get_profile(agent.player_id).trust_score if agent.social_graph.get_profile(agent.player_id) else 0
            if my_trust < -0.6:
                summary_parts.append("- **战术建议**: 你目前疑点极高。考虑今晚“自杀”传位给爪牙（Star-pass）以洗清嫌疑。")

        if agent.perceived_role_id in ["fortune_teller", "empath", "undertaker"]:
            summary_parts.append(f"- **伪装同步**: 你目前的伪装身份是 {get_role_name(agent.perceived_role_id)}。请确保护航此身份。")

        # Spy book intelligence
        spy_book_summaries = agent.working_memory.get_objective_memory_summaries("spy_book")
        if spy_book_summaries:
            if agent.role_id == "spy":
                summary_parts.append("- **间谍魔典**: 你拥有完整的角色信息。在邪恶频道中分享关键发现（如谁是僧侣/士兵），帮助恶魔选择击杀目标。")
            else:
                summary_parts.append("- **队友情报**: 你的邪恶同伴（间谍）可能已经分享了场上角色信息，请关注邪恶频道中的情报。")

        if len(summary_parts) <= 1:
            return ""
        return "\n".join(summary_parts)

    # ------------------------------------------------------------------
    # Night coordination messaging for evil team
    # ------------------------------------------------------------------

    async def build_evil_night_coordination_message(
        self,
        action: dict[str, Any],
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext | None = None,
    ) -> str:
        """Generate a night coordination message for the evil team channel.

        Uses LLM for strategic quality, falls back to template on failure.
        """
        agent = self._agent
        if agent.team != Team.EVIL.value:
            return ""
        if visible_state.phase not in {GamePhase.FIRST_NIGHT, GamePhase.NIGHT}:
            return ""

        action_name = action.get("action")
        target_id = action.get("target")
        role_id = agent.perceived_role_id or agent.role_id
        target_name = agent._player_name_from_visible_state(target_id, visible_state) if isinstance(target_id, str) else None

        # Build context for LLM
        context_parts = [f"你的底牌角色：{get_role_name(role_id)}"]

        profile = agent.social_graph.get_profile(agent.player_id)
        if profile and profile.current_self_claim:
            context_parts.append(f"你白天跳的身份：{get_role_name(profile.current_self_claim)}")

        if target_name:
            context_parts.append(f"你今晚的目标：{target_name}")

        # Add strategic summary
        strategic = self.get_evil_strategic_summary(visible_state)
        if strategic:
            context_parts.append(strategic)

        # Team claims context
        team_claims = agent.deception_tracker.get_team_claims()
        if team_claims:
            claims_str = "、".join(f"{n}跳{r}" for n, r in team_claims.items())
            context_parts.append(f"队友已分配的伪装：{claims_str}")

        # Prior evil channel conversation history
        evil_chat_lines: list[str] = []
        for msg in visible_state.public_chat_history:
            if msg.recipient_ids and msg.speaker != agent.player_id:
                speaker_name = "未知"
                for p in visible_state.players:
                    if p.player_id == msg.speaker:
                        speaker_name = p.name
                        break
                evil_chat_lines.append(f"{speaker_name}: {msg.content}")
        if evil_chat_lines:
            # Include last 5 messages to avoid prompt bloat
            recent = evil_chat_lines[-5:]
            context_parts.append("邪恶频道最近的对话：\n" + "\n".join(recent))

        # Difficulty-based quality
        difficulty = agent.difficulty_preset
        if difficulty.competence >= 0.7:
            quality_hint = "请给出具体的战术理由，解释为什么选这个目标，以及白天如何配合。"
        else:
            quality_hint = "简要说明你的行动和白天配合计划。"

        prompt = (
            f"你是邪恶阵营成员，正在夜晚频道向队友汇报你的行动计划。\n"
            f"{chr(10).join(context_parts)}\n"
            f"{quality_hint}\n"
            f"用1-2句话，像在私聊中对队友说话一样自然。不要泄露推理过程的细节。"
        )

        # Try LLM, fall back to template
        try:
            from src.llm.base_backend import Message
            response = await agent.backend.generate(
                system_prompt=prompt,
                messages=[Message(role="user", content="请直接输出邪恶频道的夜晚协调消息。")],
                temperature=difficulty.temperature,
                max_tokens=150,
            )
            content = (response.content or "").strip()
            if content:
                return content
        except Exception:
            pass

        # Template fallback
        return self._build_template_coordination_message(action, visible_state, legal_context)

    def _build_template_coordination_message(
        self,
        action: dict[str, Any],
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext | None = None,
    ) -> str:
        """Fallback template-based coordination message."""
        agent = self._agent
        target_id = action.get("target")
        role_id = agent.perceived_role_id or agent.role_id
        target_name = agent._player_name_from_visible_state(target_id, visible_state) if isinstance(target_id, str) else None

        msg_parts = []
        profile = agent.social_graph.get_profile(agent.player_id)
        if profile and profile.current_self_claim:
            msg_parts.append(f"我白天已经在跳【{get_role_name(profile.current_self_claim)}】了。")
        else:
            bluffs = agent.working_memory.anchor_facts
            bluff_str = ", ".join(bluffs) if bluffs else "无固定"
            msg_parts.append(f"我目前的伪装策略是：看情况跳【{bluff_str}】。")

        if isinstance(target_id, str) and target_name:
            if role_id == "imp":
                score = agent._target_signal_score(target_id, visible_state)
                msg_parts.append(f"我今晚准备刀 {target_name}，这条线当前可疑度较高（{score:.2f}），白天可以顺着这条继续施压。")
            elif role_id == "poisoner":
                priority = agent._poisoner_priority_for_target(target_id, visible_state)
                msg_parts.append(f"我今晚准备毒 {target_name}，这人更像关键信息位（优先级 {priority:.2f}），白天看他的信息表现。")
        else:
            if role_id in {"scarlet_woman", "spy", "baron"}:
                msg_parts.append("我今晚没有主动技能，但我会继续在白天带节奏，帮恶魔挡刀，或者找准好人漏洞进行攻击。")
            else:
                msg_parts.append("我今晚没有行动目标，听大家安排。")

        return " ".join(msg_parts)

    # ------------------------------------------------------------------
    # First-night evil coordination (claim planning)
    # ------------------------------------------------------------------

    async def generate_first_night_coordination(
        self,
        visible_state: AgentVisibleState,
    ) -> str:
        """Generate a first-night coordination message for the evil team chat.

        The demon proposes claim assignments from the 3 bluffs; minions
        see the demon's message and respond/confirm.  This is a sequential
        dialogue, not parallel monologue — later speakers see earlier
        messages via visible_state.public_chat_history.
        """
        agent = self._agent
        if agent.team != Team.EVIL.value:
            return ""

        bluffs = agent.working_memory.get_objective_memory_summaries("evil_bluffs")
        teammates = agent.working_memory.get_objective_memory_summaries("evil_teammates")

        bluff_text = bluffs[0] if bluffs else "无可用伪装角色"
        teammate_text = teammates[0] if teammates else "无队友信息"

        role_hint = "恶魔（Imp）" if agent.role_id == "imp" else "爪牙（Minion）"

        # Build teammate names list for the prompt
        teammate_names = []
        for p in visible_state.players:
            if p.player_id != agent.player_id:
                prof = agent.social_graph.get_profile(p.player_id)
                if prof and prof.trust_score >= 0.9:
                    teammate_names.append(p.name)
        teammate_names_str = "、".join(teammate_names) if teammate_names else "未知队友"

        # Collect existing evil channel messages as conversation history
        evil_chat_lines: list[str] = []
        for msg in visible_state.public_chat_history:
            if msg.recipient_ids and msg.speaker != agent.player_id:
                speaker_name = "未知"
                for p in visible_state.players:
                    if p.player_id == msg.speaker:
                        speaker_name = p.name
                        break
                evil_chat_lines.append(f"{speaker_name}: {msg.content}")

        has_prior_messages = len(evil_chat_lines) > 0
        prior_context = "\n".join(evil_chat_lines) if evil_chat_lines else ""

        if agent.role_id == "imp":
            # Demon: propose claim assignments
            prompt = (
                f"你是{role_hint}，正在首夜邪恶频道中与队友商议伪装身份分配。\n"
                f"{teammate_text}\n"
                f"{bluff_text}\n"
                f"你的队友名字：{teammate_names_str}\n\n"
                f"你是恶魔，你需要给每个队友分配一个不在场角色作为伪装身份。\n"
                f"请明确说出你的分配方案，格式如：'我跳洗衣妇，{teammate_names[0] if teammate_names else '队友A'}跳共情者，{teammate_names[1] if len(teammate_names) > 1 else '队友B'}跳厨师。'\n"
                f"然后简要说明白天如何配合（比如谁给谁发金水、谁报多少个邪恶邻居等）。\n"
                f"用2-3句话，像在私聊中对队友说话一样自然。不要泄露任何推理过程。"
            )
        elif has_prior_messages:
            # Minion responding to demon's proposal
            prompt = (
                f"你是{role_hint}，正在首夜邪恶频道中与队友商议策略。\n"
                f"{teammate_text}\n"
                f"{bluff_text}\n\n"
                f"恶魔刚刚在频道里说了：\n{prior_context}\n\n"
                f"请回应恶魔的分配。如果你同意，确认你接受的角色并说明白天打算怎么演。"
                f"如果你觉得分配有问题（比如你有更好的伪装建议），提出修改意见。\n"
                f"用1-2句话，像在私聊中对队友说话一样自然。不要泄露任何推理过程。"
            )
        else:
            # Minion with no prior messages (shouldn't happen if demon goes first, but fallback)
            prompt = (
                f"你是{role_hint}，正在首夜邪恶频道中与队友商议策略。\n"
                f"{teammate_text}\n"
                f"{bluff_text}\n\n"
                f"请说明你打算白天跳什么身份，以及你的伪装计划。"
                f"用1句话，像在私聊中对队友说话一样自然。不要泄露任何推理过程。"
            )

        # Try LLM, fall back to template
        try:
            from src.llm.base_backend import Message
            response = await agent.backend.generate(
                system_prompt=prompt,
                messages=[Message(role="user", content="请直接输出邪恶频道的协调消息。")],
                temperature=agent.difficulty_preset.temperature,
                max_tokens=200,
            )
            content = (response.content or "").strip()
            if content:
                return content
        except Exception:
            pass

        # Template fallback
        if agent.role_id == "imp":
            return f"我来分配伪装身份：我跳第一个，{teammate_names[0] if teammate_names else '队友A'}跳第二个，剩下的跳第三个。白天配合好，别互相矛盾。"
        elif has_prior_messages:
            return f"收到，我按分配的身份来。白天注意不暴露，互相别拆台。"
        else:
            return f"我听恶魔安排，白天按计划发言。"
