"""Decision noise layer for difficulty-scaled randomness in AI agent behavior.

Adds controlled unpredictability to nomination and vote decisions,
scaled by difficulty level. Uses hash-based seeding for reproducibility
within a game session while still producing varied outcomes across games.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass


# Noise magnitude per difficulty level
_NOISE_MAGNITUDE: dict[str, float] = {
    "casual": 0.12,
    "standard": 0.05,
    "master": 0.02,
    "chaos": 0.18,
}

# Probability of "bold move" (unprompted nomination / retaliatory vote) per difficulty
_BOLD_MOVE_PROB: dict[str, float] = {
    "casual": 0.08,
    "standard": 0.03,
    "master": 0.01,
    "chaos": 0.15,
}

# Social reason labels for bold moves — gives Chaos actions human-readable motivation
_BOLD_MOVE_REASONS: tuple[str, ...] = (
    "retaliation",
    "pressure_test",
    "intuition",
    "story_hook",
)


@dataclass
class BoldMoveResult:
    """Result of a bold move roll, including social reason label."""
    triggered: bool
    reason: str = ""


@dataclass
class DecisionNoise:
    """Provides difficulty-scaled noise for AI agent decisions.

    Each instance is tied to a player and game context (day/round),
    producing consistent noise within the same decision point but
    varying across different contexts. Seed binds to game_id to avoid
    cross-game pattern repetition.
    """
    difficulty: str
    player_id: str
    game_id: str = ""

    @property
    def magnitude(self) -> float:
        return _NOISE_MAGNITUDE.get(self.difficulty, 0.05)

    @property
    def bold_move_probability(self) -> float:
        return _BOLD_MOVE_PROB.get(self.difficulty, 0.03)

    def _seed(self, context_key: str) -> int:
        """Deterministic seed from game_id + player_id + context key."""
        raw = f"{self.game_id}:{self.player_id}:{context_key}"
        return int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)

    def threshold_noise(self, context_key: str) -> float:
        """Return a noise value in [-magnitude, +magnitude].

        context_key should encode the decision context (e.g. "nominate_day3_round1"
        or "vote_day2_nominee_p5") so the same decision always gets the same noise.
        """
        rng = random.Random(self._seed(context_key))
        return rng.uniform(-self.magnitude, self.magnitude)

    def should_bold_move(self, context_key: str) -> BoldMoveResult:
        """Roll for a 'bold move' with a social reason label.

        Returns BoldMoveResult with triggered=True and a reason label
        (retaliation/pressure_test/intuition/story_hook) when the roll succeeds.
        """
        rng = random.Random(self._seed(context_key))
        triggered = rng.random() < self.bold_move_probability
        reason = ""
        if triggered:
            reason_idx = int(hashlib.md5(f"{context_key}:reason".encode()).hexdigest()[:8], 16)
            reason = _BOLD_MOVE_REASONS[reason_idx % len(_BOLD_MOVE_REASONS)]
        return BoldMoveResult(triggered=triggered, reason=reason)

    def pick_noisy_target(
        self,
        context_key: str,
        candidates: list[str],
        scores: dict[str, float],
        legal_targets: set[str] | None = None,
    ) -> str | None:
        """Pick a target with noise-influenced scores.

        Adds threshold_noise to each candidate's score, then picks the highest.
        If legal_targets is provided, only considers candidates in that set.
        This can cause the AI to pick a suboptimal target when noise is high.
        """
        if not candidates:
            return None
        if legal_targets is not None:
            candidates = [c for c in candidates if c in legal_targets]
            if not candidates:
                return None
        rng = random.Random(self._seed(context_key))
        noisy_scores = {
            cid: scores.get(cid, 0.0) + rng.uniform(-self.magnitude, self.magnitude)
            for cid in candidates
        }
        return max(noisy_scores, key=noisy_scores.get)
