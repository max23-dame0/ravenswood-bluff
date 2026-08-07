"""
Speech sanitization and stabilization for AIAgent.

Extracted from AIAgent to reduce god-object size. All methods access agent
state through the injected ``agent`` reference — never import AIAgent itself.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from src.content.trouble_brewing_terms import get_role_name
from src.state.game_state import AgentVisibleState, Team

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent


class SpeechSanitizer:
    """Sanitizes and stabilizes public speech content for AIAgent."""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ------------------------------------------------------------------
    # Main public methods
    # ------------------------------------------------------------------

    def sanitize_public_speech_content(self, content: str, visible_state: AgentVisibleState) -> str:
        text = content.strip()
        if not text:
            return text

        safe_anchor = self.public_speech_anchor_line(visible_state)
        unsafe_markers = (
            "【绝密",
            "已知邪恶同伴",
            "邪恶同伴名单",
            "evil_teammates",
            "evil_bluffs",
            "spy_book",
            "魔典",
            "bluff",
            "客观信息：",
            "高可信信息：",
            "绝对客观事实",
            "高可信度线索",
        )
        leaks_raw_summary = any(
            summary and summary in text
            for summary in self._hidden_memory_summaries_for_public_filter()
        )
        leaks_marker = any(marker in text for marker in unsafe_markers)
        if not leaks_raw_summary and not leaks_marker:
            return text

        if safe_anchor:
            return random.choice(
                [
                    f"{safe_anchor} 我现在先按这个方向聊，不把所有细节一次性摊开。",
                    f"{safe_anchor} 具体的我先不全说，但这个方向我觉得值得跟。",
                    f"{safe_anchor} 其他的等我再想想，先说这条。",
                ]
            )
        return random.choice(
            [
                "我现在有一些内部判断，但公开场上先看发言逻辑和投票轨迹，不急着把话说死。",
                "我有自己的想法，但不急着全摊开，先看看大家怎么说。",
                "有些事我心里有数，不过现在不是说的时候。",
            ]
        )

    def stabilize_speech_content_with_memory(
        self,
        content: str,
        visible_state: AgentVisibleState,
        action_type: str,
    ) -> str:
        """让真实发言自然引用高可信/客观线索，不套机械前缀。

        PLN-040 修复（2026-08-07）：不再给短发言硬拼"我先说…"固定前缀
        （公式化/机器人感来源）。改为：
        - 保留 LLM 原始发言内容（口语化、自然）；
        - 仅在发言完全未引用任何可信线索、且确实短（<40字）时，
          用多样化的口语句式补一句锚点，且允许从多个自然表达随机选择。
        """
        text = content.strip()
        if not text:
            return text

        stable_line = self.public_speech_anchor_line(visible_state)
        if not stable_line:
            return text
        if stable_line in text:
            return text
        # 保留更长的自然发言（阈值 60→40 更保守，避免覆盖 LLM 已有表达）
        if len(text) >= 40:
            return text

        # 多样化、口语化的自然补锚句式（不再用"我先说…"固定模板）。
        # stable_line 已是完整可发言句子（paraphrase 后），直接并句避免"。。"
        if action_type == "defense_speech":
            prefix = random.choice(
                [
                    "这么说吧，有一件事我比较确定：",
                    "我这边能确认的是：",
                    "别的不敢说，但这一点我有把握：",
                ]
            )
        else:
            prefix = random.choice(
                [
                    "顺嘴提一句，有一点值得大家注意：",
                    "说起来，有件事我一直在琢磨：",
                    "还有一点，我觉得挺关键的：",
                    "对了，有个细节你们可能没注意：",
                ]
            )
        return f"{prefix}{stable_line}，{text}"

    # ------------------------------------------------------------------
    # Anchor line selection
    # ------------------------------------------------------------------

    def public_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        """选择可以公开说出口的锚点，避免照抄私密信息或邪恶队友信息。"""
        agent = self._agent
        evil_coordination = self._evil_coordination_line(visible_state)
        if evil_coordination:
            return evil_coordination

        private_categories = (
            "revealed_role",
            "role_candidate_hint",
            "demon_candidate",
            "fortune_teller_info",
            "investigator_info",
            "empath_info",
            "chef_info",
            "undertaker_info",
            "washerwoman_info",
            "librarian_info",
            "ravenkeeper_info",
        )
        for category in private_categories:
            summaries = agent.working_memory.get_private_memory_summaries(category)
            if summaries:
                return self._private_info_public_paraphrase(summaries[-1], visible_state)

        public_claims = agent.working_memory.get_public_memory_summaries("role_claim")
        if public_claims:
            return public_claims[-1]

        safe_objective_categories = ("death", "failed_kill_target", "role_transfer")
        for category in safe_objective_categories:
            summaries = agent.working_memory.get_objective_memory_summaries(category)
            if summaries:
                return summaries[-1]
        return ""

    def preferred_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        """优先选择最适合真实公开发言引用的高可信/客观线索。"""
        agent = self._agent
        preferred_private_categories = (
            "revealed_role",
            "role_candidate_hint",
            "demon_candidate",
            "evil_teammates",
        )
        for category in preferred_private_categories:
            summaries = agent.working_memory.get_private_memory_summaries(category)
            if summaries:
                return summaries[-1]
        private = agent.working_memory.get_private_memory_summaries()
        if private:
            return private[-1]
        objective = agent.working_memory.get_objective_memory_summaries()
        if objective:
            return objective[-1]
        return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hidden_memory_summaries_for_public_filter(self) -> list[str]:
        agent = self._agent
        hidden: list[str] = []
        for category in (
            "evil_teammates",
            "evil_bluffs",
            "spy_book",
        ):
            hidden.extend(agent.working_memory.get_objective_memory_summaries(category))
            hidden.extend(agent.working_memory.get_private_memory_summaries(category))
        hidden.extend(agent.working_memory.get_private_memory_summaries())
        return [item for item in hidden if item]

    def _evil_coordination_line(self, visible_state: AgentVisibleState) -> str:
        agent = self._agent
        if agent.team != Team.EVIL:
            return ""
        teammate_summaries = agent.working_memory.get_objective_memory_summaries("evil_teammates")
        if not teammate_summaries:
            return ""

        evil_teammate_ids: set[str] = set()
        for player in visible_state.players:
            if player.player_id == agent.player_id:
                continue
            if any(player.name in summary for summary in teammate_summaries):
                evil_teammate_ids.add(player.player_id)

        if not evil_teammate_ids:
            return ""

        claims = agent.social_graph.get_all_self_claims()
        for teammate_id in evil_teammate_ids:
            claim_role_id = claims.get(teammate_id)
            if not claim_role_id:
                continue
            teammate_name = agent._player_name_from_visible_state(teammate_id, visible_state)
            claim_name = get_role_name(claim_role_id)
            return f"我暂时更愿意把 {teammate_name} 当成一个在认真给信息的人，他跳 {claim_name} 这条线我不会先急着否掉。"

        bluff_summaries = agent.working_memory.get_objective_memory_summaries("evil_bluffs")
        if bluff_summaries:
            return random.choice(
                [
                    "场上这身份牌现在都还没捂热，咱们先别急着挨个拆。",
                    "要我说，今天就先看大家发言的劲儿和投票的路子，身份的事往后放放。",
                    "现在谁都说自己是好人，与其争身份，不如先看谁的话经不起推敲。",
                ]
            )
        return ""

    def _mentioned_visible_names(self, summary: str, visible_state: AgentVisibleState) -> list[str]:
        agent = self._agent
        names: list[str] = []
        for player in visible_state.players:
            if player.player_id == agent.player_id:
                continue
            if player.name and player.name in summary:
                names.append(player.name)
        return names

    def _private_info_public_paraphrase(
        self, summary: str, visible_state: AgentVisibleState
    ) -> str:
        names = self._mentioned_visible_names(summary, visible_state)
        if len(names) >= 2:
            pair = "、".join(names[:2])
            return random.choice(
                [
                    f"我手里有一条信息让我更关注 {pair} 这组关系，但细节我先不完全摊开。",
                    f"我觉得 {pair} 之间有些值得琢磨的地方，具体我先不说。",
                    f"有条线索把 {pair} 串在一起了，我还在消化。",
                ]
            )
        if len(names) == 1:
            return random.choice(
                [
                    f"我手里有一条信息让我暂时更关注 {names[0]}，但我不想把底牌一次性说死。",
                    f"有件事让我对 {names[0]} 的看法变了，但我先不说是什么。",
                    f"{names[0]} 身上有条线索我一直没想通。",
                ]
            )
        return random.choice(
            [
                "我手里有一条信息会影响我的判断，但现在先看公开发言能不能对上。",
                "我有条私密线索，目前还不适合公开。",
                "有件事我一直在想，但说出来可能反而帮到不该帮的人。",
            ]
        )
