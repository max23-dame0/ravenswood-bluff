"""Multi-difficulty comparison acceptance script.

Validates that the 4 difficulty presets produce measurably different behaviors
across temperature, prompts, persona overrides, noise, and agent construction.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.ai_agent import AIAgent, Persona
from src.agents.decision_noise import DecisionNoise, _NOISE_MAGNITUDE
from src.agents.difficulty_presets import PRESETS, DifficultyPreset, get_preset
from src.llm.mock_backend import MockBackend


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
# 1. Temperature spread
# ------------------------------------------------------------------


def check_temperature_spread() -> None:
    print("[1] Temperature spread across difficulties")
    casual_t = PRESETS["casual"].temperature
    standard_t = PRESETS["standard"].temperature
    master_t = PRESETS["master"].temperature
    chaos_t = PRESETS["chaos"].temperature

    _check("casual (0.9) > standard (0.7)", casual_t > standard_t)
    _check("standard (0.7) > master (0.4)", standard_t > master_t)
    _check("chaos (1.0) > standard (0.7)", chaos_t > standard_t)
    _check("casual temperature == 0.9", casual_t == 0.9)
    _check("standard temperature == 0.7", standard_t == 0.7)
    _check("master temperature == 0.4", master_t == 0.4)
    _check("chaos temperature == 1.0", chaos_t == 1.0)
    _check("all four temperatures are distinct", len({casual_t, standard_t, master_t, chaos_t}) == 4)


# ------------------------------------------------------------------
# 2. Prompt content uniqueness
# ------------------------------------------------------------------


def check_prompt_content_uniqueness() -> None:
    print("[2] Prompt content uniqueness")
    casual_mod = PRESETS["casual"].prompt_modifier
    master_mod = PRESETS["master"].prompt_modifier
    chaos_mod = PRESETS["chaos"].prompt_modifier
    standard_mod = PRESETS["standard"].prompt_modifier

    _check("standard prompt_modifier is empty", standard_mod == "")

    # casual contains intuition/emotion keywords
    _check(
        "casual contains '直觉' or '感性'",
        "直觉" in casual_mod or "感性" in casual_mod,
    )

    # master contains cross-validation/rigor keywords
    _check(
        "master contains '交叉验证' or '严谨'",
        "交叉验证" in master_mod or "严谨" in master_mod,
    )

    # chaos contains conspiracy/random keywords
    _check(
        "chaos contains '阴谋论' or '随机'",
        "阴谋论" in chaos_mod or "随机" in chaos_mod,
    )

    # Each non-standard modifier is unique (no two are identical)
    _check("casual != master prompt_modifier", casual_mod != master_mod)
    _check("casual != chaos prompt_modifier", casual_mod != chaos_mod)
    _check("master != chaos prompt_modifier", master_mod != chaos_mod)


# ------------------------------------------------------------------
# 3. Persona override differences
# ------------------------------------------------------------------


def check_persona_override_differences() -> None:
    print("[3] Persona override differences")
    casual_offset = PRESETS["casual"].persona_overrides.get("nomination_threshold_offset", 0.0)
    standard_offset = PRESETS["standard"].persona_overrides.get("nomination_threshold_offset", 0.0)
    master_offset = PRESETS["master"].persona_overrides.get("nomination_threshold_offset", 0.0)
    chaos_offset = PRESETS["chaos"].persona_overrides.get("nomination_threshold_offset", 0.0)

    _check("casual nomination_threshold_offset > 0", casual_offset > 0)
    _check("standard nomination_threshold_offset == 0 (no override)", standard_offset == 0)
    _check("master nomination_threshold_offset < 0", master_offset < 0)
    _check("chaos nomination_threshold_offset < 0", chaos_offset < 0)
    _check("casual > master offset", casual_offset > master_offset)
    _check("casual > chaos offset", casual_offset > chaos_offset)


# ------------------------------------------------------------------
# 4. Noise magnitude ordering
# ------------------------------------------------------------------


def check_noise_magnitude_ordering() -> None:
    print("[4] Noise magnitude ordering")
    chaos_mag = _NOISE_MAGNITUDE["chaos"]
    casual_mag = _NOISE_MAGNITUDE["casual"]
    standard_mag = _NOISE_MAGNITUDE["standard"]
    master_mag = _NOISE_MAGNITUDE["master"]

    _check("chaos (0.18) > casual (0.12)", chaos_mag > casual_mag)
    _check("casual (0.12) > standard (0.05)", casual_mag > standard_mag)
    _check("standard (0.05) > master (0.02)", standard_mag > master_mag)
    _check("chaos magnitude == 0.18", chaos_mag == 0.18)
    _check("casual magnitude == 0.12", casual_mag == 0.12)
    _check("standard magnitude == 0.05", standard_mag == 0.05)
    _check("master magnitude == 0.02", master_mag == 0.02)

    # Verify via DecisionNoise instances
    for key in ("casual", "standard", "master", "chaos"):
        dn = DecisionNoise(difficulty=key, player_id="test")
        _check(
            f"DecisionNoise('{key}').magnitude == {_NOISE_MAGNITUDE[key]}",
            dn.magnitude == _NOISE_MAGNITUDE[key],
        )


# ------------------------------------------------------------------
# 5. Evil strategy prompt differences
# ------------------------------------------------------------------


def check_evil_strategy_prompt_differences() -> None:
    print("[5] Evil strategy prompt differences")
    standard_evil = PRESETS["standard"].evil_strategy_prompt
    master_evil = PRESETS["master"].evil_strategy_prompt

    _check("standard evil_strategy_prompt baseline exists", standard_evil != "")
    _check("master evil_strategy_prompt is non-empty", master_evil != "")
    _check(
        "master evil_strategy_prompt is longer than standard (more aggressive)",
        len(master_evil) > len(standard_evil),
    )

    # Verify master's evil strategy contains detailed tactics
    _check(
        "master evil_strategy_prompt contains detailed tactics",
        len(master_evil) > 50,
    )


# ------------------------------------------------------------------
# 6. AIAgent construction
# ------------------------------------------------------------------


def check_agent_construction() -> None:
    print("[6] AIAgent construction with each difficulty")
    persona = Persona(
        description="Test persona",
        speaking_style="Neutral",
        archetype="logic",
    )

    expected_temps = {
        "casual": 0.9,
        "standard": 0.7,
        "master": 0.4,
        "chaos": 1.0,
    }
    expected_magnitudes = {
        "casual": 0.12,
        "standard": 0.05,
        "master": 0.02,
        "chaos": 0.18,
    }

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
            _check(
                f"AIAgent('{key}') constructed successfully",
                True,
            )
            _check(
                f"agent.difficulty_preset.temperature == {expected_temps[key]}",
                agent.difficulty_preset.temperature == expected_temps[key],
            )
            _check(
                f"agent.decision_noise.magnitude == {expected_magnitudes[key]}",
                agent.decision_noise.magnitude == expected_magnitudes[key],
            )
            _check(
                f"agent.persona_profile is a dict",
                isinstance(agent.persona_profile, dict),
            )

            # Verify difficulty overrides are applied to persona_profile
            preset = get_preset(key)
            for override_key, override_value in preset.persona_overrides.items():
                _check(
                    f"persona_profile['{override_key}'] == {override_value} for '{key}'",
                    agent.persona_profile.get(override_key) == override_value,
                )

        except Exception as exc:
            _check(f"AIAgent('{key}') constructed successfully", False)
            print(f"         Exception: {exc}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("Multi-difficulty comparison acceptance checks")
    print("=" * 60)

    check_temperature_spread()
    check_prompt_content_uniqueness()
    check_persona_override_differences()
    check_noise_magnitude_ordering()
    check_evil_strategy_prompt_differences()
    check_agent_construction()

    print("=" * 60)
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)

    if _fail_count > 0:
        print("difficulty comparison: FAILED")
        return 1

    print("difficulty comparison: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
