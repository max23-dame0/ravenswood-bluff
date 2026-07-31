"""Shared test doubles for the Ravenswood Bluff test suite.

Single source of truth for the LLM backends and agent/storyteller stubs used
across the test suite. Import from here instead of redefining a local copy:

    from tests.doubles import DummyBackend, CapturingBackend
"""

from __future__ import annotations

from typing import Any

from src.agents.base_agent import BaseAgent
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.state.game_state import Team


class DummyBackend(LLMBackend):
    """Minimal LLM backend that returns a fixed string.

    Pass ``content`` to override the default placeholder reply (e.g. "{}" for
    tests that parse the model output as JSON).
    """

    def __init__(self, content: str = "这是一个假象的LLM回复") -> None:
        self.content = content

    async def generate(
        self, system_prompt: str, messages: list[Message], **kwargs: Any
    ) -> LLMResponse:
        return LLMResponse(content=self.content, tool_calls=[])

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


class ScriptedAgent(BaseAgent):
    """Agent that returns pre-scripted actions by action_type, in order."""

    def __init__(self, pid: str, name: str, actions: dict[str, list[dict[str, Any]]]) -> None:
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

    async def decide_night_info(self, game_state: Any, player_id: str, role_id: str) -> dict:
        return {}

    async def narrate_phase(self, game_state: Any) -> str:
        return ""
