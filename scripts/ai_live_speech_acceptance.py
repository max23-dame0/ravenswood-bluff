"""Live-like speech acceptance for Alpha 1.1 M5-L.

This gate uses a delayed mock backend with the live backend speed profile. It
does not prove real-provider quality, but it catches the specific regression
where public speech falls back at the old fixed 2s budget.

Runs both 5-player and 8-player games, outputs latency P50/P95, and writes
an evidence file to docs/alpha-1.1-evidence/.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("BOTC_BACKEND", "mock")
os.environ.setdefault("AI_BACKEND_SPEED_PROFILE", "live")
os.environ["AI_FORCE_GAME_TIMEOUTS"] = "1"
os.environ["AI_ACTION_TIMEOUT_SECONDS"] = "8.0"
os.environ.setdefault("CLAIM_EXTRACTION_TIMEOUT_SECONDS", "0.5")

from src.agents.ai_agent import AIAgent
from src.agents.storyteller_agent import StorytellerAgent
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.llm.mock_backend import MockBackend
from src.orchestrator.game_loop import GameOrchestrator
from src.state.game_state import GamePhase, GameState


class DelayedMockBackend(LLMBackend):
    def __init__(self, delay_seconds: float = 2.5) -> None:
        self.delay_seconds = delay_seconds
        self.mock = MockBackend()

    async def generate(self, system_prompt: str, messages: list[Message], **kwargs) -> LLMResponse:
        await asyncio.sleep(self.delay_seconds)
        return await self.mock.generate(system_prompt, messages, **kwargs)

    def get_model_name(self) -> str:
        return "delayed-live-like-mock"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return await self.mock.get_embeddings(texts)


class _StopGame(Exception):
    pass


_pass_count = 0
_fail_count = 0


def _check(label: str, condition: bool) -> None:
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {label}")
    else:
        _fail_count += 1
        print(f"  FAIL  {label}")


async def _run_live_like_game(player_count: int = 5) -> dict:
    backend = DelayedMockBackend(delay_seconds=7.5)
    state = GameState(phase=GamePhase.SETUP)
    orch = GameOrchestrator(state)
    orch.storyteller_agent = StorytellerAgent(backend)
    orch.default_agent_backend = backend

    speak_events: list[dict] = []
    original_publish = orch.event_bus.publish

    async def publish_with_capture(event):
        await original_publish(event)
        if event.event_type == "player_speaks":
            speak_events.append(
                {
                    "actor": event.actor,
                    "content": event.payload.get("content", ""),
                    "round": event.payload.get("round", 0),
                }
            )
            if len(speak_events) >= player_count:
                raise _StopGame("speech measurement complete")
        if event.event_type in {"execution_resolved", "game_settlement_ready"}:
            raise _StopGame("measurement complete")

    orch.event_bus.publish = publish_with_capture  # type: ignore[assignment]

    loop_task = asyncio.create_task(orch.run_game_loop())
    try:
        await asyncio.sleep(0.1)
        await orch.run_setup_with_options(
            player_count=player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=1,
            storyteller_mode="auto",
            audit_mode=True,
            max_nomination_rounds=1,
            backend_mode="mock",
        )
        await asyncio.wait_for(loop_task, timeout=120)
    except (_StopGame, asyncio.CancelledError):
        pass
    finally:
        if not loop_task.done():
            loop_task.cancel()
            try:
                await loop_task
            except (asyncio.CancelledError, _StopGame):
                pass
        if getattr(orch, "_claim_extraction_tasks", None):
            await asyncio.sleep(0.05)

    metrics: list[dict] = []
    for agent in orch.broker.agents.values():
        if isinstance(agent, AIAgent):
            metrics.extend(agent.export_action_metrics())

    return {
        "player_count": player_count,
        "speak_events": speak_events,
        "metrics": metrics,
        "summary": orch.collect_ai_action_metrics()["summary"],
        "latency_summary": orch.get_action_latency_summary(),
    }


def _has_effective_content(content: str) -> bool:
    markers = ("我更想", "回应", "解释", "逻辑", "提名", "投票", "票型", "发言", "方向", "线索", "站死")
    return len(content.strip()) >= 18 and sum(1 for marker in markers if marker in content) >= 1


def _chain_template_rate(events: list[dict]) -> float:
    if not events:
        return 0.0
    chain_markers = (
        "我先回应一下 Player",
        "我觉得这里还不能直接定论",
        "把自己的逻辑讲清楚，尤其是他前后态度有没有对上",
    )
    chain_like = sum(
        1
        for event in events
        if any(marker in event["content"] for marker in chain_markers)
    )
    return chain_like / len(events)


def _analyze_game(result: dict) -> dict:
    """Analyze a single game result and return structured metrics."""
    speak_metrics = [m for m in result["metrics"] if m.get("action_type") == "speak"]
    speak_count = len(speak_metrics)
    fallback_count = sum(1 for m in speak_metrics if m.get("fallback_used"))
    llm_success = sum(1 for m in speak_metrics if m.get("speech_source") == "live_llm")
    cache_finalized = sum(1 for m in speak_metrics if str(m.get("speech_source") or "").startswith("cache_finalized"))
    hard_timeout_records = [
        m for m in result["metrics"]
        if str(m.get("fallback_reason") or "").startswith("orchestrator_hard_timeout")
    ]

    fallback_rate = fallback_count / speak_count if speak_count else 0
    success_or_cache_rate = (llm_success + cache_finalized) / speak_count if speak_count else 0
    effective = [e for e in result["speak_events"] if _has_effective_content(e["content"])]
    effective_rate = len(effective) / len(result["speak_events"]) if result["speak_events"] else 0
    chain_rate = _chain_template_rate(result["speak_events"])

    speak_latency = result["latency_summary"].get("by_action_type", {}).get("speak", {})

    return {
        "player_count": result["player_count"],
        "speech_count": speak_count,
        "fallback_count": fallback_count,
        "fallback_rate": round(fallback_rate, 3),
        "llm_success_count": llm_success,
        "cache_finalized_count": cache_finalized,
        "llm_or_cache_rate": round(success_or_cache_rate, 3),
        "orchestrator_timeout_count": len(hard_timeout_records),
        "effective_content_rate": round(effective_rate, 3),
        "chain_template_rate": round(chain_rate, 3),
        "speak_latency_p50_ms": speak_latency.get("p50_ms", 0),
        "speak_latency_p95_ms": speak_latency.get("p95_ms", 0),
        "speak_latency_max_ms": speak_latency.get("max_ms", 0),
        "round_stats": result["summary"].get("speech", {}).get("round_stats", {}),
    }


def _print_analysis(analysis: dict) -> None:
    pc = analysis["player_count"]
    print(f"  [{pc}p] speeches: {analysis['speech_count']}")
    print(f"  [{pc}p] fallback_rate: {analysis['fallback_rate']:.0%}")
    print(f"  [{pc}p] llm_or_cache_rate: {analysis['llm_or_cache_rate']:.0%}")
    print(f"  [{pc}p] effective_content_rate: {analysis['effective_content_rate']:.0%}")
    print(f"  [{pc}p] chain_template_rate: {analysis['chain_template_rate']:.0%}")
    print(f"  [{pc}p] orchestrator_timeout: {analysis['orchestrator_timeout_count']}")
    print(f"  [{pc}p] speak latency: P50={analysis['speak_latency_p50_ms']:.0f}ms "
          f"P95={analysis['speak_latency_p95_ms']:.0f}ms max={analysis['speak_latency_max_ms']:.0f}ms")


def _write_evidence(analyses: list[dict]) -> Path:
    """Write evidence file to docs/alpha-1.1-evidence/."""
    evidence_dir = REPO_ROOT / "docs" / "alpha-1.1-evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"m5l_live_speech_{ts}.md"
    filepath = evidence_dir / filename

    lines = [
        "# M5-L Live-Like Speech Acceptance Evidence",
        "",
        f"**Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"**Backend**: delayed-live-like-mock (7.5s delay)",
        f"**Speed profile**: live",
        f"**Timeout budget**: 8.0s (env AI_ACTION_TIMEOUT_SECONDS)",
        f"**Player counts tested**: {', '.join(str(a['player_count']) for a in analyses)}",
        "",
        "## Results Summary",
        "",
        "| Metric | 5-player | 8-player | Target |",
        "|--------|----------|----------|--------|",
    ]

    def _val(key: str, fmt: str = ".0%") -> list[str]:
        vals = []
        for a in analyses:
            v = a.get(key, 0)
            vals.append(f"{v:{fmt}}")
        return vals

    for key, label, fmt, target in [
        ("fallback_rate", "fallback_rate", ".0%", "<= 20%"),
        ("llm_or_cache_rate", "LLM/cache rate", ".0%", ">= 80%"),
        ("effective_content_rate", "effective content", ".0%", ">= 70%"),
        ("chain_template_rate", "chain template", ".0%", "<= 20%"),
        ("orchestrator_timeout_count", "orchestrator timeout", "d", "== 0"),
    ]:
        vals = _val(key, fmt)
        row = f"| {label} | {' | '.join(vals)} | {target} |"
        lines.append(row)

    lines.append("")
    lines.append("### Speech Latency")
    lines.append("")
    lines.append("| Players | P50 | P95 | Max |")
    lines.append("|---------|-----|-----|-----|")
    for a in analyses:
        lines.append(f"| {a['player_count']}p | {a['speak_latency_p50_ms']:.0f}ms | "
                     f"{a['speak_latency_p95_ms']:.0f}ms | {a['speak_latency_max_ms']:.0f}ms |")

    lines.append("")
    lines.append("## Residual Risks")
    lines.append("")
    lines.append("- This uses a delayed mock backend, not a real LLM provider.")
    lines.append("- Real provider latency, token costs, and rate limits are not tested here.")
    lines.append("- Content quality depends on MockBackend responses; real LLM output varies.")
    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


async def main_async() -> None:
    global _pass_count, _fail_count

    print("=" * 60)
    print("AI live-like speech acceptance checks")
    print("=" * 60)

    analyses: list[dict] = []

    for player_count in [5, 8]:
        print(f"\n--- {player_count}-player game ---")
        result = await _run_live_like_game(player_count=player_count)
        analysis = _analyze_game(result)
        analyses.append(analysis)
        _print_analysis(analysis)

    # Use the worst-case across both games for gate checks
    worst_fallback = max(a["fallback_rate"] for a in analyses)
    worst_success = min(a["llm_or_cache_rate"] for a in analyses)
    worst_effective = min(a["effective_content_rate"] for a in analyses)
    worst_chain = max(a["chain_template_rate"] for a in analyses)
    total_timeout = sum(a["orchestrator_timeout_count"] for a in analyses)
    total_speeches = sum(a["speech_count"] for a in analyses)

    print(f"\n--- Combined gates (worst-case across {len(analyses)} games) ---")
    _check("speeches collected", total_speeches > 0)
    _check("speak metrics collected", total_speeches > 0)
    _check("live-like speak fallback rate <= 20%", worst_fallback <= 0.20)
    _check("live-like LLM/cache speech rate >= 80%", worst_success >= 0.80)
    _check("orchestrator hard timeout == 0", total_timeout == 0)
    _check("effective speech content >= 70%", worst_effective >= 0.70)
    _check("chain template rate <= 20%", worst_chain <= 0.20)

    # Write evidence file
    evidence_path = _write_evidence(analyses)
    print(f"\n  evidence: {evidence_path.relative_to(REPO_ROOT)}")


def main() -> int:
    asyncio.run(main_async())
    total = _pass_count + _fail_count
    print("=" * 60)
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)
    return 0 if _fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
