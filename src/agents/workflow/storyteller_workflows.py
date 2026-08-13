"""说书人裁决工作流化试点 — PLN-041 Phase 4 T14。

把说书人 6 工具（assess_balance / choose_distortion / adjudicate_night_info /
compose_narration / deliver_verdict / review_balance）编排为显式 Workflow：

- **包装非重写**：每个节点的 handler 复用 `StorytellerAgent.invoke_tool`
  （即既有工具注册表行为），不改变任何裁决逻辑；
- **确定性红线**：真实信息计算永远在 `adjudicate_night_info` 节点（规则引擎），
  LLM 只可能出现在 `choose_distortion` 节点（受 `BOTC_ST_LLM_STRATEGY` 控制，
  默认 off 不触发 LLM）；
- **可观测性**：执行时注入 `WorkflowTrace`，节点耗时/入参出参/失败点落盘
  `data/storyteller/{game_id}/workflow_trace_*.json`，支持离线回放。

试点入口：`run_night_adjudication(st, game_state, player_id, role_id)`，
行为与 `StorytellerAgent.decide_night_info` 一致（内部即调用它），
差异仅在多产出 trace 与节点级可观测性。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.agents.workflow.engine import WorkflowEngine, WorkflowTrace
from src.agents.workflow.workflow import ToolCallNode, Workflow

WORKFLOW_ID = "night_adjudication"


def _data_dir() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


def build_night_adjudication_workflow(st) -> Workflow:
    """构造『夜晚信息裁决』显式工作流（6 工具全量声明，行为与既有链路一致）。"""

    async def _adjudicate(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        result = await st.invoke_tool(
            "adjudicate_night_info",
            game_state=ctx["game_state"],
            player_id=ctx["player_id"],
            role_id=ctx["role_id"],
        )
        ctx["info"] = result.get("info")
        return result

    async def _assess(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:

        context = st.build_decision_context(ctx["game_state"])
        result = await st.invoke_tool("assess_balance", context=context)
        ctx["balance"] = result
        return result

    async def _choose(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:

        context = st.build_decision_context(ctx["game_state"])
        return await st.invoke_tool(
            "choose_distortion",
            context=context,
            role_id=ctx["role_id"],
            info=ctx.get("info") or {},
            player_id=ctx["player_id"],
        )

    async def _compose(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        return await st.invoke_tool("compose_narration", game_state=ctx["game_state"])

    async def _deliver(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        return await st.invoke_tool(
            "deliver_verdict",
            category=kwargs.get("category", "night_info"),
            decision=kwargs.get("decision", "workflow_deliver"),
        )

    async def _review(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        return await st.invoke_tool("review_balance", game_id=ctx["game_id"])

    nodes = [
        ToolCallNode(
            node_id="adjudicate_night_info", tool_name="adjudicate_night_info", handler=_adjudicate
        ),
        ToolCallNode(node_id="assess_balance", tool_name="assess_balance", handler=_assess),
        ToolCallNode(node_id="choose_distortion", tool_name="choose_distortion", handler=_choose),
        ToolCallNode(node_id="compose_narration", tool_name="compose_narration", handler=_compose),
        ToolCallNode(node_id="deliver_verdict", tool_name="deliver_verdict", handler=_deliver),
        ToolCallNode(node_id="review_balance", tool_name="review_balance", handler=_review),
    ]
    return Workflow(
        workflow_id=WORKFLOW_ID,
        nodes=nodes,
        entry_node_id="adjudicate_night_info",
        next_node_map={
            "adjudicate_night_info": "assess_balance",
            "assess_balance": "choose_distortion",
            "choose_distortion": "compose_narration",
            "compose_narration": "deliver_verdict",
            "deliver_verdict": "review_balance",
        },
    )


async def run_night_adjudication(st, game_state, player_id: str, role_id: str) -> dict[str, Any]:
    """执行夜晚信息裁决工作流（行为等价 decide_night_info + trace）。

    Returns:
        {"info": ..., "trace_path": str | None, "results": {...}}
    """
    workflow = build_night_adjudication_workflow(st)
    trace_dir = _data_dir() / "storyteller" / str(game_state.game_id)
    trace = WorkflowTrace(trace_dir)
    engine = WorkflowEngine(workflow, trace=trace)
    context = {
        "game_state": game_state,
        "player_id": player_id,
        "role_id": role_id,
        "game_id": str(game_state.game_id),
    }
    results = await engine.execute(context)
    trace_path = trace.save()
    return {
        "info": context.get("info"),
        "trace_path": str(trace_path) if trace_path else None,
        "results": results,
        "state_status": engine.state["status"],
    }
