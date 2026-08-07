"""PLN-040 T4 进化 A/B 基准脚本单元测试。

验证脚本纯函数逻辑：
- _player_win_rate 胜率计算（对阵胜负统计）
- _elo_mean 简化 Elo 计算
- GameOutcome 数据结构

不跑完整 mock 对局（由基准脚本本身负责）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "benchmark" / "evolution_ab_benchmark.py"


@pytest.fixture(scope="module")
def bench_mod() -> ModuleType:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location("evolution_ab_benchmark", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # 注册到 sys.modules：脚本含 @dataclass + `from __future__ import annotations`，
    # dataclass 处理字符串注解时需要 cls.__module__ 在 sys.modules 中可查。
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


def _outcome(
    bench_mod: ModuleType, winner: str, player_teams: list[str]
) -> object:
    return bench_mod.GameOutcome(
        game_id="g",
        winner=winner,
        winning_team=winner,
        players=[{"player_id": f"p{i}", "team": t} for i, t in enumerate(player_teams)],
    )


def test_win_rate_all_won(bench_mod) -> None:
    o = _outcome(bench_mod, "good", ["good", "good", "good", "evil", "evil"])
    rate, _ = bench_mod._player_win_rate([o])
    assert rate == 3 / 5


def test_win_rate_mixed_games(bench_mod) -> None:
    o1 = _outcome(bench_mod, "good", ["good", "good", "good", "evil", "evil"])
    o2 = _outcome(bench_mod, "evil", ["good", "good", "good", "evil", "evil"])
    rate, _ = bench_mod._player_win_rate([o1, o2])
    # 局1 good 赢（3 玩家胜）；局2 evil 赢（2 玩家胜）→ 5/10 = 0.5
    assert rate == 0.5


def test_win_rate_empty(bench_mod) -> None:
    rate, _ = bench_mod._player_win_rate([])
    assert rate == 0.0


def test_elo_starts_1500_and_updates(bench_mod) -> None:
    o = _outcome(bench_mod, "good", ["good", "good", "good", "evil", "evil"])
    # good 3 人 +10，evil 2 人 -10 → 均值应 > 1500（good 多 1 人）
    elo = bench_mod._elo_mean([o])
    assert elo > 1500.0


def test_elo_two_games_direction(bench_mod) -> None:
    o1 = _outcome(bench_mod, "good", ["good", "good", "good", "evil", "evil"])
    o2 = _outcome(bench_mod, "good", ["good", "good", "good", "evil", "evil"])
    assert bench_mod._elo_mean([o1, o2]) > bench_mod._elo_mean([o1])


def test_outcome_without_winner_ignored(bench_mod) -> None:
    o = bench_mod.GameOutcome(
        game_id="g", winner=None, winning_team="", players=[{"player_id": "p1", "team": "good"}]
    )
    rate, _ = bench_mod._player_win_rate([o])
    assert rate == 0.0
