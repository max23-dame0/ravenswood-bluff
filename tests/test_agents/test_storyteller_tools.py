"""说书人工具注册表测试（PLN-038 阶段 S）。

覆盖：6 工具可调、choose_distortion 枚举化且行为兼容、
BOTC_ST_LLM_STRATEGY=off 时与重构前一致、review_balance 落盘。
"""

from __future__ import annotations

import pytest

from src.agents.storyteller_agent import StorytellerAgent
from src.agents.storyteller_tools import DistortionStrategy, StorytellerToolRegistry
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import DummyBackend


def _storyteller() -> StorytellerAgent:
    return StorytellerAgent(backend=DummyBackend(content="{}"), mode="auto")


def _game_state() -> GameState:
    return GameState(
        game_id="fixed-st-game",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p3", name="Charlie", role_id="chef", team=Team.GOOD),
        ),
    )


def test_tool_names_expose_six_tools():
    st = _storyteller()
    assert set(st.tool_names) == {
        "assess_balance",
        "choose_distortion",
        "adjudicate_night_info",
        "compose_narration",
        "deliver_verdict",
        "review_balance",
    }


def test_distortion_strategy_enum_coerce_preserves_values():
    # 枚举值与旧字符串完全一致（保证审计与测试兼容）
    assert DistortionStrategy.coerce("none") is DistortionStrategy.NONE
    assert (
        DistortionStrategy.coerce("empath_binary_flip.default").value
        == "empath_binary_flip.default"
    )
    assert DistortionStrategy.coerce("unknown_strategy") is DistortionStrategy.NONE
    assert DistortionStrategy.coerce(None) is DistortionStrategy.NONE


def test_invoke_assess_balance():
    st = _storyteller()
    game = _game_state()
    context = _build_context(st, game)
    result = asyncio_run(st.invoke_tool("assess_balance", context=context))
    assert result["tool"] == "assess_balance"
    assert "score" in result


def test_invoke_deliver_verdict():
    st = _storyteller()
    result = asyncio_run(
        st.invoke_tool("deliver_verdict", category="night_info", decision="distort", reason="平衡")
    )
    assert result["tool"] == "deliver_verdict"
    assert result["verdict"]["category"] == "night_info"


def test_choose_distortion_off_matches_legacy_behavior(monkeypatch):
    # BOTC_ST_LLM_STRATEGY=off（默认）：choose_distortion 走纯启发式，distortion 字符串不变
    monkeypatch.setenv("BOTC_ST_LLM_STRATEGY", "off")
    st = _storyteller()
    game = _game_state()
    context = _build_context(st, game)
    info = {"chef_pairs": 1}
    distorted, strategy = StorytellerToolRegistry.choose_distortion(st, context, "chef", info, "p1")
    assert strategy.value in {
        "chef_pairs_offset.help_evil",
        "chef_pairs_passthrough",
    }


def test_choose_distortion_async_defaults_to_heuristic(monkeypatch):
    # 无 LLM backend 介入时（BOTC_ST_LLM_STRATEGY=off）仍启发式兜底
    monkeypatch.setenv("BOTC_ST_LLM_STRATEGY", "off")
    st = _storyteller()
    game = _game_state()
    context = _build_context(st, game)
    distorted, strategy = asyncio_run(
        StorytellerToolRegistry.choose_distortion_async(
            st, context, "chef", {"chef_pairs": 0}, "p1"
        )
    )
    assert isinstance(strategy, DistortionStrategy)
    assert "chef_pairs" in strategy.value


def test_review_balance_and_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    st = _storyteller()
    # 先记录一些判决
    st.record_judgement(
        "night_info", "distort", "平衡", distortion_strategy="chef_pairs_offset.help_evil"
    )
    st.record_judgement("execution", "normal", "正常")
    result = asyncio_run(st.invoke_tool("review_balance", game_id="fixed-st-game"))
    assert result["tool"] == "review_balance"
    assert result["review"]["game_id"] == "fixed-st-game"
    assert result["review"]["distortion_entries"]
    assert result["archive_path"]
    import pathlib

    assert pathlib.Path(result["archive_path"]).exists()


def test_invoke_unknown_tool_raises():
    st = _storyteller()
    with pytest.raises(KeyError):
        asyncio_run(st.invoke_tool("nope"))


def test_adjudicate_night_info_invoke(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    st = StorytellerAgent(backend=DummyBackend(content="{}"), mode="mock")
    game = _game_state()
    result = asyncio_run(
        st.invoke_tool("adjudicate_night_info", game_state=game, player_id="p1", role_id="chef")
    )
    assert result["tool"] == "adjudicate_night_info"


def _build_context(st, game):
    return st.build_decision_context(game)


def asyncio_run(coro):
    import asyncio

    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
