"""说书人代理 (Storyteller Agent)。"""

from __future__ import annotations

from typing import Any

from src.agents.storyteller_delegation import (
    StorytellerAgentDelegation,
    StorytellerDecisionContext,
)
from src.agents.storyteller_tools import StorytellerProfileStore

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
        # PLN-038 阶段 E：说书人跨局档案（进化机制）
        self.profile_store = StorytellerProfileStore()

    # ------------------------------------------------------------------
    # PLN-038 阶段 S：说书人工具注册表入口
    # ------------------------------------------------------------------

    @property
    def tool_names(self) -> tuple[str, ...]:
        """说书人可用工具清单。"""
        from src.agents.storyteller_tools import StorytellerToolRegistry

        return StorytellerToolRegistry.TOOL_NAMES

    async def invoke_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """统一工具调用入口（PLN-038 阶段 S）。"""
        from src.agents.storyteller_tools import StorytellerToolRegistry

        registry = StorytellerToolRegistry
        if tool_name == "assess_balance":
            return {"tool": tool_name, **registry.assess_balance(self, kwargs["context"])}
        if tool_name == "choose_distortion":
            distorted, strategy = await registry.choose_distortion_async(
                self,
                kwargs["context"],
                kwargs["role_id"],
                kwargs["info"],
                kwargs.get("player_id", ""),
            )
            return {
                "tool": tool_name,
                "info": distorted,
                "distortion_strategy": strategy.value,
            }
        if tool_name == "adjudicate_night_info":
            result = await registry.adjudicate_night_info(
                self, kwargs["game_state"], kwargs["player_id"], kwargs["role_id"]
            )
            return {"tool": tool_name, "info": result}
        if tool_name == "compose_narration":
            narration = await registry.compose_narration(self, kwargs["game_state"])
            return {"tool": tool_name, "narration": narration}
        if tool_name == "deliver_verdict":
            entry = registry.deliver_verdict(
                self,
                kwargs["category"],
                kwargs["decision"],
                kwargs.get("reason"),
                **{k: v for k, v in kwargs.items() if k not in {"category", "decision", "reason"}},
            )
            return {"tool": tool_name, "verdict": entry}
        if tool_name == "review_balance":
            summary = registry.review_balance(self, kwargs["game_id"])
            path = registry.save_balance_archive(self, kwargs["game_id"], summary)
            return {"tool": tool_name, "review": summary, "archive_path": str(path)}
        raise KeyError(f"unknown storyteller tool: {tool_name}")

    # ------------------------------------------------------------------
    # PLN-038 阶段 E：说书人进化机制（跨局档案）
    # ------------------------------------------------------------------

    def finalize_game_profile(self, game_id: str, lesson: str = "") -> dict[str, Any]:
        """局末提炼：将本局判决统计沉淀到说书人跨局档案。

        统计本局决策账本中的扭曲次数与总判决数（确定性），
        并记录一条可复用的主持经验（可选）。
        """
        ledger = self.decision_ledger
        judgement_count = len(ledger)
        distortion_events = sum(
            1 for e in ledger if (e.get("distortion_strategy") or "") not in {"", "none", None}
        )
        profile = self.profile_store.record_game_summary(
            game_id=game_id,
            judgement_count=judgement_count,
            distortion_events=distortion_events,
            lesson=lesson,
        )
        return {
            "judgement_count": judgement_count,
            "distortion_events": distortion_events,
            "profile": profile,
        }
