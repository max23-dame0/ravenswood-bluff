"""Acceptance checks for the difficulty system end-to-end."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.ai_agent import AIAgent, Persona
from src.agents.difficulty_presets import (
    PRESETS,
    DifficultyPreset,
    get_preset,
)
from src.llm.mock_backend import MockBackend
from src.state.game_state import DifficultyLevel, GameConfig


_pass_count = 0
_fail_count = 0


def _check(label: str, condition: bool) -> None:
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {label}")
    else:
        _fail_count += 1
        print(f"  FAIL  {label}")


# ------------------------------------------------------------------
# 1. DifficultyLevel enum
# ------------------------------------------------------------------

def check_enum() -> None:
    print("[1] DifficultyLevel enum")
    _check("CASUAL value is 'casual'", DifficultyLevel.CASUAL.value == "casual")
    _check("STANDARD value is 'standard'", DifficultyLevel.STANDARD.value == "standard")
    _check("MASTER value is 'master'", DifficultyLevel.MASTER.value == "master")
    _check("CHAOS value is 'chaos'", DifficultyLevel.CHAOS.value == "chaos")
    _check("round-trip from string", DifficultyLevel("master") is DifficultyLevel.MASTER)
    _check("is str subclass", isinstance(DifficultyLevel.CASUAL, str))


# ------------------------------------------------------------------
# 2. GameConfig accepts difficulty
# ------------------------------------------------------------------

def check_game_config() -> None:
    print("[2] GameConfig difficulty field")
    default_cfg = GameConfig(player_count=5)
    _check("default difficulty is STANDARD", default_cfg.difficulty == DifficultyLevel.STANDARD)

    for level in DifficultyLevel:
        cfg = GameConfig(player_count=5, difficulty=level)
        _check(f"accepts {level.value}", cfg.difficulty == level)


# ------------------------------------------------------------------
# 3. get_preset() returns valid presets
# ------------------------------------------------------------------

def check_get_preset() -> None:
    print("[3] get_preset() for all difficulties")
    for key in ("casual", "standard", "master", "chaos"):
        preset = get_preset(key)
        _check(f"'{key}' returns DifficultyPreset", isinstance(preset, DifficultyPreset))
        _check(f"'{key}' has non-empty name", bool(preset.name))
        _check(f"'{key}' temperature in [0, 2]", 0.0 <= preset.temperature <= 2.0)

    fallback = get_preset("unknown_difficulty")
    standard = get_preset("standard")
    _check("unknown input defaults to standard", fallback is standard)


# ------------------------------------------------------------------
# 4. Temperature ordering
# ------------------------------------------------------------------

def check_temperature_ordering() -> None:
    print("[4] Temperature ordering")
    casual_t = PRESETS["casual"].temperature
    standard_t = PRESETS["standard"].temperature
    master_t = PRESETS["master"].temperature
    chaos_t = PRESETS["chaos"].temperature

    _check("casual > standard", casual_t > standard_t)
    _check("standard > master", standard_t > master_t)
    _check("chaos > standard", chaos_t > standard_t)
    _check("master is lowest", master_t <= min(casual_t, standard_t, chaos_t))


# ------------------------------------------------------------------
# 5. Prompt modifiers and persona overrides
# ------------------------------------------------------------------

def check_prompt_content() -> None:
    print("[5] Prompt modifiers and persona overrides")
    _check("standard prompt_modifier is empty (baseline has no modifier)", PRESETS["standard"].prompt_modifier == "")
    _check("standard persona_overrides is empty", PRESETS["standard"].persona_overrides == {})

    # Standard baseline contract: strategy prompts must exist
    std = PRESETS["standard"]
    _check("standard evil_strategy_prompt baseline exists", std.evil_strategy_prompt != "")
    _check("standard good_strategy_prompt baseline exists", std.good_strategy_prompt != "")
    _check("standard speech_style_prompt baseline exists", std.speech_style_prompt != "")

    for key in ("casual", "master", "chaos"):
        _check(f"{key} prompt_modifier non-empty", PRESETS[key].prompt_modifier != "")
        _check(f"{key} persona_overrides non-empty", len(PRESETS[key].persona_overrides) > 0)
        _check(f"{key} evil_strategy_prompt non-empty", PRESETS[key].evil_strategy_prompt != "")
        _check(f"{key} speech_style_prompt non-empty", PRESETS[key].speech_style_prompt != "")


# ------------------------------------------------------------------
# 5b. Multi-axis parameters
# ------------------------------------------------------------------

def check_multi_axis() -> None:
    print("[5b] Multi-axis difficulty parameters")
    axes = ("competence", "deception", "volatility", "expressiveness", "information_openness", "nomination_intelligence")
    for key in ("casual", "standard", "master", "chaos"):
        preset = PRESETS[key]
        for axis in axes:
            val = getattr(preset, axis)
            _check(f"{key}.{axis} in [0,1]", 0.0 <= val <= 1.0)

    # Ordering checks
    _check("master competence >= all others",
           PRESETS["master"].competence >= max(PRESETS[k].competence for k in ("casual", "standard", "chaos")))
    _check("chaos volatility >= all others",
           PRESETS["chaos"].volatility >= max(PRESETS[k].volatility for k in ("casual", "standard", "master")))
    _check("master deception >= all others",
           PRESETS["master"].deception >= max(PRESETS[k].deception for k in ("casual", "standard", "chaos")))
    _check("master nomination_intelligence >= all others",
           PRESETS["master"].nomination_intelligence >= max(PRESETS[k].nomination_intelligence for k in ("casual", "standard", "chaos")))
    _check("casual nomination_intelligence <= standard",
           PRESETS["casual"].nomination_intelligence <= PRESETS["standard"].nomination_intelligence)

    # Latency budget structure
    required_actions = ("vote", "nomination_intent", "night_action", "speak", "defense_speech")
    for key in ("casual", "standard", "master", "chaos"):
        budget = PRESETS[key].latency_budget
        for action in required_actions:
            _check(f"{key} latency_budget[{action}] > 0", action in budget and budget[action] > 0)


# ------------------------------------------------------------------
# 6. AIAgent construction with each difficulty
# ------------------------------------------------------------------

def check_agent_construction() -> None:
    print("[6] AIAgent construction with each difficulty")
    persona = Persona(
        description="Test persona",
        speaking_style="Neutral",
        archetype="logic",
    )

    for key in ("casual", "standard", "master", "chaos"):
        backend = MockBackend()
        try:
            agent = AIAgent(
                player_id="test_p1",
                name="TestAgent",
                backend=backend,
                persona=persona,
                player_count=5,
                difficulty=key,
            )
            _check(f"AIAgent(difficulty='{key}') constructed", True)
            _check(f"agent.difficulty == '{key}'", agent.difficulty == key)
            _check(f"agent.difficulty_preset is DifficultyPreset", isinstance(agent.difficulty_preset, DifficultyPreset))
        except Exception as exc:
            _check(f"AIAgent(difficulty='{key}') constructed", False)
            print(f"         Exception: {exc}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Difficulty system acceptance checks")
    print("=" * 60)

    check_enum()
    check_game_config()
    check_get_preset()
    check_temperature_ordering()
    check_prompt_content()
    check_multi_axis()
    check_agent_construction()

    print("=" * 60)
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)

    if _fail_count > 0:
        print("difficulty acceptance: FAILED")
        return 1

    print("difficulty acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
