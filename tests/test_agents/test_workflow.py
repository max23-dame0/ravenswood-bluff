"""T11/T12: Workflow DSL + WorkflowEngine 测试 — PLN-041 Phase 4。

覆盖：
- DSL：tool_call / condition / parallel 节点声明式定义；
- 引擎：顺序调度、条件分支、并行执行、状态跟踪；
- 超时重试、失败传播；
- 事件发布（EventBus）；
- trace 落盘 + 回放（T13）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.agents.workflow.engine import WorkflowEngine, WorkflowTrace
from src.agents.workflow.workflow import (
    ConditionNode,
    ParallelNode,
    ToolCallNode,
    Workflow,
    WorkflowError,
)


def _echo_tool(name: str):
    async def _run(ctx: dict, **kwargs: dict) -> dict:
        return {"tool": name, "ctx": ctx, **kwargs}

    return _run


def _sum_tool(name: str):
    async def _run(ctx: dict, **kwargs: dict) -> dict:
        total = sum(int(v) for v in kwargs.values() if isinstance(v, int))
        return {"tool": name, "sum": total}

    return _run


# ---------------------------------------------------------------------------
# DSL 定义
# ---------------------------------------------------------------------------


def test_tool_call_node_definition() -> None:
    node = ToolCallNode(
        node_id="n1", tool_name="assess", handler=_echo_tool("assess"), params={"x": 1}
    )
    assert node.node_id == "n1"
    assert node.tool_name == "assess"
    assert node.kind == "tool_call"


def test_condition_node_definition() -> None:
    node = ConditionNode(
        node_id="c1",
        condition=lambda ctx: ctx.get("go") is True,
        then_node=ToolCallNode(node_id="t1", tool_name="t", handler=_echo_tool("t")),
        else_node=ToolCallNode(node_id="e1", tool_name="e", handler=_echo_tool("e")),
    )
    assert node.kind == "condition"


def test_parallel_node_definition() -> None:
    node = ParallelNode(
        node_id="p1",
        branches=[
            ToolCallNode(node_id="b1", tool_name="a", handler=_echo_tool("a")),
            ToolCallNode(node_id="b2", tool_name="b", handler=_echo_tool("b")),
        ],
    )
    assert node.kind == "parallel"
    assert len(node.branches) == 2


def test_workflow_build_and_validate() -> None:
    wf = Workflow(
        workflow_id="wf-1",
        nodes=[
            ToolCallNode(node_id="n1", tool_name="a", handler=_echo_tool("a")),
        ],
        entry_node_id="n1",
    )
    assert wf.workflow_id == "wf-1"
    assert wf.entry_node_id == "n1"


def test_workflow_missing_entry_raises() -> None:
    with pytest.raises(WorkflowError):
        Workflow(workflow_id="wf", nodes=[], entry_node_id="missing")


def test_workflow_unknown_node_returns_none() -> None:
    wf = Workflow(workflow_id="wf", nodes=[], entry_node_id="")
    assert wf.get_node("nope") is None


# ---------------------------------------------------------------------------
# 引擎：顺序 / 条件 / 并行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_runs_sequential_nodes() -> None:
    wf = Workflow(
        workflow_id="seq",
        nodes=[
            ToolCallNode(node_id="a", tool_name="a", handler=_echo_tool("a")),
            ToolCallNode(node_id="b", tool_name="b", handler=_echo_tool("b")),
        ],
        entry_node_id="a",
        next_node_map={"a": "b"},
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({"seed": 1})
    assert result["a"]["tool"] == "a"
    assert result["b"]["tool"] == "b"


@pytest.mark.asyncio
async def test_engine_condition_branch() -> None:
    then_node = ToolCallNode(node_id="t", tool_name="t", handler=_echo_tool("t"))
    else_node = ToolCallNode(node_id="e", tool_name="e", handler=_echo_tool("e"))
    wf = Workflow(
        workflow_id="cond",
        nodes=[
            ConditionNode(
                node_id="c",
                condition=lambda ctx: ctx.get("go"),
                then_node=then_node,
                else_node=else_node,
            ),
            then_node,
            else_node,
        ],
        entry_node_id="c",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({"go": True})
    assert "t" in result
    assert "e" not in result


@pytest.mark.asyncio
async def test_engine_parallel_branches() -> None:
    wf = Workflow(
        workflow_id="par",
        nodes=[
            ParallelNode(
                node_id="p",
                branches=[
                    ToolCallNode(node_id="b1", tool_name="a", handler=_sum_tool("a")),
                    ToolCallNode(node_id="b2", tool_name="b", handler=_sum_tool("b")),
                ],
            ),
        ],
        entry_node_id="p",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({})
    assert result["b1"]["sum"] == 0
    assert result["b2"]["sum"] == 0


@pytest.mark.asyncio
async def test_engine_parallel_with_params() -> None:
    wf = Workflow(
        workflow_id="par2",
        nodes=[
            ParallelNode(
                node_id="p",
                branches=[
                    ToolCallNode(
                        node_id="b1", tool_name="a", handler=_sum_tool("a"), params={"x": 1, "y": 2}
                    ),
                    ToolCallNode(
                        node_id="b2", tool_name="b", handler=_sum_tool("b"), params={"x": 10}
                    ),
                ],
            ),
        ],
        entry_node_id="p",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({})
    assert result["b1"]["sum"] == 3
    assert result["b2"]["sum"] == 10


@pytest.mark.asyncio
async def test_engine_tracks_state() -> None:
    wf = Workflow(
        workflow_id="state",
        nodes=[ToolCallNode(node_id="a", tool_name="a", handler=_echo_tool("a"))],
        entry_node_id="a",
    )
    engine = WorkflowEngine(wf)
    await engine.execute({})
    assert engine.state["status"] == "completed"
    assert "a" in engine.state["node_results"]


# ---------------------------------------------------------------------------
# 超时 / 失败
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_node_timeout() -> None:
    async def _slow(ctx: dict, **kwargs: dict) -> dict:
        await asyncio.sleep(5)
        return {"tool": "slow"}

    wf = Workflow(
        workflow_id="timeout",
        nodes=[ToolCallNode(node_id="a", tool_name="a", handler=_slow, timeout_seconds=0.1)],
        entry_node_id="a",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({})
    assert "error" in result["a"]
    assert engine.state["status"] == "failed"


@pytest.mark.asyncio
async def test_engine_retries_on_failure() -> None:
    attempts = {"n": 0}

    async def _flaky(ctx: dict, **kwargs: dict) -> dict:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("flaky")
        return {"tool": "ok"}

    wf = Workflow(
        workflow_id="retry",
        nodes=[
            ToolCallNode(
                node_id="a", tool_name="a", handler=_flaky, retry_count=3, retry_delay_seconds=0
            )
        ],
        entry_node_id="a",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({})
    assert result["a"]["tool"] == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_engine_failure_propagates() -> None:
    async def _boom(ctx: dict, **kwargs: dict) -> dict:
        raise RuntimeError("boom")

    wf = Workflow(
        workflow_id="fail",
        nodes=[ToolCallNode(node_id="a", tool_name="a", handler=_boom, retry_count=1)],
        entry_node_id="a",
    )
    engine = WorkflowEngine(wf)
    result = await engine.execute({})
    assert "error" in result["a"]
    assert engine.state["status"] == "failed"


# ---------------------------------------------------------------------------
# Trace（T13）
# ---------------------------------------------------------------------------


def test_trace_records_entries(tmp_path: Path) -> None:
    trace = WorkflowTrace(tmp_path)
    trace.start("wf-1")
    trace.record_node("a", {"in": 1}, {"out": 2}, 0.01, error=None)
    trace.finish("completed")
    entries = trace.entries()
    assert len(entries) == 3
    assert entries[0]["event"] == "start"
    assert entries[1]["event"] == "node"
    assert entries[1]["node_id"] == "a"
    assert entries[2]["event"] == "finish"


def test_trace_persists_and_replays(tmp_path: Path) -> None:
    trace = WorkflowTrace(tmp_path)
    trace.start("wf-1")
    trace.record_node("a", {"in": 1}, {"out": 2}, 0.01, error=None)
    trace.finish("completed")
    path = trace.save()
    assert path.exists()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["workflow_id"] == "wf-1"
    assert len(raw["entries"]) == 3


def test_trace_empty_entries(tmp_path: Path) -> None:
    trace = WorkflowTrace(tmp_path)
    assert trace.entries() == []
    assert trace.save() is None
