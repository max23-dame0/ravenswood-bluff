"""
MemoryController - 统一管理 AI Agent 的记忆与人格刷新。

从 AIAgent 中提取，通过组合模式持有对 AIAgent 的引用。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.agents.memory.episodic_memory import Episode
from src.agents.memory.working_memory import Observation
from src.agents.persona_registry import Archetype, get_archetype
from src.content.trouble_brewing_terms import (
    get_role_description,
    get_role_name,
    get_role_persona_hint,
)

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent
    from src.state.game_state import AgentVisibleState, GameState

logger = logging.getLogger(__name__)


class MemoryController:
    """统一管理 AI Agent 的人格刷新、记忆反思、阶段归档、社交图谱同步和数据快照。"""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ------------------------------------------------------------------
    # 1. Persona Profile Refresh
    # ------------------------------------------------------------------

    def refresh_persona_profile(self) -> None:
        """刷新人格画像，根据角色和原型生成稳定的性格特征。"""
        agent = self._agent
        role_id = agent.role_id or "unknown"
        role_name = get_role_name(role_id)
        role_description = get_role_description(role_id, fallback="普通玩家")
        role_hint = get_role_persona_hint(role_id, fallback="保持自然、连贯且像真人。")
        voice_anchor = agent.persona.voice_anchor or agent._pick_stable(
            [
                "先说结论再补理由",
                "先观察再表态",
                "喜欢轻微追问",
                "习惯用反问确认细节",
                "更偏向简短而直接",
                "会先给出保守判断",
            ],
            agent.player_id,
            role_id,
            "voice_anchor",
        )
        decision_style = agent.persona.decision_style or agent._pick_stable(
            [
                "谨慎推进，只有在证据够强时才主动出手。",
                "在有把握前先保持试探，不轻易下最终结论。",
                "偏好稳定推进，优先选择最能解释局势的方案。",
                "如果局势模糊，会先选最不容易暴露自己的路径。",
                "倾向于快速形成判断，但不会让语气显得机械。",
                "会在行动前留一手，但仍保持像真人那样摇摆。",
            ],
            agent.player_id,
            role_id,
            "decision_style",
        )
        speech_rhythm = agent._pick_stable(
            [
                "短句偏多，节奏稳。",
                "喜欢先抛态度再补理由。",
                "偶尔加一点自嘲或试探。",
                "会用反问制造一点压力。",
                "语气比较克制，不会过度激动。",
                "会刻意把话说得更像当场反应。",
            ],
            agent.player_id,
            role_id,
            "speech_rhythm",
        )
        risk_tolerance = agent._pick_stable(
            ["保守", "均衡", "激进"],
            agent.player_id,
            role_id,
            agent.persona.description,
            agent.persona.speaking_style,
            "risk_tolerance",
        )
        social_style = agent._pick_stable(
            ["从众", "独立", "带节奏"],
            agent.player_id,
            role_id,
            agent.persona.description,
            agent.persona.speaking_style,
            "social_style",
        )
        assertiveness = agent._pick_stable(
            ["温和", "中性", "强势"],
            agent.player_id,
            role_id,
            agent.persona.description,
            agent.persona.speaking_style,
            "assertiveness",
        )
        # 加载原型 (Archetype)
        archetype = get_archetype(agent.persona.archetype_key)

        posture = "邪恶阵营" if agent.team == "evil" else "正义阵营"
        signature = agent._stable_hash(agent.player_id, role_id, agent.persona.description, agent.persona.speaking_style)[:10]
        agent.persona_signature = signature
        agent.persona_profile = {
            "role_id": role_id,
            "role_name": role_name,
            "role_description": role_description,
            "role_hint": role_hint,
            "voice_anchor": voice_anchor or archetype.voice_anchor,
            "decision_style": decision_style or archetype.thinking_template,
            "speech_rhythm": speech_rhythm,
            "risk_tolerance": risk_tolerance or archetype.risk_preference,
            "social_style": social_style or archetype.social_style,
            "assertiveness": assertiveness or archetype.assertiveness,
            "posture": posture,
            "signature": signature,
            "archetype": archetype,
        }

        # Apply difficulty overrides
        preset = agent.difficulty_preset
        for key, value in preset.persona_overrides.items():
            agent.persona_profile[key] = value

    # ------------------------------------------------------------------
    # 2. Memory Reflection
    # ------------------------------------------------------------------

    async def reflect(self, visible_state: AgentVisibleState) -> None:
        """
        内部反思逻辑：将当前 WorkingMemory 中的原始观察总结为"局势印象"并存回。
        这是减少上下文窗口压力、形成长期认知的核心。
        """
        agent = self._agent
        if agent.working_memory.is_empty:
            return

        recent_context = agent.working_memory.get_recent_context(limit=agent._obs_limit)
        system_prompt = f"""你是一名正在深入思考《血染钟楼》对局局势的玩家：{agent.name} ({agent.perceived_role_id})。
你要根据当前的近期记忆，总结出你的【局势总体印象】。

请输出一段 200 字以内的总结，包含：
1. 场上谁看起来最可疑，为什么？
2. 场上谁是你目前愿意暂时信任的盟友？
3. 目前存在的重大矛盾或未解之谜。
4. 你目前采取的公开策略（如：假装是占卜师，或者保持低调）。

请只返回总结文本，不要 JSON，不要额外说明。"""

        try:
            from src.llm.base_backend import Message
            response = await agent.backend.generate(
                system_prompt=system_prompt,
                messages=[Message(role="user", content=f"这是你的近期记忆，请提炼局势印象：\n\n{recent_context}")]
            )
            impression = response.content.strip()
            if impression:
                # 存入持久化印象层
                agent.working_memory.add_impression(f"记忆反思（D{visible_state.day_number}）: {impression}")

                # 构造一条总结性的观察片段，存入观察层并触发压缩
                summary_obs = Observation(
                    observation_id=f"reflect-{visible_state.day_number}-{visible_state.round_number}",
                    content=f"【自我反思总结】我现在的总体印象是：{impression[:100]}...",
                    phase=visible_state.phase,
                    round_number=visible_state.round_number
                )
                agent.working_memory.compact(summary_obs)
                logger.info(f"[{agent.name}] 完成了一次记忆反思与蒸馏。")
        except Exception as e:
            logger.error(f"[{agent.name}] 记忆反思失败: {e}")

    async def reflect_if_needed(self, visible_state: AgentVisibleState) -> bool:
        """Public method: check observation count and trigger reflection if threshold exceeded.

        Called by the orchestrator at phase boundaries (end of day discussion, end of first night)
        so agents consolidate memory without blocking the action pipeline.

        Returns True if reflection was triggered, False otherwise.
        """
        agent = self._agent
        if len(agent.working_memory.observations) > agent._reflection_threshold:
            await self.reflect(visible_state)
            return True
        return False

    # ------------------------------------------------------------------
    # 3. Internal Thinking
    # ------------------------------------------------------------------

    async def think(self, prompt: str, visible_state: AgentVisibleState) -> str:
        """内部思考过程，不产生对外影响，仅存入工作记忆"""
        agent = self._agent
        thought_process = f"思考结果: 针对 '{prompt}' 的总结。"
        agent.working_memory.add_thought(thought_process)
        return thought_process

    # ------------------------------------------------------------------
    # 4. Phase Memory Archival
    # ------------------------------------------------------------------

    async def archive_phase_memory(self, visible_state: AgentVisibleState) -> None:
        """
        在阶段切换前把当前阶段的工作记忆提炼为情节记忆。
        W3-D: 升级为逻辑摘要，而不仅是文本切片。
        """
        agent = self._agent
        if agent.working_memory.is_empty:
            return

        # 获取当前阶段的所有观察和思考
        current_obs = [obs.content for obs in agent.working_memory.observations if obs.phase == visible_state.phase]
        current_thoughts = agent.working_memory.internal_thoughts[-5:]

        if not current_obs and not current_thoughts:
            agent.working_memory.clear_transient()
            return

        summary = ""
        # 如果信息量较多，调用 LLM 进行提炼；否则使用简单拼接
        if len(current_obs) > 3:
            try:
                from src.llm.base_backend import Message
                obs_context = "\n".join([f"- {o}" for o in current_obs])
                thought_context = "\n".join([f"- {t}" for t in current_thoughts])

                distill_prompt = f"""请对刚结束的阶段进行极简归纳（30字以内）。
涉及阶段：{visible_state.phase} (D{visible_state.day_number})
发生事件：
{obs_context}
内部判断：
{thought_context}
请总结核心进展和当前对谁最怀疑。"""

                response = await agent.backend.generate(
                    system_prompt="你是一个逻辑严密的血染钟楼玩家。请提供精炼的阶段归纳。",
                    messages=[Message(role="user", content=distill_prompt)]
                )
                summary = response.content.strip() or "阶段总结完成"
            except Exception as e:
                logger.warning(f"[{agent.name}] 内存归档LLM调用失败: {e}")

        # 兜底：信息量少或 LLM 失败时使用规则总结
        if not summary:
            parts = []
            if current_obs:
                parts.append(f"事态: {';'.join(current_obs[:2])}")
            if current_thoughts:
                parts.append(f"想法: {current_thoughts[-1]}")
            summary = " | ".join(parts)

        episode = Episode(
            phase=visible_state.phase,
            round_number=visible_state.round_number,
            day_number=visible_state.day_number,
            summary=summary[:280],
        )
        # [Task B] 将阶段总结存入向量记忆
        if getattr(agent, "vector_memory", None):
            import asyncio
            asyncio.create_task(
                agent.vector_memory.add_text(
                    f"阶段总结 ({visible_state.phase}): {summary[:280]}",
                    {"type": "phase_summary", "phase": str(visible_state.phase), "round": visible_state.round_number}
                )
            )
        # 提取关键事件标签
        for obs in agent.working_memory.observations:
            if obs.phase == visible_state.phase and obs.source_event:
                if obs.source_event.event_type not in episode.key_events:
                    episode.key_events.append(obs.source_event.event_type)

        agent.episodic_memory.add_episode(episode)
        agent.working_memory.clear_transient()
        logger.info(f"[{agent.name}] 归档了阶段记忆: {visible_state.phase}")

    # ------------------------------------------------------------------
    # 5. Data Snapshot Summary
    # ------------------------------------------------------------------

    def build_data_snapshot_summary(self) -> dict[str, Any]:
        """为数据采集提供轻量 AI 摘要。"""
        agent = self._agent
        claim_summary: dict[str, list[str]] = {}
        for player_id, profile in agent.social_graph.profiles.items():
            if not profile.claim_history:
                continue
            claim_summary[player_id] = [
                agent.social_graph._format_claim_record(record)
                for record in profile.claim_history[-2:]
            ]

        embedding_status: dict[str, Any] = {}
        if hasattr(agent.backend, "get_embedding_status"):
            try:
                embedding_status = dict(getattr(agent.backend, "get_embedding_status")())
            except Exception:
                embedding_status = {}

        vector_stats = agent.vector_memory.get_stats() if hasattr(agent.vector_memory, "get_stats") else {}
        last_query = vector_stats.get("last_query") or agent._last_retrieval_query
        top_hits = vector_stats.get("last_hits_preview") or [item.get("text", "") for item in agent._last_retrieval_items[:3]]
        hit_count = vector_stats.get("last_hit_count", len(agent._last_retrieval_items))

        return {
            "working_memory_summary": {
                "objective": agent.working_memory.get_objective_memory_summaries()[-3:],
                "high_confidence": agent.working_memory.get_private_memory_summaries()[-3:],
                "public": agent.working_memory.get_public_memory_summaries()[-3:],
                "observations": [obs.content for obs in agent.working_memory.observations[-3:]],
                "impressions": agent.working_memory.impressions[-3:],
            },
            "social_graph_summary": agent.social_graph.get_graph_summary(),
            "claim_history_summary": claim_summary,
            "retrieval_summary": {
                "status": vector_stats.get("status", "unknown"),
                "embeddings_enabled": vector_stats.get("embeddings_enabled"),
                "disable_reason": vector_stats.get("disable_reason") or embedding_status.get("disabled_reason"),
                "last_query": last_query,
                "hit_count": hit_count,
                "top_hits": top_hits,
                "vector_stats": vector_stats,
                "embedding_status": embedding_status,
            },
        }

    # ------------------------------------------------------------------
    # 6. Social Graph Synchronization
    # ------------------------------------------------------------------

    def sync_social_graph(self, game_state: GameState) -> None:
        """从完整 GameState 初始化社交图谱中的所有玩家。"""
        agent = self._agent
        for player in game_state.players:
            agent.social_graph.init_player(player.player_id, player.name)

    def prime_social_graph_from_state(self, visible_state: AgentVisibleState) -> None:
        """根据可见状态中的聊天消息更新社交图谱的信任/怀疑分数。"""
        agent = self._agent
        visible_messages = list(visible_state.public_chat_history)
        state_signature = agent._stable_hash(
            visible_state.day_number,
            visible_state.round_number,
            len(visible_messages),
            len(visible_state.visible_event_log),
        )
        if state_signature == agent._last_social_prime_signature:
            return

        agent._last_social_prime_signature = state_signature
        for player in visible_state.players:
            agent.social_graph.init_player(player.player_id, player.name)

        suspicion_keywords = ("怀疑", "可疑", "怪", "假", "骗", "不对", "危险")
        trust_keywords = ("信任", "支持", "同意", "靠谱", "好人", "合理")
        # W3-C: 获取人格原型以调整信任度变化速率
        profile_p = agent.persona_profile or {}
        archetype = profile_p.get("archetype")
        decay_multi = archetype.trust_decay_rate if isinstance(archetype, Archetype) else 1.0
        growth_multi = archetype.trust_growth_rate if isinstance(archetype, Archetype) else 1.0

        for message in visible_messages[-10:]:
            content = message.content.lower()
            for player in visible_state.players:
                if player.player_id == agent.player_id:
                    continue
                player_name = player.name.lower()
                if player_name not in content:
                    continue
                profile = agent.social_graph.get_profile(player.player_id)
                if not profile:
                    continue
                if any(keyword in content for keyword in suspicion_keywords):
                    # 怀疑信号增强
                    profile.trust_score = max(-1.0, profile.trust_score - (0.18 * decay_multi))
                    profile.notes.append(f"聊天里出现对 {player.name} 的怀疑信号")
                if any(keyword in content for keyword in trust_keywords):
                    # 信任信号增强
                    profile.trust_score = min(1.0, profile.trust_score + (0.10 * growth_multi))
                    profile.notes.append(f"聊天里出现对 {player.name} 的信任信号")
