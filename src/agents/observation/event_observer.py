"""
Event observation, social graph updates, critical event memory, role statement
extraction, and event formatting for AIAgent.

Extracted from AIAgent to reduce god-object size. All methods access agent
state through the injected ``agent`` reference -- never import AIAgent at
runtime.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from src.agents.memory.social_graph import ClaimRecord
from src.agents.memory.working_memory import Observation
from src.agents.persona.persona import ParsedRoleStatement
from src.content.trouble_brewing_terms import TROUBLE_BREWING_ROLE_TERMS, get_role_name
from src.state.game_state import (
    AgentVisibleState,
    ChatMessage,
    GameEvent,
)

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent

logger = logging.getLogger(__name__)


class EventObserver:
    """Handles event observation, social graph updates, critical event memory,
    role statement extraction, and event formatting for AIAgent."""

    def __init__(self, agent: AIAgent) -> None:
        self._agent = agent

    # ------------------------------------------------------------------
    # Social graph updates from events
    # ------------------------------------------------------------------

    def process_event_for_social_graph(self, event: GameEvent) -> None:
        """根据观察到的事件自动微调对场上其他人的信任分"""
        agent = self._agent
        actor_id = event.actor
        target_id = event.target

        # 1. 提名事件：提名者对被提名者通常持有怀疑态度
        if event.event_type == "nomination_started" and actor_id and target_id:
            # 如果我是被提名者，我对提名者的信任度大幅下降
            if target_id == agent.player_id:
                agent.social_graph.update_trust(actor_id, -0.3)
            # 如果我看到别人提名别人，我对提名者的判断取决于我对被提名者的看法（暂留待以后逻辑化）
            # 当前简化处理：提名行为本身是一个强对抗信号

        # 2. 投票事件：观察谁在投谁
        elif event.event_type == "vote_cast" and actor_id and target_id:
            voted_yes = event.payload.get("vote", False)
            # 如果别人投了我且投的是赞成死刑，信用下降
            if target_id == agent.player_id and voted_yes:
                agent.social_graph.update_trust(actor_id, -0.2)
            # 如果别人投了我且投的是反对死刑，信用上升
            elif target_id == agent.player_id and not voted_yes:
                agent.social_graph.update_trust(actor_id, 0.15)

        # 3. 死亡事件：被执行死刑的人如果身份揭露（如果有的话），可以大幅逆推
        elif event.event_type == "execution_resolved":
            # 这里需要结合 visible_state 的身份变化，如果发现投错好人，则对推进者减分
            pass

    # ------------------------------------------------------------------
    # Main entry: observe an event
    # ------------------------------------------------------------------

    async def observe_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        """接收系统广播的事件并存入工作记忆"""
        agent = self._agent
        if not agent._is_event_visible_to_self(event):
            return
        # 将事件格式化为可读的观察结果
        content = self.format_event_to_text(event, visible_state)
        if not content:
            return

        obs = Observation(
            observation_id=event.event_id,
            content=content,
            source_event=event,
            phase=visible_state.phase,
            round_number=visible_state.round_number
        )
        agent.working_memory.add_observation(obs)

        # W3-D: 基于事件自动化更新社交图谱
        self.process_event_for_social_graph(event)
        self.remember_critical_event(event, visible_state)
        await self.ingest_visible_event_to_vector_memory(event)

    # ------------------------------------------------------------------
    # Vector memory ingestion
    # ------------------------------------------------------------------

    async def ingest_visible_event_to_vector_memory(self, event: GameEvent) -> None:
        """将当前玩家可见的事件摄入向量记忆。"""
        agent = self._agent
        try:
            if event.event_type == "player_speaks":
                message = ChatMessage(
                    speaker=event.actor or "unknown",
                    content=event.payload.get("content", ""),
                    phase=event.phase,
                    round_number=event.round_number,
                    target_player=event.target,
                )
                await agent.vector_memory.add_message(message)
                return
            await agent.vector_memory.add_event(event)
        except Exception as exc:
            logger.warning("[%s] 向量记忆摄入失败: %s", agent.name, exc)

    # ------------------------------------------------------------------
    # Critical event memory storage
    # ------------------------------------------------------------------

    def remember_critical_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        agent = self._agent
        if event.event_type == "private_info_delivered" and event.target == agent.player_id:
            payload = event.payload or {}
            info_type = payload.get("type", "night_info")
            title = payload.get("title") or get_role_name(agent.perceived_role_id or agent.role_id or "unknown")
            lines = payload.get("lines", [])
            detail = " ".join(str(line) for line in lines[:3]) if isinstance(lines, list) else ""
            remembered = f"{title}: {detail}".strip(": ")
            self.store_private_info_memory(
                info_type,
                remembered or f"你收到了私密信息: {info_type}",
                visible_state,
            )
            self.store_targeted_private_hints(info_type, payload, visible_state)

            # Structured spy book storage — each player-role as separate memory
            if info_type == "spy_book":
                book = payload.get("book", [])
                for entry in book:
                    pid = entry.get("player_id", "")
                    role_id = entry.get("role_id", "unknown")
                    team = entry.get("team", "unknown")
                    player_name = agent._player_name_from_visible_state(pid, visible_state) if pid else "未知"
                    role_name = get_role_name(role_id)
                    agent.working_memory.remember_objective_info(
                        "spy_book",
                        f"【间谍魔典】{player_name} 的真实身份是 {role_name}（{team}阵营）",
                        day_number=visible_state.day_number,
                        round_number=visible_state.round_number,
                        source="spy_book",
                    )

            teammates = payload.get("teammates", [])
            if teammates:
                teammates_str = ', '.join(teammates)
                agent.working_memory.remember_objective_info(
                    "evil_teammates",
                    f"【绝密推演可用】已知邪恶同伴名单：{teammates_str}",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="evil_team_info",
                )
                for teammate_name in teammates:
                    teammate = next((player for player in visible_state.players if player.name == teammate_name), None)
                    if teammate:
                        agent.social_graph.init_player(teammate.player_id, teammate.name)
                        agent.social_graph.add_note(teammate.player_id, "已由邪恶私密信息确认是己方队友")
                        agent.social_graph.update_trust(teammate.player_id, 1.0)

            bluffs = payload.get("bluffs", [])
            if bluffs:
                bluff_names = [get_role_name(role_id) for role_id in bluffs]
                bluffs_str = ', '.join(bluff_names)
                agent.working_memory.remember_objective_info(
                    "evil_bluffs",
                    f"【伪装策略】适合邪恶阵营穿的衣服（bluff）：{bluffs_str}",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="evil_bluff_info",
                )
            return

        # Extract claim assignments from evil coordination messages
        if event.event_type == "player_speaks" and event.payload.get("is_private") and agent.team == "evil":
            content = event.payload.get("content", "")
            speaker = event.actor
            if speaker != agent.player_id and content:
                self._extract_team_claims_from_coordination(content, agent, visible_state)
            return

        if event.event_type == "nomination_started":
            agent.working_memory.remember_objective_info(
                "nomination",
                f"{agent._player_name_from_visible_state(event.actor, visible_state)} 提名了 {agent._player_name_from_visible_state(event.target, visible_state)}",
                day_number=visible_state.day_number,
                round_number=visible_state.round_number,
                source="event_log",
            )
            return

        if event.event_type == "voting_resolved":
            votes = event.payload.get("votes", 0)
            needed = event.payload.get("needed", 0)
            passed = "通过" if event.payload.get("passed") else "未通过"
            agent.working_memory.remember_objective_info(
                "voting_result",
                f"对 {agent._player_name_from_visible_state(event.target, visible_state)} 的投票结果：{passed}（{votes}/{needed}）",
                day_number=visible_state.day_number,
                round_number=visible_state.round_number,
                source="event_log",
            )
            return

        # [GAME-3.2] 恶魔感知自己的夜晚击杀结果（哑刀持久化到记忆层）
        if event.event_type == "night_kill" and event.actor == agent.player_id:
            target_name = agent._player_name_from_visible_state(event.target, visible_state)
            failed = event.payload.get("failed", False)
            reason = event.payload.get("reason", "unknown")
            redirected = event.payload.get("redirected_from")

            if failed:
                agent.working_memory.remember_objective_info(
                    "kill_failed",
                    f"你在第 {visible_state.round_number} 轮尝试击杀 {target_name} 失败（原因: {reason}）。该目标可能受僧侣保护或为士兵。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="night_kill_result",
                )
                # 追踪失败历史，用于后续决策
                if not hasattr(agent, "_kill_failure_history"):
                    agent._kill_failure_history: dict[str, int] = {}
                target_id = event.target or "unknown"
                agent._kill_failure_history[target_id] = agent._kill_failure_history.get(target_id, 0) + 1
                count = agent._kill_failure_history[target_id]
                agent.working_memory.remember_objective_info(
                    "failed_kill_target",
                    f"{target_name} 是高风险刀人失败目标：已连续失败 {count} 次（原因: {reason}）。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="night_kill_result",
                )
                if count >= 2:
                    agent.working_memory.remember_objective_info(
                        "kill_blacklist",
                        f"警告：{target_name} 已被连续攻击 {count} 次均失败，极大概率受到持续保护，应立即放弃该目标。",
                        day_number=visible_state.day_number,
                        round_number=visible_state.round_number,
                        source="night_kill_analysis",
                    )
            elif redirected:
                redirected_name = agent._player_name_from_visible_state(redirected, visible_state)
                agent.working_memory.remember_objective_info(
                    "kill_redirected",
                    f"你在第 {visible_state.round_number} 轮尝试击杀 {redirected_name}，但攻击被转移到了 {target_name}（可能是市长转位）。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="night_kill_result",
                )
            else:
                agent.working_memory.remember_objective_info(
                    "kill_success",
                    f"你在第 {visible_state.round_number} 轮成功击杀了 {target_name}。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="night_kill_result",
                )
            return

        if event.event_type in {"player_death", "execution_resolved"}:
            target_name = agent._player_name_from_visible_state(event.target, visible_state)
            reason = event.payload.get("reason")
            summary = f"{target_name} 死亡"
            if reason:
                summary += f"，原因：{reason}"
            agent.working_memory.remember_objective_info(
                "death",
                summary,
                day_number=visible_state.day_number,
                round_number=visible_state.round_number,
                source="event_log",
            )

            # [Task D] 自动冻结死者记忆
            if event.target and event.target != agent.player_id:
                profile = agent.social_graph.get_profile(event.target)
                if profile and not profile.is_frozen:
                    # 如果此人有跳身份且没有明显的改口冲突，则冻结
                    if profile.current_self_claim and agent.social_graph.claim_conflict_count(event.target) == 0:
                        summary_text = f"死者，跳身份为 {get_role_name(profile.current_self_claim)}，生前表现稳定。"
                        agent.social_graph.freeze_player(event.target, summary_text)
            return

        # [GAME-3.3] 角色转移事件（Star-pass）：新恶魔继承身份与 bluffs
        if event.event_type == "role_transfer" and event.target == agent.player_id:
            payload = event.payload or {}
            new_role = payload.get("new_role")
            reason = payload.get("reason", "unknown")
            bluffs = payload.get("bluffs", [])
            old_perceived = payload.get("old_perceived_role")

            if new_role:
                agent.role_id = new_role
                agent.true_role_id = new_role
                # 保持公开伪装身份不变
                if old_perceived:
                    agent.perceived_role_id = old_perceived

                agent.working_memory.remember_objective_info(
                    "role_transfer",
                    f"你的角色已从爪牙变为【小恶魔】（原因: {reason}）。你现在是恶魔，每晚需要选择一名玩家击杀。你的公开伪装身份仍然是 {get_role_name(old_perceived or agent.perceived_role_id or 'unknown')}。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="role_transfer",
                )

            if bluffs:
                bluff_names = [get_role_name(b) for b in bluffs]
                agent.working_memory.remember_objective_info(
                    "evil_bluffs",
                    f"可用的伪装角色（bluffs）: {', '.join(bluff_names)}",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="role_transfer_bluffs",
                )

            logger.info("[%s] 角色转移完成: 新角色=%s, 伪装=%s, bluffs=%s",
                       agent.name, new_role, old_perceived, bluffs)
            return

        if event.event_type in {"player_speaks", "defense_started"} and event.actor and event.actor != agent.player_id:
            actor_name = agent._player_name_from_visible_state(event.actor, visible_state)
            extracted = event.payload.get("extracted_claims")
            if extracted is not None:
                statements = [
                    ParsedRoleStatement(
                        role_id=c.get("role_id"),
                        claim_type=c.get("claim_type"),
                        subject_player_ids=tuple(c.get("subject_player_ids", [])),
                        source_text=event.payload.get("content", "")
                    ) for c in extracted
                ]
            else:
                statements = self.extract_role_statements(event.payload.get("content", ""), event.actor, visible_state)
            for statement in statements:
                if event.event_type == "defense_started" and statement.claim_type == "self_claim":
                    continue  # defense speeches deny, not claim — filter false positives
                if statement.claim_type == "self_claim":
                    agent.social_graph.init_player(event.actor, actor_name)
                    agent.social_graph.record_claim(
                        event.actor,
                        statement.role_id,
                        "self_claim",
                        source_text=statement.source_text,
                        round_number=visible_state.round_number,
                        day_number=visible_state.day_number,
                        speaker_id=event.actor,
                        speaker_name=actor_name,
                    )
                    agent.social_graph.add_note(event.actor, f"公开跳身份为 {get_role_name(statement.role_id)}")

                    # [Task D] 如果此人之前被冻结，现在改口了，必须解冻
                    profile = agent.social_graph.get_profile(event.actor)
                    if profile and profile.is_frozen and profile.current_self_claim != statement.role_id:
                        agent.social_graph.thaw_player(event.actor, f"改口跳身份: {statement.role_id}")

                    agent.working_memory.remember_fact(f"{actor_name} 公开跳身份为 {get_role_name(statement.role_id)}")
                    agent.working_memory.remember_public_info(
                        "role_claim",
                        f"{actor_name} 公开跳身份为 {get_role_name(statement.role_id)}",
                        day_number=visible_state.day_number,
                        round_number=visible_state.round_number,
                        source="public_speech",
                    )
                elif statement.claim_type == "denial":
                    agent.social_graph.init_player(event.actor, actor_name)
                    agent.social_graph.record_claim(
                        event.actor,
                        statement.role_id,
                        "denial",
                        source_text=statement.source_text,
                        round_number=visible_state.round_number,
                        day_number=visible_state.day_number,
                        speaker_id=event.actor,
                        speaker_name=actor_name,
                    )
                    agent.social_graph.add_note(event.actor, f"否认自己是 {get_role_name(statement.role_id)}")
                elif statement.claim_type in {"question", "accusation", "relay"}:
                    # Init speaker profile so claims_about_others can be stored
                    agent.social_graph.init_player(event.actor, actor_name)
                    for subject_id in statement.subject_player_ids:
                        subject_name = agent._player_name_from_visible_state(subject_id, visible_state)
                        agent.social_graph.init_player(subject_id, subject_name)

                        # Add to claims_about_others
                        prof = agent.social_graph.get_profile(event.actor)
                        if prof:
                            if subject_id not in prof.claims_about_others:
                                prof.claims_about_others[subject_id] = []
                            prof.claims_about_others[subject_id].append(
                                ClaimRecord(
                                    role_id=statement.role_id,
                                    claim_type=statement.claim_type,
                                    source_text=statement.source_text,
                                    round_number=visible_state.round_number,
                                    day_number=visible_state.day_number,
                                    speaker_id=event.actor,
                                    speaker_name=actor_name,
                                )
                            )

                        verb = "质疑像" if statement.claim_type == "question" else "怀疑是"
                        if statement.claim_type == "relay":
                            verb = "[转述-非自报] 转述称其跳了"
                        agent.social_graph.add_note(subject_id, f"{actor_name} {verb} {get_role_name(statement.role_id)}")

        # 公开发言存入公开信息层（无论是否包含角色声明）
        if event.event_type == "player_speaks" and event.actor and event.actor != agent.player_id:
            content = event.payload.get("content", "")
            if content:
                actor_name = agent._player_name_from_visible_state(event.actor, visible_state)
                agent.working_memory.remember_public_info(
                    "speech",
                    f"{actor_name}: {content[:120]}",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source="public_speech",
                )

    # ------------------------------------------------------------------
    # Private info memory storage
    # ------------------------------------------------------------------

    def store_private_info_memory(self, info_type: str, summary: str, visible_state: AgentVisibleState) -> None:
        agent = self._agent
        summary = (summary or "").strip()
        if summary and summary not in agent.working_memory.anchor_facts:
            agent.working_memory.anchor_facts.append(summary)
            agent.working_memory.anchor_facts = agent.working_memory.anchor_facts[-agent.working_memory.fact_limit:]

        objective_info_types = {"evil_team_info", "spy_book"}
        high_confidence_info_types = {
            "washerwoman_info",
            "librarian_info",
            "investigator_info",
            "chef_info",
            "empath_info",
            "undertaker_info",
            "fortune_teller_info",
            "ravenkeeper_info",
        }
        if info_type in objective_info_types:
            agent.working_memory.remember_objective_info(
                info_type,
                summary,
                day_number=visible_state.day_number,
                round_number=visible_state.round_number,
                source="private_info",
            )
            return
        if info_type in high_confidence_info_types:
            agent.working_memory.remember_private_info(
                info_type,
                summary,
                day_number=visible_state.day_number,
                round_number=visible_state.round_number,
                source="storyteller_private_info",
            )
            return
        agent.working_memory.remember_private_info(
            info_type,
            summary,
            day_number=visible_state.day_number,
            round_number=visible_state.round_number,
            source="private_info",
        )

    # ------------------------------------------------------------------
    # Team claim extraction from evil coordination messages
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_team_claims_from_coordination(content: str, agent: Any, visible_state: AgentVisibleState) -> None:
        """Extract role claim assignments from evil channel coordination messages.

        Looks for patterns like '我跳XX', '我跳【XX】', '{name}跳YY'.
        Stores results in the deception tracker's team claims.
        """
        import re

        # Pattern: <subject>跳<role> — subject can be a name or 我
        # Handles: "我跳洗衣妇", "我跳【洗衣妇】", "A跳共情者"
        matches = re.findall(r'([一-鿿\w]+?)跳[【\[]?([一-鿿]+)[】\]，。、\s]?', content)
        for claimant, role_name in matches:
            if claimant in ("我", "我方", "本人"):
                # Resolve "我" to the speaker's name
                speaker_name = None
                for p in visible_state.players:
                    if p.player_id == agent.player_id:
                        speaker_name = p.name
                        break
                claimant = speaker_name or claimant
            # Store raw Chinese role name — the tracker only needs uniqueness
            agent.deception_tracker.record_team_claim(claimant, role_name)

    # ------------------------------------------------------------------
    # Targeted private hints from night info
    # ------------------------------------------------------------------

    def store_targeted_private_hints(
        self,
        info_type: str,
        payload: dict[str, Any],
        visible_state: AgentVisibleState,
    ) -> None:
        agent = self._agent
        role_seen = payload.get("role_seen")
        role_name = get_role_name(role_seen) if role_seen else None
        players: list[str] = list(payload.get("players", [])) if isinstance(payload.get("players", []), list) else []

        def player_name(pid: str) -> str:
            return agent._player_name_from_visible_state(pid, visible_state)

        if info_type in {"washerwoman_info", "librarian_info", "investigator_info"} and players and role_seen:
            for pid in players:
                if info_type == "investigator_info":
                    summary = f"【绝密线索】根据你收到的情报，{player_name(pid)} 可能是 {role_name}。"
                else:
                    summary = f"【内部直觉】根据目前掌握的信息，{player_name(pid)} 可能是 {role_name}。"
                agent.working_memory.remember_private_info(
                    "role_candidate_hint",
                    summary,
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source=info_type,
                )

        if info_type == "fortune_teller_info" and players and payload.get("has_demon", payload.get("result")):
            for pid in players:
                agent.working_memory.remember_private_info(
                    "demon_candidate",
                    f"{player_name(pid)} 出现在你的占卜高可信结果里，至少其中一人可能是恶魔。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source=info_type,
                )

        for target_key in ("player_id", "target_player", "target"):
            target_id = payload.get(target_key)
            if isinstance(target_id, str) and target_id and role_seen:
                agent.working_memory.remember_private_info(
                    "revealed_role",
                    f"{player_name(target_id)} 的身份被高可信信息指出为 {role_name}。",
                    day_number=visible_state.day_number,
                    round_number=visible_state.round_number,
                    source=info_type,
                )
                break

    # ------------------------------------------------------------------
    # Event formatting
    # ------------------------------------------------------------------

    def format_event_to_text(self, event: GameEvent, visible_state: AgentVisibleState) -> str:
        """将事件对象渲染为自然语言描述"""
        agent = self._agent
        actor = agent._player_name_from_visible_state(event.actor, visible_state) if event.actor else "系统"
        target = agent._player_name_from_visible_state(event.target, visible_state) if event.target else "某个目标"

        if event.event_type == "player_speaks":
            msg = event.payload.get("content", "")
            return f"\U0001f4ac {actor} 说: '{msg}'"
        elif event.event_type == "nomination_started":
            return f"⚠️ {actor} 发起了对 {target} 的处决提名。"
        elif event.event_type == "vote_cast":
            decision = "赞成" if event.payload.get("vote") else "反对"
            return f"✋ {actor} 对处决 {target} 投了 {decision}票。"
        elif event.event_type == "voting_resolved":
            passed = event.payload.get("passed", False)
            return f"⚖️ 对 {target} 的投票结果出炉: 票数{'足够' if passed else '不足'}将其送上处决台。"
        elif event.event_type in {"player_death", "execution_resolved"}:
            return f"\U0001f480 {target} 已经死亡。"
        elif event.event_type == "private_info_delivered":
            info_type = event.payload.get("type", "night_info")
            title = event.payload.get("title")
            lines = event.payload.get("lines", [])
            detail = " ".join(str(line) for line in lines[:2]) if isinstance(lines, list) else ""
            if title and detail:
                return f"\U0001f319 你收到了私密信息 {title}: {detail}"
            if detail:
                return f"\U0001f319 你收到了私密信息 {info_type}: {detail}"
            return f"\U0001f319 你收到了私密信息: {info_type}"

        return f"系统事件: {event.event_type}"

    # ------------------------------------------------------------------
    # Role term iteration
    # ------------------------------------------------------------------

    def _iter_role_terms(self) -> list[tuple[str, str, str]]:
        role_terms: list[tuple[str, str, str]] = []
        for role_id, term in TROUBLE_BREWING_ROLE_TERMS.items():
            role_terms.append((role_id, term["zh_name"], term["en_name"]))
            # W3-C: 增加常用别名支持，兼容测试用例与玩家口语（如：占卜师=预言家，投毒者=毒师，酒鬼=醉汉）
            if role_id == "fortune_teller":
                role_terms.append((role_id, "预言家", "Fortune Teller"))
            elif role_id == "poisoner":
                role_terms.append((role_id, "毒师", "Poisoner"))
            elif role_id == "drunken":
                role_terms.append((role_id, "醉汉", "Drunk"))
        return sorted(role_terms, key=lambda item: len(item[1]), reverse=True)

    # ------------------------------------------------------------------
    # Role statement extraction from speech text
    # ------------------------------------------------------------------

    def extract_role_statements(
        self,
        content: str,
        speaker_id: str,
        visible_state: AgentVisibleState,
    ) -> list[ParsedRoleStatement]:
        agent = self._agent
        text = (content or "").strip()
        if not text:
            return []
        lowered = text.lower()
        statements: list[ParsedRoleStatement] = []

        for role_id, zh_name, en_name in self._iter_role_terms():
            if zh_name not in text and en_name.lower() not in lowered:
                continue

            # Check for relay first (e.g. "X says he is Y")
            relay_found = False
            for player in visible_state.players:
                if player.player_id == speaker_id: continue
                if player.name not in text: continue
                relay_patterns = (
                    rf"{re.escape(player.name)}[^。？！\n]*说[^。？！\n]*(?:跳|是).{{0,4}}{re.escape(zh_name)}",
                    rf"{re.escape(player.name)}[^。？！\n]*自报[^。？！\n]*{re.escape(zh_name)}"
                )
                if any(re.search(p, text) for p in relay_patterns):
                    statements.append(ParsedRoleStatement(
                        role_id=role_id, claim_type="relay", subject_player_ids=(player.player_id,), source_text=text
                    ))
                    relay_found = True
                    break
            if relay_found:
                continue

            denial_patterns = (
                f"我不是{zh_name}",
                f"我没跳{zh_name}",
                f"我没有跳{zh_name}",
                f"我什么时候说我是{zh_name}",
                f"我从来没说过我是{zh_name}",
            )
            if any(pattern in text for pattern in denial_patterns):
                statements.append(
                    ParsedRoleStatement(
                        role_id=role_id,
                        claim_type="denial",
                        subject_player_ids=(speaker_id,),
                        source_text=text,
                    )
                )
                continue

            # Chinese self-claim: 我 + verb + role_name, with sentence-level context validation
            cn_self_claim = rf"我(?:确实|其实|这把)?(?:跳|报|明牌|是)(?:了|个)?{re.escape(zh_name)}"
            match_obj = re.search(cn_self_claim, text)
            if match_obj:
                # Sentence-level context: text since last sentence delimiter
                preceding = text[:match_obj.start()]
                last_delim = max(
                    preceding.rfind('。'), preceding.rfind('？'),
                    preceding.rfind('！'), preceding.rfind('\n'), 0,
                )
                sentence_ctx = text[last_delim:]
                # Skip if hypothetical marker in same sentence
                if re.search(r'(?:如果|要是|假设|就算|哪怕)', sentence_ctx):
                    pass  # fall through to accusation/question checks
                # Skip if attribution/relay marker in same sentence (requires a subject)
                elif re.search(r'(?:你说|他说|据称|有人(?:说|认为|觉得)|大家(?:说|讨论)|P\d+说)', sentence_ctx):
                    pass  # fall through
                else:
                    statements.append(
                        ParsedRoleStatement(
                            role_id=role_id,
                            claim_type="self_claim",
                            subject_player_ids=(speaker_id,),
                            source_text=text,
                        )
                    )
                    continue
            # English self-claim patterns (exact word boundaries, no context needed)
            en_self_patterns = (
                rf"\bi am {re.escape(en_name.lower())}\b",
                rf"\bi'm {re.escape(en_name.lower())}\b",
                rf"\bclaim(?:ed)? {re.escape(en_name.lower())}\b",
            )
            if any(re.search(p, lowered) for p in en_self_patterns):
                statements.append(
                    ParsedRoleStatement(
                        role_id=role_id,
                        claim_type="self_claim",
                        subject_player_ids=(speaker_id,),
                        source_text=text,
                    )
                )
                continue

            for player in visible_state.players:
                if player.player_id == speaker_id:
                    continue
                if player.name not in text:
                    continue
                # accusation/question checks
                if re.search(rf"{re.escape(player.name)}[^。？！\n]*(?:是不是|是).{{0,4}}{re.escape(zh_name)}", text):
                    statements.append(
                        ParsedRoleStatement(
                            role_id=role_id,
                            claim_type="question",
                            subject_player_ids=(player.player_id,),
                            source_text=text,
                        )
                    )
                    break
                if re.search(rf"{re.escape(player.name)}[^。？！\n]*(?:像|可能是|就是).{{0,4}}{re.escape(zh_name)}", text):
                    statements.append(
                        ParsedRoleStatement(
                            role_id=role_id,
                            claim_type="accusation",
                            subject_player_ids=(player.player_id,),
                            source_text=text,
                        )
                    )
                    break

        deduped: list[ParsedRoleStatement] = []
        seen: set[tuple[str, str, tuple[str, ...]]] = set()
        for statement in statements:
            key = (statement.role_id, statement.claim_type, statement.subject_player_ids)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(statement)
        return deduped
