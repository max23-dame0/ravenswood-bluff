"""T6: 检索持久化测试 — PLN-041 Phase 2。

验证索引语料 + metadata 落盘 `data/agents/_retrieval/` 与启动重建。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.memory.retrieval.retrieval_store import (
    RetrievalStore,
    build_default_store,
)

SAMPLE_CHUNKS = [
    {
        "text": "角色: 小恶魔（Imp） 邪恶 demon 能力: 每晚选择一名玩家使其死亡。",
        "metadata": {"type": "rule", "role_id": "imp", "team": "evil"},
    },
    {
        "text": "角色: 共情者（Empath） 善良 townsfolk 能力: 每晚得知相邻邪恶人数。",
        "metadata": {"type": "rule", "role_id": "empath", "team": "good"},
    },
]


def test_store_roundtrip(tmp_path: Path) -> None:
    store = RetrievalStore(base_dir=tmp_path)
    store.save_chunks(SAMPLE_CHUNKS)
    meta_path = tmp_path / "chunks_meta.json"
    assert meta_path.exists()

    loaded = RetrievalStore(base_dir=tmp_path).load_chunks()
    assert len(loaded) == 2
    assert loaded[0]["metadata"]["role_id"] == "imp"
    assert loaded[0]["text"] == SAMPLE_CHUNKS[0]["text"]


def test_load_missing_store_returns_empty(tmp_path: Path) -> None:
    store = RetrievalStore(base_dir=tmp_path / "nonexistent")
    assert store.load_chunks() == []


def test_roundtrip_preserves_metadata_fields(tmp_path: Path) -> None:
    store = RetrievalStore(base_dir=tmp_path)
    store.save_chunks(SAMPLE_CHUNKS)
    loaded = store.load_chunks()
    for original, restored in zip(SAMPLE_CHUNKS, loaded, strict=True):
        assert restored["metadata"] == original["metadata"]


def test_build_default_store_persists_to_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = build_default_store()
    assert store._retrieval_dir == tmp_path / "agents" / "_retrieval"


def test_corrupt_metadata_returns_empty(tmp_path: Path) -> None:
    target = tmp_path / "chunks_meta.json"
    target.write_text("{corrupt json", encoding="utf-8")
    store = RetrievalStore(base_dir=tmp_path)
    assert store.load_chunks() == []
