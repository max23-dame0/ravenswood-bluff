"""认知工作流 (Cognitive Workflow) — PLN-042 T3。

把"先思考再说话"显式化为工作流节点：

    recall  : 构建记忆快照 + 加载当前激活观点摘要
    reason  : 确定性证据提取 → 置信度计算 → 门控（无硬证据强断言降级）
    speak   : 基于论点语言化（确定性模板：claim + 硬证据 + 软印象）
    record  : 观点落盘 viewpoints.jsonl + trace 落盘

设计原则（红线）：
- **确定性核心**：证据提取/置信度/门控/语言化全部确定性，LLM 不参与
  数值与论证（守住确定性红线）；LLM 的"表达"发生在 AIAgent 主路径——
  本工作流产出的观点摘要作为 user 段动态上下文注入（T4 集成）；
- **门控防幻觉**：纯软印象的强断言（"一定是"）在 reason 阶段被降级为
  "可能"——幻觉在**生成前**被拦截；
- **仅 live 落盘**：无 ViewpointStore（mock 默认）时直接返回 None，
  不产生任何文件。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.agents.reasoning.viewpoint_engine import ViewpointEngine
from src.agents.workflow.engine import WorkflowEngine, WorkflowTrace
from src.agents.workflow.workflow import ToolCallNode, Workflow

WORKFLOW_ID = "cognitive_speech"


def cognitive_speak_enabled() -> bool:
    """认知发言试点开关：`BOTC_COGNITIVE_SPEAK=1` 开启，默认 off（行为兼容）。"""
    return os.getenv("BOTC_COGNITIVE_SPEAK", "").strip().lower() in {"1", "true"}


def _data_dir() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


def build_cognitive_speech_workflow(agent) -> Workflow:
    """构造『认知发言』工作流（recall→reason→speak→record）。"""

    async def _recall(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        memory = agent.build_memory_snapshot() if hasattr(agent, "build_memory_snapshot") else {}
        ctx["memory"] = memory
        store = agent.get_viewpoint_store() if hasattr(agent, "get_viewpoint_store") else None
        ctx["viewpoint_summary"] = store.build_summary() if store else ""
        return {"memory_keys": list(memory.keys()), "summary_len": len(ctx["viewpoint_summary"])}

    async def _reason(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        engine = ViewpointEngine()
        memory: dict[str, list[str]] = ctx.get("memory") or {}
        claim = str(kwargs.get("claim") or ctx.get("claim") or "")
        subject_id = str(kwargs.get("subject_player_id") or ctx.get("subject_player_id") or "")
        subject_name = str(kwargs.get("subject_name") or ctx.get("subject_name") or "")
        if not claim or not subject_id:
            # 无明确论点对象时，从记忆（hard+soft）提取"最可疑"目标
            for bucket in ("hard", "soft"):
                for text in memory.get(bucket, []):
                    for name in _candidate_names(text):
                        subject_name = name
                        break
                    if subject_name:
                        break
                if subject_name:
                    break
            if not subject_name:
                ctx["claim"] = ""
                ctx["confidence"] = 0.0
                return {"claim": "", "confidence": 0.0, "gated": True}
            claim = f"{subject_name} 可能是恶魔"
        claim = claim.replace("{subject}", subject_name)

        evidence = engine.extract_evidence(memory)
        hard_count = sum(1 for e in evidence if e.kind == "hard")
        soft_count = sum(1 for e in evidence if e.kind == "soft")
        confidence = (
            engine.build_viewpoint(
                subject_player_id=subject_id or "unknown",
                subject_name=subject_name,
                claim=claim,
                memory=memory,
                source_action="speak",
                day_number=int(ctx.get("day_number", 1)),
                round_number=int(ctx.get("round_number", 1)),
                evidence=evidence,
            ).confidence
            if (hard_count or soft_count)
            else 0.0
        )

        gated = not engine.passes_gate(hard_count, soft_count)
        if gated:
            claim = engine.soft_claim_fallback(claim)
        ctx["claim"] = claim
        ctx["confidence"] = confidence
        ctx["evidence"] = [e.to_dict() for e in evidence]
        return {
            "claim": claim,
            "confidence": confidence,
            "gated": gated,
            "hard": hard_count,
            "soft": soft_count,
        }

    async def _speak(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        claim = str(ctx.get("claim") or "")
        evidence = ctx.get("evidence") or []
        hard = [e for e in evidence if e.get("kind") == "hard"]
        soft = [e for e in evidence if e.get("kind") == "soft"]
        if not claim:
            ctx["content"] = ""
            return {"content": ""}
        parts = [f"我的看法是：{claim}"]
        if hard:
            parts.append("依据：" + "；".join(e["detail"][:50] for e in hard[:2]))
        if soft:
            parts.append("另外，" + "；".join(e["detail"][:40] for e in soft[:2]))
        ctx["content"] = "。".join(parts) + "。"
        return {"content": ctx["content"]}

    async def _record(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        store = agent.get_viewpoint_store() if hasattr(agent, "get_viewpoint_store") else None
        claim = str(ctx.get("claim") or "")
        if store is None or not claim:
            return {"recorded": False}
        evidence = [e for e in (ctx.get("evidence") or []) if e.get("kind")]
        from src.agents.reasoning.viewpoint import Evidence

        vp = store.add_viewpoint(
            subject_player_id=str(ctx.get("subject_player_id") or "unknown"),
            subject_name=str(ctx.get("subject_name") or ""),
            claim=claim,
            evidence=[
                Evidence(
                    kind=e.get("kind", "soft"),
                    source=e.get("source", ""),
                    detail=e.get("detail", ""),
                    day_number=int(e.get("day_number", 0) or 0),
                    round_number=int(e.get("round_number", 0) or 0),
                )
                for e in evidence
            ],
            confidence=float(ctx.get("confidence", 0.0) or 0.0),
            source_action="speak",
            day_number=int(ctx.get("day_number", 1)),
            round_number=int(ctx.get("round_number", 1)),
        )
        return {"recorded": vp is not None}

    nodes = [
        ToolCallNode(node_id="recall", tool_name="recall", handler=_recall),
        ToolCallNode(node_id="reason", tool_name="reason", handler=_reason),
        ToolCallNode(node_id="speak", tool_name="speak", handler=_speak),
        ToolCallNode(node_id="record", tool_name="record", handler=_record),
    ]
    return Workflow(
        workflow_id=WORKFLOW_ID,
        nodes=nodes,
        entry_node_id="recall",
        next_node_map={"recall": "reason", "reason": "speak", "speak": "record"},
    )


def _candidate_names(text: str) -> list[str]:
    """从记忆文本中粗提取候选玩家名（P 开头编号）。"""
    import re

    return re.findall(r"(?:P\d+|p\d+|[A-Za-z]{2,8}-\d)", text)


async def run_cognitive_speech(
    agent, player_id: str, visible_state, context: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """执行认知发言工作流。

    - 无 ViewpointStore（mock 默认关闭）→ 返回 None，零文件；
    - 否则返回 {"claim", "content", "confidence", "trace_path", "results"}。
    """
    store = agent.get_viewpoint_store() if hasattr(agent, "get_viewpoint_store") else None
    if store is None or not store.enabled:
        return None
    workflow = build_cognitive_speech_workflow(agent)
    trace_dir = _data_dir() / "agents" / player_id / "games" / str(context.get("game_id", ""))
    trace = WorkflowTrace(trace_dir)
    engine = WorkflowEngine(workflow, trace=trace)
    ctx = dict(context or {})
    ctx["player_id"] = player_id
    results = await engine.execute(ctx)
    trace_path = trace.save()
    return {
        "claim": ctx.get("claim", ""),
        "confidence": ctx.get("confidence", 0.0),
        "content": ctx.get("content", ""),
        "trace_path": str(trace_path) if trace_path else None,
        "results": results,
        "state_status": engine.state["status"],
    }
