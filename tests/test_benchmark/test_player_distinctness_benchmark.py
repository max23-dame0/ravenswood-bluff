"""PLN-040 T1 行为指纹基准脚本单元测试。

验证 scripts/benchmark/player_distinctness_benchmark.py 的纯函数逻辑：
- 指纹聚合正确性（aggregate_player_fingerprint）
- 归一化与除零处理（_normalize）
- 欧氏距离计算（euclidean_distance）
- fallback 判定（_entry_is_fallback）
- 决策确定性判定（_entry_uncertain）

不跑完整 mock 对局（由基准脚本本身负责）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "benchmark" / "player_distinctness_benchmark.py"


@pytest.fixture(scope="module")
def bench() -> ModuleType:
    """加载基准脚本为模块（scripts 非包，用 spec 加载）。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("player_distinctness_benchmark", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# _entry_is_fallback / _entry_uncertain
# ---------------------------------------------------------------------------


def test_is_fallback_by_speech_source(bench) -> None:
    entry = {
        "action": {
            "action": "speak",
            "content": "我是好人",
            "speech_source": "fallback_after_timeout",
        }
    }
    assert bench._entry_is_fallback(entry) is True


def test_is_fallback_by_reason(bench) -> None:
    entry = {"action": {"action": "vote", "fallback_reason": "invalid_vote_decision"}}
    assert bench._entry_is_fallback(entry) is True


def test_is_fallback_by_flag(bench) -> None:
    entry = {"action": {"action": "vote", "fallback": True}}
    assert bench._entry_is_fallback(entry) is True


def test_not_fallback_draft_reuse(bench) -> None:
    # 草稿复用不是 fallback
    entry = {
        "action": {
            "action": "speak",
            "content": "复用草稿",
            "speech_source": "cache_finalized_draft_reuse",
        }
    }
    assert bench._entry_is_fallback(entry) is False


def test_entry_uncertain_detects_keywords(bench) -> None:
    entry = {"action": {"action": "vote", "decision": True, "reasoning": "无法判断，随意"}}
    assert bench._entry_uncertain(entry) is True


def test_entry_certain_when_no_keyword(bench) -> None:
    entry = {"action": {"action": "vote", "decision": True, "reasoning": "因为他首夜被刀"}}
    assert bench._entry_uncertain(entry) is False


# ---------------------------------------------------------------------------
# aggregate_player_fingerprint
# ---------------------------------------------------------------------------


def test_aggregate_counts_actions_by_type(bench) -> None:
    entries = [
        {
            "player_id": "p1",
            "action_type": "speak",
            "action": {"action": "speak", "content": "我是占卜师，p2 是坏人"},
            "usage": {"total_tokens": 100},
        },
        {
            "player_id": "p1",
            "action_type": "vote",
            "action": {"action": "vote", "decision": True},
        },
        {
            "player_id": "p1",
            "action_type": "vote",
            "action": {"action": "vote", "decision": False},
        },
        {
            "player_id": "p1",
            "action_type": "nomination_intent",
            "action": {"action": "nomination_intent"},
        },
        {
            "player_id": "p1",
            "action_type": "night_action",
            "action": {"action": "night_action"},
        },
    ]
    fp = bench.aggregate_player_fingerprint(entries, "p1")
    assert fp["speak_count"] == 1.0
    assert fp["vote_activity"] > 0
    assert fp["nomination_activity"] > 0
    assert fp["night_action_count"] == 1.0
    assert fp["vote_yes_rate"] == 0.5
    assert fp["speech_active_rate"] == 1.0


def test_aggregate_ignores_other_player(bench) -> None:
    entries = [
        {
            "player_id": "p2",
            "action_type": "speak",
            "action": {"action": "speak", "content": "p2 的发言"},
        }
    ]
    fp = bench.aggregate_player_fingerprint(entries, "p1")
    assert fp["speak_count"] == 0.0
    assert fp["avg_speech_len"] == 0.0


def test_aggregate_empty_speech_lowers_active_rate(bench) -> None:
    entries = [
        {
            "player_id": "p1",
            "action_type": "speak",
            "action": {"action": "speak", "content": ""},
        }
    ]
    fp = bench.aggregate_player_fingerprint(entries, "p1")
    assert fp["speech_active_rate"] == 0.0


def test_aggregate_speech_len_stats(bench) -> None:
    entries = [
        {
            "player_id": "p1",
            "action_type": "speak",
            "action": {"action": "speak", "content": "短"},
        },
        {
            "player_id": "p1",
            "action_type": "speak",
            "action": {"action": "speak", "content": "这是一条很长的发言用于测试长度统计"},
        },
    ]
    fp = bench.aggregate_player_fingerprint(entries, "p1")
    assert fp["speak_count"] == 2.0
    assert fp["avg_speech_len"] > 1.0
    assert fp["speech_len_var"] >= 0.0


def test_aggregate_tokens_and_reasoning(bench) -> None:
    entries = [
        {
            "player_id": "p1",
            "action_type": "vote",
            "action": {"action": "vote", "decision": True},
            "usage": {"total_tokens": 200},
            "thought": "因为他发言矛盾，选择投票",
        }
    ]
    fp = bench.aggregate_player_fingerprint(entries, "p1")
    assert fp["avg_total_tokens"] == 200.0
    assert fp["avg_reasoning_len"] > 0.0


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


def test_normalize_scales_to_max(bench) -> None:
    values = {"speak_count": 5.0, "avg_speech_len": 0.0}
    scale = {"speak_count": 10.0, "avg_speech_len": 1.0}
    norm = bench._normalize(values, scale)
    assert norm["speak_count"] == 0.5
    assert norm["avg_speech_len"] == 0.0


def test_normalize_zero_scale_no_div_zero(bench) -> None:
    values = {"speak_count": 0.0, "avg_speech_len": 0.0}
    scale = {"speak_count": 0.0, "avg_speech_len": 0.0}
    norm = bench._normalize(values, scale)
    assert norm["speak_count"] == 0.0
    assert norm["avg_speech_len"] == 0.0


def test_normalize_clamps_above_1(bench) -> None:
    values = {"speak_count": 15.0}
    scale = {"speak_count": 10.0}
    norm = bench._normalize(values, scale)
    assert norm["speak_count"] == 1.0


# ---------------------------------------------------------------------------
# euclidean_distance
# ---------------------------------------------------------------------------


def test_euclidean_same_vector_zero(bench) -> None:
    a = {dim: 0.5 for dim in bench.FINGERPRINT_DIMS}
    assert bench.euclidean_distance(a, dict(a)) == 0.0


def test_euclidean_opposite_one(bench) -> None:
    a = {dim: 0.0 for dim in bench.FINGERPRINT_DIMS}
    b = {dim: 1.0 for dim in bench.FINGERPRINT_DIMS}
    # 各维差 1，欧氏距离 sqrt(ndim) / sqrt(ndim) = 1.0
    assert bench.euclidean_distance(a, b) == 1.0


def test_euclidean_bounds(bench) -> None:
    a = {dim: 0.2 for dim in bench.FINGERPRINT_DIMS}
    b = {dim: 0.7 for dim in bench.FINGERPRINT_DIMS}
    d = bench.euclidean_distance(a, b)
    assert 0.0 <= d <= 1.0


def test_fingerprint_dims_span(bench) -> None:
    """指纹维度 ≥ 10（PLN-040 T1 DoD）。"""
    assert len(bench.FINGERPRINT_DIMS) >= 10
