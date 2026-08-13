"""T1: 观点-证据模型测试 — PLN-042。

覆盖：
- Evidence/Viewpoint 数据类字段与分级；
- ViewpointStore JSONL 落盘/加载往返；
- 激活观点查询与摘要构建；
- 仅 live 落盘（mock 零污染）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.reasoning.viewpoint import (
    Evidence,
    Viewpoint,
    ViewpointStore,
    viewpoint_enabled,
)


def _evidence(kind: str = "hard", detail: str = "说书人指出 P2 可能是恶魔") -> Evidence:
    return Evidence(
        kind=kind, source="fortune_teller_info", detail=detail, day_number=1, round_number=1
    )


def test_evidence_fields() -> None:
    ev = _evidence()
    assert ev.kind == "hard"
    assert ev.source == "fortune_teller_info"
    assert ev.day_number == 1


def test_viewpoint_fields() -> None:
    vp = Viewpoint(
        viewpoint_id="vp-1",
        subject_player_id="p2",
        subject_name="Bob",
        claim="P2 可能是恶魔",
        evidence=[_evidence()],
        confidence=0.7,
        status="active",
        source_action="speak",
        day_number=1,
        round_number=1,
    )
    assert vp.status == "active"
    assert vp.confidence == 0.7
    assert len(vp.evidence) == 1


def test_viewpoint_supersede() -> None:
    vp = Viewpoint(
        viewpoint_id="vp-1",
        subject_player_id="p2",
        subject_name="Bob",
        claim="P2 可能是恶魔",
        evidence=[_evidence()],
        confidence=0.7,
        status="active",
        source_action="speak",
        day_number=1,
        round_number=1,
    )
    vp.mark_superseded()
    assert vp.status == "superseded"


def test_store_add_and_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = ViewpointStore(player_id="p1", game_id="game-A", enabled=True)
    store.add_viewpoint(
        subject_player_id="p2",
        subject_name="Bob",
        claim="P2 可能是恶魔",
        evidence=[_evidence()],
        confidence=0.7,
        source_action="speak",
        day_number=1,
        round_number=1,
    )
    assert store.path is not None
    assert store.path.exists()
    lines = store.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    raw = json.loads(lines[0])
    assert raw["claim"] == "P2 可能是恶魔"
    assert raw["status"] == "active"
    assert raw["evidence"][0]["kind"] == "hard"


def test_store_active_viewpoints_only() -> None:
    store = ViewpointStore.__new__(ViewpointStore)
    store._viewpoints = [
        Viewpoint(
            viewpoint_id="a",
            subject_player_id="p2",
            subject_name="Bob",
            claim="A",
            evidence=[],
            confidence=0.6,
            status="active",
            source_action="speak",
            day_number=1,
            round_number=1,
        ),
        Viewpoint(
            viewpoint_id="b",
            subject_player_id="p3",
            subject_name="Cathy",
            claim="B",
            evidence=[],
            confidence=0.5,
            status="superseded",
            source_action="speak",
            day_number=1,
            round_number=1,
        ),
    ]
    active = store.get_active_viewpoints()
    assert len(active) == 1
    assert active[0].viewpoint_id == "a"


def test_store_build_summary_contains_claims() -> None:
    store = ViewpointStore.__new__(ViewpointStore)
    store._viewpoints = [
        Viewpoint(
            viewpoint_id="a",
            subject_player_id="p2",
            subject_name="Bob",
            claim="P2 可能是恶魔",
            evidence=[
                Evidence(
                    kind="hard",
                    source="fortune_teller_info",
                    detail="指出 P2",
                    day_number=1,
                    round_number=1,
                ),
                Evidence(
                    kind="soft",
                    source="public_claim",
                    detail="Cathy 说 P2 可疑",
                    day_number=1,
                    round_number=1,
                ),
            ],
            confidence=0.7,
            status="active",
            source_action="speak",
            day_number=1,
            round_number=1,
        )
    ]
    summary = store.build_summary()
    assert "P2 可能是恶魔" in summary
    assert "0.7" in summary
    assert "硬证据" in summary
    assert "软印象" in summary


def test_viewpoint_enabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    assert viewpoint_enabled()
    monkeypatch.setenv("BOTC_VIEWPOINTS", "0")
    assert not viewpoint_enabled()


def test_viewpoint_disabled_mock_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.delenv("BOTC_VIEWPOINTS", raising=False)
    assert not viewpoint_enabled()


def test_viewpoint_enabled_live_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_BACKEND", "live")
    monkeypatch.delenv("BOTC_VIEWPOINTS", raising=False)
    assert viewpoint_enabled()
