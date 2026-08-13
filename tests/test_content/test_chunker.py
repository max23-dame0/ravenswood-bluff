"""T2: 分块器测试 — PLN-041 Phase 1。

验证规则知识条目分块与历史对局 jsonl 分块（轮次+事件，带元数据）。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.memory.retrieval.chunker import (
    chunk_rule_knowledge,
    chunk_session_jsonl,
)


def test_chunk_rule_knowledge_per_role() -> None:
    chunks = chunk_rule_knowledge()
    # 22 角色 → 22 块
    assert len(chunks) == 22
    role_ids = {c["metadata"]["role_id"] for c in chunks}
    assert role_ids == {c["metadata"]["role_id"] for c in chunks}
    for chunk in chunks:
        assert chunk["metadata"]["type"] == "rule"
        assert chunk["metadata"]["role_id"]
        assert chunk["metadata"]["team"] in {"good", "evil"}
        assert chunk["metadata"]["role_type"] in {"townsfolk", "outsider", "minion", "demon"}
        assert chunk["text"]


def test_chunk_rule_text_contains_name_and_ability() -> None:
    chunks = chunk_rule_knowledge()
    by_role = {c["metadata"]["role_id"]: c for c in chunks}
    imp = by_role["imp"]
    assert "小恶魔" in imp["text"]
    assert "死亡" in imp["text"]
    washerwoman = by_role["washerwoman"]
    assert "洗衣妇" in washerwoman["text"]
    assert "村民" in washerwoman["text"]


def test_chunk_session_jsonl_by_round(tmp_path: Path) -> None:
    lines = [
        json.dumps({"type": "game_start", "round": 1}, ensure_ascii=False),
        json.dumps(
            {"type": "event", "round": 1, "payload": {"event_type": "night_kill"}},
            ensure_ascii=False,
        ),
        json.dumps({"type": "message", "round": 2, "speaker": "p1"}, ensure_ascii=False),
        json.dumps(
            {"type": "event", "round": 2, "payload": {"event_type": "nomination"}},
            ensure_ascii=False,
        ),
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    chunks = chunk_session_jsonl(str(path))
    # 事件/消息两类 → 3 条（game_start 类型不索引）
    assert len(chunks) == 3
    rounds = {c["metadata"]["round"] for c in chunks}
    assert rounds == {1, 2}
    for chunk in chunks:
        assert chunk["metadata"]["type"] in {"event", "message"}
        assert chunk["metadata"]["round"] in {1, 2}


def test_chunk_session_ignores_unknown_types(tmp_path: Path) -> None:
    lines = [
        json.dumps({"type": "weird", "round": 1}, ensure_ascii=False),
        json.dumps({"type": "event", "round": 1}, ensure_ascii=False),
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    chunks = chunk_session_jsonl(str(path))
    assert len(chunks) == 1
    assert chunks[0]["metadata"]["type"] == "event"


def test_chunk_session_missing_file() -> None:
    assert chunk_session_jsonl("no/such/file.jsonl") == []
