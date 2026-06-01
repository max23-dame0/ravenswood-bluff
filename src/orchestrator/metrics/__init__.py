"""MetricsCollector — latency tracking, action metrics, data snapshots."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Any

from src.agents.base_agent import BaseAgent

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Latency tracking, action metrics, and data snapshots extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    async def _timed_act(
        self,
        agent: BaseAgent,
        visible_state: Any,
        action_type: str,
        legal_context: Any = None,
        player_id: str = "",
        phase: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run agent.act() with latency tracking and hard time budget.

        On timeout, returns a legal fallback action and records the fallback reason.
        """
        budget_ms = self._action_budget_ms(agent, action_type)
        budget_s = budget_ms / 1000.0
        start = time.perf_counter()
        fallback_used = False
        fallback_reason = ""

        try:
            act_call = agent.act(visible_state, action_type, legal_context=legal_context, **kwargs)
            if self._should_wait_without_orchestrator_timeout(agent, action_type):
                action = await act_call
            else:
                action = await asyncio.wait_for(
                    act_call,
                    timeout=budget_s,
                )
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            fallback_used = True
            fallback_reason = f"orchestrator_hard_timeout:{action_type}"
            action = self._smart_latency_fallback(agent, action_type, visible_state, legal_context, fallback_reason)
            logger.warning(
                f"[Speed] {player_id} {action_type} timed out after {elapsed_ms:.0f}ms "
                f"(budget {budget_ms}ms), using fallback"
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            fallback_used = True
            fallback_reason = f"error:{type(exc).__name__}"
            action = self._smart_latency_fallback(agent, action_type, visible_state, legal_context, fallback_reason)
            self._record_recent_exception(f"{action_type}:{player_id}", exc)

        elapsed_ms = (time.perf_counter() - start) * 1000
        agent_metric = self._latest_agent_metric(agent, action_type)
        if action_type in {"speak", "defense_speech"}:
            self._record_speech_metric_from_action(visible_state, action_type, action, agent_metric, fallback_used, fallback_reason)

        # Record latency
        latency_record = {
            "player_id": player_id or getattr(agent, "player_id", "unknown"),
            "action_type": action_type,
            "phase": phase,
            "latency_ms": round(elapsed_ms, 1),
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "timeout_budget_ms": budget_ms,
            "budget_source": "agent_difficulty_preset" if hasattr(agent, "_action_timeout_seconds") else "orchestrator_default",
        }
        if agent_metric:
            latency_record["agent_fallback_used"] = bool(agent_metric.get("fallback_used"))
            latency_record["agent_fallback_reason"] = agent_metric.get("fallback_reason", "")
            latency_record["speech_source"] = agent_metric.get("speech_source", "")
            latency_record["backend_speed_profile"] = agent_metric.get("backend_speed_profile", "")
        self._o._action_latencies.append(latency_record)
        if hasattr(self._o.data_collector, "record_action_latency"):
            self._o.data_collector.record_action_latency(
                player_id=latency_record["player_id"],
                action_type=action_type,
                phase=phase,
                latency_ms=elapsed_ms,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )
        return action

    @staticmethod
    def _should_wait_without_orchestrator_timeout(agent: BaseAgent, action_type: str) -> bool:
        if os.getenv("AI_FORCE_GAME_TIMEOUTS", "0") == "1":
            return False
        if action_type not in {"speak", "defense_speech"}:
            return False
        # Human agents: always wait, no timeout for speech
        from src.agents.human_agent import HumanAgent
        if isinstance(agent, HumanAgent):
            return True
        profile = getattr(agent, "_backend_speed_profile", "")
        return profile in {"live", "live_slow"}

    def _action_budget_ms(self, agent: BaseAgent, action_type: str) -> int:
        getter = getattr(agent, "_action_timeout_seconds", None)
        if callable(getter):
            try:
                agent_ms = int(float(getter(action_type)) * 1000)
                margin = 1500 if action_type in {"speak", "defense_speech"} else 500
                return max(agent_ms + margin, self._o._action_latency_budgets.get(action_type, 2000))
            except Exception:
                pass
        return self._o._action_latency_budgets.get(action_type, 2000)

    @staticmethod
    def _latest_agent_metric(agent: BaseAgent, action_type: str) -> dict[str, Any] | None:
        exporter = getattr(agent, "export_action_metrics", None)
        if not callable(exporter):
            return None
        try:
            records = exporter(limit=5)
        except Exception:
            return None
        for rec in reversed(records or []):
            if rec.get("action_type") == action_type:
                return rec
        return None

    def _record_speech_metric_from_action(
        self,
        visible_state: Any,
        action_type: str,
        action: dict[str, Any],
        agent_metric: dict[str, Any] | None,
        orchestrator_fallback: bool,
        orchestrator_reason: str,
    ) -> None:
        key = (getattr(visible_state, "day_number", self._o.state.day_number), getattr(visible_state, "round_number", self._o.state.round_number))
        stats = self._o.day_discussion_handler._speech_round_stats.setdefault(
            key,
            {
                "speech_count": 0,
                "fallback_count": 0,
                "orchestrator_timeout_count": 0,
                "cache_finalized_count": 0,
                "llm_success_count": 0,
            },
        )
        stats["speech_count"] += 1
        speech_source = (agent_metric or {}).get("speech_source") or action.get("speech_source") or ""
        agent_fallback = bool((agent_metric or {}).get("fallback_used"))
        if orchestrator_fallback or agent_fallback:
            stats["fallback_count"] += 1
        if orchestrator_reason.startswith("orchestrator_hard_timeout"):
            stats["orchestrator_timeout_count"] += 1
        if str(speech_source).startswith("cache_finalized"):
            stats["cache_finalized_count"] += 1
        if speech_source == "live_llm":
            stats["llm_success_count"] += 1

        # Fallback circuit breaker: warn when a single round has excessive fallback
        if action_type == "speak" and stats["speech_count"] >= 3:
            round_fallback_rate = stats["fallback_count"] / stats["speech_count"]
            if round_fallback_rate >= 0.4 and not stats.get("release_blocker_logged"):
                stats["release_blocker_logged"] = True
                logger.warning(
                    "[M5-L][release_blocker] day=%s round=%s fallback_rate=%.0f%% (%d/%d) "
                    "llm_success=%d cache_finalized=%d orchestrator_timeout=%d",
                    key[0], key[1],
                    round_fallback_rate * 100,
                    stats["fallback_count"], stats["speech_count"],
                    stats["llm_success_count"],
                    stats["cache_finalized_count"],
                    stats["orchestrator_timeout_count"],
                )

    @staticmethod
    def _latency_fallback(action_type: str, legal_context: Any = None) -> dict[str, Any]:
        """Return a legal fallback action when the primary path times out.

        This is the orchestrator-level hard timeout. Agent-level fallback
        (with persona-aware content) should have already fired first.
        """
        import random
        if action_type == "vote":
            return {"action": "vote", "decision": False, "reasoning": "orchestrator_hard_timeout:vote"}
        if action_type == "nomination_intent":
            return {"action": "not_nominating", "target": "not_nominating", "reasoning": "orchestrator_hard_timeout:nomination_intent"}
        if action_type == "speak":
            content = random.choice([
                "我还在想。",
                "让我再琢磨一下。",
                "嗯……等我理理思路。",
                "我在整理思路，稍等。",
                "有点复杂，我再想想。",
            ])
            return {"action": "speak", "content": content, "reasoning": "orchestrator_hard_timeout:speak"}
        if action_type == "defense_speech":
            content = random.choice([
                "我没有要补充的。",
                "该说的我都说了。",
                "我能说的就这些了。",
                "我没什么好辩解的。",
            ])
            return {"action": "speak", "content": content, "reasoning": "orchestrator_hard_timeout:defense_speech"}
        if action_type == "night_action":
            return {"action": "none", "reasoning": "orchestrator_hard_timeout:night_action"}
        return {"action": "none", "reasoning": f"orchestrator_hard_timeout:{action_type}"}

    @staticmethod
    def _smart_latency_fallback(
        agent: Any,
        action_type: str,
        visible_state: Any,
        legal_context: Any,
        reason: str,
    ) -> dict[str, Any]:
        """Try agent's intelligent fallback before falling back to hardcoded defaults.

        When the orchestrator hard timeout fires, the agent's own fallback may not
        have had a chance to execute. This method calls the agent's _fallback_decision
        to get a persona-aware, game-state-aware decision instead of a dumb default.
        """
        fallback_fn = getattr(agent, "_fallback_decision", None)
        if callable(fallback_fn):
            try:
                return fallback_fn(visible_state, legal_context, action_type, reason)
            except Exception as exc:
                logger.debug(
                    "[Speed] agent _fallback_decision failed for %s: %s, using hardcoded fallback",
                    action_type, exc,
                )
        return MetricsCollector._latency_fallback(action_type, legal_context)

    def get_action_latency_summary(self) -> dict[str, Any]:
        """Compute P50/P95/max/timeout stats from collected latency records."""
        if not self._o._action_latencies:
            return {"record_count": 0, "by_action_type": {}}

        by_type: dict[str, list[float]] = {}
        timeout_counts: dict[str, int] = {}
        fallback_counts: dict[str, int] = {}

        for rec in self._o._action_latencies:
            at = rec["action_type"]
            by_type.setdefault(at, []).append(rec["latency_ms"])
            if rec["fallback_used"]:
                fallback_counts[at] = fallback_counts.get(at, 0) + 1
                if "latency_budget_exceeded" in rec.get("fallback_reason", ""):
                    timeout_counts[at] = timeout_counts.get(at, 0) + 1

        def _percentile(data: list[float], pct: float) -> float:
            if not data:
                return 0.0
            sorted_data = sorted(data)
            idx = int(len(sorted_data) * pct / 100)
            return sorted_data[min(idx, len(sorted_data) - 1)]

        summary: dict[str, Any] = {"record_count": len(self._o._action_latencies), "by_action_type": {}}
        for at, latencies in by_type.items():
            summary["by_action_type"][at] = {
                "count": len(latencies),
                "p50_ms": round(_percentile(latencies, 50), 1),
                "p95_ms": round(_percentile(latencies, 95), 1),
                "max_ms": round(max(latencies), 1),
                "timeout_count": timeout_counts.get(at, 0),
                "fallback_count": fallback_counts.get(at, 0),
            }
        return summary

    def _record_recent_exception(self, context: str, exc: Exception) -> None:
        self._o._recent_exception = {
            "context": context,
            "type": type(exc).__name__,
            "message": str(exc),
            "timestamp": time.time(),
        }

    def _human_player_ids(self) -> set[str]:
        if self._o.state.config and self._o.state.config.human_player_ids:
            return set(self._o.state.config.human_player_ids)
        return set()

    def _ai_discussion_message_limit(self) -> int | None:
        config = self._o.state.config
        if not config or not config.is_human_participant:
            return None
        if config.ai_discussion_message_limit is not None:
            return max(0, int(config.ai_discussion_message_limit))
        all_ai_count = sum(
            1
            for player in self._o.state.players
            if player.player_id not in self._human_player_ids()
        )
        return all_ai_count

    def _record_pace_event(self, event: dict[str, Any]) -> None:
        payload = dict(self._o.state.payload)
        events = list(payload.get("pace_events", []))
        event.setdefault("phase", self._o.state.phase.value)
        event.setdefault("day_number", self._o.state.day_number)
        event.setdefault("round_number", self._o.state.round_number)
        event.setdefault("timestamp", time.time())
        events.append(event)
        payload["pace_events"] = events[-20:]
        self._o.state = self._o.state.with_update(payload=payload)

    def _collect_ai_action_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for agent in self._o.broker.agents.values():
            exporter = getattr(agent, "export_action_metrics", None)
            if not exporter:
                continue
            try:
                records.extend(exporter())
            except Exception as exc:
                logger.warning("export_action_metrics failed for %s: %s", getattr(agent, "player_id", "unknown"), exc)
        return records

    def _snapshot_ai_action_positions(self) -> dict[str, int]:
        positions: dict[str, int] = {}
        for player_id, agent in self._o.broker.agents.items():
            exporter = getattr(agent, "export_action_metrics", None)
            if not exporter:
                continue
            try:
                positions[player_id] = len(exporter())
            except Exception as exc:
                logger.warning("export_action_metrics failed for %s: %s", getattr(agent, "player_id", "unknown"), exc)
                positions[player_id] = 0
        return positions

    def _collect_ai_action_records_since(self, positions: dict[str, int]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for player_id, agent in self._o.broker.agents.items():
            exporter = getattr(agent, "export_action_metrics", None)
            if not exporter:
                continue
            try:
                agent_records = exporter()
            except Exception as exc:
                logger.warning("export_action_metrics failed for %s: %s", getattr(agent, "player_id", "unknown"), exc)
                continue
            records.extend(agent_records[positions.get(player_id, 0):])
        return records

    @staticmethod
    def _percentile(sorted_values: list[float], p: float) -> float:
        if not sorted_values:
            return 0.0
        k = (len(sorted_values) - 1) * (p / 100.0)
        f = int(k)
        c = f + 1
        if c >= len(sorted_values):
            return sorted_values[-1]
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])

    def _latency_stats(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        latencies = sorted(float(r.get("latency_ms", 0) or 0) for r in records)
        if not latencies:
            return {"p50_ms": 0, "p95_ms": 0, "max_ms": 0, "count": 0}
        return {
            "p50_ms": round(self._percentile(latencies, 50), 1),
            "p95_ms": round(self._percentile(latencies, 95), 1),
            "max_ms": round(latencies[-1], 1),
            "count": len(latencies),
        }

    def _latency_by_action_type(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        by_type: dict[str, list[float]] = {}
        for r in records:
            at = str(r.get("action_type") or "unknown")
            by_type.setdefault(at, []).append(float(r.get("latency_ms", 0) or 0))
        result = {}
        for at, vals in by_type.items():
            vals.sort()
            result[at] = {
                "p50_ms": round(self._percentile(vals, 50), 1),
                "p95_ms": round(self._percentile(vals, 95), 1),
                "max_ms": round(vals[-1], 1),
                "count": len(vals),
            }
        return result

    def _summarize_ai_action_records(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        total_tokens = sum(int(item.get("total_tokens", 0) or 0) for item in records)
        fallback_count = sum(1 for item in records if item.get("fallback_used"))
        fallback_tokens = sum(int(item.get("total_tokens", 0) or 0) for item in records if item.get("fallback_used"))
        by_player: dict[str, int] = {}
        by_action_type: dict[str, int] = {}
        by_phase: dict[str, int] = {}
        fallback_by_player: dict[str, int] = {}
        fallback_by_action_type: dict[str, int] = {}
        fallback_by_phase: dict[str, int] = {}
        speak_records = [item for item in records if item.get("action_type") in {"speak", "defense_speech"}]
        speak_fallbacks = [item for item in speak_records if item.get("fallback_used")]
        llm_speeches = [item for item in speak_records if item.get("speech_source") == "live_llm"]
        cache_speeches = [item for item in speak_records if str(item.get("speech_source") or "").startswith("cache_finalized")]
        for item in records:
            player_id = str(item.get("player_id") or "unknown")
            action_type = str(item.get("action_type") or "unknown")
            phase = str(item.get("phase") or "unknown")
            tokens = int(item.get("total_tokens", 0) or 0)
            by_player[player_id] = by_player.get(player_id, 0) + tokens
            by_action_type[action_type] = by_action_type.get(action_type, 0) + tokens
            by_phase[phase] = by_phase.get(phase, 0) + tokens
            if item.get("fallback_used"):
                fallback_by_player[player_id] = fallback_by_player.get(player_id, 0) + 1
                fallback_by_action_type[action_type] = fallback_by_action_type.get(action_type, 0) + 1
                fallback_by_phase[phase] = fallback_by_phase.get(phase, 0) + 1
        top_calls = sorted(records, key=lambda item: int(item.get("total_tokens", 0) or 0), reverse=True)[:10]
        return {
            "action_count": len(records),
            "total_tokens": total_tokens,
            "average_tokens_per_action": round(total_tokens / len(records), 2) if records else 0,
            "fallback_count": fallback_count,
            "fallback_rate": round(fallback_count / len(records), 3) if records else 0,
            "fallback_tokens": fallback_tokens,
            "fallback_token_share": round(fallback_tokens / total_tokens, 3) if total_tokens else 0,
            "tokens_by_player": by_player,
            "tokens_by_action_type": by_action_type,
            "tokens_by_phase": by_phase,
            "fallback_by_player": fallback_by_player,
            "fallback_by_action_type": fallback_by_action_type,
            "fallback_by_phase": fallback_by_phase,
            "top_token_actions": top_calls,
            "latency": self._latency_stats(records),
            "latency_by_action_type": self._latency_by_action_type(records),
            "speech": {
                "count": len(speak_records),
                "fallback_count": len(speak_fallbacks),
                "fallback_rate": round(len(speak_fallbacks) / len(speak_records), 3) if speak_records else 0,
                "llm_successful_speech_rate": round(len(llm_speeches) / len(speak_records), 3) if speak_records else 0,
                "cache_finalized_rate": round(len(cache_speeches) / len(speak_records), 3) if speak_records else 0,
                "round_stats": {
                    f"day{day}_round{round_no}": dict(stats)
                    for (day, round_no), stats in self._o.day_discussion_handler._speech_round_stats.items()
                },
            },
            "claim_extraction_failures": dict(self._o._claim_extraction_failures),
        }

    def collect_ai_action_metrics(self, limit: int = 40) -> dict[str, Any]:
        records = self._collect_ai_action_records()
        records.sort(key=lambda item: (item.get("day_number", 0), item.get("round_number", 0), item.get("latency_ms", 0)))
        return {
            "summary": self._summarize_ai_action_records(records),
            "recent": records[-limit:],
        }

    def collect_runtime_diagnostics(self) -> dict[str, Any]:
        now = time.time()
        phase_elapsed_ms = int((now - self._o._phase_started_at) * 1000) if self._o._phase_started_at else None
        current_phase_records = self._collect_ai_action_records_since(self._o._phase_started_action_positions)
        return {
            "current_phase": self._o.state.phase.value,
            "current_waiting_for": self._o._current_waiting_for,
            "last_progress_at": self._o._last_progress_at,
            "seconds_since_progress": round(now - self._o._last_progress_at, 2) if self._o._last_progress_at else None,
            "phase_elapsed_ms": phase_elapsed_ms,
            "recent_exception": self._o._recent_exception,
            "current_phase_ai_action_summary": self._summarize_ai_action_records(current_phase_records),
            "phase_durations": self._o._phase_duration_history[-20:],
            "pace_events": list(self._o.state.payload.get("pace_events", []))[-20:],
        }

    def _record_data_snapshot(self, stage: str, **extra_summary: Any) -> None:
        last_event = self._o.state.event_log[-1].event_type if self._o.state.event_log else None
        nomination_state = self._o.state.payload.get("nomination_state", {})
        ai_snapshot = self._build_ai_data_snapshot_summary()
        snapshot = {
            "game_id": self._o.state.game_id,
            "stage": stage,
            "phase": self._o.state.phase.value,
            "day_number": self._o.state.day_number,
            "round_number": self._o.state.round_number,
            "summary": {
                "alive_count": self._o.state.alive_count,
                "dead_count": self._o.state.player_count - self._o.state.alive_count,
                "player_count": self._o.state.player_count,
                "chat_messages": len(self._o.state.chat_history),
                "last_event_type": last_event,
                "nomination_stage": nomination_state.get("stage"),
                "visible_state_summary": {
                    "alive_players": [player.name for player in self._o.state.get_alive_players()],
                    "dead_players": [player.name for player in self._o.state.players if not player.is_alive],
                    "current_nominee": self._o._player_label(self._o.state.current_nominee) if self._o.state.current_nominee else None,
                    "current_nominator": self._o._player_label(self._o.state.current_nominator) if self._o.state.current_nominator else None,
                },
                "working_memory_summary": ai_snapshot["working_memory_summary"],
                "social_graph_summary": ai_snapshot["social_graph_summary"],
                "claim_history_summary": ai_snapshot["claim_history_summary"],
                "retrieval_summary": ai_snapshot["retrieval_summary"],
                **extra_summary,
            },
        }
        self._o.data_collector.record_snapshot(snapshot)

    def _build_ai_data_snapshot_summary(self) -> dict[str, Any]:
        summary = {
            "working_memory_summary": {},
            "social_graph_summary": {},
            "claim_history_summary": {},
            "retrieval_summary": {},
        }
        for player_id, agent in self._o.broker.agents.items():
            if not hasattr(agent, "build_data_snapshot_summary"):
                continue
            try:
                agent_summary = agent.build_data_snapshot_summary()
            except Exception as exc:
                logger.warning("build_data_snapshot_summary failed for %s: %s", player_id, exc)
                continue
            summary["working_memory_summary"][player_id] = agent_summary.get("working_memory_summary", {})
            summary["social_graph_summary"][player_id] = agent_summary.get("social_graph_summary", "")
            summary["claim_history_summary"][player_id] = agent_summary.get("claim_history_summary", {})
            summary["retrieval_summary"][player_id] = agent_summary.get("retrieval_summary", {})
        return summary
