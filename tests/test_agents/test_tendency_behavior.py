"""tendency 行为标签映射测试（PLN-040 T3）。

覆盖：
- tendency_behavior_overrides：四维 → risk_tolerance/social_style/assertiveness 标签
- refresh_persona_profile 应用 overrides（决策引擎消费的标签被覆盖）
- build_evolved_tendency_summary 连续画像文案（差异化描述）
- BOTC_TENDENCY_STEP 标定步长覆盖
"""

from __future__ import annotations

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from tests.doubles import CapturingBackend


def _make_agent(tmp_path, monkeypatch, player_id: str = "p1") -> AIAgent:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id=player_id,
        name=f"Agent{player_id}",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-T3")
    return agent


def _set_tendency(agent: AIAgent, **values: float) -> None:
    profile = agent._player_profile.load_profile()
    profile["tendency"].update(values)
    agent._player_profile.save_profile()


# ---------------------------------------------------------------------------
# tendency_behavior_overrides
# ---------------------------------------------------------------------------


def test_high_aggression_maps_to_aggressive_labels(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.8, risk_taking=0.5, talkativeness=0.5, caution=0.3)
    overrides = agent.tendency_behavior_overrides()
    assert overrides["risk_tolerance"] == "激进"
    assert overrides["social_style"] == "带节奏"
    assert overrides["assertiveness"] == "强势"


def test_high_caution_maps_to_conservative_labels(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.3, risk_taking=0.3, talkativeness=0.4, caution=0.9)
    overrides = agent.tendency_behavior_overrides()
    assert overrides["risk_tolerance"] == "保守"
    assert overrides["assertiveness"] == "温和"


def test_low_talkativeness_maps_to_follower(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.4, risk_taking=0.5, talkativeness=0.2, caution=0.5)
    overrides = agent.tendency_behavior_overrides()
    assert overrides["social_style"] == "从众"


def test_balanced_tendency_maps_neutral(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.5, risk_taking=0.5, talkativeness=0.5, caution=0.5)
    overrides = agent.tendency_behavior_overrides()
    # 中性区间不覆盖，保留原有 _pick_stable/archetype 结果
    assert overrides == {}


def test_default_tendency_no_overrides(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    overrides = agent.tendency_behavior_overrides()
    assert overrides == {}


def test_near_neutral_tendency_no_overrides(tmp_path, monkeypatch):
    """轻微偏离中性（如 0.58）不触发覆盖，避免对默认行为造成扰动。"""
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.58, risk_taking=0.58, talkativeness=0.58, caution=0.58)
    overrides = agent.tendency_behavior_overrides()
    assert overrides == {}


# ---------------------------------------------------------------------------
# refresh_persona_profile 应用 overrides
# ---------------------------------------------------------------------------


def test_persona_profile_applies_tendency(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.8, risk_taking=0.6, talkativeness=0.7, caution=0.3)
    from src.state.game_state import GamePhase, GameState, PlayerState, Team

    state = GameState(
        game_id="game-T3",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(PlayerState(player_id="p1", name="A", role_id="washerwoman", team=Team.GOOD),),
    )
    agent.synchronize_role(state.get_player("p1"))
    profile = agent.persona_profile or {}
    assert profile["risk_tolerance"] == "激进"
    assert profile["social_style"] == "带节奏"
    assert profile["assertiveness"] == "强势"


def test_persona_profile_conservative(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.2, risk_taking=0.2, talkativeness=0.3, caution=0.9)
    from src.state.game_state import GamePhase, GameState, PlayerState, Team

    state = GameState(
        game_id="game-T3",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(PlayerState(player_id="p1", name="A", role_id="washerwoman", team=Team.GOOD),),
    )
    agent.synchronize_role(state.get_player("p1"))
    profile = agent.persona_profile or {}
    assert profile["risk_tolerance"] == "保守"
    assert profile["assertiveness"] == "温和"


# ---------------------------------------------------------------------------
# build_evolved_tendency_summary 连续画像
# ---------------------------------------------------------------------------


def test_tendency_summary_continuous_text(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    _set_tendency(agent, aggression=0.8, risk_taking=0.3, talkativeness=0.7, caution=0.5)
    text = agent.build_evolved_tendency()
    assert "攻击性偏强" in text
    assert "冒险度偏弱" in text
    assert "健谈度偏强" in text
    assert "你的打法倾向" in text


def test_tendency_summary_differentiates_players(tmp_path, monkeypatch):
    agent_a = _make_agent(tmp_path, monkeypatch, "p1")
    _set_tendency(agent_a, aggression=0.9, risk_taking=0.9, talkativeness=0.9, caution=0.1)
    text_a = agent_a.build_evolved_tendency()
    assert "攻击性偏强" in text_a

    # 重置倾向为保守，摘要应显著不同
    agent_b = _make_agent(tmp_path, monkeypatch, "p2")
    _set_tendency(agent_b, aggression=0.1, risk_taking=0.1, talkativeness=0.1, caution=0.9)
    text_b = agent_b.build_evolved_tendency()
    assert text_a != text_b
    assert "攻击性偏弱" in text_b
    assert "谨慎度偏强" in text_b


# ---------------------------------------------------------------------------
# BOTC_TENDENCY_STEP 标定步长
# ---------------------------------------------------------------------------


def test_tendency_step_env_scales_delta(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_TENDENCY_STEP", "0.10")
    agent = _make_agent(tmp_path, monkeypatch)
    delta = agent._derive_tendency_delta(won=True, team="good")
    assert delta["talkativeness"] >= 0.09  # 默认 0.02 * (0.10/0.02) = 0.10 ± 扰动


def test_tendency_step_default_is_002(tmp_path, monkeypatch):
    monkeypatch.delenv("BOTC_TENDENCY_STEP", raising=False)
    agent = _make_agent(tmp_path, monkeypatch)
    delta = agent._derive_tendency_delta(won=True, team="good")
    assert delta["talkativeness"] < 0.03
