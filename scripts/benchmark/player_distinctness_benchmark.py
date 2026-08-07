"""AI 玩家行为指纹基准（PLN-040 T1）。

量化"当前 AI 玩家到底有多同质"——从 mock 对局 trace 聚合每玩家行为指纹向量，
计算两两归一化欧氏距离矩阵，输出基线报告，作为差异化进化（T3）的前后对照。

指纹维度（≥10 维，均归一化到 0~1）：
1. 发言量：发言次数（speak 动作数）
2. 平均发言长度（字符）
3. 发言长度方差
4. 发言主动率：有内容发言 / 全部发言（内容为空的占比越低越主动）
5. 提名活跃度：nomination_intent / speak 次数
6. 投票活跃度：vote 次数
7. 投票通过率：vote decision=True 占比
8. 夜晚行动数：night_action 次数
9. 行动总 token（usage.total_tokens 均值归一化）
10. fallback 率：fallback 动作占比
11. 决策 reasoning 长度均值
12. 决策确定性：decision 中不含 "unknown" / "不确定" 的占比

输出：
- 指纹向量 CSV 到 --out-dir 目录
- 两两距离矩阵 + 汇总报告（均值/最大/最小距离）到 data/bench/player_distinctness_report.json
- 控制台打印摘要

用法：
  python scripts/benchmark/player_distinctness_benchmark.py \
      --games 10 --player-count 8 --out-dir data/bench
  python scripts/benchmark/player_distinctness_benchmark.py --seed 42 --games 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.engine.data_collector import GameDataCollector

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("player_distinctness")


# ---------------------------------------------------------------------------
# 指纹定义
# ---------------------------------------------------------------------------

FINGERPRINT_DIMS = (
    "speak_count",
    "avg_speech_len",
    "speech_len_var",
    "speech_active_rate",
    "nomination_activity",
    "vote_activity",
    "vote_yes_rate",
    "night_action_count",
    "avg_total_tokens",
    "fallback_rate",
    "avg_reasoning_len",
    "decision_certainty",
)


def _safe_mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _safe_var(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return round(sum((v - mean) ** 2 for v in values) / (len(values) - 1), 4)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _normalize(values: dict[str, float], max_scale: dict[str, float]) -> dict[str, float]:
    """按列 max_scale 归一化到 0~1（缺失维取 0；max_scale 为 0 时该维视为 0）。"""
    result: dict[str, float] = {}
    for dim in FINGERPRINT_DIMS:
        scale = max_scale.get(dim, 1.0)
        result[dim] = _clamp01(values.get(dim, 0.0) / scale) if scale > 0 else 0.0
    return result


# ---------------------------------------------------------------------------
# 从 trace 聚合单玩家指纹
# ---------------------------------------------------------------------------


def _entry_speech_len(entry: dict[str, Any]) -> float:
    action = entry.get("action") or {}
    content = action.get("content") or action.get("speech") or ""
    if isinstance(content, str):
        return float(len(content))
    return 0.0


def _entry_decision_bool(entry: dict[str, Any]) -> bool | None:
    action = entry.get("action") or {}
    decision = action.get("decision")
    if isinstance(decision, bool):
        return decision
    return None


def _entry_uncertain(entry: dict[str, Any]) -> bool:
    text = json.dumps(entry.get("action") or {}, ensure_ascii=False)
    return any(k in text for k in ("unknown", "不确定", "无法判断", "NoInfo"))


def _entry_is_fallback(entry: dict[str, Any]) -> bool:
    """判定一条动作是否为 fallback（thought_trace 不含 fallback_used，从 action 特征推断）。"""
    action = entry.get("action") or {}
    speech_source = str(action.get("speech_source", ""))
    if speech_source.startswith("fallback"):
        return True
    if action.get("fallback_reason") or action.get("llm_error_reason"):
        return True
    # 决策 dict 含 "fallback" 标记（部分 fallback 路径会带）
    return action.get("fallback") is True


def aggregate_player_fingerprint(
    entries: list[dict[str, Any]], player_id: str
) -> dict[str, float]:
    """从单个玩家的全部 thought_trace 记录聚合行为指纹向量。"""
    speak_lens: list[float] = []
    speak_count = 0
    empty_speech = 0
    nominate_count = 0
    vote_count = 0
    vote_yes = 0
    night_count = 0
    fallback_count = 0
    total_tokens: list[float] = []
    reasoning_lens: list[float] = []
    uncertain = 0
    total_actions = 0

    for entry in entries:
        if entry.get("player_id") != player_id:
            continue
        total_actions += 1
        action = entry.get("action") or {}
        action_type = entry.get("action_type") or action.get("action_type") or action.get("action") or ""
        at = str(action_type)

        if at in ("speak", "defense_speech") or (at == "speak"):
            speak_count += 1
            length = _entry_speech_len(entry)
            speak_lens.append(length)
            if length < 1:
                empty_speech += 1
        elif "nominate" in at or at in ("nomination_intent", "nominate", "not_nominating"):
            nominate_count += 1
        elif at == "vote":
            vote_count += 1
            decision = _entry_decision_bool(entry)
            if decision is True:
                vote_yes += 1
        elif at in ("night_action", "slayer_shot"):
            night_count += 1

        if _entry_is_fallback(entry):
            fallback_count += 1

        usage = entry.get("usage") or {}
        tt = usage.get("total_tokens")
        if isinstance(tt, (int, float)):
            total_tokens.append(float(tt))

        thought = entry.get("thought") or entry.get("llm_thought") or ""
        if isinstance(thought, str) and thought.strip():
            reasoning_lens.append(float(len(thought)))

        if _entry_uncertain(entry):
            uncertain += 1

    n = max(1, total_actions)
    vote_n = max(1, vote_count)
    speech_n = max(1, speak_count)
    avg_len = _safe_mean(speak_lens)
    var_len = _safe_var(speak_lens)

    return {
        "speak_count": float(speak_count),
        "avg_speech_len": avg_len,
        "speech_len_var": var_len,
        "speech_active_rate": _clamp01(1.0 - empty_speech / speech_n),
        "nomination_activity": _clamp01(nominate_count / n),
        "vote_activity": _clamp01(vote_count / n),
        "vote_yes_rate": _clamp01(vote_yes / vote_n),
        "night_action_count": float(night_count),
        "avg_total_tokens": _safe_mean(total_tokens),
        "fallback_rate": _clamp01(fallback_count / n),
        "avg_reasoning_len": _safe_mean(reasoning_lens),
        "decision_certainty": _clamp01(1.0 - uncertain / n),
    }


def euclidean_distance(a: dict[str, float], b: dict[str, float]) -> float:
    """两指纹向量的归一化欧氏距离（各维均已在 0~1，除以 sqrt(ndim) 归一到 0~1）。"""
    squared = sum((a[dim] - b[dim]) ** 2 for dim in FINGERPRINT_DIMS)
    return round((squared ** 0.5) / (len(FINGERPRINT_DIMS) ** 0.5), 4)


# ---------------------------------------------------------------------------
# 跑 mock 对局并读取 trace
# ---------------------------------------------------------------------------


async def _run_one_game(player_count: int, timeout: int, audit: bool) -> str:
    from simulate_game import SimulationOptions, run_simulation

    options = SimulationOptions(
        backend="mock",
        player_count=player_count,
        discussion_rounds=1,
        timeout_seconds=timeout,
        stop_after="day_1",
        audit_mode=audit,
        max_nomination_rounds=2,
    )
    await run_simulation(options)
    return ""  # game_id 在 summary 中，但 trace 文件名按时间生成，此处由调用方扫描最新文件


def _load_latest_game_id() -> str | None:
    """从 data/sessions 最新文件的 game_id 字段推断（比文件名拆分更稳健）。"""
    sessions_dir = Path("data/sessions")
    if not sessions_dir.exists():
        return None
    files = sorted(sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for file in files:
        try:
            with open(file, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    gid = data.get("game_id")
                    if gid:
                        return str(gid)
                    break
        except (OSError, json.JSONDecodeError):
            continue
    return None


def collect_from_sessions(game_id: str) -> dict[str, list[dict[str, Any]]]:
    """读取指定 game_id 的全部 thought_trace，按 player_id 分组。"""
    collector = GameDataCollector()
    payload = collector.export_ai_traces(game_id, base_dir="data/sessions")
    by_player: dict[str, list[dict[str, Any]]] = {}
    for entry in payload.get("entries", []):
        if entry.get("record_type") != "thought_trace":
            continue
        raw = entry.get("raw") or {}
        pid = raw.get("player_id")
        if not pid:
            continue
        by_player.setdefault(pid, []).append(raw)
    return by_player


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def run_benchmark(
    games: int = 10,
    player_count: int = 8,
    seed: int = 42,
    timeout: int = 120,
    audit: bool = True,
    out_dir: str = "data/bench",
) -> dict[str, Any]:
    """跑 N 局 mock 对局，聚合行为指纹，输出距离矩阵与报告。"""
    random.seed(seed)  # 固定 MockBackend 全局随机（每局再细分）

    per_game_by_player: list[dict[str, dict[str, float]]] = []
    for i in range(games):
        # 每局重新 seed（seed+i），保证整批 benchmark 可复现
        random.seed(seed + i)
        logger.warning("[局 %d/%d] 运行 mock 对局（seed=%d）...", i + 1, games, seed + i)
        asyncio.run(_run_one_game(player_count, timeout, audit))
        game_id = _load_latest_game_id()
        if not game_id:
            logger.warning("未找到 trace，跳过本局")
            continue
        by_player = collect_from_sessions(game_id)
        fingerprints = {
            pid: aggregate_player_fingerprint(entries, pid) for pid, entries in by_player.items()
        }
        if fingerprints:
            per_game_by_player.append(fingerprints)

    if not per_game_by_player:
        raise RuntimeError("没有可用对局数据，请检查 data/sessions 与 mock 对局是否成功")

    # ---- 跨局稳定玩家池 ----
    all_players = sorted({pid for game in per_game_by_player for pid in game})
    max_scale = _column_max_scale(per_game_by_player)
    normalized_by_game = [
        {pid: _normalize(fp, max_scale) for pid, fp in game.items()} for game in per_game_by_player
    ]

    # ---- 两两距离（跨全部局样本） ----
    distances: list[float] = []
    pair_distances: dict[str, float] = {}
    for game_fp in normalized_by_game:
        pids = sorted(game_fp)
        for idx, a in enumerate(pids):
            for b in pids[idx + 1 :]:
                d = euclidean_distance(game_fp[a], game_fp[b])
                distances.append(d)
                key = f"{a}↔{b}"
                pair_distances[key] = max(pair_distances.get(key, 0.0), d)

    # ---- 跨局稳定性（同玩家各局指纹两两距离） ----
    stability: dict[str, float] = {}
    for pid in all_players:
        vecs = [game[pid] for game in normalized_by_game if pid in game]
        if len(vecs) >= 2:
            ds = [euclidean_distance(vecs[i], vecs[j]) for i in range(len(vecs)) for j in range(i + 1, len(vecs))]
            stability[pid] = round(sum(ds) / len(ds), 4)
        else:
            stability[pid] = None

    report = {
        "meta": {
            "plan": "PLN-040 T1",
            "games": len(per_game_by_player),
            "player_count": player_count,
            "seed": seed,
            "generated_at": None,
        },
        "fingerprint_dims": list(FINGERPRINT_DIMS),
        "per_player_fingerprints": {
            pid: {k: fp[k] for k in FINGERPRINT_DIMS} for pid, fp in normalized_by_game[0].items()
        },
        "distance_summary": {
            "pair_count": len(distances),
            "mean_distance": round(sum(distances) / len(distances), 4),
            "max_distance": round(max(distances), 4),
            "min_distance": round(min(distances), 4),
        },
        "pair_distances": {k: v for k, v in sorted(pair_distances.items())},
        "stability": {pid: v for pid, v in sorted(stability.items()) if v is not None},
    }
    report["meta"]["generated_at"] = __import__("datetime").datetime.now().isoformat()

    # ---- 落盘 ----
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_path = out_path / "player_distinctness_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out_path / "player_fingerprints.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        import csv

        writer = csv.writer(f)
        writer.writerow(["player_id"] + list(FINGERPRINT_DIMS))
        for pid, fp in report["per_player_fingerprints"].items():
            writer.writerow([pid] + [fp[d] for d in FINGERPRINT_DIMS])

    return report


def _column_max_scale(per_game_by_player: list[dict[str, dict[str, float]]]) -> dict[str, float]:
    """计算各维度的跨局最大值，用于归一化。"""
    scale: dict[str, float] = {}
    for dim in FINGERPRINT_DIMS:
        values = [fp.get(dim, 0.0) for game in per_game_by_player for fp in game.values()]
        scale[dim] = max(values) if values else 1.0
    return scale


def print_summary(report: dict[str, Any]) -> None:
    ds = report["distance_summary"]
    print("\n" + "=" * 60)
    print("AI 玩家行为指纹基准（PLN-040 T1）")
    print("=" * 60)
    print(f"对局数: {report['meta']['games']} | 玩家数: {report['meta']['player_count']} | seed: {report['meta']['seed']}")
    print(f"指纹维度: {len(report['fingerprint_dims'])}")
    print(f"两两距离样本: {ds['pair_count']}")
    print(f"  mean_distance: {ds['mean_distance']}")
    print(f"  max_distance:  {ds['max_distance']}")
    print(f"  min_distance:  {ds['min_distance']}")
    print("跨局稳定性（同玩家各局指纹平均距离，越小越稳定）:")
    for pid, d in sorted(report["stability"].items()):
        print(f"  {pid}: {d}")
    print(f"\n报告已写入: {Path('data/bench') / 'player_distinctness_report.json'}")
    print("=" * 60 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 玩家行为指纹基准（PLN-040 T1）")
    parser.add_argument("--games", type=int, default=10, help="mock 对局数（默认 10）")
    parser.add_argument("--player-count", type=int, default=8, help="每局玩家数（默认 8）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")
    parser.add_argument("--timeout", type=int, default=120, help="单局超时秒数（默认 120）")
    parser.add_argument("--out-dir", default="data/bench", help="输出目录（默认 data/bench）")
    parser.add_argument("--no-audit", action="store_true", help="关闭 audit mode")
    args = parser.parse_args()

    report = run_benchmark(
        games=args.games,
        player_count=args.player_count,
        seed=args.seed,
        timeout=args.timeout,
        audit=not args.no_audit,
        out_dir=args.out_dir,
    )
    print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
