r"""Benchmark the configured live LLM latency.

Uses the current .env / environment variables through OpenAIBackend and prints
latency distribution for short, medium, and BOTC-style speech prompts.

Examples:
  .\.venv\Scripts\python.exe scripts\llm_latency_benchmark.py --samples 3
  .\.venv\Scripts\python.exe scripts\llm_latency_benchmark.py --samples 5 --prompt-set speech
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.llm.base_backend import Message
from src.llm.openai_backend import OpenAIBackend


@dataclass(frozen=True)
class PromptCase:
    name: str
    system_prompt: str
    user_prompt: str
    max_tokens: int


PROMPT_CASES: dict[str, list[PromptCase]] = {
    "quick": [
        PromptCase(
            "ping_json",
            "你是一个只返回 JSON 的助手。",
            '请返回 {"ok": true, "note": "pong"}，不要输出额外内容。',
            80,
        ),
    ],
    "speech": [
        PromptCase(
            "botc_speech_short",
            "你是一名正在玩《血染钟楼》的真实玩家，发言要自然、有具体观点。",
            (
                "当前是第一天白天讨论。你是 Player 5，听到 Player 1 怀疑 Player 7，"
                "Player 2 说不要急着站边。请用中文生成一句 60-100 字的公开发言，"
                "包含你的关注对象和一个想追问的问题。"
            ),
            220,
        ),
        PromptCase(
            "botc_speech_medium_json",
            (
                "你是一名正在玩《血染钟楼》的 AI 玩家。请根据公开局势做发言，"
                "不要泄露私密信息，输出严格 JSON。"
            ),
            (
                "玩家列表：Player 1-Player 8。最近发言：Player 1 怀疑 Player 7；"
                "Player 2 认为先听后置位；Player 3 说票型比身份更重要。"
                "你是 Player 5，好人阵营，当前没有强身份信息。"
                '请返回 JSON：{"action":"speak","content":"...","tone":"calm","reasoning":"..."}。'
            ),
            360,
        ),
    ],
}
PROMPT_CASES["all"] = [*PROMPT_CASES["quick"], *PROMPT_CASES["speech"]]


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[-1]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


async def _measure_case(backend: OpenAIBackend, case: PromptCase, samples: int, pause: float) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for index in range(1, samples + 1):
        started = time.perf_counter()
        error = ""
        usage: dict[str, Any] = {}
        content_len = 0
        try:
            response = await backend.generate(
                system_prompt=case.system_prompt,
                messages=[Message(role="user", content=case.user_prompt)],
                temperature=0.4,
                max_tokens=case.max_tokens,
            )
            usage = response.usage
            content_len = len(response.content or "")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        results.append(
            {
                "sample": index,
                "latency_seconds": elapsed,
                "error": error,
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "content_length": content_len,
            }
        )
        status = "ERR" if error else "OK"
        print(f"  {case.name} #{index}: {elapsed:.2f}s {status} tokens={results[-1]['total_tokens']}")
        if pause > 0 and index < samples:
            await asyncio.sleep(pause)

    latencies = [r["latency_seconds"] for r in results if not r["error"]]
    errors = [r for r in results if r["error"]]
    return {
        "case": case.name,
        "samples": samples,
        "successes": len(latencies),
        "errors": len(errors),
        "mean_seconds": round(statistics.mean(latencies), 3) if latencies else None,
        "median_seconds": round(statistics.median(latencies), 3) if latencies else None,
        "p90_seconds": round(_percentile(latencies, 90), 3) if latencies else None,
        "p95_seconds": round(_percentile(latencies, 95), 3) if latencies else None,
        "min_seconds": round(min(latencies), 3) if latencies else None,
        "max_seconds": round(max(latencies), 3) if latencies else None,
        "avg_total_tokens": round(statistics.mean([r["total_tokens"] for r in results if r["total_tokens"]]), 1)
        if any(r["total_tokens"] for r in results)
        else 0,
        "error_examples": [r["error"] for r in errors[:3]],
        "raw": results,
    }


async def main_async(args: argparse.Namespace) -> int:
    backend = OpenAIBackend()
    print("LLM latency benchmark")
    print("=" * 72)
    print(f"model: {backend.get_model_name()}")
    print("base_url: configured via OPENAI_BASE_URL")
    print(f"samples per case: {args.samples}")
    print(f"prompt_set: {args.prompt_set}")
    print("=" * 72)

    summaries = []
    for case in PROMPT_CASES[args.prompt_set]:
        print(f"\n[{case.name}]")
        summaries.append(await _measure_case(backend, case, args.samples, args.pause_seconds))

    print("\nsummary")
    print("=" * 72)
    for item in summaries:
        print(
            f"{item['case']:<24} "
            f"ok={item['successes']}/{item['samples']} "
            f"mean={item['mean_seconds']}s "
            f"p50={item['median_seconds']}s "
            f"p90={item['p90_seconds']}s "
            f"p95={item['p95_seconds']}s "
            f"max={item['max_seconds']}s "
            f"avg_tokens={item['avg_total_tokens']}"
        )
        if item["error_examples"]:
            print(f"  errors: {item['error_examples']}")

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote JSON: {output_path}")
    return 0 if all(item["successes"] > 0 for item in summaries) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3, help="Samples per prompt case.")
    parser.add_argument(
        "--prompt-set",
        choices=sorted(PROMPT_CASES.keys()),
        default="all",
        help="Prompt cases to run.",
    )
    parser.add_argument("--pause-seconds", type=float, default=0.5, help="Pause between samples.")
    parser.add_argument("--json-output", default="", help="Optional path to write raw JSON results.")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
