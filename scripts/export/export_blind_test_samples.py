"""PLN-040 T5 真人盲测样本导出。

导出每 AI 玩家的公开发言样本（匿名化），供真人标注"某段发言出自哪个 AI"
（5 选 1，随机基线 20%）。

数据源：程序化 mock 对局后从 orchestrator.state.event_log 提取
`player_speaks` 事件（visibility=PUBLIC，payload.content 为实际发布内容）。

输出（--out-dir）：
- samples.json    所有发言样本（按玩家分组，匿名化：p1→P1... 不暴露角色）
- labeling.tsv    标注表单（每行：样本ID + 5 个候选玩家 + 空标注列）
- summary.json    统计（每玩家发言数、总样本数）

用法：
  python scripts/export/export_blind_test_samples.py --games 2 --player-count 5 --seed 42
  python scripts/export/export_blind_test_samples.py --games 3 --player-count 8 --seed 7 --out-dir data/blind
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


async def _collect_speeches(
    player_count: int,
    seed: int,
    timeout: int = 120,
    audit: bool = True,
    backend_mode: str = "mock",
) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    """跑一局对局，返回 (game_id, {player_id: [发言]})。

    backend_mode: "mock"（固定文案池，仅流程测试）或 "live"（真实 LLM 发言，
    用于真人盲测）。发言来自 event_log 的 player_speaks（PUBLIC）事件：
    实际发布内容，比 thought_trace 的决策草稿更可靠。
    """
    import os
    import random as _random

    from src.agents.storyteller_agent import StorytellerAgent
    from src.orchestrator.game_loop import GameOrchestrator
    from src.state.game_state import GamePhase, GameState, Visibility

    if backend_mode == "live":
        from src.llm.openai_backend import OpenAIBackend

        backend = OpenAIBackend()
        # 与 simulate_game live 一致：低价值动作本地判定 + 审计推进
        os.environ.setdefault("AI_FAST_LOW_VALUE_ACTIONS", "1")
        os.environ.setdefault("AI_FORCE_PROGRESS_ACTIONS", "1")
    else:
        from src.llm.mock_backend import MockBackend

        backend = MockBackend()
        _random.seed(seed)

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
            backend_mode=backend_mode,
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

    by_player: dict[str, list[dict[str, Any]]] = {}
    for event in orchestrator.state.event_log:
        if event.event_type != "player_speaks":
            continue
        if event.visibility != Visibility.PUBLIC:
            continue
        content = (event.payload or {}).get("content", "")
        if not content or not event.actor:
            continue
        by_player.setdefault(event.actor, []).append(
            {
                "content": content,
                "tone": (event.payload or {}).get("tone", "calm"),
                "round": (event.payload or {}).get("round", 1),
                "day": event.day_number,
            }
        )
    return orchestrator.state.game_id, by_player


def _anonymize(player_ids: list[str]) -> dict[str, str]:
    """生成匿名映射：p1 → P1, p2 → P2（不暴露角色/阵营）。"""
    return {pid: f"P{idx + 1}" for idx, pid in enumerate(sorted(player_ids))}


def _anonymize_content(content: str, anon_map: dict[str, str]) -> str:
    """把发言内容里的玩家名替换为匿名代号，避免内容泄露身份。

    覆盖三种写法：
    - p1 / P1（LLM 发言中常混用的小写/大写玩家 id）
    - "Player 1" / "Player 5"（游戏内玩家名字，记忆摘要会引用）
    按"较长优先"替换防止前缀误匹配。
    """
    text = content
    # 先替换 "Player N" 形式（较长，优先）
    for pid, anon in sorted(anon_map.items(), key=lambda kv: len(kv[1]), reverse=True):
        num = pid.lstrip("p")  # "p1" -> "1"
        text = text.replace(f"Player {num}", anon).replace(f"player {num}", anon)
    # 再替换裸 p1 / P1
    for pid, anon in sorted(anon_map.items(), key=lambda kv: len(kv[1]), reverse=True):
        for raw in (pid, pid.upper()):
            text = text.replace(raw, anon)
    return text


def _build_sample_id(game_id: str, seq: int) -> str:
    """稳定匿名样本 ID：不暴露 player_id（标注者无法反推匿名映射）。

    用 game_id 前缀 + 全局序号；sample_id → anon_player 的真实映射
    只存在于 samples.json（标注者不可见），score 时按 sample_id 回查。
    重新 export 会生成新 game_id 前缀，旧标注文件失效需重新标注（预期）。
    """
    return f"{game_id[:8]}_{seq:02d}"


def _shuffle_samples(samples: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """打乱样本顺序，避免同一玩家的发言连续排列被标注者识别。

    固定 seed 保证同参导出可复现（score 按 sample_id 回查，不受顺序影响）。
    """
    import random as _random

    shuffled = list(samples)
    _random.Random(seed).shuffle(shuffled)
    return shuffled


def _tsv_content(content: str) -> str:
    """清洗 TSV 单元格内容：替换换行/tab 为空格。

    TSV 以换行分行、tab 分列，发言内容若含 \n 会把一行拆成多行、
    含 \t 会错列，破坏标注表单结构。
    """
    return (
        content.replace("\r\n", " ")
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\t", " ")
    )


def export_samples(
    games: int = 2,
    player_count: int = 5,
    seed: int = 42,
    timeout: int = 120,
    max_speeches_per_player: int = 6,
    out_dir: str = "data/blind",
    backend_mode: str = "mock",
    min_length: int = 0,
) -> dict[str, Any]:
    """导出盲测样本到 out_dir。

    min_length>0 时过滤过短发言（live 局偶发的 fallback 短句偏机械，
    方案 A：滤掉 <min_length 字的发言，保证盲测样本质量）。
    """
    all_by_player: dict[str, list[dict[str, Any]]] = {}
    game_ids: list[str] = []
    for i in range(games):
        print(f"  对局 {i + 1}/{games} (backend={backend_mode}, seed={seed + i})...")
        gid, by_player = asyncio.run(
            _collect_speeches(player_count, seed + i, timeout, backend_mode=backend_mode)
        )
        game_ids.append(gid)
        for pid, speeches in by_player.items():
            if min_length > 0:
                speeches = [sp for sp in speeches if len(str(sp.get("content", ""))) >= min_length]
            all_by_player.setdefault(pid, []).extend(speeches)

    player_ids = sorted(all_by_player)
    anon_map = _anonymize(player_ids)
    if not player_ids:
        raise RuntimeError("没有收集到任何发言，请检查对局是否正常发言")

    # 每玩家取最多 N 段（去重后），构造样本（sample_id 不含 player_id，匿名）
    samples: list[dict[str, Any]] = []
    seq = 0
    for pid in player_ids:
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for sp in all_by_player[pid]:
            if sp["content"] in seen:
                continue
            seen.add(sp["content"])
            unique.append(sp)
        speeches = unique[:max_speeches_per_player]
        for sp in speeches:
            samples.append(
                {
                    "sample_id": _build_sample_id(game_ids[0], seq),
                    "anon_player": anon_map[pid],
                    # 内容中的玩家名也匿名化（防标注者通过内容反推身份）
                    "content": _anonymize_content(sp["content"], anon_map),
                    "tone": sp.get("tone", "calm"),
                }
            )
            seq += 1

    # 打乱样本顺序（M3 盲测关键）：不允许标注者按 sample_id 序号/相邻行
    # 推断"连续几条是同一玩家"——只允许凭发言风格判断。固定 seed 可复现。
    samples = _shuffle_samples(samples, seed)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # samples.json
    (out_path / "samples.json").write_text(
        json.dumps(
            {
                "meta": {
                    "plan": "PLN-040 T5",
                    "games": games,
                    "player_count": player_count,
                    "seed": seed,
                    "anon_map": anon_map,
                    "game_ids": game_ids,
                    "random_baseline": 0.2,
                },
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # labeling.tsv（标注表单：5 选 1）
    lines = ["sample_id\tcontent\t候选玩家\t标注(填 P1..P5)"]
    for s in samples:
        candidates = " / ".join(anon_map[pid] for pid in player_ids)
        lines.append(f"{s['sample_id']}\t{_tsv_content(s['content'])}\t{candidates}\t")
    (out_path / "labeling.tsv").write_text("\n".join(lines), encoding="utf-8")

    # summary.json
    summary = {
        "total_samples": len(samples),
        "per_player": {pid: len(all_by_player[pid]) for pid in player_ids},
        "anon_map": anon_map,
        "random_baseline": 0.2,
        "note": "猜中率 > 20% 且样本量 >= 30 次标注为 M3 达标；标注后计算",
    }
    (out_path / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "meta": {"games": games, "player_count": player_count, "seed": seed},
        "player_ids": player_ids,
        "anon_map": anon_map,
        "total_samples": len(samples),
        "per_player_counts": {pid: len(all_by_player[pid]) for pid in player_ids},
        "out_dir": str(out_path),
    }


def score_labels(samples_path: str | Path, labels_path: str | Path) -> dict[str, Any]:
    """根据真人标注结果计算盲测猜中率（M3：> 20% 随机基线）。

    标注文件格式（每行）：sample_id<tab>anon_player
    samples.json 含每样本真实 anon_player。
    """
    samples_path = Path(samples_path)
    labels_path = Path(labels_path)
    samples_data = json.loads(samples_path.read_text(encoding="utf-8"))
    true_map = {s["sample_id"]: s["anon_player"] for s in samples_data["samples"]}

    correct = 0
    total = 0
    by_player_correct: dict[str, int] = {}
    by_player_total: dict[str, int] = {}
    for line in labels_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "\t" not in line:
            continue
        sample_id, guess = line.split("\t", 1)
        guess = guess.strip()
        if not guess:
            continue
        true_anon = true_map.get(sample_id)
        if not true_anon:
            continue
        total += 1
        if guess == true_anon:
            correct += 1
            by_player_correct[true_anon] = by_player_correct.get(true_anon, 0) + 1
        by_player_total[true_anon] = by_player_total.get(true_anon, 0) + 1

    rate = (correct / total) if total else 0.0
    result = {
        "total_labels": total,
        "correct": correct,
        "guess_rate": round(rate, 4),
        "random_baseline": 0.2,
        "verdict": "PASS" if total >= 30 and rate > 0.2 else "FAIL",
        "by_player": {
            pid: {
                "correct": by_player_correct.get(pid, 0),
                "total": by_player_total.get(pid, 0),
                "rate": round(
                    by_player_correct.get(pid, 0) / by_player_total.get(pid, 0), 4
                )
                if by_player_total.get(pid, 0)
                else 0.0,
            }
            for pid in sorted(by_player_total)
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="PLN-040 T5 真人盲测样本导出")
    sub = parser.add_subparsers(dest="command")

    export_p = sub.add_parser("export", help="导出盲测样本")
    export_p.add_argument("--backend", choices=["mock", "live"], default="mock",
                          help="对局后端：mock（固定文案，流程测试）/ live（真实 LLM，真人盲测用）")
    export_p.add_argument("--games", type=int, default=2)
    export_p.add_argument("--player-count", type=int, default=5)
    export_p.add_argument("--seed", type=int, default=42)
    export_p.add_argument("--timeout", type=int, default=180, help="live 局单局超时（mock 默认 120）")
    export_p.add_argument("--max-speeches-per-player", type=int, default=6)
    export_p.add_argument("--min-length", type=int, default=30,
                          help="过滤少于该字数的发言（方案 A：滤掉 live 偶发 fallback 短机械句，默认 30）")
    export_p.add_argument("--out-dir", default="data/blind")

    score_p = sub.add_parser("score", help="统计标注结果")
    score_p.add_argument("--samples", default="data/blind/samples.json")
    score_p.add_argument("--labels", required=True, help="标注结果文件（sample_id<TAB>anon_player 每行）")

    args = parser.parse_args()
    if args.command == "score":
        result = score_labels(args.samples, args.labels)
        print("\n" + "=" * 60)
        print("盲测标注结果（PLN-040 T5 M3）")
        print("=" * 60)
        print(f"  标注数: {result['total_labels']} | 正确: {result['correct']} | 猜中率: {result['guess_rate']:.2%}")
        print(f"  随机基线: 20% | 结论: [{'PASS' if result['verdict'] == 'PASS' else 'FAIL'}] "
              + ("显著高于随机" if result["verdict"] == "PASS" else "未高于随机基线"))
        for pid, st in result["by_player"].items():
            print(f"    {pid}: {st['correct']}/{st['total']} = {st['rate']:.0%}")
        print("=" * 60 + "\n")
        return 0 if result["verdict"] == "PASS" else 1

    print("\n=== 导出盲测样本（PLN-040 T5）===")
    result = export_samples(
        games=args.games,
        player_count=args.player_count,
        seed=args.seed,
        timeout=args.timeout,
        max_speeches_per_player=args.max_speeches_per_player,
        out_dir=args.out_dir,
        backend_mode=args.backend,
        min_length=args.min_length,
    )
    print("\n" + "=" * 60)
    print("导出结果")
    print("=" * 60)
    print(f"  对局数: {result['meta']['games']} | 玩家数: {result['meta']['player_count']} | 后端: {args.backend}")
    print(f"  样本总数: {result['total_samples']}")
    print(f"  每玩家发言数: {result['per_player_counts']}")
    print(f"  匿名映射: {result['anon_map']}")
    print(f"  输出目录: {result['out_dir']}")
    print("  文件: samples.json / labeling.tsv / summary.json")
    print("  随机基线: 20%（5 选 1）")
    print("  * 标注后运行: python scripts/export/export_blind_test_samples.py score --labels <标注文件>")
    print("=" * 60 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
