"""结构化规则知识库 (Rule Knowledge Base) — PLN-041 Phase 1 T1。

从既有内容源导出**结构化规则条目**，作为 RAG 检索与 setup 静态注入的语料：

- 角色名/能力描述：`src/content/trouble_brewing_terms.py`
- 夜间顺序/时机：`src/content/trouble_brewing_night_order.py`
- 阵营/角色类型：`src/engine/roles/*.py`（RoleDefinition，规则引擎权威）

设计要点：
- **纯静态导出**：模块加载时构建一次，无 IO/LLM 依赖，mock 环境可用；
- **规则引擎为权威**：team/role_type 来自 `RoleDefinition`（与游戏行为一致），
  术语表只提供 zh_name/en_name/description 文案；
- 每个条目含 `night_note`（夜间顺序注记，仅夜间角色有）与 `timing`（时机标签），
  供分块器与检索使用。
"""

from __future__ import annotations

from typing import Any

from src.content.trouble_brewing_night_order import get_night_order_spec
from src.content.trouble_brewing_terms import (
    TROUBLE_BREWING_ROLE_PERSONA_HINTS,
    TROUBLE_BREWING_ROLE_TERMS,
)
from src.engine.roles.base_role import get_role_class
from src.state.game_state import RoleType, Team

# 无夜间顺序条目的"白天角色"（即使有也不注入 night_note）
_DAY_ONLY_ROLES = {"slayer", "virgin", "saint", "mayor"}


def _role_meta() -> dict[str, tuple[str, str]]:
    """role_id -> (team, role_type)。以规则引擎 RoleDefinition 为权威。"""
    meta: dict[str, tuple[str, str]] = {}
    for role_id in TROUBLE_BREWING_ROLE_TERMS:
        cls = get_role_class(role_id)
        if cls is None:
            continue
        definition = cls.get_definition()
        team = definition.team.value if isinstance(definition.team, Team) else str(definition.team)
        rtype = (
            definition.role_type.value
            if isinstance(definition.role_type, RoleType)
            else str(definition.role_type)
        )
        meta[role_id] = (team, rtype)
    return meta


def _build_entry(role_id: str, team: str, role_type: str) -> dict[str, Any]:
    term = TROUBLE_BREWING_ROLE_TERMS[role_id]
    night_spec = get_night_order_spec(role_id)
    night_note = ""
    timing = ""
    if night_spec is not None and role_id not in _DAY_ONLY_ROLES:
        night_note = night_spec.note_zh
        timing = night_spec.timing
    return {
        "role_id": role_id,
        "zh_name": term["zh_name"],
        "en_name": term["en_name"],
        "team": team,
        "role_type": role_type,
        "description": term["description"],
        "persona_hint": TROUBLE_BREWING_ROLE_PERSONA_HINTS.get(role_id, ""),
        "night_note": night_note,
        "timing": timing,
    }


def build_rule_knowledge_entries() -> list[dict[str, Any]]:
    """构建全量规则知识条目（22 角色，按剧本角色顺序）。"""
    from src.engine.scripts import TROUBLE_BREWING

    meta = _role_meta()
    entries: list[dict[str, Any]] = []
    for role_id in TROUBLE_BREWING.roles:
        if role_id not in meta:
            continue
        entries.append(_build_entry(role_id, *meta[role_id]))
    return entries


def get_rule_entry(role_id: str) -> dict[str, Any] | None:
    """按 role_id 查规则条目；不存在返回 None。"""
    for entry in RULE_KNOWLEDGE_ENTRIES:
        if entry["role_id"] == role_id:
            return entry
    return None


def build_role_rulebook_context(role_id: str, team: str) -> str:
    """为单个玩家生成『规则书』注入上下文（setup 期一次，同局稳定）。

    内容 = 角色能力（含夜间时机）+ 阵营红线（保密/推演约束）。
    未知角色返回空串（不注入未知信息，避免产生幻觉来源）。

    Args:
        role_id: 玩家角色 ID
        team: 阵营（"good" / "evil"）
    """
    entry = get_rule_entry(role_id)
    if entry is None:
        return ""
    team_label = "善良" if team == "good" else "邪恶"
    lines = [
        f"你的角色是{entry['zh_name']}（{entry['role_id']}），属于{team_label}阵营（{entry['role_type']}）。",
        f"你的能力: {entry['description']}",
    ]
    if entry.get("night_note"):
        lines.append(f"夜间行动: {entry['night_note']}")
    if entry.get("persona_hint"):
        lines.append(f"角色气质: {entry['persona_hint']}")
    if team == "evil":
        lines.append(
            "阵营红线: 绝不公开承认邪恶身份，不泄露同阵营玩家的身份与任何私密情报，言行须伪装成善良玩家。"
        )
    else:
        lines.append("阵营红线: 依据公开信息与你的能力结果推理，不臆造私密信息。")
    return "\n".join(lines)


RULE_KNOWLEDGE_ENTRIES: list[dict[str, Any]] = build_rule_knowledge_entries()
