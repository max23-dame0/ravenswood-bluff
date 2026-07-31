"""
Shared test fixtures for the Ravenswood Bluff test suite.

Provides commonly-needed test doubles and factory functions so individual
test files don't need to duplicate setup boilerplate.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest

from src.agents.ai_agent import AIAgent, Persona
from src.agents.base_agent import BaseAgent
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.llm.mock_backend import MockBackend
from src.orchestrator.event_bus import EventBus
from src.orchestrator.game_loop import GameOrchestrator
from src.orchestrator.information_broker import InformationBroker
from src.state.game_state import (
    AgentVisibleState,
    GameConfig,
    GameEvent,
    GamePhase,
    GameState,
    PlayerState,
    Team,
    Visibility,
)

# ---------------------------------------------------------------------------
# Test doubles (single source of truth → tests/doubles.py)
# ---------------------------------------------------------------------------
from tests.doubles import (
    CapturingBackend,
    DummyAgent,
    DummyBackend,
    DummyStoryteller,
    ScriptedAgent,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def agent_ctx(agent: AIAgent, state: GameState) -> tuple[AgentVisibleState, Any]:
    """Build the visible state and legal context for an agent from a GameState.

    Duplicated in 4 test files; consolidated here.
    """
    visible_state = agent._build_visible_state(state)
    legal_context = agent._build_legal_action_context(state, visible_state)
    return visible_state, legal_context


def make_event(event_type: str = "test_event", **kwargs: Any) -> GameEvent:
    """Create a GameEvent with sensible defaults."""
    defaults: dict[str, Any] = {
        "event_type": event_type,
        "phase": GamePhase.DAY_DISCUSSION,
        "round_number": 1,
    }
    defaults.update(kwargs)
    return GameEvent(**defaults)


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dummy_backend() -> DummyBackend:
    return DummyBackend()


@pytest.fixture
def mock_backend() -> MockBackend:
    return MockBackend()


@pytest.fixture
def capturing_backend() -> CapturingBackend:
    return CapturingBackend()


@pytest.fixture
def standard_game_state() -> GameState:
    """7-player Trouble Brewing game state (standard test size)."""
    return GameState(
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="empath", team=Team.GOOD),
            PlayerState(player_id="p3", name="Charlie", role_id="investigator", team=Team.GOOD),
            PlayerState(player_id="p4", name="Diana", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p5", name="Eve", role_id="librarian", team=Team.GOOD),
            PlayerState(player_id="p6", name="Frank", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p7", name="Grace", role_id="poisoner", team=Team.EVIL),
        ),
        seat_order=("p1", "p2", "p3", "p4", "p5", "p6", "p7"),
        config=GameConfig(player_count=7),
        bluffs=("monk", "soldier", "fortune_teller"),
    )


@pytest.fixture
def small_game_state() -> GameState:
    """3-player minimal game state for quick tests."""
    return GameState(
        players=(
            PlayerState(player_id="a1", name="Alice", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="a2", name="Bob", role_id="empath", team=Team.GOOD),
            PlayerState(player_id="a3", name="Charlie", role_id="washerwoman", team=Team.GOOD),
        ),
        seat_order=("a1", "a2", "a3"),
        config=GameConfig(player_count=3, discussion_rounds=1, max_nomination_rounds=1),
        bluffs=("chef", "monk", "fortune_teller"),
    )


@pytest.fixture
def dummy_state() -> GameState:
    """2-player minimal state for agent-level tests."""
    return GameState(
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
    )


@pytest.fixture
def sample_visible_state() -> AgentVisibleState:
    """Minimal AgentVisibleState for tests that don't need full state derivation."""
    return AgentVisibleState(
        game_id="test",
        phase=GamePhase.DAY_DISCUSSION,
        day_number=1,
        round_number=1,
    )


@pytest.fixture
def make_ai_agent():
    """Factory fixture for creating AIAgent instances with customizable params."""

    def _factory(
        player_id: str = "p1",
        name: str = "TestAgent",
        backend: Optional[LLMBackend] = None,
        persona: Optional[Persona] = None,
        player_count: int = 10,
        difficulty: str = "standard",
    ) -> AIAgent:
        return AIAgent(
            player_id=player_id,
            name=name,
            backend=backend or DummyBackend(),
            persona=persona or Persona(description="测试人格", speaking_style="测试风格"),
            player_count=player_count,
            difficulty=difficulty,
        )

    return _factory


@pytest.fixture
def make_orchestrator():
    """Factory fixture for creating GameOrchestrator instances with optional storyteller."""

    def _factory(
        state: Optional[GameState] = None,
        with_storyteller: bool = False,
    ) -> GameOrchestrator:
        if state is None:
            state = GameState(
                players=(
                    PlayerState(player_id="a1", name="Alice", role_id="imp", team=Team.EVIL),
                    PlayerState(player_id="a2", name="Bob", role_id="empath", team=Team.GOOD),
                    PlayerState(
                        player_id="a3", name="Charlie", role_id="washerwoman", team=Team.GOOD
                    ),
                ),
            )
        orch = GameOrchestrator(state)
        if with_storyteller:
            orch.storyteller_agent = DummyStoryteller()
        return orch

    return _factory
