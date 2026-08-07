"""跨局共享经验池 (Shared Experience Pool) — PLN-040 T2。

把每个 AI 玩家的跨局经验（局后复盘 takeaway / 经验教训 lesson）在**去私密化**后
统一沉淀到共享池，新对局按「角色 + 阵营 + 战局相似度」检索**个性化子集**注入
`act()` 的 stable_context 首段，实现"经验统一学习 + 按玩家视角差异化"，
配合 T3 的倾向差异化构成"活人感"来源。

信息隔离：
- 入池前必须过 `MemoryToolsLike.is_sensitive` 敏感过滤（恶魔/队友名单等拒绝入池）；
- 池记录只保留「角色通用经验 + 来源元信息（role/team/won）」，不携带任何玩家私密信息；
- 注入摘要仍保持同局内逐 token 稳定（setup 时算一次，勿在 act() 内重算）。

目录结构：

    data/agents/_shared_pool/
        lessons.jsonl          # 去私密化后的跨局共享经验（role/team/won + lesson/takeaway）

设计约束（对应 D013/D014 精神）：
- 战绩/胜负/角色一律来自 settlement_report（确定性），LLM 不参与沉淀；
- 检索注入必须过敏感过滤；跨局摘要放 user 首条 stable_context。
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


class SharedExperiencePool:
    """跨局共享经验池：沉淀（去私密化）→ 检索（按角色/阵营/战局相似度）→ 注入摘要。"""

    def __init__(self) -> None:
        self._pool_dir = _data_root() / "agents" / "_shared_pool"
        self._lessons_path = self._pool_dir / "lessons.jsonl"

    # ------------------------------------------------------------------
    # 沉淀（deposit）
    # ------------------------------------------------------------------

    def deposit(
        self,
        *,
        role_id: str | None,
        team: str | None,
        won: bool,
        lesson: str,
        takeaway: str = "",
        game_id: str = "",
    ) -> Path | None:
        """把一条玩家经验去私密化后写入共享池。

        入池条件：
        - lesson / takeaway 均须非空且过敏感过滤（任一敏感则整条拒绝入池）；
        - role_id 非空（角色通用经验是检索键）。
        """
        from src.agents.memory.player_profile import MemoryToolsLike

        lesson_text = (lesson or "").strip()
        takeaway_text = (takeaway or "").strip()
        if not role_id or not lesson_text:
            return None
        if MemoryToolsLike.is_sensitive(lesson_text) or MemoryToolsLike.is_sensitive(takeaway_text):
            logger.info("[shared-pool] 敏感内容拒绝入池: role=%s", role_id)
            return None

        self._pool_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": time.time(),
            "role_id": str(role_id),
            "team": (team or "unknown").lower(),
            "won": bool(won),
            "lesson": lesson_text[:240],
            "takeaway": takeaway_text[:240] if takeaway_text else "",
            "game_id": str(game_id),
        }
        with open(self._lessons_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        logger.debug("[shared-pool] 沉淀经验 role=%s team=%s", role_id, record["team"])
        return self._lessons_path

    # ------------------------------------------------------------------
    # 检索（retrieve）
    # ------------------------------------------------------------------

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._lessons_path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            with open(self._lessons_path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return records

    def retrieve(
        self,
        *,
        role_id: str | None,
        team: str | None,
        top_k: int = 3,
        max_age_days: int = 365,
    ) -> list[dict[str, Any]]:
        """按（角色，阵营，新鲜度）检索共享经验，返回 top_k 条。

        打分规则：
        - 角色命中 +3（角色通用经验最相关）；
        - 阵营命中 +1（同阵营经验次相关）；
        - 时间衰减（越新鲜分越高，避免陈旧经验挤压）；
        - 战局相似度：仅用结构元信息（role/team/won），不引入私密细节。
        """
        if not role_id:
            return []
        records = self._read_all()
        now = time.time()
        cutoff = now - max_age_days * 86400
        scored: list[tuple[float, dict[str, Any]]] = []
        for rec in records:
            if rec.get("ts", 0) < cutoff:
                continue
            score = 0.0
            if str(rec.get("role_id", "")) == str(role_id):
                score += 3.0
            if (rec.get("team") or "").lower() == (team or "").lower():
                score += 1.0
            # 新鲜度：最近 30 天全分，之后线性衰减到 0
            age = now - rec.get("ts", now)
            freshness = max(0.0, 1.0 - age / (365 * 86400))
            score += freshness * 0.5
            scored.append((score, rec))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [rec for _, rec in scored[:top_k]]

    # ------------------------------------------------------------------
    # 注入摘要（build_shared_context）
    # ------------------------------------------------------------------

    def build_shared_context(
        self,
        *,
        role_id: str | None,
        team: str | None,
        top_k: int = 3,
    ) -> str:
        """生成供 stable_context 注入的『共享经验池』摘要（纯文本，无敏感）。

        调用时机：setup 时一次（AIAgent.load_player_profile），同局内稳定。
        """
        from src.agents.memory.player_profile import MemoryToolsLike

        items = self.retrieve(role_id=role_id, team=team, top_k=top_k)
        if not items:
            return ""
        lines: list[str] = []
        for item in items:
            lesson = str(item.get("lesson", "")).strip()
            if not lesson or MemoryToolsLike.is_sensitive(lesson):
                continue
            source = f"{item.get('role_id')}({'胜' if item.get('won') else '负'})"
            lines.append(f"- [来自{source}的经验] {lesson[:120]}")
        if not lines:
            return ""
        return "【你从共享经验池中借鉴到的打法】\n" + "\n".join(lines)
