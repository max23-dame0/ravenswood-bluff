"""统一检索注入管线 (RetrievalPipeline) — PLN-041 Phase 3 T8。

收敛 `vector_memory / shared_pool / player_profile` 的检索职责为一条管线：

    retrieve → 敏感过滤 → 相关性门控 → 注入（build_pipeline_context）

设计约束（对应 D013/D014 / PLN-041 §8）：
- **敏感过滤**：所有命中过 `MemoryToolsLike.is_sensitive`，恶魔/队友名单绝不注入；
- **相关性门控**：score 低于阈值的命中丢弃；检索不到时调用方走规则兜底；
- **注入时机**：由调用方决定——setup 期静态注入（stable_context）或动态注入
  （user 末条）。本模块只负责产出可注入文本，不自行决定时机。
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.memory.retrieval.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


def filter_sensitive_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """丢弃含敏感标记的命中（恶魔/队友名单/私密信息等）。

    规则知识条目（metadata.type == "rule"）是公开静态知识，直接放行——
    `is_sensitive` 的标记含裸词「恶魔」，规则书文本（占卜师/小恶魔等）必然
    包含，误杀会清空合法检索结果。
    """
    from src.agents.memory.player_profile import MemoryToolsLike

    result: list[dict[str, Any]] = []
    for hit in hits:
        mtype = str(hit.get("metadata", {}).get("type", ""))
        if mtype == "rule":
            result.append(hit)
            continue
        if MemoryToolsLike.is_sensitive(str(hit.get("text", ""))):
            continue
        result.append(hit)
    return result


def gate_by_score(hits: list[dict[str, Any]], min_score: float = 0.3) -> list[dict[str, Any]]:
    """按相关性分数门控：低于阈值的命中丢弃。"""
    return [hit for hit in hits if float(hit.get("score", 0.0)) >= min_score]


def build_pipeline_context(hits: list[dict[str, Any]], limit: int = 3) -> str:
    """把过滤后的命中格式化为可注入的纯文本（无敏感）。

    空命中返回空串，调用方可据此走规则兜底。
    """
    if not hits:
        return ""
    lines: list[str] = []
    for hit in hits[:limit]:
        text = str(hit.get("text", "")).strip()
        if not text:
            continue
        lines.append(f"- {text[:160]}")
    if not lines:
        return ""
    return "【规则检索】\n" + "\n".join(lines)


class RetrievalPipeline:
    """统一检索管线：build 后 retrieve（异步）/ retrieve_sync（仅 BM25）。"""

    def __init__(self, backend: Any | None = None, dimension: int = 1536) -> None:
        self._hybrid = HybridRetriever(backend=backend, dimension=dimension)

    def build(self, chunks: list[dict[str, Any]]) -> None:
        """重建检索索引。"""
        self._hybrid.build(chunks)

    async def retrieve(
        self, query: str, top_k: int = 5, min_score: float = 0.3
    ) -> list[dict[str, Any]]:
        """异步双路检索：过滤敏感 → 分数门控。"""
        hits = await self._hybrid.search(query, top_k=top_k)
        hits = filter_sensitive_hits(hits)
        hits = gate_by_score(hits, min_score=min_score)
        return hits

    def retrieve_sync(
        self, query: str, top_k: int = 5, min_score: float = 0.3
    ) -> list[dict[str, Any]]:
        """同步 BM25-only 检索（无 embeddings 依赖），供非异步上下文使用。"""
        if not self._hybrid._corpus:
            return []
        sparse_hits = self._hybrid._bm25.search(query, top_k=top_k)
        sparse_hits = filter_sensitive_hits(sparse_hits)
        sparse_hits = gate_by_score(sparse_hits, min_score=min_score)
        for hit in sparse_hits:
            hit.pop("_idx", None)
        return sparse_hits
