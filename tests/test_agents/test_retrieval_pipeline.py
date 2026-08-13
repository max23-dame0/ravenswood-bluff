"""T8: 统一检索注入管线测试 — PLN-041 Phase 3。

验证 retrieve → 敏感过滤 → 相关性门控 → 注入 stable_context 的完整管线。
"""

from __future__ import annotations

import pytest

from src.agents.memory.retrieval.chunker import chunk_rule_knowledge
from src.agents.memory.retrieval.retrieval_pipeline import (
    RetrievalPipeline,
    build_pipeline_context,
    filter_sensitive_hits,
    gate_by_score,
)

SENSITIVE_CHUNKS = [
    {
        "text": "我的邪恶队友名单: p1 是恶魔 私密信息 private_info",
        "metadata": {"type": "private", "role_id": "spy", "team": "evil"},
    },
]


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


def _pipeline() -> RetrievalPipeline:
    pipeline = RetrievalPipeline(backend=FakeEmbeddingBackend(), dimension=1536)
    pipeline.build(chunk_rule_knowledge() + SENSITIVE_CHUNKS)
    return pipeline


def test_filter_sensitive_drops_private_hits() -> None:
    hits = [
        {"text": "正常规则条目", "metadata": {"type": "rule"}, "score": 0.9},
        {"text": "我的邪恶队友名单: p1 是恶魔", "metadata": {"type": "private"}, "score": 0.9},
        {"text": "私密信息 private_info", "metadata": {"type": "private"}, "score": 0.9},
    ]
    filtered = filter_sensitive_hits(hits)
    assert len(filtered) == 1
    assert filtered[0]["text"] == "正常规则条目"


def test_gate_by_score_drops_low_score() -> None:
    hits = [
        {"text": "a", "metadata": {}, "score": 0.8},
        {"text": "b", "metadata": {}, "score": 0.3},
        {"text": "c", "metadata": {}, "score": 0.5},
    ]
    gated = gate_by_score(hits, min_score=0.5)
    assert [h["text"] for h in gated] == ["a", "c"]


@pytest.mark.asyncio
async def test_pipeline_retrieve_filters_and_gates() -> None:
    pipeline = _pipeline()
    hits = await pipeline.retrieve("每晚选择一名玩家使其死亡 恶魔", top_k=4, min_score=0.0)
    assert hits
    assert all(h["metadata"]["type"] == "rule" for h in hits)
    assert all("score" in h for h in hits)


@pytest.mark.asyncio
async def test_pipeline_never_leaks_sensitive() -> None:
    pipeline = _pipeline()
    hits = await pipeline.retrieve("队友 恶魔 私密", top_k=6, min_score=0.0)
    texts = " ".join(h["text"] for h in hits)
    assert "队友名单" not in texts
    assert "private_info" not in texts
    assert "我是恶魔" not in texts


@pytest.mark.asyncio
async def test_build_pipeline_context_formats_injection() -> None:
    pipeline = _pipeline()
    hits = await pipeline.retrieve("恶魔 每晚 死亡", top_k=2, min_score=0.0)
    context = build_pipeline_context(hits)
    assert "【规则检索】" in context
    assert "小恶魔" in context or "恶魔" in context


def test_build_pipeline_context_empty() -> None:
    assert build_pipeline_context([]) == ""


def test_pipeline_search_before_build_empty() -> None:
    pipeline = RetrievalPipeline(backend=None, dimension=1536)
    hits = pipeline.retrieve_sync("anything")
    assert hits == []
