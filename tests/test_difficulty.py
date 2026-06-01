"""Unit tests for the difficulty system."""

from __future__ import annotations

import pytest

from src.agents.ai_agent import AIAgent, DeceptionTracker, Persona
from src.agents.difficulty_presets import (
    PRESETS,
    DifficultyPreset,
    get_preset,
)
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.state.game_state import DifficultyLevel, GameConfig, Team


# ============================================================
# DifficultyLevel enum
# ============================================================


class TestDifficultyLevelEnum:
    def test_has_all_four_values(self):
        assert DifficultyLevel.CASUAL.value == "casual"
        assert DifficultyLevel.STANDARD.value == "standard"
        assert DifficultyLevel.MASTER.value == "master"
        assert DifficultyLevel.CHAOS.value == "chaos"

    def test_string_conversion(self):
        assert str(DifficultyLevel.CASUAL) == "DifficultyLevel.CASUAL"
        assert DifficultyLevel("casual") is DifficultyLevel.CASUAL
        assert DifficultyLevel("standard") is DifficultyLevel.STANDARD
        assert DifficultyLevel("master") is DifficultyLevel.MASTER
        assert DifficultyLevel("chaos") is DifficultyLevel.CHAOS

    def test_is_str_subclass(self):
        assert isinstance(DifficultyLevel.CASUAL, str)
        assert DifficultyLevel.CASUAL == "casual"


# ============================================================
# GameConfig default difficulty
# ============================================================


class TestGameConfigDefaultDifficulty:
    def test_default_is_standard(self):
        config = GameConfig(player_count=5)
        assert config.difficulty == DifficultyLevel.STANDARD

    def test_accepts_explicit_difficulty(self):
        config = GameConfig(player_count=5, difficulty=DifficultyLevel.MASTER)
        assert config.difficulty == DifficultyLevel.MASTER

    def test_accepts_all_difficulty_values(self):
        for level in DifficultyLevel:
            config = GameConfig(player_count=5, difficulty=level)
            assert config.difficulty == level


# ============================================================
# get_preset()
# ============================================================


class TestGetPreset:
    def test_returns_casual_preset(self):
        preset = get_preset("casual")
        assert isinstance(preset, DifficultyPreset)
        assert preset.name == "休闲"

    def test_returns_standard_preset(self):
        preset = get_preset("standard")
        assert isinstance(preset, DifficultyPreset)
        assert preset.name == "标准"

    def test_returns_master_preset(self):
        preset = get_preset("master")
        assert isinstance(preset, DifficultyPreset)
        assert preset.name == "大师"

    def test_returns_chaos_preset(self):
        preset = get_preset("chaos")
        assert isinstance(preset, DifficultyPreset)
        assert preset.name == "混沌"

    def test_defaults_to_standard_for_unknown(self):
        preset = get_preset("nonexistent")
        standard = get_preset("standard")
        assert preset is standard

    def test_defaults_to_standard_for_empty_string(self):
        preset = get_preset("")
        standard = get_preset("standard")
        assert preset is standard


# ============================================================
# DifficultyPreset structure
# ============================================================


class TestDifficultyPresetStructure:
    def test_preset_has_required_fields(self):
        for key in ("casual", "standard", "master", "chaos"):
            preset = PRESETS[key]
            assert hasattr(preset, "name")
            assert hasattr(preset, "description")
            assert hasattr(preset, "temperature")
            assert hasattr(preset, "prompt_modifier")
            assert hasattr(preset, "evil_strategy_prompt")
            assert hasattr(preset, "good_strategy_prompt")
            assert hasattr(preset, "speech_style_prompt")
            assert hasattr(preset, "persona_overrides")
            # Multi-axis fields
            assert hasattr(preset, "competence")
            assert hasattr(preset, "deception")
            assert hasattr(preset, "volatility")
            assert hasattr(preset, "expressiveness")
            assert hasattr(preset, "information_openness")
            assert hasattr(preset, "latency_budget")
            assert hasattr(preset, "temperature_by_action")

    def test_all_four_presets_exist(self):
        assert len(PRESETS) == 4
        assert "casual" in PRESETS
        assert "standard" in PRESETS
        assert "master" in PRESETS
        assert "chaos" in PRESETS

    def test_frozen_dataclass(self):
        preset = PRESETS["standard"]
        with pytest.raises(AttributeError):
            preset.temperature = 0.99


# ============================================================
# Temperature ranges
# ============================================================


class TestTemperatureRanges:
    def test_casual_greater_than_standard(self):
        assert PRESETS["casual"].temperature > PRESETS["standard"].temperature

    def test_standard_greater_than_master(self):
        assert PRESETS["standard"].temperature > PRESETS["master"].temperature

    def test_chaos_greater_than_standard(self):
        assert PRESETS["chaos"].temperature > PRESETS["standard"].temperature

    def test_all_temperatures_in_valid_range(self):
        for preset in PRESETS.values():
            assert 0.0 <= preset.temperature <= 2.0

    def test_master_is_lowest(self):
        master_temp = PRESETS["master"].temperature
        for key, preset in PRESETS.items():
            if key != "master":
                assert preset.temperature >= master_temp


# ============================================================
# Prompt modifiers and persona overrides
# ============================================================


class TestPromptModifiersAndOverrides:
    def test_standard_has_empty_prompt_modifier(self):
        assert PRESETS["standard"].prompt_modifier == ""

    def test_non_standard_have_non_empty_prompt_modifier(self):
        for key in ("casual", "master", "chaos"):
            assert PRESETS[key].prompt_modifier != "", (
                f"Expected non-empty prompt_modifier for {key}"
            )

    def test_standard_has_empty_persona_overrides(self):
        assert PRESETS["standard"].persona_overrides == {}

    def test_non_standard_have_non_empty_persona_overrides(self):
        for key in ("casual", "master", "chaos"):
            assert len(PRESETS[key].persona_overrides) > 0, (
                f"Expected non-empty persona_overrides for {key}"
            )

    def test_non_standard_have_non_empty_evil_strategy(self):
        for key in ("casual", "master", "chaos"):
            assert PRESETS[key].evil_strategy_prompt != "", (
                f"Expected non-empty evil_strategy_prompt for {key}"
            )

    def test_all_presets_have_good_strategy_prompt(self):
        for key in ("casual", "standard", "master", "chaos"):
            assert hasattr(PRESETS[key], "good_strategy_prompt"), (
                f"Expected good_strategy_prompt on {key}"
            )

    def test_non_standard_have_non_empty_good_strategy(self):
        for key in ("casual", "master", "chaos"):
            assert PRESETS[key].good_strategy_prompt != "", (
                f"Expected non-empty good_strategy_prompt for {key}"
            )

    def test_standard_has_baseline_contract(self):
        """Standard must have explicit baseline strategy prompts, not empty."""
        standard = PRESETS["standard"]
        assert standard.evil_strategy_prompt != "", "Standard evil_strategy_prompt baseline missing"
        assert standard.good_strategy_prompt != "", "Standard good_strategy_prompt baseline missing"
        assert standard.speech_style_prompt != "", "Standard speech_style_prompt baseline missing"

    def test_all_presets_have_non_empty_speech_style(self):
        for key in ("casual", "standard", "master", "chaos"):
            assert PRESETS[key].speech_style_prompt != "", (
                f"Expected non-empty speech_style_prompt for {key}"
            )


# ============================================================
# Multi-axis difficulty parameters
# ============================================================


class TestMultiAxisDifficulty:
    def test_all_axes_in_valid_range(self):
        axes = ("competence", "deception", "volatility", "expressiveness", "information_openness")
        for key in ("casual", "standard", "master", "chaos"):
            preset = PRESETS[key]
            for axis in axes:
                val = getattr(preset, axis)
                assert 0.0 <= val <= 1.0, (
                    f"{key}.{axis} = {val} out of [0,1] range"
                )

    def test_master_highest_competence(self):
        master = PRESETS["master"].competence
        for key in ("casual", "standard", "chaos"):
            assert master >= PRESETS[key].competence, (
                f"Master competence should be >= {key}"
            )

    def test_chaos_highest_volatility(self):
        chaos = PRESETS["chaos"].volatility
        for key in ("casual", "standard", "master"):
            assert chaos >= PRESETS[key].volatility, (
                f"Chaos volatility should be >= {key}"
            )

    def test_master_highest_deception(self):
        master = PRESETS["master"].deception
        for key in ("casual", "standard", "chaos"):
            assert master >= PRESETS[key].deception, (
                f"Master deception should be >= {key}"
            )

    def test_casual_highest_information_openness(self):
        casual = PRESETS["casual"].information_openness
        for key in ("standard", "master", "chaos"):
            assert casual >= PRESETS[key].information_openness, (
                f"Casual information_openness should be >= {key}"
            )

    def test_latency_budget_has_required_actions(self):
        required = ("vote", "nomination_intent", "night_action", "speak", "defense_speech")
        for key in ("casual", "standard", "master", "chaos"):
            budget = PRESETS[key].latency_budget
            for action in required:
                assert action in budget, (
                    f"{key} latency_budget missing {action}"
                )
                assert budget[action] > 0

    def test_master_latency_budget_tightest(self):
        for action in ("vote", "nomination_intent"):
            master_val = PRESETS["master"].latency_budget[action]
            for key in ("casual", "standard", "chaos"):
                assert master_val <= PRESETS[key].latency_budget[action], (
                    f"Master {action} budget should be <= {key}"
                )


# ============================================================
# Team boundary: strategy prompts only inject for correct team
# ============================================================


class _StubBackend(LLMBackend):
    async def generate(self, system_prompt: str, messages: list[Message], **kwargs) -> LLMResponse:
        return LLMResponse(content="stub", tool_calls=[])

    def get_model_name(self) -> str:
        return "stub"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


def _make_agent(team: str, difficulty: str = "master") -> AIAgent:
    backend = _StubBackend()
    persona = Persona(description="测试人格", speaking_style="测试风格")
    agent = AIAgent(
        player_id="p_test",
        name="TestAgent",
        backend=backend,
        persona=persona,
        difficulty=difficulty,
    )
    agent.team = team
    return agent


class TestStrategyPromptTeamBoundary:
    def test_evil_agent_receives_evil_strategy(self):
        agent = _make_agent(team=Team.EVIL.value, difficulty="master")
        block = agent._build_persona_prompt_block("speak")
        assert "【邪恶策略】" in block
        assert "【正义策略】" not in block

    def test_good_agent_receives_good_strategy(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="master")
        block = agent._build_persona_prompt_block("speak")
        assert "【正义策略】" in block
        assert "【邪恶策略】" not in block

    def test_good_agent_never_receives_evil_strategy(self):
        for difficulty in ("casual", "master", "chaos"):
            agent = _make_agent(team=Team.GOOD.value, difficulty=difficulty)
            block = agent._build_persona_prompt_block("speak")
            assert "【邪恶策略】" not in block, (
                f"Good agent should not see evil strategy on {difficulty}"
            )

    def test_evil_agent_never_receives_good_strategy(self):
        for difficulty in ("casual", "master", "chaos"):
            agent = _make_agent(team=Team.EVIL.value, difficulty=difficulty)
            block = agent._build_persona_prompt_block("speak")
            assert "【正义策略】" not in block, (
                f"Evil agent should not see good strategy on {difficulty}"
            )

    def test_standard_difficulty_has_baseline_strategy_prompts(self):
        """Standard now has explicit baseline contract — strategy prompts should appear."""
        evil_agent = _make_agent(team=Team.EVIL.value, difficulty="standard")
        evil_block = evil_agent._build_persona_prompt_block("speak")
        assert "【邪恶策略】" in evil_block, "Standard evil agent should see baseline evil strategy"
        assert "【正义策略】" not in evil_block

        good_agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        good_block = good_agent._build_persona_prompt_block("speak")
        assert "【正义策略】" in good_block, "Standard good agent should see baseline good strategy"
        assert "【邪恶策略】" not in good_block

    def test_non_standard_have_non_empty_speech_style(self):
        for key in ("casual", "standard", "master", "chaos"):
            assert PRESETS[key].speech_style_prompt != "", (
                f"Expected non-empty speech_style_prompt for {key}"
            )


# ============================================================
# Faction info boundary: no hidden info leakage
# ============================================================


class TestFactionInfoBoundary:
    """Verify difficulty system does not leak hidden faction information."""

    def test_strategy_prompts_are_static_text(self):
        """Strategy prompts should not contain template variables or player IDs."""
        for key in ("casual", "standard", "master", "chaos"):
            for field in ("evil_strategy_prompt", "good_strategy_prompt", "speech_style_prompt"):
                prompt = getattr(PRESETS[key], field)
                assert "{player" not in prompt.lower(), f"{key}.{field} has template vars"
                assert "{target" not in prompt.lower(), f"{key}.{field} has target vars"
                assert "{role" not in prompt.lower(), f"{key}.{field} has role vars"

    def test_prompt_block_no_player_id_leakage(self):
        """Persona prompt blocks should not embed unexpected player IDs."""
        for difficulty in ("casual", "standard", "master", "chaos"):
            for team in (Team.GOOD.value, Team.EVIL.value):
                agent = _make_agent(team=team, difficulty=difficulty)
                block = agent._build_persona_prompt_block("speak")
                assert "p_other" not in block
                assert "p_teammate" not in block

    def test_evil_block_does_not_leak_good_strategy(self):
        """Evil agents should never see good-side strategy in their prompt."""
        for difficulty in ("casual", "master", "chaos"):
            agent = _make_agent(team=Team.EVIL.value, difficulty=difficulty)
            block = agent._build_persona_prompt_block("speak")
            assert "【邪恶策略】" in block
            assert "【正义策略】" not in block

    def test_good_block_does_not_leak_evil_strategy(self):
        """Good agents should never see evil-side strategy in their prompt."""
        for difficulty in ("casual", "standard", "master", "chaos"):
            agent = _make_agent(team=Team.GOOD.value, difficulty=difficulty)
            block = agent._build_persona_prompt_block("speak")
            assert "【正义策略】" in block
            assert "【邪恶策略】" not in block

    def test_difficulty_preserves_team_assignment(self):
        """Difficulty level must not alter the agent's team."""
        for difficulty in ("casual", "standard", "master", "chaos"):
            good = _make_agent(team=Team.GOOD.value, difficulty=difficulty)
            evil = _make_agent(team=Team.EVIL.value, difficulty=difficulty)
            assert good.team == Team.GOOD.value
            assert evil.team == Team.EVIL.value


# ============================================================
# DeceptionTracker
# ============================================================


class TestDeceptionTracker:
    def test_budget_scales_with_deception_level(self):
        tracker_low = DeceptionTracker(deception_level=0.15)
        tracker_high = DeceptionTracker(deception_level=0.7)
        assert tracker_low.max_fabrications_per_day <= tracker_high.max_fabrications_per_day

    def test_can_fabricate_within_budget(self):
        tracker = DeceptionTracker(deception_level=0.5)
        assert tracker.can_fabricate(day_number=1) is True

    def test_cannot_exceed_budget(self):
        tracker = DeceptionTracker(deception_level=0.5)
        for _ in range(tracker.max_fabrications_per_day):
            tracker.record_fabrication(day_number=1, content="test")
        assert tracker.can_fabricate(day_number=1) is False

    def test_budget_resets_per_day(self):
        tracker = DeceptionTracker(deception_level=0.5)
        for _ in range(tracker.max_fabrications_per_day):
            tracker.record_fabrication(day_number=1, content="test")
        assert tracker.can_fabricate(day_number=1) is False
        assert tracker.can_fabricate(day_number=2) is True

    def test_record_self_claim(self):
        tracker = DeceptionTracker(deception_level=0.7)
        tracker.record_self_claim("mayor", day_number=1)
        assert "mayor" in tracker.active_claims

    def test_active_claims_returns_copy(self):
        tracker = DeceptionTracker(deception_level=0.7)
        tracker.record_self_claim("mayor", day_number=1)
        claims = tracker.active_claims
        claims["fake"] = "test"
        assert "fake" not in tracker.active_claims

    def test_consistency_guidance_empty_when_no_claims(self):
        tracker = DeceptionTracker(deception_level=0.7)
        assert tracker.get_consistency_guidance() == ""

    def test_consistency_guidance_with_claims(self):
        tracker = DeceptionTracker(deception_level=0.7)
        tracker.record_self_claim("mayor", day_number=1)
        guidance = tracker.get_consistency_guidance()
        assert "mayor" in guidance
        assert "一致" in guidance

    def test_consistency_guidance_with_narrative_threads(self):
        tracker = DeceptionTracker(deception_level=0.7)
        tracker.record_fabrication(day_number=1, content="我怀疑p2是恶魔")
        guidance = tracker.get_consistency_guidance()
        assert "叙事线" in guidance

    def test_fabrication_log_tracks_content(self):
        tracker = DeceptionTracker(deception_level=0.7)
        tracker.record_fabrication(day_number=1, content="test content", target="p2")
        assert len(tracker._fabrication_log) == 1
        assert tracker._fabrication_log[0]["target"] == "p2"


class TestAgentDeceptionBudgetPrompt:
    def test_good_agent_returns_empty(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="master")
        from src.state.game_state import AgentVisibleState, GamePhase
        vs = AgentVisibleState(
            game_id="test", phase=GamePhase.DAY_DISCUSSION,
            day_number=1, round_number=1,
        )
        assert agent._deception_budget_prompt(vs) == ""

    def test_evil_agent_empty_when_budget_available(self):
        agent = _make_agent(team=Team.EVIL.value, difficulty="master")
        from src.state.game_state import AgentVisibleState, GamePhase
        vs = AgentVisibleState(
            game_id="test", phase=GamePhase.DAY_DISCUSSION,
            day_number=1, round_number=1,
        )
        result = agent._deception_budget_prompt(vs)
        assert result == ""

    def test_evil_agent_warns_at_one_remaining(self):
        agent = _make_agent(team=Team.EVIL.value, difficulty="master")
        tracker = agent.deception_tracker
        for _ in range(tracker.max_fabrications_per_day - 1):
            tracker.record_fabrication(day_number=1, content="x")
        from src.state.game_state import AgentVisibleState, GamePhase
        vs = AgentVisibleState(
            game_id="test", phase=GamePhase.DAY_DISCUSSION,
            day_number=1, round_number=1,
        )
        result = agent._deception_budget_prompt(vs)
        assert "最后一次" in result

    def test_evil_agent_blocks_when_budget_exhausted(self):
        agent = _make_agent(team=Team.EVIL.value, difficulty="master")
        tracker = agent.deception_tracker
        for _ in range(tracker.max_fabrications_per_day):
            tracker.record_fabrication(day_number=1, content="x")
        from src.state.game_state import AgentVisibleState, GamePhase
        vs = AgentVisibleState(
            game_id="test", phase=GamePhase.DAY_DISCUSSION,
            day_number=1, round_number=1,
        )
        result = agent._deception_budget_prompt(vs)
        assert "已用完" in result

    def test_evil_agent_has_consistency_in_persona_block(self):
        agent = _make_agent(team=Team.EVIL.value, difficulty="master")
        agent.deception_tracker.record_self_claim("mayor", day_number=1)
        block = agent._build_persona_prompt_block("speak")
        assert "【叙事一致性】" in block
        assert "mayor" in block


# ============================================================
# Speed profile (player-count adaptive)
# ============================================================


class TestSpeedProfile:
    def test_standard_for_small_games(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 5
        assert agent._speed_profile == "standard"

    def test_aggressive_for_8_players(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 8
        assert agent._speed_profile == "aggressive"

    def test_extreme_for_10_players(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 10
        assert agent._speed_profile == "extreme"

    def test_standard_budget_unchanged(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 5
        assert agent._action_timeout_seconds("vote") == 0.8

    def test_aggressive_budget_tighter(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 8
        assert agent._action_timeout_seconds("vote") < 0.8
        assert agent._action_timeout_seconds("vote") >= 0.6

    def test_extreme_budget_tightest(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 10
        assert agent._action_timeout_seconds("vote") < 0.8
        assert agent._action_timeout_seconds("vote") >= 0.5

    def test_env_override_still_works(self):
        agent = _make_agent(team=Team.GOOD.value, difficulty="standard")
        agent.player_count = 10
        import os
        old = os.environ.get("AI_ACTION_TIMEOUT_SECONDS")
        try:
            os.environ["AI_ACTION_TIMEOUT_SECONDS"] = "5.0"
            assert agent._action_timeout_seconds("vote") == 5.0
        finally:
            if old is None:
                os.environ.pop("AI_ACTION_TIMEOUT_SECONDS", None)
            else:
                os.environ["AI_ACTION_TIMEOUT_SECONDS"] = old
