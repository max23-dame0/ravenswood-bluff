"""T4: BM25 稀疏检索器测试 — PLN-041 Phase 2。

使用真实规则知识库语料（22 条）验证 rank_bm25 封装：
构建/检索/降级/元数据关联。
"""

from __future__ import annotations

from src.agents.memory.retrieval.bm25_retriever import BM25Retriever
from src.agents.memory.retrieval.chunker import chunk_rule_knowledge


def _corpus() -> list[dict]:
    return chunk_rule_knowledge()


def test_build_and_search_returns_hits() -> None:
    retriever = BM25Retriever()
    retriever.build(_corpus())
    hits = retriever.search("每晚选择一名玩家使其死亡 恶魔", top_k=2)
    assert hits, "expected at least one hit"
    assert hits[0]["metadata"]["role_id"] == "imp"


def test_search_matches_role_by_name() -> None:
    retriever = BM25Retriever()
    retriever.build(_corpus())
    hits = retriever.search("共情者 相邻 邪恶 人数", top_k=3)
    assert hits[0]["metadata"]["role_id"] == "empath"


def test_search_returns_metadata_with_text() -> None:
    retriever = BM25Retriever()
    retriever.build(_corpus())
    hits = retriever.search("洗衣妇 村民 首夜", top_k=1)
    assert hits[0]["metadata"]["role_id"] == "washerwoman"
    assert hits[0]["text"]


def test_search_empty_index_returns_empty() -> None:
    retriever = BM25Retriever()
    assert retriever.search("anything") == []


def test_search_before_build_returns_empty() -> None:
    retriever = BM25Retriever()
    assert retriever.search("anything", top_k=2) == []


def test_top_k_respected() -> None:
    retriever = BM25Retriever()
    retriever.build(_corpus())
    hits = retriever.search("角色能力 邪恶", top_k=2)
    assert len(hits) <= 2


def test_metadata_scores_present() -> None:
    retriever = BM25Retriever()
    retriever.build(_corpus())
    hits = retriever.search("小恶魔 恶魔 击杀", top_k=1)
    assert "score" in hits[0]
    assert hits[0]["score"] >= 0.0
