"""说书人代理 (Storyteller Agent)。"""

from __future__ import annotations

from typing import Any

from src.agents.storyteller_delegation import (
    StorytellerAgentDelegation,
    StorytellerDecisionContext,
)

# 向后兼容：保持从本模块导入 StorytellerDecisionContext 可用
__all__ = ["StorytellerAgent", "StorytellerDecisionContext"]


class StorytellerAgent(StorytellerAgentDelegation):
    """说书人代理（facade：路由 + 状态，裁量逻辑见 storyteller_delegation）。"""

    def __init__(self, backend: Any = None, mode: str = "auto", delegated: bool = False):
        self.backend = backend
        self.mode = mode
        self.delegated = delegated
        self.name = "Storyteller"
        self.player_id = "storyteller"
        self.decision_ledger: list[dict[str, Any]] = []
