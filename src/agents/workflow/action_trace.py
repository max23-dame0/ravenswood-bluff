"""玩家行动轨迹 (ActionTrace) — PLN-041 Phase 4。

把每个 AI 玩家的每次决策/发言记录为可回放的工作流轨迹：

- **包装非重写**：仅追加记录，不改变任何决策行为；
- **落盘**：`data/agents/{player_id}/games/{game_id}/action_trace.jsonl`（追加式）；
- **仅 live 落盘**：mock 测试/模拟不产生污染文件（对齐 thoughts.jsonl 约定）；
  `BOTC_TRACE_ACTIONS=1` 可强制开启（测试用）。
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


class ActionTrace:
    """玩家行动轨迹记录器（追加式 jsonl）。"""

    def __init__(self, player_id: str, game_id: str, enabled: bool) -> None:
        self._enabled = enabled
        self._path: Path | None = None
        if enabled and game_id:
            self._path = (
                _data_root() / "agents" / player_id / "games" / str(game_id) / "action_trace.jsonl"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, metric: dict[str, Any]) -> None:
        """追加一条行动轨迹（含决策摘要与节点耗时）。"""
        if not self._enabled or self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": time.time(),
                "player_id": metric.get("player_id", ""),
                "game_id": metric.get("game_id", ""),
                "role_id": metric.get("role_id", ""),
                "phase": metric.get("phase", ""),
                "day_number": metric.get("day_number"),
                "round_number": metric.get("round_number"),
                "action_type": metric.get("action_type", ""),
                "model": metric.get("model", ""),
                "latency_ms": metric.get("latency_ms", 0),
                "fallback_used": metric.get("fallback_used", False),
                "fallback_reason": metric.get("fallback_reason"),
                "speech_source": metric.get("speech_source"),
                "tool_used": metric.get("tool_used"),
                "strategy_loop_used": metric.get("strategy_loop_used"),
            }
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("[action-trace] 落盘失败: %s", exc)


def trace_enabled_for(backend: Any) -> bool:
    """仅 live 后端（BOTC_BACKEND=live/openai 等非 mock）启用轨迹。

    - `BOTC_TRACE_ACTIONS=1` 强制开启（测试/演示用）；
    - `BOTC_TRACE_ACTIONS=0` 强制关闭；
    - 默认：BOTC_BACKEND 为 mock 时关闭（mock 测试/模拟不产生污染文件，
      对齐 thoughts.jsonl 约定），否则开启。
    """
    env = os.getenv("BOTC_TRACE_ACTIONS", "").strip().lower()
    if env in {"1", "true"}:
        return True
    if env in {"0", "false"}:
        return False
    backend_env = os.getenv("BOTC_BACKEND", "").strip().lower()
    # 显式声明 live 或未声明（默认 live 倾向）视为 live
    return backend_env != "mock"
