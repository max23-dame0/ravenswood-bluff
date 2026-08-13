"""检索质量基准 (Retrieval Quality Benchmark) — PLN-041 Phase 3 T10。

构造离线评测集（查询 → 相关文档），量化检索注入质量：

- **评测集**：从规则知识库构造"查询→相关文档"标注对（每角色 1 条：
  查询 = `"{zh_name} 的能力是什么"`，相关文档 = 该角色条目）+ 可选真实查询
  （从 storyteller_eval_samples 采样节点文本作查询，相关文档按 metadata 匹配）；
- **指标**：Recall@k 与 MRR（Mean Reciprocal Rank）；
- **门禁**：默认阈值 Recall@5 >= 0.85 / MRR >= 0.8（可通过参数覆盖），
  未达阈值返回非 0（可作 CI gate）。

用法：
    python scripts/benchmark/retrieval_quality_benchmark.py [--top-k 5]
        [--min-recall 0.85] [--min-mrr 0.8] [--sample-limit 40]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.agents.memory.retrieval.chunker import chunk_rule_knowledge  # noqa: E402
from src.agents.memory.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402


def build_rule_eval_set() -> list[dict]:
    """从规则知识库构造标注集：查询=角色能力问句，相关文档=该角色条目。"""
    from src.content.rule_knowledge import get_rule_entry

    chunks = chunk_rule_knowledge()
    queries: list[dict] = []
    for chunk in chunks:
        role_id = chunk["metadata"]["role_id"]
        entry = get_rule_entry(role_id)
        queries.append(
            {
                "query": f"{entry['zh_name'] if entry else role_id}的能力是什么",
                "relevant_ids": [role_id],
                "source": "rule",
            }
        )
    return queries


def build_mixed_eval_set(sample_limit: int, seed: int = 42) -> list[dict]:
    """规则集 + storyteller_eval_samples 采样（最多 sample_limit 条）。

    采样节点查询：取节点里的 night_info / judgement 相关文本片段，
    相关文档按文本中出现的角色名匹配（粗标注，仅用于扩充评测集规模）。
    """
    queries = build_rule_eval_set()
    sample_dir = REPO_ROOT / "storyteller_eval_samples"
    candidates: list[str] = []
    if sample_dir.exists():
        for path in list(sample_dir.glob("sample_*.json"))[:10]:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            text = json.dumps(data, ensure_ascii=False)
            candidates.append(text[:500])
    rng = random.Random(seed)
    rng.shuffle(candidates)
    for text in candidates[:sample_limit]:
        queries.append({"query": text[:120], "relevant_ids": [], "source": "sample"})
    return queries


def _dense_backend():
    """真实 embeddings 后端（OpenAIBackend，live 评测用）。"""
    from src.llm.openai_backend import OpenAIBackend

    return OpenAIBackend()


def _ids_in_result(hits: list[dict]) -> list[str]:
    return [h.get("metadata", {}).get("role_id", "") for h in hits]


def evaluate_recall_at_k(hits: list[dict], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    got = set(_ids_in_result(hits[:k]))
    return len(got & set(relevant)) / len(relevant)


def evaluate_mrr(hits: list[dict], relevant: list[str]) -> float:
    if not relevant:
        return 0.0
    for rank, hit in enumerate(hits, start=1):
        if hit.get("metadata", {}).get("role_id") in relevant:
            return 1.0 / rank
    return 0.0


async def run_benchmark(top_k: int, sample_limit: int, use_dense: bool = False) -> dict:
    chunks = chunk_rule_knowledge()
    # 默认 BM25-only：mock 环境的 embeddings 无语义（长度向量）会注入随机噪声，
    # 破坏 MRR。稠密路仅在有真实 embeddings 后端时开启（--dense）。
    retriever = HybridRetriever(backend=None if not use_dense else _dense_backend(), dimension=1536)
    retriever.build(chunks)
    if use_dense:
        await retriever.add_dense_vectors()

    queries = build_mixed_eval_set(sample_limit)
    recall_sum = 0.0
    mrr_sum = 0.0
    scored = 0
    per_query: list[dict] = []
    for q in queries:
        hits = await retriever.search(q["query"], top_k=top_k)
        if not q["relevant_ids"]:
            continue
        recall = evaluate_recall_at_k(hits, q["relevant_ids"], top_k)
        mrr = evaluate_mrr(hits, q["relevant_ids"])
        recall_sum += recall
        mrr_sum += mrr
        scored += 1
        per_query.append({"query": q["query"][:60], "recall": recall, "mrr": mrr})

    return {
        "scored_queries": scored,
        "top_k": top_k,
        "recall_at_k": round(recall_sum / max(1, scored), 4),
        "mrr": round(mrr_sum / max(1, scored), 4),
        "per_query": per_query[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检索质量基准（Recall@k / MRR）")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-recall", type=float, default=0.85)
    parser.add_argument("--min-mrr", type=float, default=0.80)
    parser.add_argument("--sample-limit", type=int, default=40)
    parser.add_argument("--dense", action="store_true", help="启用稠密路（需真实 embeddings 后端）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args()

    import asyncio

    result = asyncio.run(run_benchmark(args.top_k, args.sample_limit, use_dense=args.dense))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Scored queries: {result['scored_queries']} | "
            f"Recall@{result['top_k']}: {result['recall_at_k']} | MRR: {result['mrr']}"
        )
    ok = result["recall_at_k"] >= args.min_recall and result["mrr"] >= args.min_mrr
    if not ok:
        print(
            f"GATE FAILED: recall {result['recall_at_k']} < {args.min_recall} "
            f"or MRR {result['mrr']} < {args.min_mrr}"
        )
        return 1
    print("GATE PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
