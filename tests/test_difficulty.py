"""Unit tests for the difficulty system."""

from __future__ import annotations

import pytest

from src.agents.difficulty_presets import (
    PRESETS,
    DifficultyPreset,
    get_preset,
)
from src.state.game_state import DifficultyLevel, GameConfig


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
            assert hasattr(preset, "speech_style_prompt")
            assert hasattr(preset, "persona_overrides")

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

    def test_non_standard_have_non_empty_speech_style(self):
        for key in ("casual", "master", "chaos"):
            assert PRESETS[key].speech_style_prompt != "", (
                f"Expected non-empty speech_style_prompt for {key}"
            )
