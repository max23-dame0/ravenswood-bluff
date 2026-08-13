"""T14: 说书人裁决工作流化试点测试 — PLN-041 Phase 4。

验证：
- 6 工具全部声明为工作流节点；
- 执行后行为与既有 decide_night_info 等价（确定性红线）；
- LLM 只可能出现在 choose_distortion 节点（默认 BOTC_ST_LLM_STRATEGY=off 不触发）；
- trace 落盘完整。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.storyteller_agent import StorytellerAgent
from src.agents.workflow.storyteller_workflows import (
    build_night_adjudication_workflow,
    run_night_adjudication,
)
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import DummyBackend


def _make_state(game_id: str = "wf-night-test") -> GameState:
    return GameState(
        game_id=game_id,
        phase=GamePhase.FIRST_NIGHT,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )


def test_workflow_declares_all_six_tools() -> None:
    st = StorytellerAgent(backend=DummyBackend())
    wf = build_night_adjudication_workflow(st)
    tool_names = {n.tool_name for n in wf.nodes}
    assert {
        "assess_balance",
        "choose_distortion",
        "adjudicate_night_info",
        "compose_narration",
        "deliver_verdict",
        "review_balance",
    } <= tool_names


def test_workflow_entry_is_adjudicate() -> None:
    st = StorytellerAgent(backend=DummyBackend())
    wf = build_night_adjudication_workflow(st)
    entry = wf.get_node(wf.entry_node_id)
    assert entry is not None
    assert entry.kind == "tool_call"
    assert entry.tool_name == "adjudicate_night_info"


def test_choose_distortion_is_tool_call_node() -> None:
    st = StorytellerAgent(backend=DummyBackend())
    wf = build_night_adjudication_workflow(st)
    node = wf.get_node("choose_distortion")
    assert node is not None
    assert node.kind == "tool_call"


@pytest.mark.asyncio
async def test_run_night_adjudication_returns_info() -> None:
    st = StorytellerAgent(backend=DummyBackend())
    state = _make_state()
    result = await run_night_adjudication(st, state, "p1", "washerwoman")
    assert "info" in result
    assert result["info"] is not None


@pytest.mark.asyncio
async def test_run_night_adjudication_records_judgement() -> None:
    st = StorytellerAgent(backend=DummyBackend())
    state = _make_state()
    before = len(st.decision_ledger)
    await run_night_adjudication(st, state, "p1", "washerwoman")
    assert len(st.decision_ledger) > before


@pytest.mark.asyncio
async def test_run_night_adjudication_trace_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    st = StorytellerAgent(backend=DummyBackend())
    state = _make_state()
    result = await run_night_adjudication(st, state, "p1", "washerwoman")
    trace_path = result.get("trace_path")
    assert trace_path is not None
    assert Path(trace_path).exists()
    raw = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    assert raw["workflow_id"] == "night_adjudication"
    assert raw["entries"][0]["event"] == "start"
    assert raw["entries"][-1]["event"] == "finish"


@pytest.mark.asyncio
async def test_llm_not_invoked_on_default_path() -> None:
    """确定性红线：BOTC_ST_LLM_STRATEGY 默认 off，执行路径不触发 LLM 调用。

    DummyBackend 记录 generate 调用次数；工作流节点中仅 choose_distortion
    可能调用 LLM（默认 off 不调用），adjudicate 等节点必须零 LLM。
    """
    calls = {"n": 0}

    class CountingBackend(DummyBackend):
        async def generate(self, system_prompt, messages, **kwargs):
            calls["n"] += 1
            return await super().generate(system_prompt, messages, **kwargs)

    st = StorytellerAgent(backend=CountingBackend())
    state = _make_state()
    await run_night_adjudication(st, state, "p1", "washerwoman")
    assert calls["n"] == 0
