"""T15: 玩家行动轨迹测试 — PLN-041 Phase 4。

验证：
- ActionTrace 追加式落盘 `data/agents/{player_id}/games/{game_id}/action_trace.jsonl`；
- mock 后端默认不落盘（无污染），BOTC_TRACE_ACTIONS=1 强制开启；
- AIAgent._record_action_metric 挂钩后自动记录。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from src.agents.workflow.action_trace import ActionTrace, trace_enabled_for
from src.llm.mock_backend import MockBackend
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import CapturingBackend

# 单测环境默认 mock：避免任何测试意外向 data/ 落盘 trace
os.environ.setdefault("BOTC_BACKEND", "mock")


def test_trace_disabled_by_default_for_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    assert not trace_enabled_for(MockBackend())


def test_trace_enabled_for_live_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "live")
    assert trace_enabled_for(MockBackend())


def test_trace_forced_on_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.setenv("BOTC_TRACE_ACTIONS", "1")
    assert trace_enabled_for(MockBackend())


def test_trace_forced_off_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "live")
    monkeypatch.setenv("BOTC_TRACE_ACTIONS", "0")
    assert not trace_enabled_for(MockBackend())


def test_trace_record_appends_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    trace = ActionTrace(player_id="p1", game_id="game-A", enabled=True)
    trace.record(
        {
            "player_id": "p1",
            "game_id": "game-A",
            "role_id": "imp",
            "phase": "DAY_DISCUSSION",
            "day_number": 1,
            "round_number": 2,
            "action_type": "speak",
            "model": "openai",
            "latency_ms": 120,
            "fallback_used": False,
            "speech_source": "llm",
        }
    )
    assert trace.path is not None
    assert trace.path.exists()
    lines = trace.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["player_id"] == "p1"
    assert entry["game_id"] == "game-A"
    assert entry["action_type"] == "speak"
    assert entry["latency_ms"] == 120


def test_trace_disabled_records_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    trace = ActionTrace(player_id="p1", game_id="game-A", enabled=False)
    trace.record({"action_type": "speak"})
    assert trace.path is None or not trace.path.exists()


def test_agent_records_trace_via_metric_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AIAgent 在 _record_action_metric 后自动落盘（BOTC_TRACE_ACTIONS=1 强制）。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_TRACE_ACTIONS", "1")
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-trace")
    state = GameState(
        game_id="game-trace",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    agent._record_action_metric(visible, "speak", model="capturing", latency_ms=50)
    trace_path = tmp_path / "agents" / "p1" / "games" / "game-trace" / "action_trace.jsonl"
    assert trace_path.exists()
    entry = json.loads(trace_path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert entry["action_type"] == "speak"
    assert entry["player_id"] == "p1"


def test_agent_mock_no_trace_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """mock 后端默认不落盘（对齐 thoughts.jsonl 约定，避免污染）。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-trace")
    state = GameState(
        game_id="game-trace",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),),
    )
    visible = agent._build_visible_state(state)
    agent._record_action_metric(visible, "speak", model="capturing")
    trace_path = tmp_path / "agents" / "p1" / "games" / "game-trace" / "action_trace.jsonl"
    assert not trace_path.exists()
