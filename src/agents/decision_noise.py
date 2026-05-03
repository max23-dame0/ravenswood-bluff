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


@dataclass
class DecisionNoise:
    """Provides difficulty-scaled noise for AI agent decisions.

    Each instance is tied to a player and game context (day/round),
    producing consistent noise within the same decision point but
    varying across different contexts.
    """
    difficulty: str
    player_id: str

    @property
    def magnitude(self) -> float:
        return _NOISE_MAGNITUDE.get(self.difficulty, 0.05)

    @property
    def bold_move_probability(self) -> float:
        return _BOLD_MOVE_PROB.get(self.difficulty, 0.03)

    def _seed(self, context_key: str) -> int:
        """Deterministic seed from player_id + context key."""
        raw = f"{self.player_id}:{context_key}"
        return int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)

    def threshold_noise(self, context_key: str) -> float:
        """Return a noise value in [-magnitude, +magnitude].

        context_key should encode the decision context (e.g. "nominate_day3_round1"
        or "vote_day2_nominee_p5") so the same decision always gets the same noise.
        """
        rng = random.Random(self._seed(context_key))
        return rng.uniform(-self.magnitude, self.magnitude)

    def should_bold_move(self, context_key: str) -> bool:
        """Roll for a 'bold move' — unprompted nomination, retaliatory vote, etc.

        Returns True with probability = bold_move_probability.
        """
        rng = random.Random(self._seed(context_key))
        return rng.random() < self.bold_move_probability

    def pick_noisy_target(
        self,
        context_key: str,
        candidates: list[str],
        scores: dict[str, float],
    ) -> str | None:
        """Pick a target with noise-influenced scores.

        Adds threshold_noise to each candidate's score, then picks the highest.
        This can cause the AI to pick a suboptimal target when noise is high.
        """
        if not candidates:
            return None
        rng = random.Random(self._seed(context_key))
        noisy_scores = {
            cid: scores.get(cid, 0.0) + rng.uniform(-self.magnitude, self.magnitude)
            for cid in candidates
        }
        return max(noisy_scores, key=noisy_scores.get)
