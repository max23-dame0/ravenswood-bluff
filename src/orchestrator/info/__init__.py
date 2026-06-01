"""PrivateInfoNormalizer — normalize and publish private night info payloads."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.content.trouble_brewing_terms import get_role_name
from src.state.game_state import (
    GameEvent,
    GamePhase,
    PlayerState,
    Visibility,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class PrivateInfoNormalizer:
    """Private info normalization and publishing extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    def _normalize_private_info_payload(self, player: PlayerState, payload: dict) -> dict:
        if not payload:
            return {}
        if payload.get("title") and payload.get("lines"):
            return payload

        role_id = player.true_role_id or player.role_id
        normalized = dict(payload)
        info_type = payload.get("type", "night_info")
        title = payload.get("title")
        lines: list[str] = list(payload.get("lines", []))

        if info_type == "evil_reveal":
            title = title or "邪恶阵营互认"
            teammates = payload.get("teammates", [])
            bluffs = payload.get("bluffs", [])
            lines = [f"你的邪恶队友：{', '.join(teammates) if teammates else '无'}"]
            if bluffs:
                bluff_names = ", ".join(get_role_name(role_id) for role_id in bluffs)
                lines.append(f"你的 3 个不在场角色：{bluff_names}")
        elif info_type == "washerwoman_info":
            title = title or f"{get_role_name(role_id)}信息"
            candidates = ", ".join(self._o._player_label(pid) for pid in payload.get("players", [])) or "无"
            lines = [f"{candidates} 之中，有一人是 {get_role_name(payload.get('role_seen', 'unknown'))}。"]
        elif info_type == "librarian_info":
            title = title or f"{get_role_name(role_id)}信息"
            if payload.get("has_outsider"):
                candidates = ", ".join(self._o._player_label(pid) for pid in payload.get("players", [])) or "无"
                lines = [f"{candidates} 之中，有一人是 {get_role_name(payload.get('role_seen', 'unknown'))}。"]
            else:
                lines = ["本局没有外来者。"]
        elif info_type == "investigator_info":
            title = title or f"{get_role_name(role_id)}信息"
            candidates = ", ".join(self._o._player_label(pid) for pid in payload.get("players", [])) or "无"
            lines = [f"{candidates} 之中，有一人是 {get_role_name(payload.get('role_seen', 'unknown'))}。"]
        elif info_type == "chef_info":
            title = title or f"{get_role_name(role_id)}信息"
            lines = [f"相邻的邪恶玩家对数：{payload.get('pairs', 0)}。"]
        elif info_type == "empath_info":
            title = title or f"{get_role_name(role_id)}信息"
            lines = [f"你存活的邻座中，邪恶玩家数量：{payload.get('evil_count', 0)}。"]
        elif info_type == "undertaker_info":
            title = title or f"{get_role_name(role_id)}信息"
            seen_role = get_role_name(payload.get("role_seen", "unknown"))
            seen_player = self._o._player_label(payload.get("player_id")) if payload.get("player_id") else "今天被处决的玩家"
            lines = [f"{seen_player} 的身份是：{seen_role}。"]
        elif info_type == "fortune_teller_info":
            title = title or f"{get_role_name(role_id)}信息"
            pair = ", ".join(self._o._player_label(pid) for pid in payload.get("players", [])) or "这两人"
            result = "至少有一人是恶魔" if payload.get("has_demon") else "这两人都不是恶魔"
            lines = [f"{pair}：{result}。"]
        elif info_type == "ravenkeeper_info":
            title = title or f"{get_role_name(role_id)}信息"
            seen_role = get_role_name(payload.get("role_seen", "unknown"))
            seen_player = self._o._player_label(payload.get("player_id")) if payload.get("player_id") else "该玩家"
            lines = [f"你得知 {seen_player} 的身份是：{seen_role}。"]
        elif info_type == "spy_book":
            title = title or "间谍魔典"
            book = payload.get("book", [])
            lines = []
            for entry in book:
                pname = self._o._player_label(entry.get("player_id", ""))
                rname = get_role_name(entry.get("role_id", "unknown"))
                team = entry.get("team", "unknown")
                alive = "存活" if entry.get("is_alive", True) else "死亡"
                lines.append(f"{pname}: {rname}（{team}阵营, {alive}）")
            if not lines:
                lines = ["魔典信息为空。"]
        else:
            title = title or f"{get_role_name(role_id)}信息"
            if not lines:
                lines = [
                    f"{key}: {value}"
                    for key, value in payload.items()
                    if key not in {"type", "title", "lines"}
                ] or ["你收到了新的私密信息。"]

        normalized["type"] = info_type
        normalized["title"] = title
        normalized["lines"] = lines
        return normalized

    async def _publish_private_info(self, phase: GamePhase, target: str, trace_id: str, payload: dict) -> None:
        player = self._o.state.get_player(target)
        if not player:
            return
        normalized_payload = self._normalize_private_info_payload(player, payload)
        await self._o._publish_event(GameEvent(
            event_type="private_info_delivered",
            phase=phase,
            round_number=self._o.state.round_number,
            trace_id=trace_id,
            target=target,
            visibility=Visibility.PRIVATE,
            payload=normalized_payload,
        ))
        self._o._log_storyteller(
            "private_info_delivered",
            phase=phase.value,
            target=target,
            trace_id=trace_id,
            info_type=normalized_payload.get("type", "unknown"),
            title=normalized_payload.get("title", ""),
        )
        self._o._record_storyteller_judgement(
            "private_info",
            decision="deliver",
            phase=phase.value,
            target=target,
            trace_id=trace_id,
            info_type=normalized_payload.get("type", "unknown"),
            title=normalized_payload.get("title", ""),
        )
