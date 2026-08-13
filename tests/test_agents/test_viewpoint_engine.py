"""T2: 证据提取与置信度引擎测试 — PLN-042。

覆盖：
- 从工作记忆分类提取 hard/soft 证据；
- 置信度计算（硬证据高权重、软证据低权重、封顶 0.95）；
- 观点演化（新证据更新 / 冲突废弃）；
- 无证据断言置信度 < 门控阈值。
"""

from __future__ import annotations

from src.agents.reasoning.viewpoint_engine import (
    CONFLICT_BAY,
    MIN_GATE_CONFIDENCE,
    ViewpointEngine,
    classify_evidence,
    compute_confidence,
)


def test_classify_hard_evidence_sources() -> None:
    hard_sources = [
        "fortune_teller_info",
        "investigator_info",
        "empath_info",
        "chef_info",
        "revealed_role",
        "demon_candidate",
        "evil_teammates",
        "role_candidate_hint",
    ]
    for source in hard_sources:
        assert classify_evidence(source) == "hard"


def test_classify_soft_evidence_sources() -> None:
    soft_sources = ["role_claim", "public_claim", "observation", "impression"]
    for source in soft_sources:
        assert classify_evidence(source) == "soft"


def test_compute_confidence_hard_only() -> None:
    conf = compute_confidence(hard_count=2, soft_count=0)
    assert conf >= 0.6


def test_compute_confidence_soft_only_below_gate() -> None:
    conf = compute_confidence(hard_count=0, soft_count=1)
    assert conf < MIN_GATE_CONFIDENCE


def test_compute_confidence_caps_at_max() -> None:
    conf = compute_confidence(hard_count=10, soft_count=10)
    assert conf <= 0.95


def test_compute_confidence_monotonic() -> None:
    assert compute_confidence(3, 0) > compute_confidence(1, 0)
    assert compute_confidence(1, 2) > compute_confidence(1, 0)


def test_engine_extracts_evidence_from_memory() -> None:
    """P1-1 修复后：一条 hard 文本只产生一条 Evidence（不再被 8 个来源名重复标记）。"""
    memory = {
        "hard": ["高可信信息：P2 可能是恶魔（占卜师指出）", "客观信息：P2 是队友"],
        "soft": ["公开信息：P3 说 P2 很可疑", "P2 最近自报占卜师"],
    }
    engine = ViewpointEngine()
    evidence = engine.extract_evidence(memory)
    hard = [e for e in evidence if e.kind == "hard"]
    soft = [e for e in evidence if e.kind == "soft"]
    assert len(hard) == 2
    assert len(soft) == 2
    # source 统一为 "hard_memory"，不再伪造为 8 个具体来源名
    assert all(e.source == "hard_memory" for e in hard)
    assert all(e.source == "public_claim" for e in soft)


def test_single_hard_evidence_confidence_not_capped() -> None:
    """P1-1 修复后：单条硬证据置信度 ≈ 0.52，不再因 ×8 虚高封顶 0.95。"""
    memory = {"hard": ["高可信信息：P2 可能是恶魔（占卜师指出）"], "soft": []}
    engine = ViewpointEngine()
    evidence = engine.extract_evidence(memory)
    conf = compute_confidence(
        hard_count=sum(1 for e in evidence if e.kind == "hard"),
        soft_count=sum(1 for e in evidence if e.kind == "soft"),
    )
    assert 0.4 <= conf <= 0.6


def test_engine_builds_viewpoint_with_confidence() -> None:
    memory = {
        "hard": ["高可信信息：P2 可能是恶魔（占卜师指出）"],
        "soft": ["公开信息：P3 说 P2 很可疑"],
    }
    engine = ViewpointEngine()
    vp = engine.build_viewpoint(
        subject_player_id="p2",
        subject_name="Bob",
        claim="P2 可能是恶魔",
        memory=memory,
        source_action="speak",
        day_number=2,
        round_number=1,
    )
    assert vp is not None
    assert vp.confidence >= 0.5
    assert any(e.kind == "hard" for e in vp.evidence)


def test_engine_viewpoint_without_hard_evidence_below_gate() -> None:
    memory = {"hard": [], "soft": ["公开信息：P3 说 P2 很可疑"]}
    engine = ViewpointEngine()
    vp = engine.build_viewpoint(
        subject_player_id="p2",
        subject_name="Bob",
        claim="P2 一定是恶魔",
        memory=memory,
        source_action="speak",
        day_number=2,
        round_number=1,
    )
    assert vp is not None
    assert vp.confidence < MIN_GATE_CONFIDENCE


def test_engine_confidence_gate_constants() -> None:
    assert CONFLICT_BAY == 0.2
    assert MIN_GATE_CONFIDENCE == 0.45


def test_gate_requires_hard_evidence() -> None:
    """P1-2 修复后：门控由 hard_count 判定，纯软印象一律拦截。"""
    engine = ViewpointEngine()
    assert engine.passes_gate(hard_count=1, soft_count=0)
    assert engine.passes_gate(hard_count=2, soft_count=3)
    # 关键：≥2 条软印象置信度数值会越过 0.45，但门控仍必须拦截
    assert not engine.passes_gate(hard_count=0, soft_count=1)
    assert not engine.passes_gate(hard_count=0, soft_count=2)
    assert not engine.passes_gate(hard_count=0, soft_count=10)


def test_two_soft_impressions_conf_exceeds_threshold_but_gate_blocks() -> None:
    """P1-2 修复：soft=2 时 conf=0.47 ≥ 0.45，数值越过阈值但门控仍按 hard 判定拦截。"""
    conf = compute_confidence(hard_count=0, soft_count=2)
    assert conf >= MIN_GATE_CONFIDENCE
    assert not ViewpointEngine.passes_gate(hard_count=0, soft_count=2)
