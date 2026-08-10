"""speech_sanitizer 机械开场词剥离测试（PLN-040 发言拟人化）。

覆盖：
- 高频固定口头应答开场（"行，""我先说个结论吧""我先说句心里话"）被剥离
- 保留实质内容、不破坏句子主体
- 非机械开场（正常发言）保持不变
- 剩余内容过短时不裁剪（避免过度处理）
- sanitize_public_speech_content 入口也应用剥离
"""

from __future__ import annotations

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from src.agents.speech.speech_sanitizer import SpeechSanitizer
from tests.doubles import CapturingBackend


def _make_sanitizer(tmp_path, monkeypatch) -> tuple[SpeechSanitizer, AIAgent]:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = AIAgent(
        player_id="p1",
        name="AgentP1",
        backend=CapturingBackend(content="{}"),
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-sanitizer")
    return agent._speech_sanitizer, agent


# ---------------------------------------------------------------------------
# _strip_mechanical_opener
# ---------------------------------------------------------------------------


def test_strip_leading_xing(tmp_path, monkeypatch):
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    out = sanitizer._strip_mechanical_opener("行，第一天嘛大家先别藏着掖着。")
    assert out == "第一天嘛大家先别藏着掖着。"


def test_strip_leading_wo_xian_shuo(tmp_path, monkeypatch):
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    assert (
        sanitizer._strip_mechanical_opener("我先说个结论吧，P1 说自己是厨师。")
        == "P1 说自己是厨师。"
    )
    assert (
        sanitizer._strip_mechanical_opener("我先说句心里话，我有点慌。")
        == "我有点慌。"
    )


def test_strip_xing_ba(tmp_path, monkeypatch):
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    assert sanitizer._strip_mechanical_opener("行吧，我先表态。") == "我先表态。"


def test_keeps_normal_speech(tmp_path, monkeypatch):
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    text = "昨晚我看了一下，P3 的说法对不上。"
    assert sanitizer._strip_mechanical_opener(text) == text


def test_keeps_short_remainder(tmp_path, monkeypatch):
    """剥离后剩余过短（<4 字）时保留原文，避免过度裁剪。"""
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    text = "行，好的。"
    assert sanitizer._strip_mechanical_opener(text) == text


def test_not_matching_word_inside(tmp_path, monkeypatch):
    """'行，' 只剥离句首，不误伤句中。"""
    sanitizer, _ = _make_sanitizer(tmp_path, monkeypatch)
    text = "我觉得这个行，大家怎么看？"
    assert sanitizer._strip_mechanical_opener(text) == text


# ---------------------------------------------------------------------------
# sanitize_public_speech_content 应用剥离
# ---------------------------------------------------------------------------


def test_sanitize_applies_opener_strip(tmp_path, monkeypatch):
    sanitizer, agent = _make_sanitizer(tmp_path, monkeypatch)
    from src.state.game_state import GamePhase, GameState, PlayerState, Team

    state = GameState(
        game_id="game-sanitizer",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(PlayerState(player_id="p1", name="A", role_id="washerwoman", team=Team.GOOD),),
    )
    agent.synchronize_role(state.get_player("p1"))
    visible = agent._build_visible_state(state)
    out = sanitizer.sanitize_public_speech_content("行，先听大家说。", visible)
    assert out == "先听大家说。"
