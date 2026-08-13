"""PLN-041 检索质量 + 工作流轨迹完整性验收 gate。

Gate 1 — 检索质量：规则评测集 Recall@k / MRR 必须达阈值（默认 0.85/0.80）；
Gate 2 — 工作流轨迹完整性：执行一个迷你工作流，验证 trace 落盘
（start/node/finish 三事件齐全，可回放）。

用法：
    python scripts/acceptance/retrieval_workflow_acceptance.py
        [--min-recall 0.85] [--min-mrr 0.80]

返回非 0 表示 gate 失败（作为发布 blocker）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmark.retrieval_quality_benchmark import (  # noqa: E402
    run_benchmark,
)

from src.agents.workflow.engine import WorkflowEngine, WorkflowTrace  # noqa: E402
from src.agents.workflow.workflow import ToolCallNode, Workflow  # noqa: E402


async def _gate_retrieval_quality(min_recall: float, min_mrr: float) -> int:
    result = await run_benchmark(top_k=5, sample_limit=0, use_dense=False)
    print(
        f"[retrieval] scored={result['scored_queries']} "
        f"Recall@5={result['recall_at_k']} MRR={result['mrr']}"
    )
    if result["recall_at_k"] < min_recall or result["mrr"] < min_mrr:
        print(
            f"[retrieval] GATE FAILED: recall {result['recall_at_k']} < {min_recall} "
            f"or MRR {result['mrr']} < {min_mrr}"
        )
        return 1
    print("[retrieval] GATE PASSED")
    return 0


async def _gate_workflow_trace() -> int:
    """迷你工作流 + trace 落盘 + 回放完整性校验。"""

    async def _step_a(ctx: dict, **kwargs: dict) -> dict:
        return {"tool": "a", "ok": True}

    async def _step_b(ctx: dict, **kwargs: dict) -> dict:
        return {"tool": "b", "sum": kwargs.get("x", 0) + 1}

    wf = Workflow(
        workflow_id="acceptance-demo",
        nodes=[
            ToolCallNode(node_id="a", tool_name="a", handler=_step_a),
            ToolCallNode(node_id="b", tool_name="b", handler=_step_b, params={"x": 41}),
        ],
        entry_node_id="a",
        next_node_map={"a": "b"},
    )
    with tempfile.TemporaryDirectory() as tmp:
        trace = WorkflowTrace(Path(tmp))
        engine = WorkflowEngine(wf, trace=trace)
        results = await engine.execute({})
        if results.get("b", {}).get("sum") != 42:
            print(f"[workflow] GATE FAILED: unexpected result {results}")
            return 1
        path = trace.save()
        if path is None:
            print("[workflow] GATE FAILED: trace not persisted")
            return 1
        raw = json.loads(path.read_text(encoding="utf-8"))
        events = [e["event"] for e in raw["entries"]]
        if events[0] != "start" or events[-1] != "finish" or "node" not in events:
            print(f"[workflow] GATE FAILED: trace incomplete {events}")
            return 1
        node_events = [e for e in raw["entries"] if e["event"] == "node"]
        if {e["node_id"] for e in node_events} != {"a", "b"}:
            print(f"[workflow] GATE FAILED: missing node entries {node_events}")
            return 1
    print("[workflow] GATE PASSED (trace persisted, replayable)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PLN-041 检索 + 工作流 gate")
    parser.add_argument("--min-recall", type=float, default=0.85)
    parser.add_argument("--min-mrr", type=float, default=0.80)
    args = parser.parse_args()

    rc1 = asyncio.run(_gate_retrieval_quality(args.min_recall, args.min_mrr))
    rc2 = asyncio.run(_gate_workflow_trace())
    if rc1 or rc2:
        print("\nretrieval_workflow_acceptance: FAILED")
        return 1
    print("\nretrieval_workflow_acceptance: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
