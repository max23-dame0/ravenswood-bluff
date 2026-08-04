"""
记忆工具集 (MemoryTools)

让 AI 玩家自主维护认知（PLN-038 阶段 C）：

| 工具 | 职责 |
|---|---|
| `append_memory` | 主动写入一条观察 / 印象（过隔离层校验） |
| `read_memory` | 按类型/关键词读取记忆摘要 |
| `reflect` | 自主触发一次记忆反思（蒸馏为局势印象） |
| `archive_phase` | 自主归档当前阶段记忆到情节记忆并落盘 |

存储落盘：`data/agents/{player_id}/`（记忆文件 + 结构化子文件）。
写入内容经 `Visibility` 隔离层校验：`TEAM_EVIL`/`PRIVATE` 私密信息禁止进入
可被他人读取的存储；落盘文件默认仅本 agent 使用（文件级隔离）。

引擎兜底钩子（`MemoryController.reflect_if_needed` / `archive_phase_memory`）保留。
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agents.ai_agent import AIAgent
    from src.state.game_state import AgentVisibleState

logger = logging.getLogger(__name__)


# TEAM_EVIL 私密内容不得写入任何可检索/可落盘存储
_SENSITIVE_MARKERS = (
    "邪恶队友",
    "恶魔",
    "我是恶魔",
    "队友名单",
    "private_info",
    "TEAM_EVIL",
)


class MemoryTools:
    """记忆工具：agent 自主读写 / 反思 / 归档，附隔离校验与落盘。"""

    # ------------------------------------------------------------------
    # 路径与隔离
    # ------------------------------------------------------------------

    @staticmethod
    def agent_dir(player_id: str) -> Path:
        """玩家级记忆根目录（跨局档案区，不含单局记忆）。"""
        base = Path(os.getenv("BOTC_DATA_DIR", "data")) / "agents" / player_id
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def game_dir(player_id: str, game_id: str | None) -> Path:
        """单局记忆目录：data/agents/{player_id}/games/{game_id}/。

        PLN-038 阶段 E：每局独立目录，避免跨局记忆串味。
        game_id 缺失时回退到玩家根目录（向后兼容单测 / 手动构造）。
        """
        base = Path(os.getenv("BOTC_DATA_DIR", "data")) / "agents" / player_id
        if game_id:
            base = base / "games" / str(game_id)
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def _is_sensitive(text: str) -> bool:
        return any(marker in (text or "") for marker in _SENSITIVE_MARKERS)

    @staticmethod
    def _validate_visibility(agent: AIAgent, content: str, visibility: str | None) -> None:
        """隔离层校验：私密/邪恶内容禁止写入可检索记忆（阶段 C 红线）。"""
        if MemoryTools._is_sensitive(content):
            raise ValueError("memory_write_blocked:sensitive_content")
        if visibility in {"private", "TEAM_EVIL", "PRIVATE"}:
            raise ValueError("memory_write_blocked:private_visibility")

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    @staticmethod
    def append_memory(
        agent: AIAgent,
        visible_state: AgentVisibleState,
        content: str,
        tier: str = "public",
        category: str | None = None,
        source_event: Any = None,
    ) -> dict[str, Any]:
        """主动写入一条记忆（观察层）。

        Args:
            tier: "public"（公开）/ "objective"（客观事实）/ "private"（高可信线索）
            category: 记忆分类（如 "fortune_teller_info" / "role_candidate_hint"）
            source_event: 关联事件（可选）
        """
        MemoryTools._validate_visibility(agent, content, tier)
        summary = content[:200]
        if tier == "objective":
            agent.working_memory.remember_objective_info(category or "objective", summary)
        elif tier == "private":
            agent.working_memory.remember_private_info(category or "private", summary)
        else:
            agent.working_memory.remember_public_info(category or "public", summary)
        # 落盘（追加到本局记忆文件，对局隔离）
        entry = {
            "ts": time.time(),
            "tier": tier,
            "category": category,
            "content": summary,
            "day": visible_state.day_number,
            "round": visible_state.round_number,
        }
        game_id = getattr(agent, "game_id", None)
        MemoryTools._append_to_disk(agent.player_id, game_id, entry)
        return {"ok": True, "entry": entry}

    @staticmethod
    def _append_to_disk(player_id: str, game_id: str | None, entry: dict[str, Any]) -> Path:
        path = MemoryTools.game_dir(player_id, game_id) / "memory.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return path

    @staticmethod
    def _read_disk_entries(
        player_id: str, game_id: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        path = MemoryTools.game_dir(player_id, game_id) / "memory.jsonl"
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return entries[-limit:]

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    @staticmethod
    def read_memory(
        agent: AIAgent, tier: str | None = None, category: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """按类型/分类读取记忆摘要（内存 + 落盘文件）。"""
        in_memory: list[str] = []
        if tier in {None, "objective"}:
            in_memory.extend(agent.working_memory.get_objective_memory_summaries())
        if tier in {None, "private"}:
            in_memory.extend(agent.working_memory.get_private_memory_summaries())
        if tier in {None, "public"}:
            in_memory.extend(agent.working_memory.get_public_memory_summaries())
        if category:
            in_memory = [m for m in in_memory if category in (m or "")]
        game_id = getattr(agent, "game_id", None)
        disk = MemoryTools._read_disk_entries(agent.player_id, game_id, limit)
        disk_texts = [
            f"[D{entry.get('day')}R{entry.get('round')}] {entry.get('content', '')}"
            for entry in disk
        ]
        merged = [*in_memory[-limit:], *disk_texts[-limit:]]
        # 去重
        seen: list[str] = []
        for item in merged:
            if item not in seen:
                seen.append(item)
        return {"tier": tier, "category": category, "items": seen[-limit:]}

    @staticmethod
    async def reflect(agent: AIAgent, visible_state: AgentVisibleState) -> dict[str, Any]:
        """自主触发一次记忆反思（蒸馏观察为局势印象）。"""
        from src.agents.tools.memory_tools import MemoryTools

        await agent._reflect(visible_state)
        MemoryTools._record_tool_event(
            agent.player_id,
            getattr(agent, "game_id", None),
            "reflect",
            {"ok": True},
        )
        return {
            "ok": True,
            "impressions": list(agent.working_memory.impressions[-3:]),
            "observation_count": len(agent.working_memory.observations),
        }

    @staticmethod
    async def archive_phase(agent: AIAgent, visible_state: AgentVisibleState) -> dict[str, Any]:
        """自主归档当前阶段记忆到情节记忆。"""
        await agent.archive_phase_memory(visible_state)
        MemoryTools._record_tool_event(
            agent.player_id,
            getattr(agent, "game_id", None),
            "archive_phase",
            {"ok": True},
        )
        return {
            "ok": True,
            "episode_count": len(agent.episodic_memory.episodes)
            if hasattr(agent.episodic_memory, "episodes")
            else 0,
        }

    @staticmethod
    def _record_tool_event(
        player_id: str, game_id: str | None, tool_name: str, data: dict[str, Any]
    ) -> None:
        MemoryTools._append_to_disk(
            player_id, game_id, {"ts": time.time(), "tool": tool_name, **data}
        )
