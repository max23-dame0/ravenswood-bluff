from __future__ import annotations

from typing import Any


class DeceptionTracker:
    """跟踪邪恶方的公开声明和虚构预算，确保叙事一致性。"""

    def __init__(self, deception_level: float = 0.5) -> None:
        # 每日虚构预算: deception=0.7 → max 2 fabrications/day
        self.max_fabrications_per_day: int = max(1, int(deception_level * 3))
        self._self_claims: dict[str, str] = {}  # role_id -> claim_text
        self._fabrication_log: list[dict[str, Any]] = []
        self._daily_fabrication_count: dict[int, int] = {}
        self._narrative_threads: list[str] = []
        self._team_claims: dict[str, str] = {}  # player_name -> role_id (teammate claims)

    @property
    def active_claims(self) -> dict[str, str]:
        return dict(self._self_claims)

    def record_self_claim(self, role_id: str, day_number: int, context: str = "") -> None:
        self._self_claims[role_id] = context or f"D{day_number}: claimed {role_id}"

    def can_fabricate(self, day_number: int) -> bool:
        return self._daily_fabrication_count.get(day_number, 0) < self.max_fabrications_per_day

    def record_fabrication(self, day_number: int, content: str, target: str = "") -> None:
        self._daily_fabrication_count[day_number] = self._daily_fabrication_count.get(day_number, 0) + 1
        self._fabrication_log.append({
            "day": day_number,
            "content": content[:100],
            "target": target,
        })
        if content not in self._narrative_threads:
            self._narrative_threads.append(content[:80])
        self._narrative_threads = self._narrative_threads[-5:]

    def get_consistency_guidance(self) -> str:
        if not self._self_claims and not self._narrative_threads:
            return ""
        parts = []
        if self._self_claims:
            roles = ", ".join(self._self_claims.keys())
            parts.append(f"你已公开跳身份为 {roles}。后续发言必须与之一致，不要改口。")
        if self._narrative_threads:
            parts.append(f"你正在推进的叙事线: {'; '.join(self._narrative_threads[-2:])}。继续沿着这条线推进，不要突然换故事。")
        return " ".join(parts)

    # --- Team-level claim coordination ---

    def record_team_claim(self, player_name: str, role_id: str) -> None:
        """Track what role a teammate is claiming to avoid duplicate claims."""
        self._team_claims[player_name] = role_id

    def get_team_claims(self) -> dict[str, str]:
        """Return mapping of teammate name -> claimed role."""
        return dict(self._team_claims)

    def get_available_bluffs(self, all_bluffs: list[str]) -> list[str]:
        """Return bluff roles not yet claimed by teammates."""
        claimed = set(self._team_claims.values())
        return [b for b in all_bluffs if b not in claimed]
