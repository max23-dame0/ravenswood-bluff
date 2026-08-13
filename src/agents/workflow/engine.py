"""WorkflowEngine 执行器 — PLN-041 Phase 4 T12。

调度 + 状态跟踪 + 超时重试 + trace 落盘：

- **调度**：从 entry 节点开始，按 next_node_map 顺序推进；条件节点按
  condition 结果分支；并行节点并发执行所有分支；
- **状态跟踪**：`state.status`（running/completed/failed）+ `node_results`；
- **超时重试**：ToolCallNode 支持 timeout_seconds（超时记为失败）与
  retry_count（失败重试）；
- **可观测性**：可选注入 `WorkflowTrace`，节点执行/失败全程记录。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from src.agents.workflow.workflow import (
    ConditionNode,
    Node,
    ParallelNode,
    ToolCallNode,
    Workflow,
)


class WorkflowTrace:
    """工作流执行轨迹：start / record_node / finish → 落盘 JSON + 回放。"""

    def __init__(self, base_dir) -> None:
        self._base_dir = base_dir
        self._workflow_id = ""
        self._entries: list[dict[str, Any]] = []

    def start(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id
        self._entries.append({"event": "start", "workflow_id": workflow_id, "ts": time.time()})

    def record_node(
        self,
        node_id: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any] | None,
        duration: float,
        error: str | None = None,
    ) -> None:
        self._entries.append(
            {
                "event": "node",
                "node_id": node_id,
                "inputs": inputs,
                "outputs": outputs,
                "duration": round(duration, 4),
                "error": error,
                "ts": time.time(),
            }
        )

    def finish(self, status: str) -> None:
        self._entries.append({"event": "finish", "status": status, "ts": time.time()})

    def entries(self) -> list[dict[str, Any]]:
        return list(self._entries)

    def save(self):
        """落盘 `{base_dir}/workflow_trace_{ts}.json`；无轨迹返回 None。"""
        import json
        from pathlib import Path

        if not self._entries:
            return None
        base = Path(self._base_dir)
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"workflow_trace_{int(time.time() * 1000)}.json"
        payload = {"workflow_id": self._workflow_id, "entries": self._entries}
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8"
        )
        return path


class WorkflowEngine:
    """工作流执行器。"""

    def __init__(self, workflow: Workflow, trace: WorkflowTrace | None = None) -> None:
        self._workflow = workflow
        self._trace = trace
        self.state: dict[str, Any] = {
            "status": "idle",
            "workflow_id": workflow.workflow_id,
            "node_results": {},
        }
        if trace is not None:
            trace.start(workflow.workflow_id)

    # ------------------------------------------------------------------
    # 执行入口
    # ------------------------------------------------------------------

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """从入口节点开始执行；返回 {node_id: result}。"""
        self.state["status"] = "running"
        entry = self._workflow.get_node(self._workflow.entry_node_id)
        if entry is None:
            self.state["status"] = "failed"
            return self.state["node_results"]
        try:
            await self._run_node(entry, context)
            self.state["status"] = "completed"
        except WorkflowRuntimeError as exc:
            self.state["status"] = "failed"
            self.state["error"] = str(exc)
        if self._trace is not None:
            self._trace.finish(self.state["status"])
        return self.state["node_results"]

    # ------------------------------------------------------------------
    # 节点调度
    # ------------------------------------------------------------------

    async def _run_node(self, node: Node, context: dict[str, Any]) -> None:
        if isinstance(node, ToolCallNode):
            await self._run_tool_call(node, context)
        elif isinstance(node, ConditionNode):
            await self._run_condition(node, context)
        elif isinstance(node, ParallelNode):
            await self._run_parallel(node, context)
        else:
            raise WorkflowRuntimeError(f"unknown node kind: {node.kind}")

        # 顺序推进
        next_id = self._workflow.next_node_map.get(node.node_id)
        if next_id:
            nxt = self._workflow.get_node(next_id)
            if nxt is None:
                raise WorkflowRuntimeError(f"next node '{next_id}' not found")
            await self._run_node(nxt, context)

    async def _run_tool_call(self, node: ToolCallNode, context: dict[str, Any]) -> None:
        inputs = dict(node.params)
        inputs["ctx"] = context
        result: dict[str, Any] = {}
        error: str | None = None
        start = time.perf_counter()
        try:
            for attempt in range(node.retry_count + 1):
                try:
                    result = await asyncio.wait_for(
                        node.handler(context, **node.params), timeout=node.timeout_seconds
                    )
                    error = None
                    break
                except (TimeoutError, Exception) as exc:  # noqa: BLE001
                    error = f"{type(exc).__name__}: {exc}"
                    if attempt < node.retry_count:
                        await asyncio.sleep(node.retry_delay_seconds)
        except Exception as exc:  # noqa: BLE001 - 兜底
            error = f"{type(exc).__name__}: {exc}"
        duration = time.perf_counter() - start

        if error is not None:
            self.state["node_results"][node.node_id] = {"error": error}
        else:
            self.state["node_results"][node.node_id] = result
        if self._trace is not None:
            self._trace.record_node(
                node.node_id,
                inputs=inputs,
                outputs=self.state["node_results"][node.node_id],
                duration=duration,
                error=error,
            )
        if error is not None:
            raise WorkflowRuntimeError(f"node '{node.node_id}' failed: {error}")

    async def _run_condition(self, node: ConditionNode, context: dict[str, Any]) -> None:
        try:
            go = bool(node.condition(context))
        except Exception as exc:  # noqa: BLE001
            raise WorkflowRuntimeError(f"condition '{node.node_id}' raised: {exc}") from exc
        target = node.then_node if go else node.else_node
        if target is not None:
            await self._run_node(target, context)

    async def _run_parallel(self, node: ParallelNode, context: dict[str, Any]) -> None:
        await asyncio.gather(*(self._run_node(branch, context) for branch in node.branches))


class WorkflowRuntimeError(Exception):
    """工作流运行时错误（节点失败/超时/缺失）。"""
