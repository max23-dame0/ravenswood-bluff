"""
AI Agent 实现

通过 LLM 驱动的游戏内角色。

本文件为 facade：仅负责编排与路由，具体行为逻辑下沉到子模块
（`decision/prompt/memory/observation/speech/strategy/...`）与委托层
`ai_agent_delegation.py`（见 `DECISIONS.md` D006）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import time
from typing import Any

from src.agents.ai_agent_delegation import (
    DecisionDelegationMixin,
    EvilDelegationMixin,
    MemoryDelegationMixin,
    ObserverDelegationMixin,
    PromptDelegationMixin,
    SignalSummaryMixin,
    SpeechDelegationMixin,
)
from src.agents.base_agent import BaseAgent

# Re-export from extracted modules for backward compatibility
from src.agents.deception.deception_tracker import DeceptionTracker
from src.agents.decision.decision_engine import DecisionEngine
from src.agents.decision.decision_noise import DecisionNoise
from src.agents.difficulty_presets import DifficultyPreset, get_preset
from src.agents.memory.episodic_memory import EpisodicMemory
from src.agents.memory.memory_controller import MemoryController
from src.agents.memory.player_profile import PlayerProfileStore
from src.agents.memory.social_graph import SocialGraph
from src.agents.memory.vector_memory import VectorMemory
from src.agents.memory.working_memory import WorkingMemory
from src.agents.observation.event_observer import EventObserver
from src.agents.persona.persona import Persona
from src.agents.prompt.prompt_factory import PromptFactory
from src.agents.speech.speech_sanitizer import SpeechSanitizer
from src.agents.strategy.evil_strategy import EvilStrategy
from src.content.trouble_brewing_terms import get_role_name
from src.engine.data_collector import GameDataCollector
from src.llm.base_backend import LLMBackend
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    PlayerState,
)

logger = logging.getLogger(__name__)


class AIAgent(
    DecisionDelegationMixin,
    PromptDelegationMixin,
    MemoryDelegationMixin,
    ObserverDelegationMixin,
    SpeechDelegationMixin,
    EvilDelegationMixin,
    SignalSummaryMixin,
    BaseAgent,
):
    """
    AI 智能体（facade：编排 + 路由，逻辑见子模块与 ai_agent_delegation）
    """

    def __init__(
        self,
        player_id: str,
        name: str,
        backend: LLMBackend,
        persona: Persona,
        player_count: int = 10,
        data_collector: GameDataCollector | None = None,
        difficulty: str = "standard",
    ) -> None:
        super().__init__(player_id, name)

        # 依赖
        self.backend = backend
        self.persona = persona
        self.player_count = player_count
        self.data_collector = data_collector
        self.difficulty = difficulty
        self.difficulty_preset: DifficultyPreset = get_preset(difficulty)
        self.decision_noise = DecisionNoise(difficulty=difficulty, player_id=player_id)
        self.deception_tracker = DeceptionTracker(deception_level=self.difficulty_preset.deception)

        # 动态计算记忆限制
        # 1. 观察记录：15人局约 45 条，10人局 30 条
        self._obs_limit = max(20, int(player_count * 3))
        # 2. 事实记录：15人局约 30 条
        self._fact_limit = max(15, int(player_count * 2))
        # 3. 反思阈值：积累到多少条观察后触发一次蒸馏
        self._reflection_threshold = max(30, int(player_count * 5))

        # 记忆模块
        self.working_memory = WorkingMemory(
            observation_limit=self._obs_limit,
            fact_limit=self._fact_limit,
            internal_thought_limit=5,
            impression_limit=max(5, int(player_count / 2)),
            storage_limit=max(40, int(player_count * 4)),
        )
        self.episodic_memory = EpisodicMemory()
        embedding_dimension = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        self.vector_memory = VectorMemory(backend=backend, dimension=embedding_dimension)
        self.social_graph = SocialGraph(
            my_player_id=player_id,
            note_limit=max(30, int(player_count * 3)),
            claim_limit=max(20, int(player_count * 2)),
            summary_note_limit=6,
            summary_claim_limit=5,
        )
        self._last_retrieval_query: str = ""
        self._last_retrieval_items: list[dict[str, Any]] = []
        self._last_social_prime_signature: str = ""
        self.action_metrics: list[dict[str, Any]] = []
        self._pending_fallback_reason: str | None = None
        self._fallback_turn_counter: int = 0
        self._prompt_factory = PromptFactory(self)
        self._speech_sanitizer = SpeechSanitizer(self)
        self._decision_engine = DecisionEngine(self)
        self._event_observer = EventObserver(self)
        self._evil_strategy = EvilStrategy(self)
        self._memory_controller = MemoryController(self)
        # PLN-038 阶段 E：对局隔离 + 玩家跨局档案
        self.game_id: str | None = None
        self._player_profile = PlayerProfileStore(player_id, name)
        self._long_term_summary: str = ""
        self._refresh_persona_profile()

    # 按 action type 的硬时间预算（秒）
    ACTION_BUDGET: dict[str, float] = {
        "vote": 2.0,
        "nomination_intent": 2.0,
        "night_action": 1.5,
        "speak": 2.0,
        "defense_speech": 2.5,
    }
    _DEFAULT_BUDGET = 3.0

    # 按 action type 的 LLM 思考/输出策略表（PLN-037 P0-4.1）
    LLM_STRATEGY_BY_ACTION: dict[str, dict[str, Any]] = {
        # max_tokens 需为 thinking 预留充足空间（2026-08-05 live 实测：DeepSeek thinking
        # 长度波动大——nomination_intent reasoning 835~1200、speak 270~1000、vote 可达 800，
        # 上限不足会 finish=length 致 content/tool_calls 全空、empty_response fallback。
        # 再提高一档（~25% 余量）以稳定清零 fallback；实际占用以实测再收敛）。
        "vote": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 1600},
        "night_action": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 1400},
        "nominate": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 1600},
        "nomination_intent": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 2400},
        "speak": {"thinking": "disabled", "reasoning_effort": "low", "max_tokens": 2000},
        "defense_speech": {"thinking": "disabled", "reasoning_effort": "low", "max_tokens": 2000},
        "reflect": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 150},
        "archive": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 150},
        "claim": {"thinking": "disabled", "reasoning_effort": None, "max_tokens": 150},
        "think": {"thinking": "disabled", "reasoning_effort": "low", "max_tokens": 1000},
    }

    # 高价值推理动作：这些动作按难度预设开启深度思考（用户决策 2026-08-05）。
    _HIGH_VALUE_THINKING_ACTIONS = {
        "speak",
        "defense_speech",
        "nominate",
        "nomination_intent",
        "vote",
        "night_action",
        "think",
    }

    def _thinking_level(self) -> str:
        """按难度预设返回思考强度 off/medium/high；env AI_THINKING_LEVEL 可全局覆盖。"""
        override = os.getenv("AI_THINKING_LEVEL", "").strip().lower()
        if override in {"off", "low", "medium", "high"}:
            return "off" if override == "low" else override
        level_by_difficulty = {
            "casual": "off",
            "standard": "medium",
            "master": "high",
            "chaos": "high",
        }
        difficulty = getattr(self, "difficulty", "standard")
        key = difficulty.value if hasattr(difficulty, "value") else str(difficulty)
        return level_by_difficulty.get(key, "medium")

    def _llm_strategy_for_action(self, action_type: str) -> dict[str, Any]:
        """返回该动作对应的 LLM 策略；未知动作给保守兜底（不关思考但限 max_tokens）。

        深度思考强度按难度预设分级（用户决策 2026-08-05）：
        casual=off / standard=medium / master=high / chaos=high；
        env AI_THINKING_LEVEL 可全局覆盖。reflect/archive/claim 等总结类动作保持 disabled。
        """
        strategy = dict(
            self.LLM_STRATEGY_BY_ACTION.get(
                action_type,
                {"thinking": None, "reasoning_effort": None, "max_tokens": 400},
            )
        )
        if action_type in self._HIGH_VALUE_THINKING_ACTIONS:
            level = self._thinking_level()
            if level == "off":
                strategy["thinking"] = "disabled"
                strategy["reasoning_effort"] = None
            elif level == "medium":
                strategy["thinking"] = "enabled"
                strategy["reasoning_effort"] = "medium"
            else:  # high
                strategy["thinking"] = "enabled"
                strategy["reasoning_effort"] = "high"
        else:
            strategy["thinking"] = "disabled"
            strategy["reasoning_effort"] = None
        return strategy

    def _append_player_thought_log(
        self,
        visible_state: AgentVisibleState,
        action: dict[str, Any],
        llm_thought: str,
        decision_reasoning: str,
        usage: dict | None,
        action_type: str,
    ) -> None:
        """把一次动作的思考轨迹追加到玩家对局记录
        `data/agents/{player_id}/games/{game_id}/thoughts.jsonl`（对局隔离）。

        为未来"共享经验池"设计（2026-08-05）：每个玩家视角的思考独立落盘，
        局后统一沉淀、新对局跨局复用，配合人格设定形成差异化的活人感。
        仅 live 后端落盘（mock 的模式匹配无沉淀价值，避免测试/模拟污染数据目录）。
        """
        try:
            from src.agents.tools.memory_tools import MemoryTools
            from src.llm.mock_backend import MockBackend

            if isinstance(self.backend, MockBackend):
                return

            game_id = self.game_id or getattr(visible_state, "game_id", None)
            base = MemoryTools.game_dir(self.player_id, game_id)
            entry = {
                "ts": time.time(),
                "phase": str(visible_state.phase),
                "round_number": visible_state.round_number,
                "day_number": getattr(visible_state, "day_number", None),
                "action_type": action_type,
                "action": action,
                "llm_thought": llm_thought,
                "decision_reasoning": decision_reasoning,
                "usage": usage or {},
            }
            with open(base / "thoughts.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("[%s] 思考记录落盘失败: %s", self.name, exc)

    def _extract_decision_from_reasoning(self, reasoning: str) -> str:
        """DeepSeek thinking 末尾可能写出决策 JSON；content 为空时从中恢复（2026-08-05）。

        复用 OpenAIBackend._extract_json_objects 扫描文本中的 JSON 对象，
        只返回含 action 键的决策对象 JSON 文本。
        """
        if not reasoning:
            return ""
        try:
            from src.llm.openai_backend import OpenAIBackend
        except ImportError:  # pragma: no cover - 防御性
            return ""
        for obj in OpenAIBackend._extract_json_objects(reasoning):
            if isinstance(obj, dict) and "action" in obj:
                return json.dumps(obj, ensure_ascii=False)
        return ""

    def _action_timeout_seconds(self, action_type: str = "") -> float:
        env_override = os.getenv("AI_ACTION_TIMEOUT_SECONDS")
        if env_override:
            try:
                return max(1.0, float(env_override))
            except ValueError:
                pass
        preset_budget_ms = self.difficulty_preset.latency_budget.get(action_type)
        base = (
            (preset_budget_ms / 1000.0)
            if preset_budget_ms
            else self.ACTION_BUDGET.get(action_type, self._DEFAULT_BUDGET)
        )
        if self._backend_speed_profile in {"live", "live_slow"}:
            live_minimums = {
                "vote": 20.0,
                "nomination_intent": 40.0,
                "night_action": 60.0,
                "speak": 300.0,
                "defense_speech": 300.0,
            }
            slow_minimums = {
                "vote": 30.0,
                "nomination_intent": 60.0,
                "night_action": 90.0,
                "speak": 420.0,
                "defense_speech": 420.0,
            }
            minimums = (
                slow_minimums if self._backend_speed_profile == "live_slow" else live_minimums
            )
            base = max(base, minimums.get(action_type, base))
        # Adaptive scaling: tighter budgets for larger games, but do not squeeze live LLM actions.
        if self._backend_speed_profile in {"live", "live_slow"} and action_type in {
            "vote",
            "nomination_intent",
            "night_action",
            "speak",
            "defense_speech",
        }:
            return base
        if self._speed_profile == "extreme":
            return max(0.5, base * 0.7)
        if self._speed_profile == "aggressive":
            return max(0.6, base * 0.85)
        return base

    @property
    def _backend_speed_profile(self) -> str:
        override = os.getenv("AI_BACKEND_SPEED_PROFILE", "").strip().lower()
        if override in {"mock", "fast", "live", "live_slow"}:
            return override
        backend_name = self.backend.__class__.__name__.lower() if self.backend else ""
        module_name = self.backend.__class__.__module__.lower() if self.backend else ""
        model_name = ""
        try:
            model_name = (self.backend.get_model_name() or "").lower()
        except Exception:
            model_name = ""
        if "mock" in backend_name or "stub" in backend_name or "dummy" in backend_name:
            return "mock"
        if "openai_backend" in module_name or os.getenv("BOTC_BACKEND", "").lower() in {
            "live",
            "auto",
        }:
            if any(marker in model_name for marker in ("flash", "fast", "mini", "turbo")):
                return "live"
            return "live_slow"
        return "fast"

    def _should_wait_without_game_timeout(self, action_type: str) -> bool:
        if os.getenv("AI_FORCE_GAME_TIMEOUTS", "0") == "1":
            return False
        return action_type in {"speak", "defense_speech"} and self._backend_speed_profile in {
            "live",
            "live_slow",
        }

    def _record_action_metric(
        self,
        visible_state: AgentVisibleState,
        action_type: str,
        *,
        model: str = "",
        usage: dict[str, Any] | None = None,
        latency_ms: int = 0,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        **extra: Any,
    ) -> None:
        usage = usage or {}
        metric = {
            "game_id": visible_state.game_id,
            "player_id": self.player_id,
            "role_id": self.role_id or self.perceived_role_id or "unknown",
            "phase": visible_state.phase.value
            if hasattr(visible_state.phase, "value")
            else str(visible_state.phase),
            "day_number": visible_state.day_number,
            "round_number": visible_state.round_number,
            "action_type": action_type,
            "model": model or (self.backend.get_model_name() if self.backend else "unknown"),
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "prompt_cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens", 0) or 0),
            "prompt_cache_miss_tokens": int(usage.get("prompt_cache_miss_tokens", 0) or 0),
            "reasoning_tokens": int(usage.get("reasoning_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "timeout_budget_ms": int(self._action_timeout_seconds(action_type) * 1000),
            "backend_speed_profile": self._backend_speed_profile,
            "budget_source": "env_override"
            if os.getenv("AI_ACTION_TIMEOUT_SECONDS")
            else "difficulty_preset",
        }
        metric.update(extra)
        self.action_metrics.append(metric)
        self.action_metrics = self.action_metrics[-200:]
        if fallback_used:
            logger.warning(
                "[%s] fallback action recorded: action_type=%s reason=%s",
                self.name,
                action_type,
                fallback_reason,
            )

    def export_action_metrics(self, limit: int | None = None) -> list[dict[str, Any]]:
        metrics = list(self.action_metrics)
        return metrics[-limit:] if limit else metrics

    @staticmethod
    def _parse_llm_decision_json(response_text: str) -> dict[str, Any]:
        """Parse a decision JSON object from strict JSON or lightly decorated model output."""
        text = response_text.strip()
        if not text:
            raise ValueError("empty_response")

        candidates = [text]
        fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if fence_match:
            candidates.insert(0, fence_match.group(1).strip())

        decoder = json.JSONDecoder()
        last_error: Exception | None = None
        for candidate in candidates:
            cleaned = candidate.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, dict):
                    return parsed
                raise ValueError("decision_json_not_object")
            except Exception as exc:
                last_error = exc

            start = cleaned.find("{")
            while start != -1:
                try:
                    parsed, _ = decoder.raw_decode(cleaned[start:])
                    if isinstance(parsed, dict):
                        return parsed
                    raise ValueError("decision_json_not_object")
                except json.JSONDecodeError:
                    start = cleaned.find("{", start + 1)
                except Exception as exc:
                    last_error = exc
                    break

        if last_error:
            raise last_error
        raise json.JSONDecodeError("No JSON object found", text, 0)

    def synchronize_role(self, player_state: PlayerState) -> None:
        super().synchronize_role(player_state)
        # 初始化信任图谱，只针对他人
        # 可以在获取完整玩家列表后进行，这里不强制
        logger.debug(f"[{self.name}] 角色已同步: {self.role_id} ({self.team} 阵营)")
        self._refresh_persona_profile()

    def _stable_hash(self, *parts: Any) -> str:
        seed = "||".join("" if part is None else str(part) for part in parts)
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _pick_stable(self, options: list[str], *parts: Any) -> str:
        if not options:
            return ""
        digest = self._stable_hash(*parts)
        index = int(digest[:8], 16) % len(options)
        return options[index]

    def _difficulty_threshold_offset(self, key: str) -> float:
        """Get a numeric threshold offset from the difficulty preset, if present."""
        value = self.difficulty_preset.persona_overrides.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        return 0.0

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough token estimate: ~2 chars per token for mixed Chinese/English."""
        return max(1, len(text) // 2)

    @staticmethod
    def _cap_memory_section(text: str, max_tokens: int) -> str:
        """Truncate a memory section to fit within max_tokens, preserving structure."""
        if not text:
            return text
        estimated = AIAgent._estimate_tokens(text)
        if estimated <= max_tokens:
            return text
        # Proportionally truncate to fit
        ratio = max_tokens / estimated
        target_chars = int(len(text) * ratio * 0.9)  # 10% margin
        truncated = text[:target_chars]
        # Cut at last complete line
        last_newline = truncated.rfind("\n")
        if last_newline > target_chars // 2:
            truncated = truncated[:last_newline]
        return truncated + "\n... (记忆已截断以控制长度)"

    @staticmethod
    def _profile_claimed_role_id(profile: Any) -> str | None:
        if not profile:
            return None
        return getattr(profile, "current_self_claim", getattr(profile, "claimed_role_id", None))

    @property
    def _speed_profile(self) -> str:
        """Speed profile based on player count: standard/aggressive/extreme."""
        if self.player_count >= 10:
            return "extreme"
        if self.player_count >= 8:
            return "aggressive"
        return "standard"

    def _should_use_local_low_value_action(self, action_type: str) -> bool:
        if os.getenv("AI_FAST_LOW_VALUE_ACTIONS", "0") != "1":
            return False
        return action_type in {"nomination_intent", "vote"}

    async def act(
        self,
        visible_state: AgentVisibleState,
        action_type: str,
        legal_context: AgentActionLegalContext | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """决定如何行动"""
        logger.info(
            "[%s] 需要执行动作: %s persona=%s role=%s",
            self.name,
            action_type,
            self.persona_signature or "unknown",
            self.role_id or "unknown",
        )

        # Sync game_id to decision noise for cross-game seed isolation
        if not self.decision_noise.game_id and visible_state.game_id:
            self.decision_noise.game_id = visible_state.game_id
        # PLN-038 阶段 E：绑定当前对局 game_id（记忆工具对局隔离）
        if not self.game_id and visible_state.game_id:
            self.game_id = visible_state.game_id

        # W3-C: 检查记忆深度，必要时触发反思 (针对大局人数动态缩放)
        # refinement_mode 时跳过反思 — 草稿已经生成过，直接用
        refinement_mode = kwargs.get("refinement_mode", False)
        if (
            not refinement_mode
            and len(self.working_memory.observations) > self._reflection_threshold
        ):
            await self._reflect(visible_state)

        legal_context = legal_context or AgentActionLegalContext()
        self._prime_social_graph_from_state(visible_state)

        if self._should_use_local_low_value_action(action_type):
            decision = self._local_low_value_decision(visible_state, legal_context, action_type)
            self._record_action_metric(
                visible_state,
                action_type,
                model="local-heuristic",
                latency_ms=0,
                fallback_used=False,
            )
            return decision

        slayer_target = None
        if self._can_attempt_slayer_shot(visible_state, legal_context, action_type):
            slayer_target = self._select_slayer_shot_target(visible_state)
            if slayer_target:
                target_id, suspicion = slayer_target
                target_name = self._player_name_from_visible_state(target_id, visible_state)
                logger.info(
                    "[%s] 主动决定发动猎手技能: target=%s suspicion=%.2f",
                    self.name,
                    target_id,
                    suspicion,
                )
                self._record_action_metric(
                    visible_state,
                    "slayer_shot",
                    latency_ms=0,
                    fallback_used=False,
                )
                return {
                    "action": "slayer_shot",
                    "target": target_id,
                    "reasoning": f"我是猎手，当前对 {target_name} 的恶魔怀疑度极高（{suspicion:.2f}），决定白天主动开枪。",
                }

        # PLN-037 P0-4.3 + 方案B：有效草稿直接复用，跳过第二次 LLM（speak 输出减半）。
        # 仅当 refinement_mode=False（该 AI 是本轮首位发言者，无人插话）才直接复用；
        # refinement_mode=True（本轮已有人发言）时走下方完整 LLM，基于最新局势精炼草稿。
        cached_speech_draft = str(kwargs.get("cached_speech_draft") or "").strip()
        if (
            cached_speech_draft
            and action_type in {"speak", "defense_speech"}
            and not refinement_mode
        ):
            content = self._sanitize_public_speech_content(cached_speech_draft, visible_state)
            self._record_action_metric(
                visible_state,
                action_type,
                model="draft-reuse",
                latency_ms=0,
                fallback_used=False,
                speech_source="cache_finalized_draft_reuse",
                tool_used=False,
            )
            return {
                "action": "speak",
                "content": content,
                "tone": "calm" if action_type == "speak" else "defensive",
                "reasoning": "复用预生成草稿（P0-4.3，跳过二次 LLM）。",
                "speech_source": "cache_finalized_draft_reuse",
            }

        # W3-C: 语义记忆检索 (Task B)
        # refinement_mode 时跳过向量检索 — 省掉 embedding API 调用
        search_query = f"{action_type} {kwargs.get('target', '')}"
        if refinement_mode:
            retrieved_items = []
        else:
            retrieved_items = await self.vector_memory.search(search_query, top_k=5)
        self._last_retrieval_query = search_query.strip()
        self._last_retrieval_items = list(retrieved_items)
        retrieved_text = ""
        if retrieved_items:
            retrieved_text = "\n【相关的历史记忆回溯】\n" + "\n".join(
                [f"- {it['text']}" for it in retrieved_items]
            )

        # W3-C/A3-MEM-3: 严格按 MemoryTier 分块提取记忆
        objective_memories = self.working_memory.get_objective_memory_summaries()
        high_confidence_memories = self.working_memory.get_private_memory_summaries()
        public_memories = self.working_memory.get_public_memory_summaries()

        # Dedup: remove high_confidence items that overlap with objective facts
        if objective_memories and high_confidence_memories:
            obj_set = set(objective_memories)
            high_confidence_memories = [m for m in high_confidence_memories if m not in obj_set]

        tier_text_blocks = []
        if objective_memories:
            tier_text_blocks.append(
                "【绝对客观事实 (OBJECTIVE - 100%可信)】\n"
                + "\n".join([f"- {m}" for m in objective_memories])
            )
        if high_confidence_memories:
            tier_text_blocks.append(
                "【高可信度线索 (HIGH_CONFIDENCE - 夜晚结果或私密信息)】\n"
                + "\n".join([f"- {m}" for m in high_confidence_memories])
            )
        if public_memories:
            # 去重：过滤掉与社交图谱自报身份重复的公开记忆
            graph_claims = set()
            for _pid, prof in self.social_graph.profiles.items():
                if prof.current_self_claim:
                    graph_claims.add(
                        f"{prof.name} 公开跳身份为 {get_role_name(prof.current_self_claim)}"
                    )
            filtered_public = (
                [m for m in public_memories if m not in graph_claims]
                if graph_claims
                else public_memories
            )
            # 限制公开记忆的条数避免刷屏
            tier_text_blocks.append(
                "【公开讨论与声明 (PUBLIC - 可能存在欺骗与伪装)】\n"
                + "\n".join([f"- {m}" for m in filtered_public[-15:]])
            )

        tiered_memory_text = "\n\n".join(tier_text_blocks)
        episodic_text = self.episodic_memory.get_summary(max_episodes=8)
        social_text = self.social_graph.get_graph_summary()
        visible_state_text = self._build_visible_state_summary(visible_state)

        # Token budget: cap memory sections to prevent prompt bloat
        tiered_memory_text = self._cap_memory_section(tiered_memory_text, 800)
        episodic_text = self._cap_memory_section(episodic_text, 400)
        social_text = self._cap_memory_section(social_text, 300)

        perceived_role = self.perceived_role_id or self.role_id
        action_context = self._build_action_context(visible_state, legal_context, action_type)
        cached_speech_draft = str(kwargs.get("cached_speech_draft") or "").strip()
        strategic_thought = str(kwargs.get("strategic_thought") or "").strip()
        if strategic_thought and action_type in {
            "speak",
            "defense_speech",
            "vote",
            "nominate",
            "nomination_intent",
            "night_action",
        }:
            action_context = (
                f"{action_context}\n【内心策略独白】{strategic_thought}\n"
                "这是你行动前的内心思考，可作为决策参考，但公开发言不得直接引用其中的私密结论。"
            )
        if cached_speech_draft and action_type in {"speak", "defense_speech"}:
            action_context = (
                f"{action_context}\n【预思考草稿】{cached_speech_draft}\n"
                "请基于最新局势修正这份草稿，不要原样照抄，也不要引用你不可公开的信息。"
            )
        action_style_block = self._build_action_style_block(action_type, visible_state)

        # PLN-039 T1/T3：system 双层重组（全局静态层 + Agent 局部静态层）。
        #   system = 层1(全局绝对静态：公共规则+核心原则+8工具schema+输出格式，跨Agent逐token一致)
        #          + 层2(Agent局部静态：玩家名单+身份+稳定人格锚点+目标，同Agent整局稳定)
        #   user1  = 跨局玩家记忆（同局稳定）
        #   user2  = 全部动态内容（本局记忆/局势/动作格式/动作类型/JSON schema）后置，最大化稳定前缀。
        # 变化点后置是 DeepSeek 前缀缓存命中的关键：任何变化点都会截断完整前缀缓存。
        stable_rules = self._build_stable_system_prompt(visible_state)

        # 稳定长上下文（跨局玩家记忆，同局内逐 token 稳定）作为 user 首条（D013 约束③）
        long_term = self._long_term_summary.strip()
        long_term_block = f"\n【你的跨局玩家记忆（进化）】\n{long_term}\n" if long_term else ""
        stable_context = long_term_block.strip() or "【跨局记忆】本局新玩家，尚无跨局记忆。"

        # 逐次变化内容（本局记忆 + 局势 + 动作格式）全部后置为 user 末条，最大化可缓存前缀
        dynamic_context = f"""【你的记忆与档案】
{episodic_text}

{social_text}

【核心分层记忆】
{tiered_memory_text}

{self._deception_budget_prompt(visible_state)}

【当前动作风格与战略】
{action_style_block}

【你可见的局势摘要】
{visible_state_text}

当前动作补充要求：{action_context}

        【动作与输出格式】
当前需要执行的动作类型：{action_type}，请只调用与该动作对应的工具；其余工具忽略。
请优先调用对应工具完成动作；工具不可用或需跳过时可返回如下 JSON（不要包含任何多余文字）：
{self._json_schema_for_action(action_type)}"""

        action_started = time.perf_counter()
        response = None
        self._pending_fallback_reason = None
        try:
            from src.agents.tools.action_tool_registry import GameActionToolRegistry
            from src.llm.base_backend import Message

            strategy = self._llm_strategy_for_action(action_type)
            # PLN-039 T2：tools 全量固定传递（8 个工具恒定），消除 tools 参数导致的缓存前缀变化。
            tool_defs = GameActionToolRegistry.all_tool_defs()
            # 三层前缀：稳定规则层(system) → 稳定长上下文(user) → 逐次变化短内容(user)
            backend_call = self.backend.generate(
                system_prompt=stable_rules,
                messages=[
                    Message(role="user", content=stable_context),
                    Message(
                        role="user",
                        content=(
                            f"{dynamic_context}\n\n"
                            "请通过调用工具完成动作。若工具不可用或你决定不行动，"
                            f"可返回适用于动作 `{action_type}` 的 JSON 决策。"
                        ),
                    ),
                ],
                tools=tool_defs,
                temperature=self.difficulty_preset.temperature,
                max_tokens=strategy.get("max_tokens"),
                thinking=strategy.get("thinking"),
                reasoning_effort=strategy.get("reasoning_effort"),
            )
            if self._should_wait_without_game_timeout(action_type):
                response = await backend_call
            else:
                response = await asyncio.wait_for(
                    backend_call,
                    timeout=self._action_timeout_seconds(action_type),
                )
            # 工具调用主导路径（PLN-038 阶段 A）
            tool_decision = GameActionToolRegistry.decision_from_tool_calls(
                response.tool_calls, action_type
            )
            if tool_decision is not None:
                decision = self._normalize_decision(
                    visible_state, legal_context, action_type, tool_decision
                )
                fallback_reason = self._pending_fallback_reason
                # per-player 思考记录（工具调用路径同样记录 reasoning + 决策，2026-08-05）
                self._append_player_thought_log(
                    visible_state,
                    decision,
                    str(getattr(response, "reasoning_content", "") or "").strip(),
                    decision.get("reasoning", ""),
                    response.usage,
                    action_type,
                )
                self._record_action_metric(
                    visible_state,
                    action_type,
                    model=response.model,
                    usage=response.usage,
                    latency_ms=int((time.perf_counter() - action_started) * 1000),
                    fallback_used=bool(fallback_reason),
                    fallback_reason=fallback_reason,
                    speech_source="tool_calling"
                    if action_type in {"speak", "defense_speech"}
                    else "",
                    tool_used=True,
                )
                return decision
            # JSON fallback；content 为空时尝试从 reasoning_content（DeepSeek thinking）恢复决策 JSON
            response_text = response.content or ""
            if not str(response_text).strip():
                response_text = self._extract_decision_from_reasoning(
                    str(getattr(response, "reasoning_content", "") or "")
                )
            decision = self._parse_llm_decision_json(response_text)
            decision = self._normalize_decision(visible_state, legal_context, action_type, decision)
            fallback_reason = self._pending_fallback_reason

            # 思考轨迹：data_collector（全局） + per-player 对局落盘（独立于 data_collector）
            llm_thought = str(getattr(response, "reasoning_content", "") or "").strip()
            thought = decision.get("reasoning", "")
            if self.data_collector:
                combined_thought = (
                    f"[深度思考]\n{llm_thought}\n[决策推理]\n{thought}"
                    if llm_thought
                    else thought
                )
                self.data_collector.record_thought_trace(
                    player_id=self.player_id,
                    role_id=self.role_id,
                    phase=str(visible_state.phase),
                    round_number=visible_state.round_number,
                    thought=combined_thought,
                    action=decision,
                    context={
                        "retrieved_text_len": len(retrieved_text)
                        if "retrieved_text" in locals()
                        else 0
                    },
                    usage=response.usage,
                )
            self._append_player_thought_log(
                visible_state,
                decision,
                llm_thought,
                thought,
                response.usage,
                action_type,
            )

            if "reasoning" in decision:
                logger.info(f"[{self.name}] 内部思考: {decision['reasoning']}")
            self._record_action_metric(
                visible_state,
                action_type,
                model=response.model,
                usage=response.usage,
                latency_ms=int((time.perf_counter() - action_started) * 1000),
                fallback_used=bool(fallback_reason),
                fallback_reason=fallback_reason,
                speech_source="live_llm" if action_type in {"speak", "defense_speech"} else "",
            )
            return decision
        except Exception as e:
            if isinstance(e, asyncio.TimeoutError):
                reason = f"latency_budget_exceeded:{action_type}"
            elif str(e) == "empty_response":
                reason = "empty_response"
            else:
                reason = f"llm_error:{type(e).__name__}"
            if cached_speech_draft and action_type in {"speak", "defense_speech"}:
                elapsed_seconds = time.perf_counter() - action_started
                if response is None:
                    logger.info(
                        "[%s] LLM %s 未返回，已等待 %.1fs（配置预算 %.1fs），使用预思考草稿完成发言。reason=%s",
                        self.name,
                        action_type,
                        elapsed_seconds,
                        self._action_timeout_seconds(action_type),
                        reason,
                    )
                else:
                    preview = re.sub(r"\s+", " ", (response.content or "").strip())[:180]
                    logger.info(
                        "[%s] LLM %s 已返回但决策不可用，耗时 %.1fs，使用预思考草稿完成发言。reason=%s response_preview=%r",
                        self.name,
                        action_type,
                        elapsed_seconds,
                        reason,
                        preview,
                    )
                content = self._sanitize_public_speech_content(cached_speech_draft, visible_state)
                self._record_action_metric(
                    visible_state,
                    action_type,
                    model=response.model if response else "",
                    usage=response.usage if response else {},
                    latency_ms=int((time.perf_counter() - action_started) * 1000),
                    fallback_used=False,
                    fallback_reason=None,
                    speech_source="cache_finalized_after_llm_error",
                    llm_error_reason=reason,
                )
                return {
                    "action": "speak",
                    "content": content,
                    "tone": "calm" if action_type == "speak" else "defensive",
                    "reasoning": f"使用预思考草稿完成发言。({reason})",
                    "speech_source": "cache_finalized_after_llm_error",
                }
            if isinstance(e, asyncio.TimeoutError):
                elapsed_seconds = time.perf_counter() - action_started
                logger.warning(
                    "[%s] LLM %s 超时，使用兜底决策: elapsed=%.1fs budget=%.1fs reason=%s",
                    self.name,
                    action_type,
                    elapsed_seconds,
                    self._action_timeout_seconds(action_type),
                    reason,
                )
            else:
                logger.error("[%s] LLM 调用失败: reason=%s error=%r", self.name, reason, e)
            decision = self._fallback_decision(
                visible_state, legal_context, action_type, reason=reason
            )
            self._record_action_metric(
                visible_state,
                action_type,
                model=response.model if response else "",
                usage=response.usage if response else {},
                latency_ms=int((time.perf_counter() - action_started) * 1000),
                fallback_used=True,
                fallback_reason=reason,
                speech_source="fallback" if action_type in {"speak", "defense_speech"} else "",
            )
            return decision

    async def act_with_strategy(
        self,
        visible_state: AgentVisibleState,
        action_type: str,
        legal_context: AgentActionLegalContext | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """策略先行决策 loop（PLN-038 阶段 B）：think → act。

        与 `act()` 相比：
        1. 对非简单动作（speak/defense_speech/nominate/night_action）先做一次
           低预算 `think`（内心独白，见 MemoryController.think），产出策略；
        2. 若已有 `cached_speech_draft`（草稿校验通过），直接净化复用草稿，
           **跳过第二次 LLM 调用**（PLN-037 P0-4.3，speak 输出减半）；
        3. 否则把策略独白注入 `act()` 的 action_context，再发起动作。

        LLM 不可用 / 草稿缺失时行为与 `act()` 完全一致，保证向后兼容。
        """
        strategy_loop_used = False
        cached_draft = str(kwargs.get("cached_speech_draft") or "").strip()
        refinement_mode = bool(kwargs.get("refinement_mode"))

        # 草稿直接复用：有有效草稿的发言类动作不再二次 LLM
        if cached_draft and action_type in {"speak", "defense_speech"}:
            content = self._sanitize_public_speech_content(cached_draft, visible_state)
            self._record_action_metric(
                visible_state,
                action_type,
                model="draft-reuse",
                latency_ms=0,
                fallback_used=False,
                speech_source="cache_finalized_draft_reuse_no_llm",
                tool_used=False,
                strategy_loop_used=False,
            )
            return {
                "action": "speak",
                "content": content,
                "tone": "calm" if action_type == "speak" else "defensive",
                "reasoning": "复用预思考草稿（策略先行 loop，跳过二次 LLM）。",
                "speech_source": "cache_finalized_draft_reuse_no_llm",
            }

        # 简单决策直接走 act()，不引入额外 think 成本
        if action_type in {"vote", "nomination_intent"} or refinement_mode:
            return await self.act(visible_state, action_type, legal_context=legal_context, **kwargs)

        # 策略先行：低预算 think → act
        if not self._should_use_local_low_value_action(action_type):
            think_prompt = f"即将执行动作 {action_type}。请思考当前局势与你的最优策略。"
            thought = await self.think(think_prompt, visible_state)
            if thought:
                kwargs["strategic_thought"] = thought
                strategy_loop_used = True
        decision = await self.act(visible_state, action_type, legal_context=legal_context, **kwargs)
        if strategy_loop_used:
            decision = dict(decision)
            decision.setdefault("strategy_loop_used", True)
        return decision

    # ------------------------------------------------------------------
    # PLN-038 阶段 E：玩家进化机制（跨局长期记忆）
    # ------------------------------------------------------------------

    def set_game_context(self, game_id: str) -> None:
        """绑定当前对局 game_id（记忆工具对局隔离 + 跨局种子隔离）。"""
        self.game_id = game_id
        self.decision_noise.game_id = game_id

    def load_player_profile(self) -> None:
        """开局加载跨局玩家档案：生成『过往经验』摘要供 prompt 注入。

        进化的关键：把以往对局的战绩与经验教训带入本局，
        让 agent 表现更接近有长期记忆的人类玩家。
        PLN-040 T2：合并共享经验池的个性化子集（按角色/阵营检索，去私密化）。
        """
        self._long_term_summary = self._player_profile.build_long_term_summary(limit=6)
        # T2 共享经验池：同角色/阵营的跨局经验（setup 时算一次，保持前缀稳定）
        try:
            from src.agents.memory.shared_pool import SharedExperiencePool

            shared = SharedExperiencePool().build_shared_context(
                role_id=self.role_id,
                team=(self.team.value if hasattr(self.team, "value") else str(self.team or "")),
            )
            if shared:
                self._long_term_summary = (
                    f"{self._long_term_summary}\n{shared}"
                    if self._long_term_summary
                    else shared
                )
        except Exception as exc:
            logger.warning("[shared-pool] 共享经验注入失败 %s: %s", self.player_id, exc)

    @property
    def player_profile(self) -> dict[str, Any]:
        return self._player_profile.load_profile()

    def finalize_game_lesson(
        self,
        *,
        won: bool,
        role_id: str | None = None,
        team: str | None = None,
        lesson: str = "",
    ) -> dict[str, Any]:
        """局末提炼：记录战绩 + 追加一条经验教训（玩家进化落盘）。

        Args:
            won: 本局是否获胜
            role_id: 本局真实角色
            team: 本局阵营（good/evil）
            lesson: 本局总结出的可复用经验（非私密、不含队友名单）
        """
        profile = self._player_profile.record_game_result(won=won, role_id=role_id, team=team)
        if lesson:
            self._player_profile.append_lesson(
                {
                    "game_id": self.game_id or "",
                    "won": won,
                    "role_id": role_id or "",
                    "team": (team or "").lower(),
                    "lesson": lesson[:200],
                }
            )
        return {"profile": profile, "lesson_recorded": bool(lesson)}

    # ------------------------------------------------------------------
    # 拟人化进化：局中反思 / 局后复盘 / 学习他人 / 调整策略
    # ------------------------------------------------------------------

    def add_in_game_reflection(self, content: str, *, phase: str = "") -> None:
        """局中反思：把当前阶段的一个决策/判断沉淀为即时经验。

        拟人化：人类玩家对局中会不断自我校正。此方法让 agent 把
        "刚才这个做法对不对"沉淀下来，供本局后续与未来对局参考。
        """
        self._player_profile.add_reflection(
            {
                "game_id": self.game_id or "",
                "phase": phase,
                "reflection": content[:160],
            }
        )

    def finalize_game_review(
        self,
        *,
        won: bool,
        role_id: str | None = None,
        team: str | None = None,
        takeaway: str = "",
        strategy_delta: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """局后复盘 + 调整策略：沉淀多维复盘并微调行动倾向。

        拟人化核心：人类玩家赢/输都会复盘，据此调整后续打法。
        此方法：(1) 记录战绩；(2) 落盘复盘要点；(3) 基于胜负/角色
        微调倾向（如恶魔胜率高→更敢冒险），实现水平增长。
        """
        profile = self._player_profile.record_game_result(won=won, role_id=role_id, team=team)
        if takeaway:
            self._player_profile.add_game_review(
                {
                    "game_id": self.game_id or "",
                    "won": won,
                    "role_id": role_id or "",
                    "team": (team or "").lower(),
                    "takeaway": takeaway[:160],
                }
            )
        # 调整策略：基于本局结果做倾向微调（默认由战绩反馈推导）
        deltas = strategy_delta or self._derive_tendency_delta(won=won, team=team)
        if deltas:
            self._player_profile.evolve_strategies(
                {
                    "game_id": self.game_id or "",
                    "won": won,
                    "reason": takeaway[:80] or "根据本局表现调整打法",
                    "tendency_delta": deltas,
                }
            )
        return {"profile": profile, "reviewed": bool(takeaway), "evolved": bool(deltas)}

    def learn_play_style(self, role_id: str, lesson: str) -> None:
        """学习他人经验：记录一条从强势玩家打法中学到的经验。

        拟人化：人类玩家会模仿高手的战术。此方法沉淀
        "某个角色/阵营的打法思路"，供未来对局参考。
        """
        self._player_profile.learn_from_others(
            {
                "game_id": self.game_id or "",
                "role_id": role_id or "",
                "lesson": lesson[:160],
            }
        )

    def build_evolved_tendency(self) -> str:
        """生成当前进化后的行动倾向描述（调整策略的可注入结果）。"""
        return self._player_profile.build_evolved_tendency_summary()

    def _derive_tendency_delta(self, *, won: bool, team: str | None = None) -> dict[str, float]:
        """基于本局结果的默认倾向微调（规则驱动，确定性）。

        模拟人类玩家的学习规律：赢了强化当前打法，输了微调方向。
        """
        team = (team or "").lower()
        delta: dict[str, float] = {}
        if won:
            # 赢了：强化获胜打法（分阵营），更自信
            if team == "evil":
                # 恶魔胜：伪装与节奏 → 强化谨慎（保护信息）+ 主动施压
                delta = {"caution": 0.02, "aggression": 0.01}
            else:
                # 正义胜：推演与沟通 → 强化健谈 + 敢施压
                delta = {"talkativeness": 0.02, "aggression": 0.01}
        else:
            # 输了：朝相反方向微调，尝试不同打法
            if team == "evil":
                # 邪恶输：暴露过多 → 更谨慎、更收敛
                delta = {"caution": 0.02, "risk_taking": -0.01}
            else:
                # 正义输：推演不足 → 更积极发言、更敢施压
                delta = {"talkativeness": 0.02, "aggression": 0.01}
        # PLN-040 T3 M5 标定：步长可用 BOTC_TENDENCY_STEP 覆盖（默认 0.02，
        # 标定实验可调 0.05/0.10/0.15 观察行为差异；仍守 0.05~0.95 边界）
        step = float(os.getenv("BOTC_TENDENCY_STEP", "0.02"))
        delta = {k: v * step / 0.02 for k, v in delta.items()}
        # 轻微随机扰动，避免所有玩家收敛到同一打法
        for k in list(delta):
            delta[k] = round(delta[k] + random.uniform(-0.005, 0.005), 3)
        return delta

    def build_long_term_context(self) -> str:
        """供 system prompt 注入的跨局经验摘要（空则返回空串）。"""
        return self._long_term_summary

    # ------------------------------------------------------------------
    # PLN-040 T3：tendency → 行为标签映射（差异化注入核心）
    # ------------------------------------------------------------------

    def tendency_behavior_overrides(self) -> dict[str, str]:
        """把进化倾向（tendency 四维）映射为决策引擎消费的行为标签。

        决策引擎（decision_engine.py）通过 `_persona_modifier` 消费
        persona_profile 的 risk_tolerance / social_style / assertiveness
        三组标签来调整提名/投票阈值。T3 让 tendency 真实影响行为：
        - talkativeness 高 → 带节奏（更主动施压、更多发言倾向）
        - aggression 高     → 激进 + 强势
        - caution 高        → 保守 + 温和
        - risk_taking 高    → 激进（敢冒险）

        返回值合并进 persona_profile（setup 时一次，前缀稳定）。

        仅当 tendency 显著偏离中性（>=0.65 或 <=0.35）才覆盖对应标签；
        中性区间（0.35~0.65）不覆盖，保留原有 _pick_stable/archetype 结果，
        保证默认玩家行为与 T3 前完全一致（不改变既有决策行为）。
        """
        profile = self._player_profile.load_profile()
        tendency = profile.get("tendency") or {}
        t = {
            k: float(tendency.get(k, 0.5))
            for k in ("aggression", "risk_taking", "talkativeness", "caution")
        }
        overrides: dict[str, str] = {}
        # risk_tolerance：保守(高caution或低risk) / 激进(高aggression或高risk)；中性不覆盖
        if t["caution"] >= 0.65 or t["risk_taking"] <= 0.35:
            overrides["risk_tolerance"] = "保守"
        elif t["aggression"] >= 0.65 or t["risk_taking"] >= 0.65:
            overrides["risk_tolerance"] = "激进"
        # social_style：带节奏(高talk或高aggression) / 从众(低talk)；中性不覆盖
        if t["talkativeness"] >= 0.65 or t["aggression"] >= 0.65:
            overrides["social_style"] = "带节奏"
        elif t["talkativeness"] <= 0.35:
            overrides["social_style"] = "从众"
        # assertiveness：强势(高aggression) / 温和(高caution)；中性不覆盖
        if t["aggression"] >= 0.65:
            overrides["assertiveness"] = "强势"
        elif t["caution"] >= 0.65:
            overrides["assertiveness"] = "温和"
        return overrides

    # ------------------------------------------------------------------
    # 记忆工具对局隔离辅助
    # ------------------------------------------------------------------

    def memory_dir(self) -> Any:
        """当前对局的记忆落盘目录（games/{game_id}/），无 game_id 时回退玩家根目录。"""
        from src.agents.tools.memory_tools import MemoryTools

        return MemoryTools.game_dir(self.player_id, self.game_id)

    async def generate_draft_speech(
        self,
        visible_state: AgentVisibleState,
        legal_context: AgentActionLegalContext | None = None,
    ) -> dict[str, Any] | None:
        """Generate a speech draft for pre-generation cache.

        Lightweight version of act("speak") that skips:
        - _reflect() — not needed for a draft
        - vector_memory.search() — saves an embedding API call
        - Full episodic memory — uses summary only

        The prompt is still persona-aware and memory-aware,
        just without the expensive RAG step.
        """
        legal_context = legal_context or AgentActionLegalContext()
        self._prime_social_graph_from_state(visible_state)

        # Tiered memory (fast — pure data access)
        objective_memories = self.working_memory.get_objective_memory_summaries()
        high_confidence_memories = self.working_memory.get_private_memory_summaries()
        public_memories = self.working_memory.get_public_memory_summaries()

        tier_text_blocks = []
        if objective_memories:
            tier_text_blocks.append(
                "【绝对客观事实】\n" + "\n".join([f"- {m}" for m in objective_memories])
            )
        if high_confidence_memories:
            tier_text_blocks.append(
                "【高可信度线索】\n" + "\n".join([f"- {m}" for m in high_confidence_memories])
            )
        if public_memories:
            tier_text_blocks.append(
                "【公开讨论与声明】\n" + "\n".join([f"- {m}" for m in public_memories[-10:]])
            )

        tiered_memory_text = "\n\n".join(tier_text_blocks) if tier_text_blocks else "暂无记忆。"
        social_text = self.social_graph.get_graph_summary()
        visible_state_text = self._build_visible_state_summary(visible_state)
        action_context = self._build_action_context(visible_state, legal_context, "speak")

        # Token budget: cap memory sections
        tiered_memory_text = self._cap_memory_section(tiered_memory_text, 600)
        social_text = self._cap_memory_section(social_text, 200)

        # PLN-039 T3：草稿 system 复用 act() 的稳定 system（层1全局静态 + 层2 Agent 局部静态），
        # 动态内容（社交图谱/局势摘要/记忆/动作格式）全部移入 user 末条，保证前缀可命中主缓存。
        system_prompt = self._build_stable_system_prompt(visible_state)

        dynamic_draft = f"""【你的记忆与档案】
{tiered_memory_text}

{social_text}

{self._deception_budget_prompt(visible_state)}

【你可见的局势摘要】
{visible_state_text}

当前动作补充要求：{action_context}

【动作与输出格式】
当前需要执行的动作类型：speak，请只调用与该动作对应的工具；其余工具忽略。
请只返回一个 speak 动作的 JSON 决策，格式如下：
{{
  "action": "speak",
  "content": "你作为玩家的公开发言内容（口语化，不要照抄记忆）",
  "tone": "calm/suspicious/confused/assertive/emotional",
  "reasoning": "你的内部推理（不公开）"
}}
只返回 JSON，不要输出任何额外说明。"""

        try:
            from src.agents.tools.action_tool_registry import GameActionToolRegistry
            from src.llm.base_backend import Message

            strategy = self._llm_strategy_for_action("speak")
            response = await asyncio.wait_for(
                self.backend.generate(
                    system_prompt=system_prompt,
                    messages=[Message(role="user", content=dynamic_draft)],
                    tools=GameActionToolRegistry.all_tool_defs(),
                    temperature=self.difficulty_preset.temperature,
                    max_tokens=strategy.get("max_tokens"),
                    thinking=strategy.get("thinking"),
                    reasoning_effort=strategy.get("reasoning_effort"),
                ),
                timeout=self._action_timeout_seconds("speak"),
            )
            response_text = response.content or ""
            decision = self._parse_llm_decision_json(response_text)
            if not decision.get("content"):
                return None
            # Apply sanitization even for drafts
            decision["content"] = self._sanitize_public_speech_content(
                str(decision["content"]), visible_state
            )
            return decision
        except Exception as exc:
            logger.debug("[generate_draft_speech] %s failed: %s", self.name, exc)
            return None
