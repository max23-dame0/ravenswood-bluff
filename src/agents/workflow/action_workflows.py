"""全动作声明式工作流 (Action Workflows) — PLN-043 T2/T3/T4。

把 agent 玩家的**全部动作决策**统一为显式工作流编排：

    recall   : 记忆快照（hard/soft 分级）+ 激活观点摘要 → 注入 strategic_thought
    decide   : 按动作类型复用决策原语（本地启发式 / 猎手判定 / 草稿复用 / LLM 工具调用）
    validate : 合法性校验（decision 必须含 action 字段，非法回退 fallback）
    record   : 决策结果回写观点库（观点演化闭环）+ workflow trace 落盘

设计红线（包装非重写）：
- 节点**复用 AIAgent 既有决策原语**（`_decide_local_low_value` / `_decide_slayer_shot` /
  `_draft_reuse_decision` / `_decide_via_llm`），不重新实现决策逻辑；
- 开关 `BOTC_WORKFLOW_ACTIONS=1` 默认 off，关闭时 act() 走原路径零差异；
- token 分级：vote/nomination_intent 零 LLM（本地启发式）；reason 确定性零 LLM；
- 观点回写进 user 段（D013/D014）；快照排除阵营私密（复用 build_memory_snapshot）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.agents.workflow.engine import WorkflowEngine, WorkflowTrace
from src.agents.workflow.workflow import ToolCallNode, Workflow

# 动作类型 → 工作流 id（speak 认知工作流已有独立编排，这里统一路由）
ACTION_WORKFLOW_IDS: dict[str, str] = {
    "speak": "action_speak",
    "defense_speech": "action_defense",
    "vote": "action_vote",
    "nomination_intent": "action_nomination_intent",
    "nominate": "action_nominate",
    "night_action": "action_night",
    "death_trigger": "action_death_trigger",
    "slayer_shot": "action_slayer_shot",
}

# decide 节点走本地启发式的动作（零 LLM，确定性）
_LOCAL_LOW_VALUE_ACTIONS = {"vote", "nomination_intent"}


def workflow_actions_enabled() -> bool:
    """全动作工作流开关：`BOTC_WORKFLOW_ACTIONS=1` 开启，默认 off（行为兼容）。"""
    return os.getenv("BOTC_WORKFLOW_ACTIONS", "").strip().lower() in {"1", "true"}


def _data_dir() -> Path:
    return Path(os.getenv("BOTC_DATA_DIR", "data"))


def build_action_workflow(agent, action_type: str) -> Workflow:
    """构造『动作决策』显式工作流（recall→decide→validate→record）。

    Args:
        agent: AIAgent 实例（注入决策原语）
        action_type: speak/vote/nominate/night_action/... 之一
    """
    workflow_id = ACTION_WORKFLOW_IDS.get(action_type, f"action_{action_type}")

    async def _recall(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        """记忆快照 + 观点摘要 → 注入 strategic_thought（供 LLM 决策路径参考）。"""
        memory = agent.build_memory_snapshot() if hasattr(agent, "build_memory_snapshot") else {}
        ctx["memory"] = memory
        summary = ""
        store = agent.get_viewpoint_store() if hasattr(agent, "get_viewpoint_store") else None
        if store is not None:
            summary = store.build_summary()
        if summary:
            existing = str(ctx.get("strategic_thought") or "")
            ctx["strategic_thought"] = f"{existing}\n{summary}".strip()
        return {"memory_keys": list(memory.keys()), "viewpoint_summary_len": len(summary)}

    async def _decide(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        """按动作类型复用决策原语（顺序严格对齐 act()：local → slayer → draft → LLM）。

        注意：act() 对所有 action_type 先过 `_decide_slayer_shot`（其内部仅对
        speak/nomination_intent 且猎手角色触发），不是只有 "slayer_shot" 动作类型。
        """
        visible_state = ctx["visible_state"]
        legal_context = ctx["legal_context"]
        decision: dict[str, Any] | None = None

        if action_type in _LOCAL_LOW_VALUE_ACTIONS and agent._should_use_local_low_value_action(
            action_type
        ):
            decision = await agent._decide_local_low_value(
                visible_state, legal_context, action_type
            )
        if decision is None:
            decision = await agent._decide_slayer_shot(visible_state, legal_context, action_type)
        if decision is None:
            cached_draft = str(ctx.get("cached_speech_draft") or "").strip()
            draft_decision = agent._draft_reuse_decision(
                visible_state,
                action_type,
                cached_draft,
                refinement_mode=bool(ctx.get("llm_kwargs", {}).get("refinement_mode")),
            )
            if draft_decision is not None:
                decision = draft_decision
        if decision is None:
            # P1-3：recall 注入的观点摘要合并进 LLM kwargs（strategic_thought）
            llm_kwargs = dict(ctx.get("llm_kwargs", {}))
            summary_thought = str(ctx.get("strategic_thought") or "").strip()
            if summary_thought:
                llm_kwargs["strategic_thought"] = (
                    f"{llm_kwargs.get('strategic_thought', '')}\n{summary_thought}".strip()
                )
            decision = await agent._decide_via_llm(
                visible_state, legal_context, action_type, **llm_kwargs
            )

        ctx["decision"] = decision if decision is not None else {}
        return {"action_type": action_type, "decision": ctx["decision"]}

    async def _validate(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        """合法性校验：decision 必须含 action 字段；非法回退 fallback（防工作流产出无效决策）。"""
        visible_state = ctx["visible_state"]
        legal_context = ctx["legal_context"]
        decision = ctx.get("decision") or {}
        if not isinstance(decision, dict) or not decision.get("action"):
            fallback = agent._fallback_decision(
                visible_state,
                legal_context,
                action_type,
                reason="workflow_invalid_decision",
            )
            ctx["decision"] = fallback
            return {"validated": False, "fallback_reason": "workflow_invalid_decision"}
        return {"validated": True}

    async def _record(ctx: dict[str, Any], **kwargs: dict) -> dict[str, Any]:
        """决策结果回写观点库（观点演化闭环，T4）+ 返回记录状态。"""
        decision = ctx.get("decision") or {}
        recorded = False
        store = agent.get_viewpoint_store() if hasattr(agent, "get_viewpoint_store") else None
        if store is not None:
            recorded = _feedback_decision_to_viewpoints(
                agent,
                store,
                decision,
                int(ctx.get("day_number", 1)),
                int(ctx.get("round_number", 1)),
                visible_state=ctx.get("visible_state"),
            )
        return {"recorded": recorded, "action": decision.get("action")}

    nodes = [
        ToolCallNode(node_id="recall", tool_name="recall", handler=_recall),
        ToolCallNode(node_id="decide", tool_name="decide", handler=_decide),
        ToolCallNode(node_id="validate", tool_name="validate", handler=_validate),
        ToolCallNode(node_id="record", tool_name="record", handler=_record),
    ]
    return Workflow(
        workflow_id=workflow_id,
        nodes=nodes,
        entry_node_id="recall",
        next_node_map={"recall": "decide", "decide": "validate", "validate": "record"},
    )


def _extract_candidate_players(reasoning: str, visible_state) -> list[tuple[str, str]]:
    """从 reasoning 提取被提及的玩家，返回 (player_id, display_name)。

    - display_name 用大写 player_id（"p2"→"P2"），与观点库既有约定
      （Viewpoint.subject_name 用 player_id 风格）一致；
    - 匹配源为**真实玩家名单**（P2-6：不再硬编码 P1-P10，支持任意
      player_count 与命名风格）；
    - 无 visible_state 时回退 player_id 正则。
    """
    import re

    pairs: list[tuple[str, str]] = []
    players = getattr(visible_state, "players", ()) or ()
    for player in players:
        pid = str(getattr(player, "player_id", "") or "")
        pname = str(getattr(player, "name", "") or "")
        # pid 用词边界精确匹配（防 "p1" 误匹配 "p10"），name 用完整子串匹配
        pid_hit = bool(
            pid and re.search(rf"(?i)(?<![a-z0-9]){re.escape(pid)}(?![a-z0-9])", reasoning)
        )
        name_hit = bool(pname and pname in reasoning)
        if pid_hit or name_hit:
            pairs.append((pid, pid.upper()))
    if pairs:
        return pairs
    for match in re.findall(r"[Pp](\d+)", reasoning):
        pairs.append((f"p{match}", f"P{match}"))
    return pairs


def _feedback_decision_to_viewpoints(
    agent, store, decision: dict[str, Any], day_number: int, round_number: int, visible_state=None
) -> bool:
    """把决策结果作为新证据回写观点库（观点演化闭环）。

    - 有激活观点：仅对 `vp.subject_name in candidates` 的观点按 subject 匹配
      更新（P1-4：证据不跨主题盲目注入，同一 reasoning 单条证据）；
    - 无激活观点：为**每个**候选创建软印象观点（P2-7：多候选不丢弃；
      不 gate 故不注入发言，仅作演化起点）；
    - reasoning 无可提取玩家时跳过（不产生噪音观点）。
    """
    from src.agents.reasoning.viewpoint import Evidence
    from src.agents.reasoning.viewpoint_engine import ViewpointEngine, compute_confidence

    reasoning = str(decision.get("reasoning") or "")
    if not reasoning:
        return False
    candidates = _extract_candidate_players(reasoning, visible_state)
    if not candidates:
        return False
    candidate_names = {name for _, name in candidates}
    engine = ViewpointEngine()
    active = store.get_active_viewpoints()
    updated_any = False
    if active:
        for vp in active:
            if vp.subject_name not in candidate_names:
                continue  # P1-4：证据按 subject 匹配，不跨主题注入
            new_evidence = [
                Evidence(kind="soft", source="decision_feedback", detail=reasoning[:120])
            ]
            _, action = engine.update_with_new_evidence(vp, new_evidence)
            if action == "updated":
                store.update_confidence(vp.viewpoint_id, vp.confidence)
                updated_any = True
            elif action == "superseded":
                store.supersede(vp.viewpoint_id)
                updated_any = True
        return updated_any
    # 无激活观点：为每个候选创建软印象观点（演化起点，不 gate）
    existing_names = {vp.subject_name for vp in store._viewpoints}
    for pid, name in candidates:
        if name in existing_names:
            continue  # 已有观点（含 superseded），不重复创建
        evidence = [Evidence(kind="soft", source="decision_feedback", detail=reasoning[:120])]
        store.add_viewpoint(
            subject_player_id=pid,
            subject_name=name,
            claim=f"{name} 可疑",
            evidence=evidence,
            confidence=compute_confidence(0, len(evidence)),
            source_action="decision_feedback",
            day_number=day_number,
            round_number=round_number,
        )
        updated_any = True
    return updated_any


async def run_action_workflow(
    agent, visible_state, legal_context, action_type: str, **kwargs
) -> dict[str, Any]:
    """执行『动作决策』工作流，返回与 act() 同构的 decision dict。

    - 返回 {"action": ..., ...}（与 act() 一致）；
    - 额外附带 trace_path（工作流轨迹落盘，可回放）。
    """
    workflow = build_action_workflow(agent, action_type)
    player_id = agent.player_id
    game_id = str(getattr(visible_state, "game_id", "") or "")
    trace_dir = _data_dir() / "agents" / player_id / "games" / game_id
    trace = WorkflowTrace(trace_dir)
    engine = WorkflowEngine(workflow, trace=trace)

    ctx: dict[str, Any] = {
        "visible_state": visible_state,
        "legal_context": legal_context,
        "day_number": int(getattr(visible_state, "day_number", 1) or 1),
        "round_number": int(getattr(visible_state, "round_number", 1) or 1),
        "cached_speech_draft": str(kwargs.get("cached_speech_draft") or "").strip(),
        "llm_kwargs": dict(kwargs),
    }
    await engine.execute(ctx)
    trace_path = trace.save()
    decision = dict(ctx.get("decision") or {})
    if trace_path is not None:
        decision["workflow_trace_path"] = str(trace_path)
    return decision
