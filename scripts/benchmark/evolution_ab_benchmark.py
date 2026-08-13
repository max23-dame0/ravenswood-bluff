"""进化有效性 A/B 基准（PLN-040 T4）。

验证"进化机制是否让 AI 玩家真的变强"（M4：进化 K 局后 vs 冷启动的胜率/Elo 差分）：

- **对照组（冷启动）**：BOTC_DATA_DIR 指向空目录，无任何跨局档案，跑 N 局测试局统计胜率。
- **实验组（进化 K 局）**：先跑 K 局完整 mock 局（game_over 触发 _finalize_agent_player_profiles
  落盘 profile/经验/倾向），再跑 N 局测试局统计胜率。
- 进化链路：进化局 → finalize_game_review 微调 tendency（BOTC_TENDENCY_STEP 可放大）
  → tendency >=0.65 覆盖 persona 标签 → 本地判定路径 threshold 变化 → 行为/胜率变化。

指标（M4）：
- 胜率差分：进化组均值胜率 - 冷启动组均值胜率（目标 +5pp）
- Elo 差分：两组玩家简单 Elo（胜+10/负-10），对比均值（目标 +25）

用法：
  python scripts/benchmark/evolution_ab_benchmark.py --evolve-games 10 --test-games 20 --player-count 5 --seed 42
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 程序化对局循环（不依赖 run_simulation 的 print-only 流程）
# ---------------------------------------------------------------------------


@dataclass
class GameOutcome:
    game_id: str
    winner: str | None
    winning_team: str | None
    players: list[dict[str, Any]]


async def _play_full_game(
    player_count: int,
    seed: int,
    timeout: int = 120,
    audit: bool = True,
) -> GameOutcome:
    """跑一局完整 mock 对局到 game_over，返回胜负与玩家明细。"""
    import random as _random

    from src.agents.storyteller_agent import StorytellerAgent
    from src.llm.mock_backend import MockBackend
    from src.orchestrator.game_loop import GameOrchestrator
    from src.state.game_state import GamePhase, GameState

    _random.seed(seed)
    backend = MockBackend()
    state = GameState(phase=GamePhase.SETUP)
    orchestrator = GameOrchestrator(state)
    storyteller = StorytellerAgent(backend)
    orchestrator.storyteller_agent = storyteller
    orchestrator.default_agent_backend = backend

    loop_task = asyncio.create_task(orchestrator.run_game_loop())
    try:
        await asyncio.sleep(0.2)
        await orchestrator.run_setup_with_options(
            player_count=player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=1,
            storyteller_mode="auto",
            audit_mode=audit,
            max_nomination_rounds=2,
            backend_mode="mock",
        )
        try:
            await asyncio.wait_for(loop_task, timeout=timeout)
        except TimeoutError:
            if not loop_task.done():
                loop_task.cancel()
            with __import__("contextlib").suppress(asyncio.CancelledError):
                await loop_task
    finally:
        pass

    winner = orchestrator.winner
    report = orchestrator.settlement_report or {}
    return GameOutcome(
        game_id=orchestrator.state.game_id,
        winner=winner.value if winner else None,
        winning_team=str(report.get("winning_team", "") or ""),
        players=[
            {
                "player_id": p.get("player_id"),
                "team": str(p.get("team", "")).lower(),
            }
            for p in report.get("players", [])
        ],
    )


# ---------------------------------------------------------------------------
# 档案预置与目录隔离
# ---------------------------------------------------------------------------


def _fresh_data_dir(tmp_root: Path, name: str) -> Path:
    """创建并返回隔离的 BOTC_DATA_DIR（删除残留）。"""
    d = tmp_root / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _set_env(data_dir: Path, seed: int) -> None:
    os.environ["BOTC_DATA_DIR"] = str(data_dir)
    # 与 T3 标定一致：走本地判定路径，tendency 阈值真实生效（方案 3）
    os.environ["AI_FAST_LOW_VALUE_ACTIONS"] = "1"
    os.environ.pop("AI_FORCE_PROGRESS_ACTIONS", None)
    # 进化步长（默认 ±0.02；可调大加速进化到 0.65 覆盖阈值的局数）
    os.environ.setdefault("BOTC_TENDENCY_STEP", "0.02")


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def _player_win_rate(outcomes: list[GameOutcome]) -> tuple[float, float]:
    """返回（总胜率, 平均玩家胜率）。"""
    if not outcomes:
        return 0.0, 0.0
    won_count = 0
    total = 0
    for o in outcomes:
        if not o.winning_team:
            continue
        for p in o.players:
            total += 1
            if p.get("team") == o.winning_team:
                won_count += 1
    rate = (won_count / total) if total else 0.0
    return rate, rate


def _elo_mean(outcomes: list[GameOutcome]) -> float:
    """简化 Elo：每玩家从 1500 起，胜 +10 / 负 -10，返回平均值。"""
    if not outcomes:
        return 1500.0
    elo: dict[str, float] = {}
    for o in outcomes:
        if not o.winning_team:
            continue
        for p in o.players:
            pid = p.get("player_id")
            elo.setdefault(pid, 1500.0)
            won = p.get("team") == o.winning_team
            elo[pid] += 10.0 if won else -10.0
    return round(sum(elo.values()) / len(elo), 1) if elo else 1500.0


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def _run_group(
    data_dir: Path,
    name: str,
    *,
    test_games: int,
    player_count: int,
    seed_base: int,
    timeout: int,
    fresh_each_game: bool = False,
) -> list[GameOutcome]:
    """跑一组测试局。

    fresh_each_game=True 时每局前清空档案目录——用于对照组（冷启动）隔离：
    每局结束的 _finalize_agent_player_profiles 会写档案，若不清理则对照组
    在测试过程中也在"进化"，削弱冷/热启动对照纯度。
    """
    _set_env(data_dir, seed_base)
    outcomes: list[GameOutcome] = []
    for i in range(test_games):
        if fresh_each_game:
            _fresh_data_dir(data_dir, "agents")
        print(f"  [{name}] 测试局 {i + 1}/{test_games}...")
        outcomes.append(
            await _play_full_game(player_count=player_count, seed=seed_base + i, timeout=timeout)
        )
    return outcomes


async def _run_evolution(
    data_dir: Path,
    *,
    evolve_games: int,
    player_count: int,
    seed_base: int,
    timeout: int,
) -> None:
    """跑 K 局完整局让玩家进化（触发 finalize_game_review 落盘 profile）。"""
    _set_env(data_dir, seed_base)
    for i in range(evolve_games):
        print(f"  [进化] 局 {i + 1}/{evolve_games}...")
        await _play_full_game(player_count=player_count, seed=seed_base + i, timeout=timeout)


def run_ab(
    evolve_games: int = 10,
    test_games: int = 20,
    player_count: int = 5,
    seed: int = 42,
    timeout: int = 120,
) -> dict[str, Any]:
    tmp_root = Path("tmp_work/evolution_ab")
    control_dir = _fresh_data_dir(tmp_root, "control")
    evolved_dir = _fresh_data_dir(tmp_root, "evolved")

    print("\n=== 对照组（冷启动，每局前清空档案） ===")
    control_outcomes = asyncio.run(
        _run_group(
            control_dir,
            "control",
            test_games=test_games,
            player_count=player_count,
            seed_base=seed,
            timeout=timeout,
            fresh_each_game=True,
        )
    )

    print("\n=== 实验组（先进化 K 局，再测试） ===")
    asyncio.run(
        _run_evolution(
            evolved_dir,
            evolve_games=evolve_games,
            player_count=player_count,
            seed_base=seed,
            timeout=timeout,
        )
    )
    # 实验组测试期保留进化档案（不清理），验证进化注入的持续效果
    evolved_outcomes = asyncio.run(
        _run_group(
            evolved_dir,
            "evolved",
            test_games=test_games,
            player_count=player_count,
            seed_base=seed,
            timeout=timeout,
            fresh_each_game=False,
        )
    )

    control_win, _ = _player_win_rate(control_outcomes)
    evolved_win, _ = _player_win_rate(evolved_outcomes)
    control_elo = _elo_mean(control_outcomes)
    evolved_elo = _elo_mean(evolved_outcomes)

    return {
        "meta": {
            "plan": "PLN-040 T4",
            "evolve_games": evolve_games,
            "test_games": test_games,
            "player_count": player_count,
            "seed": seed,
        },
        "control": {
            "games": len(control_outcomes),
            "player_win_rate": round(control_win, 4),
            "elo_mean": control_elo,
            "finished_games": sum(1 for o in control_outcomes if o.winning_team),
        },
        "evolved": {
            "games": len(evolved_outcomes),
            "player_win_rate": round(evolved_win, 4),
            "elo_mean": evolved_elo,
            "finished_games": sum(1 for o in evolved_outcomes if o.winning_team),
        },
        "delta": {
            "win_rate_pp": round((evolved_win - control_win) * 100, 2),
            "elo": round(evolved_elo - control_elo, 1),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="进化有效性 A/B 基准（PLN-040 T4）")
    parser.add_argument("--evolve-games", type=int, default=10, help="进化局数 K（默认 10）")
    parser.add_argument("--test-games", type=int, default=20, help="测试局数 N（默认 20）")
    parser.add_argument("--player-count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    report = run_ab(
        evolve_games=args.evolve_games,
        test_games=args.test_games,
        player_count=args.player_count,
        seed=args.seed,
        timeout=args.timeout,
    )

    print("\n" + "=" * 60)
    print("进化有效性 A/B 基准（PLN-040 T4）")
    print("=" * 60)
    c, e, d = report["control"], report["evolved"], report["delta"]
    print(
        f"  对照组（冷启动）: 胜率 {c['player_win_rate']:.2%}  Elo {c['elo_mean']}  (局 {c['finished_games']}/{c['games']})"
    )
    print(
        f"  实验组（进化 K={report['meta']['evolve_games']}）: 胜率 {e['player_win_rate']:.2%}  Elo {e['elo_mean']}  (局 {e['finished_games']}/{e['games']})"
    )
    print(f"  胜率差分: {d['win_rate_pp']:+.2f}pp  Elo 差分: {d['elo']:+.1f}")
    verdict = "PASS" if d["win_rate_pp"] >= 5.0 or d["elo"] >= 25.0 else "FAIL"
    print(
        f"  结论: [{'PASS' if verdict == 'PASS' else 'FAIL'}]  "
        + ("进化组显著优于冷启动" if verdict == "PASS" else "进化未显著提升（输出诊断）")
    )
    print("=" * 60 + "\n")

    out_path = Path("tmp_work/evolution_ab_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        __import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"报告已写入: {out_path}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
