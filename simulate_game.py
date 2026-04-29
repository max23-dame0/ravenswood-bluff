import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import suppress
from dataclasses import dataclass

from src.llm.mock_backend import MockBackend
from src.llm.openai_backend import OpenAIBackend
from src.orchestrator.game_loop import GameOrchestrator
from src.state.game_state import GamePhase, GameState, Team


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("simulation")


class SimulationStop(Exception):
    """Raised internally when the requested audit stop condition is reached."""


@dataclass
class SimulationOptions:
    backend: str
    player_count: int
    discussion_rounds: int
    timeout_seconds: int
    stop_after: str
    audit_mode: bool
    max_nomination_rounds: int | None


@dataclass(frozen=True)
class StopMatch:
    status: str
    reason: str


def parse_args() -> SimulationOptions:
    parser = argparse.ArgumentParser(description="快速审计或真实 LLM 短局验证。")
    parser.add_argument("--backend", choices=("mock", "live"), default="mock")
    parser.add_argument("--player-count", type=int, default=5)
    parser.add_argument("--discussion-rounds", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--stop-after", choices=("first_execution", "day_1", "night_2", "game_over"), default="first_execution")
    parser.add_argument("--audit-mode", action="store_true")
    parser.add_argument("--max-nomination-rounds", type=int, default=2)
    args = parser.parse_args()
    return SimulationOptions(
        backend=args.backend,
        player_count=args.player_count,
        discussion_rounds=args.discussion_rounds,
        timeout_seconds=args.timeout_seconds,
        stop_after=args.stop_after,
        audit_mode=bool(args.audit_mode),
        max_nomination_rounds=args.max_nomination_rounds,
    )


def build_backend(mode: str):
    from dotenv import load_dotenv

    load_dotenv()
    if mode == "mock":
        print(">>> [信息] 使用 MockBackend 进行快速规则审计。")
        return MockBackend()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("已请求 live backend，但当前环境没有 OPENAI_API_KEY")
    os.environ.setdefault("AI_FAST_LOW_VALUE_ACTIONS", "1")
    os.environ.setdefault("AI_FORCE_PROGRESS_ACTIONS", "1")
    if os.getenv("AI_FAST_LOW_VALUE_ACTIONS") == "1":
        print(">>> [信息] live 模拟启用低价值动作本地启发式：nomination_intent, vote。")
    if os.getenv("AI_FORCE_PROGRESS_ACTIONS") == "1":
        print(">>> [信息] live 模拟启用审计推进策略：本地投票优先赞成以触发处决链。")
    print(">>> [信息] 使用 OpenAIBackend 进行真实模型短局验证。")
    return OpenAIBackend()


def merged_events(orchestrator: GameOrchestrator):
    seen = set()
    merged = []
    for source_events in (getattr(orchestrator.state, "event_log", ()), getattr(orchestrator.event_log, "events", ())):
        for event in source_events:
            key = json.dumps(
                {
                    "event_type": event.event_type,
                    "trace_id": event.trace_id,
                    "actor": event.actor,
                    "target": event.target,
                    "round_number": event.round_number,
                    "payload": event.payload or {},
                },
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
    return merged


def collect_summary(orchestrator: GameOrchestrator) -> dict:
    events = merged_events(orchestrator)
    collect_ai_metrics = getattr(orchestrator, "collect_ai_action_metrics", None)
    ai_metrics = collect_ai_metrics(limit=0) if collect_ai_metrics else {"summary": {}}
    ai_summary = ai_metrics.get("summary", {})
    collect_runtime = getattr(orchestrator, "collect_runtime_diagnostics", None)
    runtime = collect_runtime() if collect_runtime else {}
    top_actions = []
    for item in ai_summary.get("top_token_actions", [])[:3]:
        top_actions.append(
            {
                "player_id": item.get("player_id"),
                "role_id": item.get("role_id"),
                "phase": item.get("phase"),
                "action_type": item.get("action_type"),
                "total_tokens": item.get("total_tokens"),
                "latency_ms": item.get("latency_ms"),
                "fallback_used": item.get("fallback_used"),
                "fallback_reason": item.get("fallback_reason"),
            }
        )
    phases = [e for e in events if e.event_type == "phase_changed"]
    nominations = [e for e in events if e.event_type == "nomination_started"]
    nomination_prompts = [
        e for e in events
        if e.event_type in {"nomination_prompted", "nomination_window_opened"}
    ]
    nomination_attempts = [e for e in events if e.event_type == "nomination_attempted"]
    votes = [e for e in events if e.event_type == "vote_cast"]
    execution_resolutions = [e for e in events if e.event_type == "execution_resolved"]
    actual_executions = [
        e for e in execution_resolutions
        if e.payload.get("executed") or e.target
    ]
    night_actions = [e for e in events if e.event_type == "night_action_resolved"]
    return {
        "game_id": orchestrator.state.game_id,
        "phase_count": len(phases),
        "nomination_prompt_count": len(nomination_prompts),
        "nomination_attempt_count": len(nomination_attempts),
        "legal_nomination_count": len(nominations),
        "vote_count": len(votes),
        "execution_count": len(actual_executions),
        "execution_resolution_count": len(execution_resolutions),
        "night_action_count": len(night_actions),
        "last_execution": actual_executions[-1].payload if actual_executions else None,
        "current_phase": orchestrator.state.phase.value,
        "day_number": orchestrator.state.day_number,
        "round_number": orchestrator.state.round_number,
        "alive_count": orchestrator.state.alive_count,
        "ai_action_count": ai_summary.get("action_count", 0),
        "ai_total_tokens": ai_summary.get("total_tokens", 0),
        "ai_average_tokens_per_action": ai_summary.get("average_tokens_per_action", 0),
        "ai_fallback_count": ai_summary.get("fallback_count", 0),
        "ai_fallback_rate": ai_summary.get("fallback_rate", 0),
        "ai_tokens_by_phase": ai_summary.get("tokens_by_phase", {}),
        "ai_tokens_by_action_type": ai_summary.get("tokens_by_action_type", {}),
        "ai_tokens_by_player": ai_summary.get("tokens_by_player", {}),
        "ai_top_token_actions": top_actions,
        "phase_durations": runtime.get("phase_durations", []),
    }


def _phase_day(event) -> int:
    payload = event.payload or {}
    day_number = payload.get("day_number")
    if isinstance(day_number, int):
        return day_number
    return getattr(event, "day_number", 0) or 0


def event_stop_match(event, stop_after: str) -> StopMatch | None:
    if stop_after == "game_over" and event.event_type == "phase_changed":
        if event.phase == GamePhase.GAME_OVER:
            return StopMatch("game_over", f"event={event.event_type}, phase=game_over")
    if stop_after == "first_execution":
        if event.event_type == "execution_resolved" and bool(event.payload.get("executed") or event.target):
            executed = event.payload.get("executed") or event.target
            return StopMatch("first_execution", f"execution_resolved executed={executed}")
    if stop_after == "day_1":
        if event.event_type == "phase_changed" and event.phase == GamePhase.NIGHT and _phase_day(event) >= 2:
            return StopMatch("day_1", f"phase_changed to night after day 1, day_number={_phase_day(event)}")
        if event.phase == GamePhase.GAME_OVER:
            return StopMatch("day_1", "game_over before day_1 boundary")
    if stop_after == "night_2":
        if event.event_type == "phase_changed" and event.phase == GamePhase.NIGHT and _phase_day(event) >= 2:
            return StopMatch("night_2", f"phase_changed to night_2, day_number={_phase_day(event)}")
        if event.phase == GamePhase.GAME_OVER:
            return StopMatch("night_2", "game_over before night_2 boundary")
    return None


def stop_match(orchestrator: GameOrchestrator, stop_after: str) -> StopMatch | None:
    events = merged_events(orchestrator)
    if stop_after == "game_over":
        if orchestrator.state.phase == GamePhase.GAME_OVER:
            return StopMatch("game_over", "state.phase=game_over")
        for event in events:
            match = event_stop_match(event, stop_after)
            if match:
                return match
        return None
    if stop_after == "first_execution":
        for event in events:
            match = event_stop_match(event, stop_after)
            if match:
                return match
        return None
    if stop_after == "day_1":
        if orchestrator.state.phase == GamePhase.GAME_OVER:
            return StopMatch("day_1", "state.phase=game_over before day_1 boundary")
        for event in events:
            match = event_stop_match(event, stop_after)
            if match:
                return match
        return None
    if stop_after == "night_2":
        if orchestrator.state.phase == GamePhase.GAME_OVER:
            return StopMatch("night_2", "state.phase=game_over before night_2 boundary")
        for event in events:
            match = event_stop_match(event, stop_after)
            if match:
                return match
        return None
    return None


def should_stop(orchestrator: GameOrchestrator, stop_after: str) -> bool:
    return stop_match(orchestrator, stop_after) is not None


def event_triggers_stop(event, stop_after: str) -> bool:
    return event_stop_match(event, stop_after) is not None


async def wait_for_stop_condition(orchestrator: GameOrchestrator, stop_after: str, timeout_seconds: int):
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        match = stop_match(orchestrator, stop_after)
        if match:
            return match.status
        await asyncio.sleep(0.2)
    return "timeout"


async def run_simulation(options: SimulationOptions):
    print("\n" + "=" * 60)
    print("=== [开始全自动对局测试 & 规则审计] ===")
    print("=" * 60 + "\n")
    print(
        f">>> 配置: backend={options.backend}, players={options.player_count}, "
        f"discussion_rounds={options.discussion_rounds}, stop_after={options.stop_after}, "
        f"timeout={options.timeout_seconds}s"
    )

    backend = build_backend(options.backend)
    state = GameState(phase=GamePhase.SETUP)
    orchestrator = GameOrchestrator(state)

    from src.agents.storyteller_agent import StorytellerAgent

    storyteller = StorytellerAgent(backend)
    orchestrator.storyteller_agent = storyteller
    orchestrator.default_agent_backend = backend

    stop_reason = {"value": "timeout", "detail": ""}
    original_publish = orchestrator.event_bus.publish

    async def publish_with_stop(event):
        await original_publish(event)
        match = event_stop_match(event, options.stop_after)
        if match is None and options.stop_after != "game_over":
            match = stop_match(orchestrator, options.stop_after)
        if match:
            stop_reason["value"] = match.status
            stop_reason["detail"] = match.reason
            logger.info(
                ">>> [STOP] 命中停止条件: stop_after=%s, reason=%s, event=%s, phase=%s, round=%s",
                options.stop_after,
                match.reason,
                event.event_type,
                event.phase,
                event.round_number,
            )
            raise SimulationStop(match.reason)

    orchestrator.event_bus.publish = publish_with_stop  # type: ignore[assignment]

    loop_task = asyncio.create_task(orchestrator.run_game_loop())
    try:
        await asyncio.sleep(0.2)
        await orchestrator.run_setup_with_options(
            player_count=options.player_count,
            host_id="host",
            is_human=False,
            discussion_rounds=options.discussion_rounds,
            storyteller_mode="auto",
            audit_mode=options.audit_mode,
            max_nomination_rounds=options.max_nomination_rounds,
            backend_mode=options.backend,
        )

        print(">>> [OK] setup 完成。")
        print(f">>> 当前座位顺序: {list(orchestrator.state.seat_order)}")
        try:
            await asyncio.wait_for(loop_task, timeout=options.timeout_seconds)
        except asyncio.TimeoutError:
            stop_reason["value"] = "timeout"
            if not loop_task.done():
                loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await loop_task
        except SimulationStop:
            with suppress(SimulationStop):
                await loop_task
        else:
            stop_reason["value"] = "game_over" if orchestrator.state.phase == GamePhase.GAME_OVER else "completed"
    finally:
        orchestrator.event_bus.publish = original_publish  # type: ignore[assignment]

    summary = collect_summary(orchestrator)
    print("\n" + "-" * 60)
    print("审计摘要")
    for key, value in summary.items():
        print(f"- {key}: {value}")
    print(f"- stop_after_requested: {options.stop_after}")
    print(f"- stop_status: {stop_reason['value']}")
    if stop_reason["detail"]:
        print(f"- stop_reason: {stop_reason['detail']}")
    if orchestrator.winner:
        print(f"- winner: {orchestrator.winner.value}")
    print("-" * 60 + "\n")
    return 0 if stop_reason["value"] == options.stop_after else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run_simulation(parse_args())))
    except Exception as exc:
        logger.exception("模拟局运行失败: %s", exc)
        raise
