"""SettlementBuilder — end-of-game settlement report construction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from src.state.game_state import GameEvent, Team

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class SettlementBuilder:
    """End-of-game settlement report construction extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    def _build_settlement_report(self) -> dict[str, Any]:
        """组装完整的结算报告数据"""
        state = self._o.state
        events = list(state.event_log)

        # 胜负判定
        winning_team = self._o.winner.value if self._o.winner else "unknown"
        victory_reason = self._determine_victory_reason()

        # 玩家统计
        player_stats: dict[str, dict[str, int]] = {}
        for p in state.players:
            player_stats[p.player_id] = {
                "nominations_made": 0,
                "times_nominated": 0,
                "votes_cast": 0,
                "votes_yes": 0,
            }

        for event in events:
            if event.event_type == "nomination_started":
                if event.actor and event.actor in player_stats:
                    player_stats[event.actor]["nominations_made"] += 1
                if event.target and event.target in player_stats:
                    player_stats[event.target]["times_nominated"] += 1
            elif event.event_type == "vote_cast":
                if event.actor and event.actor in player_stats:
                    player_stats[event.actor]["votes_cast"] += 1
                    if event.payload.get("vote"):
                        player_stats[event.actor]["votes_yes"] += 1

        # 角色揭示
        human_ids = set()
        if state.config and state.config.human_player_ids:
            human_ids = set(state.config.human_player_ids)

        players_reveal = []
        for p in state.players:
            players_reveal.append({
                "player_id": p.player_id,
                "name": p.name,
                "true_role_id": p.true_role_id or p.role_id,
                "perceived_role_id": p.perceived_role_id,
                "team": (p.current_team or p.team).value,
                "is_alive": p.is_alive,
                "is_human": p.player_id in human_ids,
                "stats": player_stats.get(p.player_id, {}),
            })

        # 关键事件时间线
        key_event_types = {
            "nomination_started", "voting_resolved", "execution_resolved",
            "player_death", "phase_changed",
        }
        timeline = []
        for event in events:
            if event.event_type not in key_event_types:
                continue
            summary = self._summarize_event(event)
            if not summary:
                continue
            timeline.append({
                "round": event.round_number,
                "phase": event.phase.value,
                "event_type": event.event_type,
                "actor": event.actor,
                "target": event.target,
                "summary": summary,
                "timestamp": event.timestamp.isoformat(),
            })

        # 总体统计
        total_nominations = sum(1 for e in events if e.event_type == "nomination_started")
        total_executions = sum(1 for e in events if e.event_type == "execution_resolved" and e.payload.get("executed"))
        total_votes = sum(1 for e in events if e.event_type == "vote_cast")
        total_deaths = sum(1 for e in events if e.event_type == "player_death")
        judgement_summary: list[dict[str, Any]] = []
        if self._o.storyteller_agent and hasattr(self._o.storyteller_agent, "summarize_recent_judgements"):
            try:
                judgement_summary = list(self._o.storyteller_agent.summarize_recent_judgements(20))
            except Exception as exc:
                logger.warning("Failed to summarize storyteller judgements for settlement: %s", exc)

        return {
            "game_id": state.game_id,
            "winning_team": winning_team,
            "victory_reason": victory_reason,
            "duration_rounds": state.round_number,
            "days_played": state.day_number,
            "players": players_reveal,
            "timeline": timeline,
            "statistics": {
                "total_nominations": total_nominations,
                "total_executions": total_executions,
                "total_votes": total_votes,
                "total_deaths": total_deaths,
                "days_played": state.day_number,
                "player_count": len(state.players),
            },
            "judgement_summary": judgement_summary,
        }

    def _determine_victory_reason(self) -> str:
        """推断胜利原因"""
        if not self._o.winner:
            return "unknown"
        events = list(self._o.state.event_log)
        if self._o.winner == Team.GOOD:
            # 检查是否恶魔被处决
            for event in reversed(events):
                if event.event_type == "execution_resolved" and event.payload.get("executed"):
                    return "demon_executed"
                if event.event_type == "player_death":
                    return "demon_killed"
            return "demon_killed"
        else:
            # 邪恶获胜 = 只剩2人且恶魔存活
            return "last_two_alive"

    def _summarize_event(self, event: GameEvent) -> str:
        """将事件转为人可读的摘要"""
        actor = self._o._player_label(event.actor) if event.actor else ""
        target = self._o._player_label(event.target) if event.target else ""

        if event.event_type == "phase_changed":
            day = event.payload.get("day_number", "?")
            phase_names = {
                "first_night": "第一夜",
                "day_discussion": f"第{day}天 白天讨论",
                "nomination": f"第{day}天 提名阶段",
                "night": f"第{day}天 夜晚",
                "game_over": "游戏结束",
            }
            return phase_names.get(event.phase.value, f"阶段: {event.phase.value}")

        if event.event_type == "nomination_started":
            return f"{actor} 提名了 {target}"

        if event.event_type == "voting_resolved":
            passed = event.payload.get("passed", False)
            votes = event.payload.get("votes", 0)
            needed = event.payload.get("needed", 0)
            result = "通过" if passed else "未通过"
            return f"投票{result} ({votes}/{needed}票) - {target}"

        if event.event_type == "execution_resolved":
            executed = event.payload.get("executed")
            if executed:
                return f"{self._o._player_label(executed)} 被处决"
            return "今天无人被处决"

        if event.event_type == "player_death":
            reason = event.payload.get("reason", "night")
            if reason == "night":
                return f"{target} 在夜晚死亡"
            return f"{target} 死亡"

        return ""
