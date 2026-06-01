"""
Shared test fixtures for the Ravenswood Bluff test suite.

Provides commonly-needed test doubles and factory functions so individual
test files don't need to duplicate setup boilerplate.
"""

from __future__ import annotations

import pytest
from typing import Any, Optional

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
# Test backends
# ---------------------------------------------------------------------------


class DummyBackend(LLMBackend):
    """Minimal LLM backend that returns a fixed Chinese string."""

    async def generate(
        self, system_prompt: str, messages: list[Message], **kwargs: Any
    ) -> LLMResponse:
        return LLMResponse(content="这是一个假象的LLM回复", tool_calls=[])

    def get_model_name(self) -> str:
        return "dummy-model"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            base = float(len(text) or 1)
            vectors.append([base] * 1536)
        return vectors


class CapturingBackend(LLMBackend):
    """Records every system_prompt it receives; returns a configurable content string."""

    def __init__(self, content: str = "{}") -> None:
        self.content = content
        self.calls: list[str] = []

    async def generate(
        self, system_prompt: str, messages: list[Message], **kwargs: Any
    ) -> LLMResponse:
        self.calls.append(system_prompt)
        return LLMResponse(content=self.content, tool_calls=[])

    def get_model_name(self) -> str:
        return "capturing"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


# ---------------------------------------------------------------------------
# Test doubles for agents
# ---------------------------------------------------------------------------


class ScriptedAgent(BaseAgent):
    """Agent that returns pre-scripted actions by action_type, in order."""

    def __init__(
        self, pid: str, name: str, actions: dict[str, list[dict[str, Any]]]
    ) -> None:
        super().__init__(player_id=pid, name=name)
        self.actions = actions
        self.counters: dict[str, int] = {}

    async def act(
        self, visible_state: Any, action_type: str, legal_context: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        c = self.counters.get(action_type, 0)
        lst = self.actions.get(action_type, [])
        if c < len(lst):
            self.counters[action_type] = c + 1
            return lst[c]
        return {"action": action_type}

    async def observe_event(self, event: Any, visible_state: Any) -> None:
        pass

    async def think(self, prompt: str, visible_state: Any) -> str:
        return ""


class DummyAgent(BaseAgent):
    """Minimal agent that records observed events and returns empty actions."""

    def __init__(self, pid: str, team: Team) -> None:
        super().__init__(player_id=pid, name=f"Agent_{pid}")
        self._team = team
        self.observed_events: list[Any] = []

    def synchronize_role(self, state: Any) -> None:
        self.team = self._team.value

    async def act(
        self, visible_state: Any, action_type: str, legal_context: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return {}

    async def observe_event(self, event: Any, visible_state: Any) -> None:
        self.observed_events.append(event)

    async def think(self, prompt: str, visible_state: Any) -> str:
        return ""


class DummyStoryteller:
    """Minimal storyteller stub for orchestrator tests."""

    async def decide_drunk_role(self, script: Any, role_ids: Any) -> str:
        return "washerwoman"

    async def decide_initial_setup_info(self, game_state: Any) -> Any:
        return game_state

    async def build_night_order(self, game_state: Any, phase: Any) -> list:
        return []

    def role_receives_storyteller_info(self, role_id: str) -> bool:
        return True

    async def decide_night_info(
        self, game_state: Any, player_id: str, role_id: str
    ) -> dict:
        return {}

    async def narrate_phase(self, game_state: Any) -> str:
        return ""


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
                    PlayerState(player_id="a3", name="Charlie", role_id="washerwoman", team=Team.GOOD),
                ),
            )
        orch = GameOrchestrator(state)
        if with_storyteller:
            orch.storyteller_agent = DummyStoryteller()
        return orch

    return _factory
