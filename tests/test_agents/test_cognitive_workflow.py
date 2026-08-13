"""T3: 认知工作流测试 — PLN-042。

覆盖：
- recall→reason→speak→record 节点声明完整；
- 执行产出观点（Claim）与发言；
- 无证据断言被门控拦截（置信度不足时降级表述）；
- 观点落盘（仅 live / 强制开启）；
- trace 落盘可回放。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.reasoning.viewpoint import ViewpointStore
from src.agents.workflow.cognitive_workflow import (
    build_cognitive_speech_workflow,
    run_cognitive_speech,
)


class _FakeAgent:
    """最小 agent 替身：只提供认知工作流需要的属性。"""

    def __init__(self, memory=None, name="Alice", player_id="p1") -> None:
        self.name = name
        self.player_id = player_id
        self.role_id = "washerwoman"
        self.team = "good"
        self.memory = memory or {
            "hard": ["高可信信息：P2 可能是恶魔（占卜师指出）"],
            "soft": ["公开信息：P3 说 P2 很可疑"],
        }
        self._viewpoint_store: ViewpointStore | None = None

    def build_memory_snapshot(self) -> dict[str, list[str]]:
        return self.memory

    def get_viewpoint_store(self) -> ViewpointStore | None:
        return self._viewpoint_store

    def set_viewpoint_store(self, store: ViewpointStore) -> None:
        self._viewpoint_store = store


def test_workflow_declares_cognitive_nodes() -> None:
    agent = _FakeAgent()
    wf = build_cognitive_speech_workflow(agent)
    tool_names = {n.tool_name for n in wf.nodes}
    assert {"recall", "reason", "speak", "record"} <= tool_names


@pytest.mark.asyncio
async def test_run_cognitive_speech_produces_claim_and_speech(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _FakeAgent()
    store = ViewpointStore(player_id="p1", game_id="game-cog", enabled=True)
    agent.set_viewpoint_store(store)
    result = await run_cognitive_speech(
        agent,
        player_id="p1",
        visible_state=None,
        context={"day_number": 1, "round_number": 1, "action_type": "speak"},
    )
    assert "claim" in result
    assert result["claim"]
    assert "content" in result
    assert result["content"]


@pytest.mark.asyncio
async def test_run_cognitive_speech_persists_viewpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _FakeAgent()
    store = ViewpointStore(player_id="p1", game_id="game-cog", enabled=True)
    agent.set_viewpoint_store(store)
    await run_cognitive_speech(
        agent,
        player_id="p1",
        visible_state=None,
        context={
            "day_number": 1,
            "round_number": 1,
            "action_type": "speak",
            "subject_player_id": "p2",
            "subject_name": "Bob",
        },
    )
    assert store.path is not None
    assert store.path.exists()
    raw = json.loads(store.path.read_text(encoding="utf-8").strip().splitlines()[0])
    assert raw["subject_player_id"] == "p2"
    assert raw["confidence"] >= 0.5


@pytest.mark.asyncio
async def test_run_cognitive_speech_trace_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _FakeAgent()
    store = ViewpointStore(player_id="p1", game_id="game-cog", enabled=True)
    agent.set_viewpoint_store(store)
    result = await run_cognitive_speech(
        agent,
        player_id="p1",
        visible_state=None,
        context={"day_number": 1, "round_number": 1, "action_type": "speak"},
    )
    trace_path = result.get("trace_path")
    assert trace_path is not None
    assert Path(trace_path).exists()
    raw = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    assert raw["workflow_id"] == "cognitive_speech"
    events = [e["event"] for e in raw["entries"]]
    assert events[0] == "start"
    assert events[-1] == "finish"
    assert "node" in events


@pytest.mark.asyncio
async def test_no_evidence_claim_gets_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """纯软印象（无硬证据）的强断言必须被降级（"一定是"→"可能"）。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    agent = _FakeAgent(memory={"hard": [], "soft": ["公开信息：P3 说 P2 很可疑"]})
    store = ViewpointStore(player_id="p1", game_id="game-cog", enabled=True)
    agent.set_viewpoint_store(store)
    result = await run_cognitive_speech(
        agent,
        player_id="p1",
        visible_state=None,
        context={
            "day_number": 1,
            "round_number": 1,
            "action_type": "speak",
            "claim": "P2 一定是恶魔",
            "subject_player_id": "p2",
            "subject_name": "Bob",
        },
    )
    claim = result["claim"]
    assert "一定" not in claim
    assert "可能" in claim


@pytest.mark.asyncio
async def test_cognitive_disabled_without_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 viewpoint store（mock 默认）时返回 None，不产生任何文件。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.delenv("BOTC_VIEWPOINTS", raising=False)
    agent = _FakeAgent()
    result = await run_cognitive_speech(
        agent,
        player_id="p1",
        visible_state=None,
        context={"day_number": 1, "round_number": 1, "action_type": "speak"},
    )
    assert result is None
    assert not list(Path(tmp_path).rglob("viewpoints.jsonl"))
