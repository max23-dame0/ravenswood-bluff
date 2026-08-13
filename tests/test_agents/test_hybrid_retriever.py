"""T5: 双路混合检索（BM25 + Faiss + RRF 融合）测试 — PLN-041 Phase 2。

使用真实规则知识库语料（22 条）验证：
- BM25 路始终可用（纯本地）；
- Faiss 路在 backend 提供 embeddings 时可用；
- RRF 融合排序正确；
- 单一后端可用时降级正常。
"""

from __future__ import annotations

import pytest

from src.agents.memory.retrieval.chunker import chunk_rule_knowledge
from src.agents.memory.retrieval.hybrid_retriever import HybridRetriever


def _corpus() -> list[dict]:
    return chunk_rule_knowledge()


_KEYWORDS = (
    "恶魔",
    "每晚",
    "选择",
    "玩家",
    "死亡",
    "村民",
    "首夜",
    "处决",
    "外来者",
    "相邻",
    "邪恶",
    "人数",
    "中毒",
    "保护",
    "击杀",
    "白天",
    "公开",
    "身份",
    "能力",
    "阵营",
)


class FakeEmbeddingBackend:
    """确定性 embeddings：关键词命中 → 0/1 向量（语义接近的文本向量相近）。"""

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vectors.append([1.0 if kw in text else 0.0 for kw in _KEYWORDS])
        return vectors


class EmptyEmbeddingBackend:
    """embeddings 不可用：返回空列表（模拟降级）。"""

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return []


@pytest.mark.asyncio
async def test_hybrid_returns_results_with_bm25_only() -> None:
    retriever = HybridRetriever(backend=None, dimension=1536)
    retriever.build(_corpus())
    hits = await retriever.search("每晚选择一名玩家使其死亡 恶魔", top_k=2)
    assert hits
    assert hits[0]["metadata"]["role_id"] == "imp"


@pytest.mark.asyncio
async def test_hybrid_with_both_backends() -> None:
    retriever = HybridRetriever(backend=FakeEmbeddingBackend(), dimension=1536)
    retriever.build(_corpus())
    await retriever.add_dense_vectors()
    hits = await retriever.search("每晚选择一名玩家使其死亡 恶魔", top_k=2)
    assert hits
    assert hits[0]["metadata"]["role_id"] == "imp"


@pytest.mark.asyncio
async def test_hybrid_falls_back_when_embeddings_empty() -> None:
    retriever = HybridRetriever(backend=EmptyEmbeddingBackend(), dimension=1536)
    retriever.build(_corpus())
    await retriever.add_dense_vectors()
    hits = await retriever.search("每晚选择一名玩家使其死亡 恶魔", top_k=2)
    assert hits
    assert hits[0]["metadata"]["role_id"] == "imp"


@pytest.mark.asyncio
async def test_rrf_boosts_items_in_both_rankings() -> None:
    """RRF 融合：同时被两路命中的文档应排在前面（与仅 BM25 命中对比）。"""
    retriever = HybridRetriever(backend=FakeEmbeddingBackend(), dimension=1536)
    retriever.build(_corpus())
    await retriever.add_dense_vectors()
    hits = await retriever.search("共情者 相邻 邪恶 人数", top_k=5)
    assert hits[0]["metadata"]["role_id"] == "empath"


@pytest.mark.asyncio
async def test_search_before_build_empty() -> None:
    retriever = HybridRetriever(backend=None, dimension=1536)
    assert await retriever.search("anything") == []


@pytest.mark.asyncio
async def test_reranker_normalizes_scores() -> None:
    """RRF 分数应归一化到 0~1 区间。"""
    retriever = HybridRetriever(backend=FakeEmbeddingBackend(), dimension=1536)
    retriever.build(_corpus())
    await retriever.add_dense_vectors()
    hits = await retriever.search("每晚选择一名玩家使其死亡 恶魔", top_k=2)
    assert hits
    for hit in hits:
        assert 0.0 <= hit["score"] <= 1.0


def test_build_with_empty_does_not_raise() -> None:
    retriever = HybridRetriever(backend=None, dimension=1536)
    retriever.build([])
