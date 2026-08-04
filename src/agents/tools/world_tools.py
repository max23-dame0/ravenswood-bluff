"""
世界感知只读工具 (WorldTools)

让 AI 玩家按需查询世界状态（PLN-038 阶段 D）：

| 工具 | 职责 |
|---|---|
| `observe_state` | 当前可见局势摘要（存活/提名/阶段等） |
| `query_public_log` | 最近公开事件/发言日志 |
| `query_players` | 玩家列表（名字/存活） |
| `query_legal_context` | 当前合法动作空间（可提名目标/可夜间目标等） |

所有数据源仍经 `AgentVisibleState`（InformationBroker 隔离层），
不直接触碰 `GameState`（硬约束 2）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent
    from src.state.game_state import AgentActionLegalContext, AgentVisibleState


class WorldTools:
    """世界感知只读工具：按需查询可见世界。"""

    @staticmethod
    def observe_state(agent: AIAgent, visible_state: AgentVisibleState) -> dict[str, Any]:
        """当前可见局势摘要（仅来自 AgentVisibleState）。"""
        return {
            "phase": visible_state.phase.value
            if hasattr(visible_state.phase, "value")
            else str(visible_state.phase),
            "day_number": visible_state.day_number,
            "round_number": visible_state.round_number,
            "alive_count": sum(1 for p in visible_state.players if p.is_alive),
            "current_nominee": visible_state.current_nominee,
            "current_nominator": visible_state.current_nominator,
            "nominations_today": visible_state.nominations_today,
            "nominees_today": list(visible_state.nominees_today),
            "yes_votes": visible_state.yes_votes,
            "voted_player_ids": list(visible_state.voted_player_ids),
        }

    @staticmethod
    def query_public_log(
        agent: AIAgent, visible_state: AgentVisibleState, limit: int = 20
    ) -> list[str]:
        """最近公开事件/发言日志（格式化文本，仅可见事件）。"""
        texts: list[str] = []
        for event in visible_state.visible_event_log[-limit:]:
            texts.append(agent._format_event_to_text(event, visible_state))
        for message in visible_state.public_chat_history[-limit:]:
            texts.append(f"{message.speaker}: {message.content}")
        return texts[-limit:]

    @staticmethod
    def query_players(agent: AIAgent, visible_state: AgentVisibleState) -> list[dict[str, Any]]:
        """玩家列表（名字/存活）。"""
        return [
            {"player_id": p.player_id, "name": p.name, "is_alive": p.is_alive}
            for p in visible_state.players
        ]

    @staticmethod
    def query_legal_context(
        agent: AIAgent,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext | None = None,
    ) -> dict[str, Any]:
        """当前合法动作空间。"""
        if legal_context is None:
            from src.state.game_state import AgentActionLegalContext

            legal_context = AgentActionLegalContext()
        return {
            "legal_nomination_targets": list(legal_context.legal_nomination_targets),
            "legal_night_targets": list(legal_context.legal_night_targets),
            "votes_required": legal_context.votes_required,
            "remaining_voters": list(legal_context.remaining_voters),
            "required_targets": legal_context.required_targets,
            "can_target_self": legal_context.can_target_self,
        }
