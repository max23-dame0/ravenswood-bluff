"""Unit tests for the DecisionNoise module."""

from __future__ import annotations

import pytest

from src.agents.decision_noise import DecisionNoise, _NOISE_MAGNITUDE, _BOLD_MOVE_PROB


# ============================================================
# Magnitude ordering
# ============================================================


class TestMagnitudeOrdering:
    """chaos > casual > standard > master"""

    def test_chaos_greater_than_casual(self):
        assert _NOISE_MAGNITUDE["chaos"] > _NOISE_MAGNITUDE["casual"]

    def test_casual_greater_than_standard(self):
        assert _NOISE_MAGNITUDE["casual"] > _NOISE_MAGNITUDE["standard"]

    def test_standard_greater_than_master(self):
        assert _NOISE_MAGNITUDE["standard"] > _NOISE_MAGNITUDE["master"]

    def test_ordering_via_instances(self):
        chaos = DecisionNoise(difficulty="chaos", player_id="p1")
        casual = DecisionNoise(difficulty="casual", player_id="p1")
        standard = DecisionNoise(difficulty="standard", player_id="p1")
        master = DecisionNoise(difficulty="master", player_id="p1")
        assert chaos.magnitude > casual.magnitude > standard.magnitude > master.magnitude


# ============================================================
# Threshold noise bounds
# ============================================================


class TestThresholdNoiseBounds:
    """Noise is always in [-magnitude, +magnitude] for each difficulty."""

    @pytest.mark.parametrize("difficulty", ["casual", "standard", "master", "chaos"])
    def test_noise_within_bounds(self, difficulty):
        noise = DecisionNoise(difficulty=difficulty, player_id="p1")
        mag = noise.magnitude
        for i in range(100):
            value = noise.threshold_noise(f"context_{i}")
            assert -mag <= value <= mag, (
                f"{difficulty}: noise {value} outside [-{mag}, +{mag}]"
            )

    def test_unknown_difficulty_uses_default_magnitude(self):
        noise = DecisionNoise(difficulty="unknown", player_id="p1")
        assert noise.magnitude == 0.05
        value = noise.threshold_noise("ctx")
        assert -0.05 <= value <= 0.05


# ============================================================
# Threshold noise determinism
# ============================================================


class TestThresholdNoiseDeterminism:
    """Same context_key always returns the same noise value."""

    def test_same_key_same_result(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        first = noise.threshold_noise("day3_nominate")
        for _ in range(20):
            assert noise.threshold_noise("day3_nominate") == first

    def test_determinism_across_all_difficulties(self):
        for difficulty in ("casual", "standard", "master", "chaos"):
            noise = DecisionNoise(difficulty=difficulty, player_id="p7")
            first = noise.threshold_noise("vote_round2")
            assert noise.threshold_noise("vote_round2") == first


# ============================================================
# Threshold noise variation
# ============================================================


class TestThresholdNoiseVariation:
    """Different context_keys produce different noise values (with high probability)."""

    def test_different_keys_give_different_values(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        values = {noise.threshold_noise(f"key_{i}") for i in range(20)}
        assert len(values) > 1, "All 20 context keys returned the same noise value"

    def test_different_players_give_different_values(self):
        values = {
            DecisionNoise(difficulty="standard", player_id=f"p{i}").threshold_noise("ctx")
            for i in range(10)
        }
        assert len(values) > 1, "All 10 player_ids returned the same noise value"


# ============================================================
# Bold move probability bounds
# ============================================================


class TestBoldMoveProbability:
    """should_bold_move returns bool; probability roughly matches expected rate."""

    def test_returns_bool(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        result = noise.should_bold_move("ctx")
        assert isinstance(result, bool)

    @pytest.mark.parametrize("difficulty,expected_prob", [
        ("casual", 0.08),
        ("standard", 0.03),
        ("master", 0.01),
        ("chaos", 0.15),
    ])
    def test_probability_roughly_matches(self, difficulty, expected_prob):
        noise = DecisionNoise(difficulty=difficulty, player_id="p1")
        trials = 5000
        count = sum(
            noise.should_bold_move(f"ctx_{i}")
            for i in range(trials)
        )
        observed_rate = count / trials
        # Allow generous tolerance for statistical variation
        assert abs(observed_rate - expected_prob) < 0.03, (
            f"{difficulty}: observed {observed_rate:.3f}, expected ~{expected_prob}"
        )

    def test_unknown_difficulty_uses_default_probability(self):
        noise = DecisionNoise(difficulty="unknown", player_id="p1")
        assert noise.bold_move_probability == 0.03


# ============================================================
# Bold move determinism
# ============================================================


class TestBoldMoveDeterminism:
    """Same context_key always returns the same result."""

    def test_same_key_same_result(self):
        noise = DecisionNoise(difficulty="casual", player_id="p1")
        first = noise.should_bold_move("day1_nominate")
        for _ in range(20):
            assert noise.should_bold_move("day1_nominate") == first

    def test_determinism_across_difficulties(self):
        for difficulty in ("casual", "standard", "master", "chaos"):
            noise = DecisionNoise(difficulty=difficulty, player_id="p3")
            first = noise.should_bold_move("vote_round5")
            assert noise.should_bold_move("vote_round5") == first


# ============================================================
# Noisy target selection
# ============================================================


class TestNoisyTargetSelection:
    """pick_noisy_target always returns a valid candidate."""

    def test_returns_valid_candidate(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        candidates = ["c1", "c2", "c3", "c4"]
        scores = {"c1": 0.9, "c2": 0.7, "c3": 0.5, "c4": 0.3}
        result = noise.pick_noisy_target("ctx", candidates, scores)
        assert result in candidates

    def test_returns_valid_candidate_all_difficulties(self):
        candidates = ["a", "b", "c"]
        scores = {"a": 0.8, "b": 0.5, "c": 0.2}
        for difficulty in ("casual", "standard", "master", "chaos"):
            noise = DecisionNoise(difficulty=difficulty, player_id="p1")
            result = noise.pick_noisy_target("ctx", candidates, scores)
            assert result in candidates, f"{difficulty}: returned {result}"

    def test_single_candidate_returns_it(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        assert noise.pick_noisy_target("ctx", ["only"], {"only": 1.0}) == "only"

    def test_missing_score_defaults_to_zero(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        candidates = ["x", "y"]
        scores = {"x": 0.5}  # y has no score, defaults to 0.0
        result = noise.pick_noisy_target("ctx", candidates, scores)
        assert result in candidates


# ============================================================
# Noisy target determinism
# ============================================================


class TestNoisyTargetDeterminism:
    """Same context_key + candidates/scores returns same result."""

    def test_same_inputs_same_result(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        candidates = ["c1", "c2", "c3"]
        scores = {"c1": 0.9, "c2": 0.5, "c3": 0.1}
        first = noise.pick_noisy_target("ctx", candidates, scores)
        for _ in range(20):
            assert noise.pick_noisy_target("ctx", candidates, scores) == first

    def test_determinism_across_difficulties(self):
        candidates = ["a", "b", "c"]
        scores = {"a": 0.7, "b": 0.5, "c": 0.3}
        for difficulty in ("casual", "standard", "master", "chaos"):
            noise = DecisionNoise(difficulty=difficulty, player_id="p2")
            first = noise.pick_noisy_target("ctx", candidates, scores)
            assert noise.pick_noisy_target("ctx", candidates, scores) == first


# ============================================================
# Noisy target can differ from optimal
# ============================================================


class TestNoisyTargetDiffersFromOptimal:
    """When noise is high (chaos), noisy pick can differ from plain max-score pick."""

    def test_chaos_can_differ_from_optimal(self):
        noise = DecisionNoise(difficulty="chaos", player_id="p1")
        # Scores where optimal is clear, but noise magnitude (0.18) can flip it
        candidates = ["c1", "c2", "c3", "c4", "c5"]
        scores = {"c1": 0.55, "c2": 0.50, "c3": 0.45, "c4": 0.40, "c5": 0.35}
        optimal = max(scores, key=scores.get)

        differed = False
        for i in range(200):
            result = noise.pick_noisy_target(f"ctx_{i}", candidates, scores)
            if result != optimal:
                differed = True
                break
        assert differed, (
            "Chaos noise never produced a different pick than the optimal over 200 trials"
        )

    def test_master_rarely_differs_from_optimal(self):
        noise = DecisionNoise(difficulty="master", player_id="p1")
        candidates = ["c1", "c2"]
        scores = {"c1": 0.9, "c2": 0.1}
        optimal = max(scores, key=scores.get)

        same_count = sum(
            noise.pick_noisy_target(f"ctx_{i}", candidates, scores) == optimal
            for i in range(200)
        )
        # Master noise is tiny (0.02), so optimal should win most of the time
        assert same_count > 150, (
            f"Master noise flipped optimal too often: {same_count}/200 kept optimal"
        )


# ============================================================
# Empty candidates
# ============================================================


class TestEmptyCandidates:
    """pick_noisy_target returns None for empty list."""

    def test_empty_candidates_returns_none(self):
        noise = DecisionNoise(difficulty="standard", player_id="p1")
        assert noise.pick_noisy_target("ctx", [], {}) is None

    def test_empty_candidates_all_difficulties(self):
        for difficulty in ("casual", "standard", "master", "chaos"):
            noise = DecisionNoise(difficulty=difficulty, player_id="p1")
            assert noise.pick_noisy_target("ctx", [], {}) is None, (
                f"{difficulty}: did not return None for empty candidates"
            )
