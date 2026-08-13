"""T1: 规则知识库导出器测试 — PLN-041 Phase 1。

验证从既有内容源（terms / night_order / RoleDefinition）导出的
结构化规则知识条目完整性：22 角色、字段齐全、team/role_type 正确。
"""

from __future__ import annotations

import pytest

from src.content.rule_knowledge import (
    RULE_KNOWLEDGE_ENTRIES,
    build_rule_knowledge_entries,
    get_rule_entry,
)

EXPECTED_ROLE_COUNT = 22
EXPECTED_ROLE_TYPES = {
    # townsfolk
    "washerwoman": "townsfolk",
    "librarian": "townsfolk",
    "investigator": "townsfolk",
    "chef": "townsfolk",
    "empath": "townsfolk",
    "fortune_teller": "townsfolk",
    "undertaker": "townsfolk",
    "monk": "townsfolk",
    "ravenkeeper": "townsfolk",
    "virgin": "townsfolk",
    "slayer": "townsfolk",
    "soldier": "townsfolk",
    "mayor": "townsfolk",
    # outsiders
    "butler": "outsider",
    "drunken": "outsider",
    "recluse": "outsider",
    "saint": "outsider",
    # minions
    "poisoner": "minion",
    "spy": "minion",
    "scarlet_woman": "minion",
    "baron": "minion",
    # demon
    "imp": "demon",
}
EXPECTED_TEAMS = {
    "townsfolk": "good",
    "outsider": "good",
    "minion": "evil",
    "demon": "evil",
}


def test_all_roles_exported() -> None:
    assert len(RULE_KNOWLEDGE_ENTRIES) == EXPECTED_ROLE_COUNT


def test_every_entry_has_required_fields() -> None:
    for entry in RULE_KNOWLEDGE_ENTRIES:
        assert entry["role_id"], entry
        assert entry["zh_name"], entry
        assert entry["en_name"], entry
        assert entry["role_type"], entry
        assert entry["team"], entry
        assert entry["description"], entry


def test_role_types_correct() -> None:
    for role_id, role_type in EXPECTED_ROLE_TYPES.items():
        entry = get_rule_entry(role_id)
        assert entry is not None, f"missing {role_id}"
        assert entry["role_type"] == role_type, f"{role_id}: {entry['role_type']}"


def test_teams_correct() -> None:
    for role_id, role_type in EXPECTED_ROLE_TYPES.items():
        entry = get_rule_entry(role_id)
        assert entry["team"] == EXPECTED_TEAMS[role_type], role_id


def test_night_order_annotations_present() -> None:
    # 有夜间顺序条目且非特殊时机的角色应有 night_note
    for role_id in ("washerwoman", "imp", "monk", "spy", "butler"):
        entry = get_rule_entry(role_id)
        assert entry["night_note"], f"{role_id} missing night_note"


def test_no_night_note_for_day_only_roles() -> None:
    # 白天角色（如 slayer/virgin/saint）无夜间顺序注记
    for role_id in ("slayer", "virgin", "saint", "mayor"):
        entry = get_rule_entry(role_id)
        assert not entry["night_note"], f"{role_id} unexpected night_note"


def test_build_entries_matches_module_constant() -> None:
    entries = build_rule_knowledge_entries()
    assert entries == RULE_KNOWLEDGE_ENTRIES


def test_unknown_role_returns_none() -> None:
    assert get_rule_entry("not_a_role") is None


@pytest.mark.parametrize(
    "role_id,keyword",
    [
        ("washerwoman", "村民"),
        ("fortune_teller", "恶魔"),
        ("imp", "死亡"),
        ("saint", "处决"),
        ("drunken", "外来者"),
    ],
)
def test_description_keywords(role_id: str, keyword: str) -> None:
    entry = get_rule_entry(role_id)
    assert entry is not None
    assert keyword in entry["description"], f"{role_id}: {entry['description']}"
