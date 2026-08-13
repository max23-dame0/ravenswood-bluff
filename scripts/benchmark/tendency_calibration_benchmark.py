"""tendency 标定实验（PLN-040 T3 M5）。

验证"tendency 差异化是否真实改变 AI 玩家行为指纹"：
- 场景 A（baseline）：所有玩家 tendency 默认 0.5（均衡）
- 场景 B（polarized）：一半激进（aggression/talkativeness/risk 高），一半保守（caution 高）
- 场景 C（mixed）：每玩家倾向随机（带种子）

对每场景跑 N 局 mock 对局，用 T1 指纹基准计算组内两两距离，
输出 mean/max/min 距离对比 —— 若 B/C 显著大于 A，则 tendency 差异化生效。

用法：
  python scripts/benchmark/tendency_calibration_benchmark.py --games 3 --player-count 8 --seed 42
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_t1() -> Any:
    """加载 T1 行为指纹基准脚本模块（scripts 非包，用 spec）。"""
    spec = importlib.util.spec_from_file_location(
        "player_distinctness_benchmark",
        REPO_ROOT / "scripts" / "benchmark" / "player_distinctness_benchmark.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _preset_tendencies(
    player_ids: list[str], scenario: str, rng: random.Random
) -> dict[str, dict[str, float]]:
    """按场景为每个玩家生成 tendency 四维。"""
    presets: dict[str, dict[str, float]] = {}
    for idx, pid in enumerate(player_ids):
        if scenario == "baseline":
            presets[pid] = {
                "aggression": 0.5,
                "risk_taking": 0.5,
                "talkativeness": 0.5,
                "caution": 0.5,
            }
        elif scenario == "polarized":
            if idx % 2 == 0:
                presets[pid] = {
                    "aggression": 0.85,
                    "risk_taking": 0.8,
                    "talkativeness": 0.85,
                    "caution": 0.2,
                }
            else:
                presets[pid] = {
                    "aggression": 0.2,
                    "risk_taking": 0.2,
                    "talkativeness": 0.25,
                    "caution": 0.9,
                }
        elif scenario == "mixed":
            presets[pid] = {
                "aggression": round(rng.uniform(0.05, 0.95), 3),
                "risk_taking": round(rng.uniform(0.05, 0.95), 3),
                "talkativeness": round(rng.uniform(0.05, 0.95), 3),
                "caution": round(rng.uniform(0.05, 0.95), 3),
            }
    return presets


def _write_profiles(tmp_data_dir: Path, presets: dict[str, dict[str, float]]) -> None:
    """把 tendency 预置写入 data/agents/{pid}/profile/profile.json（临时 BOTC_DATA_DIR）。"""
    for pid, tendency in presets.items():
        profile_dir = tmp_data_dir / "agents" / pid / "profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile = {
            "player_id": pid,
            "games_played": 5,
            "wins": 3,
            "losses": 2,
            "tendency": tendency,
        }
        (profile_dir / "profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def _run_scenario(
    t1: Any,
    scenario: str,
    games: int,
    player_count: int,
    seed: int,
    tmp_data_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    """跑一个场景，返回指纹距离统计。"""
    import os

    rng = random.Random(seed)
    player_ids = [f"p{i}" for i in range(1, player_count + 1)]
    presets = _preset_tendencies(player_ids, scenario, rng)
    _write_profiles(tmp_data_dir, presets)

    os.environ["BOTC_DATA_DIR"] = str(tmp_data_dir)
    # T3.5 方案 3：复现 live 判定路径——vote/nomination 走本地启发式
    # （local_low_value_decision 消费 tendency 影响的 threshold；与
    # simulate_game live 模式 AI_FAST_LOW_VALUE_ACTIONS=1 行为一致）。
    # 注意：不设 AI_FORCE_PROGRESS_ACTIONS（那会强制 vote=True 覆盖 tendency 信号）。
    os.environ["AI_FAST_LOW_VALUE_ACTIONS"] = "1"
    report = t1.run_benchmark(
        games=games,
        player_count=player_count,
        seed=seed,
        timeout=timeout,
        audit=True,
        out_dir=str(tmp_data_dir / "bench"),
    )
    return {
        "scenario": scenario,
        "mean_distance": report["distance_summary"]["mean_distance"],
        "max_distance": report["distance_summary"]["max_distance"],
        "min_distance": report["distance_summary"]["min_distance"],
        "pair_count": report["distance_summary"]["pair_count"],
        "stability_mean": round(
            sum(report["stability"].values()) / max(1, len(report["stability"])), 4
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="tendency 标定实验（PLN-040 T3 M5）")
    parser.add_argument("--games", type=int, default=3, help="每场景 mock 对局数（默认 3）")
    parser.add_argument("--player-count", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    t1 = _load_t1()
    tmp_data_dir = Path("tmp_work/t3_calibration")
    tmp_data_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for scenario in ("baseline", "polarized", "mixed"):
        print(f"\n>>> 场景 {scenario}: 跑 {args.games} 局 mock...")
        try:
            results.append(
                _run_scenario(
                    t1,
                    scenario,
                    args.games,
                    args.player_count,
                    args.seed,
                    tmp_data_dir,
                    args.timeout,
                )
            )
        except Exception as exc:
            print(f"  场景 {scenario} 失败: {exc}")
            results.append({"scenario": scenario, "error": str(exc)})

    print("\n" + "=" * 60)
    print("tendency 标定实验结果（M5）")
    print("=" * 60)
    for r in results:
        if "error" in r:
            print(f"  {r['scenario']}: ERROR {r['error']}")
        else:
            print(
                f"  {r['scenario']:<10} mean={r['mean_distance']:.4f}  "
                f"max={r['max_distance']:.4f}  min={r['min_distance']:.4f}  "
                f"stability_mean={r['stability_mean']:.4f}  (pairs={r['pair_count']})"
            )
    # 结论判断
    stats = {r["scenario"]: r for r in results if "error" not in r}
    if {"baseline", "polarized", "mixed"} <= set(stats):
        base = stats["baseline"]["mean_distance"]
        pol = stats["polarized"]["mean_distance"]
        mix = stats["mixed"]["mean_distance"]
        print("-" * 60)
        print(f"  基线(均衡) mean={base:.4f}")
        print(
            f"  极化 mean={pol:.4f}  Delta={pol - base:+.4f}  "
            + ("[OK] 差异化生效" if pol > base else "[WARN] 未显著拉开")
        )
        print(
            f"  混合 mean={mix:.4f}  Delta={mix - base:+.4f}  "
            + ("[OK] 差异化生效" if mix > base else "[WARN] 未显著拉开")
        )
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
