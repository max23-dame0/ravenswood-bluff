"""双路混合检索器 (HybridRetriever) — PLN-041 Phase 2 T5。

BM25 稀疏路 + Faiss 稠密路 + RRF（Reciprocal Rank Fusion）融合：

- **BM25 路永远可用**：纯本地，embeddings 降级兜底；
- **Faiss 稠密路可选**：backend 提供 embeddings 且 faiss/numpy 可用时启用；
- **RRF 融合**：`score = Σ 1/(k + rank)`，两路都命中的文档自然靠前；
- 最终分数归一化到 0~1，供相关性门控使用。

后端协议：`backend.get_embeddings(texts) -> list[list[float]]`（与 LLMBackend 一致）。
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.memory.retrieval.bm25_retriever import BM25Retriever

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None

logger = logging.getLogger(__name__)

_RRF_K = 60.0


class HybridRetriever:
    """双路检索 + RRF 融合。"""

    def __init__(self, backend: Any | None = None, dimension: int = 1536) -> None:
        self._backend = backend
        self._dimension = dimension
        self._bm25 = BM25Retriever()
        self._faiss_index: Any = None
        self._corpus: list[dict[str, Any]] = []
        self._vectors: list[Any] = []
        self._dense_enabled = bool(backend is not None and faiss is not None and np is not None)

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """重建索引（BM25 + Faiss 同时构建）。"""
        self._corpus = list(chunks)
        self._bm25.build(chunks)
        self._vectors = []
        if self._dense_enabled:
            self._faiss_index = faiss.IndexFlatL2(self._dimension)
        else:
            self._faiss_index = None

    async def _embed_all(self, texts: list[str]) -> list[list[float]]:
        """批量向量化；失败返回空列表（降级为仅 BM25）。"""
        if not self._dense_enabled or self._backend is None:
            return []
        try:
            return await self._backend.get_embeddings(texts)
        except Exception as exc:  # pragma: no cover
            logger.warning("[hybrid] embeddings 失败，降级为 BM25: %s", exc)
            return []

    async def add_dense_vectors(self) -> None:
        """为当前语料批量计算向量并加入 Faiss 索引（惰性）。"""
        if not self._dense_enabled or not self._corpus:
            return
        texts = [chunk.get("text", "") for chunk in self._corpus]
        vectors = await self._embed_all(texts)
        if not vectors or len(vectors) != len(texts):
            self._faiss_index = None
            return
        try:
            self._vectors = [np.array(v, dtype="float32") for v in vectors]
            if self._faiss_index is not None:
                self._faiss_index.add(np.vstack(self._vectors))
        except Exception as exc:  # pragma: no cover
            logger.warning("[hybrid] Faiss 构建失败，降级为 BM25: %s", exc)
            self._faiss_index = None

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def _dense_search(self, query: str, top_k: int) -> list[int]:
        """稠密检索，返回语料下标列表。"""
        if self._faiss_index is None or self._faiss_index.ntotal == 0 or not self._backend:
            return []
        vectors = await self._embed_all([query])
        if not vectors:
            return []
        try:
            _dists, indices = self._faiss_index.search(
                np.array(vectors, dtype="float32"), min(top_k, self._faiss_index.ntotal)
            )
            return [int(idx) for idx in indices[0] if idx != -1]
        except Exception as exc:  # pragma: no cover
            logger.warning("[hybrid] Faiss 检索失败，降级为 BM25: %s", exc)
            return []

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """双路检索 + RRF 融合，返回带 score（0~1）的命中列表。"""
        if not self._corpus:
            return []

        sparse_hits = self._bm25.search(query, top_k=top_k * 2)
        dense_indices = await self._dense_search(query, top_k=top_k * 2)

        rrf: dict[int, float] = {}
        for rank, hit in enumerate(sparse_hits):
            idx = hit.get("_idx")
            if idx is not None and 0 <= idx < len(self._corpus):
                rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (_RRF_K + rank + 1)
        for rank, idx in enumerate(dense_indices):
            rrf[idx] = rrf.get(idx, 0.0) + 1.0 / (_RRF_K + rank + 1)

        if not rrf:
            return []
        max_score = max(rrf.values())
        ranked = sorted(rrf.items(), key=lambda item: (-item[1], item[0]))
        results: list[dict[str, Any]] = []
        for idx, score in ranked[:top_k]:
            hit = dict(self._corpus[idx])
            hit["score"] = round(score / max_score, 4)
            hit.pop("_idx", None)
            results.append(hit)
        return results
