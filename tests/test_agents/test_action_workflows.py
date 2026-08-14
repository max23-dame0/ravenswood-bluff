"""T2/T3/T4: 全动作声明式工作流测试 — PLN-043。

覆盖：
- 开关（BOTC_WORKFLOW_ACTIONS 默认 off）；
- 动作工作流节点声明（recall/decide/validate/record）；
- 各动作类型执行（vote 本地启发式 / speak 草稿复用 / nominate LLM / slayer 本地）；
- validate 非法决策回退 fallback；
- 观点回写（决策 → 观点演化闭环）；
- trace 落盘；开关关闭时 act() 原路径零差异。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from src.agents.workflow.action_workflows import (
    ACTION_WORKFLOW_IDS,
    build_action_workflow,
    run_action_workflow,
    workflow_actions_enabled,
)
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import DummyBackend

_SPEECH_JSON = '{"action":"speak","content":"我怀疑 P2 有问题","reasoning":"基于线索"}'
_VOTE_JSON = '{"action":"vote","decision":true,"reasoning":"本地投票"}'
_NOMINATE_JSON = '{"action":"nominate","target":"p2","reasoning":"提名 P2"}'


def _make_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str = _SPEECH_JSON
) -> AIAgent:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    return AIAgent(
        player_id="p1",
        name="Alice",
        backend=DummyBackend(content=content),
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )


def _make_state(game_id: str = "game-wf", phase: GamePhase = GamePhase.DAY_DISCUSSION) -> GameState:
    return GameState(
        game_id=game_id,
        phase=phase,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )


# ---------------------------------------------------------------------------
# 开关
# ---------------------------------------------------------------------------


def test_workflow_switch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOTC_WORKFLOW_ACTIONS", raising=False)
    assert not workflow_actions_enabled()


def test_workflow_switch_forced_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    assert workflow_actions_enabled()


def test_all_action_types_have_workflow_ids() -> None:
    for action in (
        "speak",
        "defense_speech",
        "vote",
        "nomination_intent",
        "nominate",
        "night_action",
        "death_trigger",
        "slayer_shot",
    ):
        assert action in ACTION_WORKFLOW_IDS


# ---------------------------------------------------------------------------
# 工作流声明
# ---------------------------------------------------------------------------


def test_workflow_declares_four_nodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # P1-5 修复：用 pytest 的 tmp_path/monkeypatch fixture（自动撤销，不污染环境），
    # 禁止用 Path(".") 或独立 MonkeyPatch 实例（会向仓库根落盘测试产物）。
    agent = _make_agent(tmp_path, monkeypatch)
    wf = build_action_workflow(agent, "vote")
    tool_names = {n.tool_name for n in wf.nodes}
    assert {"recall", "decide", "validate", "record"} <= tool_names
    assert wf.entry_node_id == "recall"


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vote_workflow_returns_local_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = _make_agent(tmp_path, monkeypatch, content=_VOTE_JSON)
    agent.set_game_context("game-wf")
    monkeypatch.setenv("AI_FAST_LOW_VALUE_ACTIONS", "1")
    state = _make_state(
        phase=GamePhase.NOMINATION,
    )
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        current_nominee="p2",
        current_nominator="p1",
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(agent, visible, lc, "vote")
    assert decision["action"] == "vote"
    assert "decision" in decision


@pytest.mark.asyncio
async def test_speak_workflow_draft_reuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(
        agent, visible, lc, "speak", cached_speech_draft="我怀疑 P2 有问题。"
    )
    assert decision["action"] == "speak"
    assert decision["speech_source"] == "cache_finalized_draft_reuse"


@pytest.mark.asyncio
async def test_refinement_mode_skips_draft_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-1 回归：refinement_mode=True 时不草稿复用，走 LLM 精炼路径。"""
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(
        agent,
        visible,
        lc,
        "speak",
        cached_speech_draft="我怀疑 P2 有问题。",
        refinement_mode=True,
    )
    assert decision["action"] == "speak"
    # 不走草稿复用（refinement_mode=True 语义：基于最新局势精炼）
    assert decision.get("speech_source") != "cache_finalized_draft_reuse"


@pytest.mark.asyncio
async def test_act_refinement_mode_skips_draft_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-1 回归（默认路径）：act() refinement_mode=True + cached_speech_draft 走 LLM。"""
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    decision = await agent.act(
        visible, "speak", cached_speech_draft="我怀疑 P2 有问题。", refinement_mode=True
    )
    assert decision["action"] == "speak"
    assert decision.get("speech_source") != "cache_finalized_draft_reuse"


@pytest.mark.asyncio
async def test_nominate_workflow_via_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch, content=_NOMINATE_JSON)
    agent.set_game_context("game-wf")
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(agent, visible, lc, "nominate")
    assert decision["action"] == "nominate"
    assert decision["target"] == "p2"


@pytest.mark.asyncio
async def test_validate_catches_invalid_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """decide 产出非法决策（无 action 字段）时 validate 回退 fallback。"""

    async def _bad_llm(visible_state, legal_context, action_type, **kwargs):
        return {"foo": "bar"}  # 无 action 字段

    agent = _make_agent(tmp_path, monkeypatch, content=_SPEECH_JSON)
    agent.set_game_context("game-wf")
    monkeypatch.setattr(agent, "_decide_via_llm", _bad_llm)
    state = _make_state()
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(agent, visible, lc, "speak")
    assert decision["action"]  # fallback 决策必含合法 action
    assert "workflow_invalid_decision" in str(decision.get("reasoning", ""))


@pytest.mark.asyncio
async def test_workflow_trace_persists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch, content=_SPEECH_JSON)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(agent, visible, lc, "speak")
    trace_path = decision.get("workflow_trace_path")
    assert trace_path is not None
    assert Path(trace_path).exists()
    raw = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    assert raw["workflow_id"] == "action_speak"
    events = [e["event"] for e in raw["entries"]]
    assert events[0] == "start" and events[-1] == "finish"
    node_ids = {e["node_id"] for e in raw["entries"] if e["event"] == "node"}
    assert {"recall", "decide", "validate", "record"} <= node_ids


@pytest.mark.asyncio
async def test_slayer_workflow_local(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """slayer_shot 动作：decide 节点走本地判定（无 LLM）。"""
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    lc = agent._build_legal_action_context(state, visible)
    decision = await run_action_workflow(agent, visible, lc, "slayer_shot")
    # 无猎手角色时不触发 → 返回空决策（工作流失败语义由调用方处理）
    assert isinstance(decision, dict)


# ---------------------------------------------------------------------------
# act() 路由（T3）：开关关闭零差异 / 开关开启走工作流
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_act_route_off_uses_original_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关关闭：act() 走原路径（无 workflow_trace_path 字段）。"""
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    decision = await agent.act(visible, "speak", cached_speech_draft="我怀疑 P2 有问题。")
    assert decision["action"] == "speak"
    assert "workflow_trace_path" not in decision


@pytest.mark.asyncio
async def test_act_route_on_uses_workflow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """开关开启：act() 路由到工作流并产出 workflow_trace_path。"""
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    agent = _make_agent(tmp_path, monkeypatch)
    agent.set_game_context("game-wf")
    state = _make_state()
    visible = agent._build_visible_state(state)
    decision = await agent.act(visible, "speak", cached_speech_draft="我怀疑 P2 有问题。")
    assert decision["action"] == "speak"
    assert decision["workflow_trace_path"]


# ---------------------------------------------------------------------------
# 观点回写（T4）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_feedback_updates_viewpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """决策 reasoning 含玩家名时回写观点库（观点演化闭环）。"""
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _make_agent(
        tmp_path,
        monkeypatch,
        content='{"action":"vote","decision":true,"reasoning":"P2 很可疑，投票处决"}',
    )
    agent.set_game_context("game-wf")
    # 预置一个激活观点（subject 与决策 reasoning 中的 "P2" 对应）
    store = agent.get_viewpoint_store()
    assert store is not None
    from src.agents.reasoning.viewpoint import Evidence

    store.add_viewpoint(
        subject_player_id="p2",
        subject_name="P2",
        claim="P2 可能是恶魔",
        evidence=[Evidence(kind="hard", source="hard_memory", detail="高可信信息：P2 可能是恶魔")],
        confidence=0.52,
        source_action="speak",
        day_number=1,
        round_number=1,
    )
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        current_nominee="p2",
        current_nominator="p1",
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    await agent.act(visible, "vote")
    # 观点被回写（vote 决策 reasoning 含 "P2" → 置信度更新，存储 ≥2 条记录）
    lines = [
        line for line in store.path.read_text(encoding="utf-8").strip().splitlines() if line.strip()
    ]
    assert len(lines) >= 2
    latest = json.loads(lines[-1])
    assert latest["confidence"] > 0.52 or latest["status"] == "superseded"


@pytest.mark.asyncio
async def test_record_creates_viewpoint_from_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无激活观点时，决策 reasoning 含玩家名 → record 创建软印象观点（演化起点）。"""
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _make_agent(
        tmp_path,
        monkeypatch,
        content='{"action":"vote","decision":true,"reasoning":"P3 也很可疑，考虑后续处决"}',
    )
    agent.set_game_context("game-wf")
    store = agent.get_viewpoint_store()
    assert store is not None
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        current_nominee="p2",
        current_nominator="p1",
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p3", name="Cathy", role_id="empath", team=Team.GOOD),
        ),
    )
    visible = agent._build_visible_state(state)
    await agent.act(visible, "vote")
    lines = [
        line for line in store.path.read_text(encoding="utf-8").strip().splitlines() if line.strip()
    ]
    assert len(lines) >= 1
    created = json.loads(lines[0])
    assert created["subject_name"] == "P3"
    assert created["claim"] == "P3 可疑"
    assert created["evidence"][0]["source"] == "decision_feedback"


@pytest.mark.asyncio
async def test_feedback_does_not_update_unmatched_viewpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-4 回归：决策 reasoning 只提 P2，subject 为 P3 的观点不得被更新。"""
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _make_agent(
        tmp_path,
        monkeypatch,
        content='{"action":"vote","decision":true,"reasoning":"P2 很可疑，投票处决"}',
    )
    agent.set_game_context("game-wf")
    store = agent.get_viewpoint_store()
    assert store is not None
    from src.agents.reasoning.viewpoint import Evidence

    store.add_viewpoint(
        subject_player_id="p3",
        subject_name="P3",
        claim="P3 可能是恶魔",
        evidence=[Evidence(kind="hard", source="hard_memory", detail="高可信信息：P3 可能是恶魔")],
        confidence=0.52,
        source_action="speak",
        day_number=1,
        round_number=1,
    )
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        current_nominee="p2",
        current_nominator="p1",
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p3", name="Cathy", role_id="empath", team=Team.GOOD),
        ),
    )
    visible = agent._build_visible_state(state)
    await agent.act(visible, "vote")
    # P3 观点不被 P2 的决策证据更新（仅 1 条记录 = 初始预置）
    lines = [
        line for line in store.path.read_text(encoding="utf-8").strip().splitlines() if line.strip()
    ]
    p3_lines = [line for line in lines if '"subject_name": "P3"' in line]
    assert len(p3_lines) == 1
    assert json.loads(p3_lines[0])["confidence"] == 0.52


@pytest.mark.asyncio
async def test_feedback_creates_viewpoints_for_all_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P2-7 回归：决策 reasoning 提多名玩家时，为每个候选都创建观点。"""
    monkeypatch.setenv("BOTC_WORKFLOW_ACTIONS", "1")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _make_agent(
        tmp_path,
        monkeypatch,
        content='{"action":"vote","decision":true,"reasoning":"P2 和 P3 都很可疑"}',
    )
    agent.set_game_context("game-wf")
    store = agent.get_viewpoint_store()
    assert store is not None
    state = GameState(
        game_id="game-wf",
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        current_nominee="p2",
        current_nominator="p1",
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p3", name="Cathy", role_id="empath", team=Team.GOOD),
        ),
    )
    visible = agent._build_visible_state(state)
    await agent.act(visible, "vote")
    lines = [
        line for line in store.path.read_text(encoding="utf-8").strip().splitlines() if line.strip()
    ]
    names = {json.loads(line)["subject_name"] for line in lines}
    assert {"P2", "P3"} <= names
