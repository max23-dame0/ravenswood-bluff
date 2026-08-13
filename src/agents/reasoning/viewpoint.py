"""观点-证据模型 (ViewpointStore) — PLN-042 T1。

把 agent 的"印象/观点"从零散文本升级为结构化认知：
- **Evidence**：一条证据（hard=说书人信息/公开行为；soft=他人发言观感），
  含来源与轮次元数据；
- **Viewpoint**：一个观点（断言 + 证据链 + 置信度 + 状态），
  支持演化（新证据更新置信度 / 冲突时 supersede）；
- **ViewpointStore**：落盘 `data/agents/{player_id}/games/{game_id}/viewpoints.jsonl`
  （追加式，**仅 live**，对齐 thoughts.jsonl / action_trace.jsonl 约定），
  并提供"激活观点查询"与"注入摘要构建"。

设计约束：
- 仅 live 落盘：`BOTC_VIEWPOINTS=1` 强制开启，`BOTC_BACKEND=mock` 默认关闭
  （mock 测试/模拟不产生污染文件）；
- 摘要注入只进 user 段（动态），system 保持逐 token 稳定（D013/D014）；
- 所有证据在写入前必须由调用方过敏感过滤。
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _data_root() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


def viewpoint_enabled() -> bool:
    """观点库启用判定。

    - `BOTC_VIEWPOINTS=1/0` 显式强制；
    - `BOTC_COGNITIVE_SPEAK=1`（认知试点）隐式强制开启；
    - 默认仅 live 后端（BOTC_BACKEND != mock）启用。
    """
    env = os.getenv("BOTC_VIEWPOINTS", "").strip().lower()
    if env in {"1", "true"}:
        return True
    if env in {"0", "false"}:
        return False
    if os.getenv("BOTC_COGNITIVE_SPEAK", "").strip().lower() in {"1", "true"}:
        return True
    return os.getenv("BOTC_BACKEND", "").strip().lower() != "mock"


@dataclass
class Evidence:
    """一条证据。kind: hard（说书人信息/公开行为）/ soft（他人发言观感）。"""

    kind: str  # "hard" | "soft"
    source: str  # 来源分类（fortune_teller_info / public_claim / ...）
    detail: str
    day_number: int = 0
    round_number: int = 0
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "detail": self.detail,
            "day_number": self.day_number,
            "round_number": self.round_number,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Evidence:
        return cls(
            kind=str(raw.get("kind", "soft")),
            source=str(raw.get("source", "")),
            detail=str(raw.get("detail", "")),
            day_number=int(raw.get("day_number", 0) or 0),
            round_number=int(raw.get("round_number", 0) or 0),
            ts=float(raw.get("ts", 0) or 0),
        )


@dataclass
class Viewpoint:
    """一个观点：断言 + 证据链 + 置信度 + 状态。"""

    viewpoint_id: str
    subject_player_id: str
    subject_name: str
    claim: str
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.5
    status: str = "active"  # active | superseded
    source_action: str = "speak"
    day_number: int = 0
    round_number: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def mark_superseded(self) -> None:
        self.status = "superseded"
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "viewpoint_id": self.viewpoint_id,
            "subject_player_id": self.subject_player_id,
            "subject_name": self.subject_name,
            "claim": self.claim,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": round(self.confidence, 3),
            "status": self.status,
            "source_action": self.source_action,
            "day_number": self.day_number,
            "round_number": self.round_number,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Viewpoint:
        return cls(
            viewpoint_id=str(raw.get("viewpoint_id", uuid.uuid4().hex[:8])),
            subject_player_id=str(raw.get("subject_player_id", "")),
            subject_name=str(raw.get("subject_name", "")),
            claim=str(raw.get("claim", "")),
            evidence=[Evidence.from_dict(e) for e in raw.get("evidence", [])],
            confidence=float(raw.get("confidence", 0.5) or 0.5),
            status=str(raw.get("status", "active")),
            source_action=str(raw.get("source_action", "speak")),
            day_number=int(raw.get("day_number", 0) or 0),
            round_number=int(raw.get("round_number", 0) or 0),
            created_at=float(raw.get("created_at", 0) or time.time()),
            updated_at=float(raw.get("updated_at", 0) or time.time()),
        )


class ViewpointStore:
    """观点库：写入/查询/摘要（JSONL 追加式，仅 live 落盘）。"""

    def __init__(self, player_id: str, game_id: str, enabled: bool) -> None:
        self._player_id = player_id
        self._enabled = enabled
        self._viewpoints: list[Viewpoint] = []
        self._path: Path | None = None
        if enabled and game_id:
            self._path = (
                _data_root() / "agents" / player_id / "games" / str(game_id) / "viewpoints.jsonl"
            )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def path(self) -> Path | None:
        return self._path

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def add_viewpoint(
        self,
        *,
        subject_player_id: str,
        subject_name: str,
        claim: str,
        evidence: list[Evidence],
        confidence: float,
        source_action: str,
        day_number: int,
        round_number: int,
    ) -> Viewpoint | None:
        """新增一个观点并落盘（enabled 时）。"""
        if not self._enabled:
            return None
        vp = Viewpoint(
            viewpoint_id=uuid.uuid4().hex[:12],
            subject_player_id=subject_player_id,
            subject_name=subject_name,
            claim=claim,
            evidence=evidence,
            confidence=max(0.0, min(1.0, confidence)),
            status="active",
            source_action=source_action,
            day_number=day_number,
            round_number=round_number,
        )
        self._viewpoints.append(vp)
        self._append(vp)
        return vp

    def update_confidence(self, viewpoint_id: str, new_confidence: float) -> Viewpoint | None:
        """更新既有观点置信度（观点演化）。"""
        for vp in self._viewpoints:
            if vp.viewpoint_id == viewpoint_id and vp.status == "active":
                vp.confidence = max(0.0, min(1.0, new_confidence))
                vp.updated_at = time.time()
                self._append(vp)
                return vp
        return None

    def supersede(self, viewpoint_id: str) -> Viewpoint | None:
        """废弃观点（证据冲突时调用）。"""
        for vp in self._viewpoints:
            if vp.viewpoint_id == viewpoint_id:
                vp.mark_superseded()
                self._append(vp)
                return vp
        return None

    def _append(self, vp: Viewpoint) -> None:
        if not self._enabled or self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(vp.to_dict(), ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            logger.warning("[viewpoint] 落盘失败: %s", exc)

    # ------------------------------------------------------------------
    # 查询与摘要
    # ------------------------------------------------------------------

    def get_active_viewpoints(self) -> list[Viewpoint]:
        return [vp for vp in self._viewpoints if vp.status == "active"]

    def build_summary(self, limit: int = 5) -> str:
        """生成注入用观点摘要（含证据分级标注），无激活观点返回空串。"""
        active = self.get_active_viewpoints()[-limit:]
        if not active:
            return ""
        lines: list[str] = []
        for vp in active:
            hard = [e for e in vp.evidence if e.kind == "hard"]
            soft = [e for e in vp.evidence if e.kind == "soft"]
            parts = [f"{vp.subject_name}：{vp.claim}（置信度 {vp.confidence:.2f}）"]
            if hard:
                parts.append(f"硬证据：{'；'.join(e.detail[:40] for e in hard[:2])}")
            if soft:
                parts.append(f"软印象：{'；'.join(e.detail[:40] for e in soft[:2])}")
            lines.append("- " + "，".join(parts))
        return "【你当前的观点与依据】\n" + "\n".join(lines)
