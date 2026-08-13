"""BM25 稀疏检索器 — PLN-041 Phase 2 T4。

基于 `rank_bm25` 的纯本地关键词检索：

- **零模型依赖**：不调用 embeddings API，mock 环境 / 离线均可使用；
- **embeddings 降级兜底**：稠密路不可用时（faiss/numpy 缺失或 embeddings 失败）
  的稳定回退；
- 检索结果携带原始 metadata 与 BM25 score，供 RRF 融合与相关性门控。

语料格式统一为 `{"text": str, "metadata": dict}`（见 `chunker.py`）。
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from rank_bm25 import BM25Okapi
except ImportError:  # pragma: no cover - 依赖缺失时禁用
    BM25Okapi = None

logger = logging.getLogger(__name__)


class BM25Retriever:
    """BM25 检索器：build 后 search，返回带 score 的命中列表。"""

    def __init__(self) -> None:
        self._corpus: list[dict[str, Any]] = []
        self._bm25: Any = None
        self._disabled_reason: str | None = None
        if BM25Okapi is None:
            self._disabled_reason = "rank_bm25 not installed"

    @property
    def disabled_reason(self) -> str | None:
        return self._disabled_reason

    @property
    def is_ready(self) -> bool:
        return self._bm25 is not None

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """用分块后的语料构建 BM25 索引（可重复调用重建）。"""
        self._corpus = list(chunks)
        if not chunks or BM25Okapi is None:
            self._bm25 = None
            return
        try:
            tokenized = [self._tokenize(chunk.get("text", "")) for chunk in chunks]
            self._bm25 = BM25Okapi(tokenized)
        except Exception as exc:  # pragma: no cover
            logger.warning("[bm25] 构建失败，检索禁用: %s", exc)
            self._bm25 = None
            self._disabled_reason = f"build_failed: {exc}"

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """轻量分词：按非字母数字字符切分 + 保留中文双字片段。"""
        import re

        tokens: list[str] = []
        for piece in re.split(r"[^\w\u4e00-\u9fff]+", text):
            piece = piece.strip().lower()
            if not piece:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]+", piece):
                # 中文：整词 + 双字滑动窗口（提高召回）
                tokens.append(piece)
                if len(piece) >= 2:
                    tokens.extend(piece[i : i + 2] for i in range(len(piece) - 1))
            else:
                tokens.append(piece)
        return tokens

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """BM25 检索，返回带 score 的命中（降序）。"""
        if not self.is_ready:
            return []
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        try:
            scores = self._bm25.get_scores(query_tokens)
        except Exception as exc:  # pragma: no cover
            logger.warning("[bm25] 检索失败: %s", exc)
            return []
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[dict[str, Any]] = []
        for idx in ranked[:top_k]:
            if scores[idx] <= 0:
                continue
            hit = dict(self._corpus[idx])
            hit["score"] = float(scores[idx])
            hit["_idx"] = idx
            hits.append(hit)
        return hits
