"""PLN-040 T5 盲测样本导出脚本单元测试。

验证纯函数逻辑：
- _anonymize 匿名映射
- score_labels 猜中率统计（M3：>20% 随机基线，样本量 >= 30）

不跑完整 mock 对局（由导出脚本本身负责）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "export" / "export_blind_test_samples.py"


@pytest.fixture(scope="module")
def exp() -> ModuleType:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("export_blind_test_samples", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# _anonymize
# ---------------------------------------------------------------------------


def test_anonymize_maps_sorted(exp) -> None:
    mapping = exp._anonymize(["p3", "p1", "p2"])
    assert mapping == {"p1": "P1", "p2": "P2", "p3": "P3"}


def test_anonymize_deterministic(exp) -> None:
    assert exp._anonymize(["p2", "p1"]) == exp._anonymize(["p1", "p2"])


# ---------------------------------------------------------------------------
# score_labels
# ---------------------------------------------------------------------------


def _write_samples(tmp_path: Path, n_per_player: int = 5) -> Path:
    samples = {
        "meta": {"random_baseline": 0.2},
        "samples": [
            {"sample_id": f"g1_{p}_{i}", "anon_player": p.upper()}
            for p in ("p1", "p2", "p3", "p4", "p5")
            for i in range(n_per_player)
        ],
    }
    path = tmp_path / "samples.json"
    path.write_text(json.dumps(samples), encoding="utf-8")
    return path


def _write_labels(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "labels.tsv"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_score_all_correct_pass(tmp_path, exp) -> None:
    samples_path = _write_samples(tmp_path, n_per_player=7)  # 35 条 ≥ 30
    lines = [f"g1_{p}_{i}\t{p.upper()}" for p in ("p1", "p2", "p3", "p4", "p5") for i in range(7)]
    labels_path = _write_labels(tmp_path, lines)
    result = exp.score_labels(samples_path, labels_path)
    assert result["total_labels"] == 35
    assert result["correct"] == 35
    assert result["guess_rate"] == 1.0
    assert result["verdict"] == "PASS"


def test_score_random_guess_fail(tmp_path, exp) -> None:
    """25 条标注、全猜错 → guess_rate=0 且样本量不足 30 → FAIL。"""
    samples_path = _write_samples(tmp_path)
    lines = [f"g1_{p}_{i}\tP1" if p != "p1" else f"g1_{p}_{i}\tP2" for p in ("p1", "p2", "p3", "p4", "p5") for i in range(5)]
    labels_path = _write_labels(tmp_path, lines)
    result = exp.score_labels(samples_path, labels_path)
    assert result["total_labels"] == 25
    assert result["guess_rate"] < 1.0
    # 样本量 < 30 → FAIL（M3 要求 >= 30）
    assert result["verdict"] == "FAIL"


def test_score_requires_30_min(tmp_path, exp) -> None:
    """即使全对，样本量不足 30 也 FAIL（M3 门槛）。"""
    samples_path = _write_samples(tmp_path, n_per_player=4)  # 20 条
    lines = [f"g1_{p}_{i}\t{p.upper()}" for p in ("p1", "p2", "p3", "p4", "p5") for i in range(4)]
    labels_path = _write_labels(tmp_path, lines)
    result = exp.score_labels(samples_path, labels_path)
    assert result["total_labels"] == 20
    assert result["verdict"] == "FAIL"  # 样本量不足


def test_score_30_plus_high_rate_pass(tmp_path, exp) -> None:
    """30+ 条标注且 >20% 猜中率 → PASS。"""
    samples_path = _write_samples(tmp_path, n_per_player=7)  # 35 条
    lines = [f"g1_{p}_{i}\t{p.upper()}" for p in ("p1", "p2", "p3", "p4", "p5") for i in range(7)]
    labels_path = _write_labels(tmp_path, lines)
    result = exp.score_labels(samples_path, labels_path)
    assert result["total_labels"] == 35
    assert result["guess_rate"] == 1.0
    assert result["verdict"] == "PASS"


def test_score_ignores_blank_lines(tmp_path, exp) -> None:
    samples_path = _write_samples(tmp_path, n_per_player=6)
    lines = [f"g1_{p}_{i}\t{p.upper()}" for p in ("p1", "p2", "p3") for i in range(6)]
    lines += ["", "g1_p4_0\t", "invalid_no_tab"]
    labels_path = _write_labels(tmp_path, lines)
    result = exp.score_labels(samples_path, labels_path)
    assert result["total_labels"] == 18
