"""T10: 检索质量评测脚本测试 — PLN-041 Phase 3。

验证指标计算与评测集构造：
- recall@k / MRR 计算正确；
- 规则评测集 22 条（每角色 1 条）；
- 混合评测集采样限流。
"""

from __future__ import annotations

from scripts.benchmark.retrieval_quality_benchmark import (
    build_mixed_eval_set,
    build_rule_eval_set,
    evaluate_mrr,
    evaluate_recall_at_k,
)


def _hits(role_ids: list[str]) -> list[dict]:
    return [{"metadata": {"role_id": rid}} for rid in role_ids]


def test_recall_at_k_hit() -> None:
    hits = _hits(["imp", "empath", "washerwoman"])
    assert evaluate_recall_at_k(hits, ["imp"], k=5) == 1.0


def test_recall_at_k_miss() -> None:
    hits = _hits(["imp", "empath"])
    assert evaluate_recall_at_k(hits, ["chef"], k=5) == 0.0


def test_recall_at_k_partial() -> None:
    hits = _hits(["imp", "empath", "washerwoman"])
    assert evaluate_recall_at_k(hits, ["imp", "chef"], k=5) == 0.5


def test_recall_respects_k() -> None:
    hits = _hits(["imp", "empath", "washerwoman"])
    assert evaluate_recall_at_k(hits, ["washerwoman"], k=2) == 0.0


def test_recall_empty_relevant() -> None:
    assert evaluate_recall_at_k(_hits(["imp"]), [], k=5) == 0.0


def test_mrr_rank_one() -> None:
    hits = _hits(["imp", "empath"])
    assert evaluate_mrr(hits, ["imp"]) == 1.0


def test_mrr_second_rank() -> None:
    hits = _hits(["imp", "empath", "chef"])
    assert evaluate_mrr(hits, ["empath"]) == 0.5


def test_mrr_miss() -> None:
    hits = _hits(["imp"])
    assert evaluate_mrr(hits, ["chef"]) == 0.0


def test_rule_eval_set_covers_all_roles() -> None:
    queries = build_rule_eval_set()
    assert len(queries) == 22
    for q in queries:
        assert q["query"]
        assert len(q["relevant_ids"]) == 1
        assert q["source"] == "rule"


def test_mixed_eval_set_respects_limit() -> None:
    queries = build_mixed_eval_set(sample_limit=3)
    rule_queries = [q for q in queries if q["source"] == "rule"]
    sample_queries = [q for q in queries if q["source"] == "sample"]
    assert len(rule_queries) == 22
    assert len(sample_queries) <= 3
