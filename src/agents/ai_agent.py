"""
AI Agent 实现

通过 LLM 驱动的游戏内角色。
"""

from __future__ import annotations

import hashlib
import asyncio
import logging
import json
import os
import re
import time
from typing import Any, Optional
from src.engine.data_collector import GameDataCollector
from src.agents.base_agent import BaseAgent
from src.agents.memory.episodic_memory import EpisodicMemory, Episode
from src.agents.memory.social_graph import ClaimRecord, SocialGraph
from src.agents.memory.working_memory import Observation, WorkingMemory
from src.agents.memory.vector_memory import VectorMemory
from src.agents.persona_registry import ARCHETYPES, Archetype, get_archetype
from src.agents.difficulty_presets import DifficultyPreset, get_preset
from src.agents.decision_noise import DecisionNoise
from src.content.trouble_brewing_terms import TROUBLE_BREWING_ROLE_TERMS, get_role_description, get_role_name, get_role_persona_hint
from src.llm.base_backend import LLMBackend
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    ChatMessage,
    GameEvent,
    GamePhase,
    GameState,
    PlayerState,
    PrivatePlayerView,
    Team,
    Visibility,
    VisiblePlayerInfo,
)

# Re-export from extracted modules for backward compatibility
from src.agents.deception.deception_tracker import DeceptionTracker
from src.agents.persona.persona import ParsedRoleStatement, Persona
from src.agents.prompt.prompt_factory import PromptFactory
from src.agents.speech.speech_sanitizer import SpeechSanitizer
from src.agents.decision.decision_engine import DecisionEngine
from src.agents.observation.event_observer import EventObserver
from src.agents.strategy.evil_strategy import EvilStrategy
from src.agents.memory.memory_controller import MemoryController

logger = logging.getLogger(__name__)


class AIAgent(BaseAgent):
    """
    AI 智能体
    """

    def __init__(
        self,
        player_id: str,
        name: str,
        backend: LLMBackend,
        persona: Persona,
        player_count: int = 10,
        data_collector: Optional[GameDataCollector] = None,
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
            storage_limit=max(40, int(player_count * 4))
        )
        self.episodic_memory = EpisodicMemory()
        embedding_dimension = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        self.vector_memory = VectorMemory(backend=backend, dimension=embedding_dimension)
        self.social_graph = SocialGraph(
            my_player_id=player_id,
            note_limit=max(30, int(player_count * 3)),
            claim_limit=max(20, int(player_count * 2)),
            summary_note_limit=6,
            summary_claim_limit=5
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

    def _action_timeout_seconds(self, action_type: str = "") -> float:
        env_override = os.getenv("AI_ACTION_TIMEOUT_SECONDS")
        if env_override:
            try:
                return max(1.0, float(env_override))
            except ValueError:
                pass
        preset_budget_ms = self.difficulty_preset.latency_budget.get(action_type)
        base = (preset_budget_ms / 1000.0) if preset_budget_ms else self.ACTION_BUDGET.get(action_type, self._DEFAULT_BUDGET)
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
            minimums = slow_minimums if self._backend_speed_profile == "live_slow" else live_minimums
            base = max(base, minimums.get(action_type, base))
        # Adaptive scaling: tighter budgets for larger games, but do not squeeze live LLM actions.
        if self._backend_speed_profile in {"live", "live_slow"} and action_type in {"vote", "nomination_intent", "night_action", "speak", "defense_speech"}:
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
        if "openai_backend" in module_name or os.getenv("BOTC_BACKEND", "").lower() in {"live", "auto"}:
            if any(marker in model_name for marker in ("flash", "fast", "mini", "turbo")):
                return "live"
            return "live_slow"
        return "fast"

    def _should_wait_without_game_timeout(self, action_type: str) -> bool:
        if os.getenv("AI_FORCE_GAME_TIMEOUTS", "0") == "1":
            return False
        return action_type in {"speak", "defense_speech"} and self._backend_speed_profile in {"live", "live_slow"}

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
            "phase": visible_state.phase.value if hasattr(visible_state.phase, "value") else str(visible_state.phase),
            "day_number": visible_state.day_number,
            "round_number": visible_state.round_number,
            "action_type": action_type,
            "model": model or (self.backend.get_model_name() if self.backend else "unknown"),
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
            "latency_ms": latency_ms,
            "fallback_used": fallback_used,
            "fallback_reason": fallback_reason,
            "timeout_budget_ms": int(self._action_timeout_seconds(action_type) * 1000),
            "backend_speed_profile": self._backend_speed_profile,
            "budget_source": "env_override" if os.getenv("AI_ACTION_TIMEOUT_SECONDS") else "difficulty_preset",
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

    def _refresh_persona_profile(self) -> None:
        return self._memory_controller.refresh_persona_profile()

    def _process_event_for_social_graph(self, event: GameEvent) -> None:
        return self._event_observer.process_event_for_social_graph(event)

    async def observe_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        return await self._event_observer.observe_event(event, visible_state)

    async def _ingest_visible_event_to_vector_memory(self, event: GameEvent) -> None:
        return await self._event_observer.ingest_visible_event_to_vector_memory(event)

    def _remember_critical_event(self, event: GameEvent, visible_state: AgentVisibleState) -> None:
        return self._event_observer.remember_critical_event(event, visible_state)

    def _store_private_info_memory(self, info_type: str, summary: str, visible_state: AgentVisibleState) -> None:
        return self._event_observer.store_private_info_memory(info_type, summary, visible_state)

    def _extract_role_ids_from_text(self, text: str) -> list[str]:
        haystack = (text or "").lower()
        found: set[str] = set()
        for role_id, zh_name, en_name in self._iter_role_terms():
            if zh_name in haystack or en_name.lower() in haystack or role_id in haystack:
                found.add(role_id)
        return list(found)

    def _role_team_hint(self, role_id: str) -> Team | None:
        from src.engine.roles.base_role import get_role_class

        role_cls = get_role_class(role_id)
        if not role_cls:
            return None
        try:
            return role_cls.get_definition().team
        except Exception:
            return None

    def _store_targeted_private_hints(self, info_type: str, payload: dict[str, Any], visible_state: AgentVisibleState) -> None:
        return self._event_observer.store_targeted_private_hints(info_type, payload, visible_state)

    def _get_evil_strategic_summary(self, visible_state: AgentVisibleState) -> str:
        return self._evil_strategy.get_evil_strategic_summary(visible_state)

    def _build_persona_prompt_block(self, action_type: str, visible_state: Optional[AgentVisibleState] = None) -> str:
        return self._prompt_factory.build_persona_prompt_block(action_type, visible_state)

    async def _reflect(self, visible_state: AgentVisibleState) -> None:
        return await self._memory_controller.reflect(visible_state)

    async def reflect_if_needed(self, visible_state: AgentVisibleState) -> bool:
        return await self._memory_controller.reflect_if_needed(visible_state)

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

        # W3-C: 检查记忆深度，必要时触发反思 (针对大局人数动态缩放)
        # refinement_mode 时跳过反思 — 草稿已经生成过，直接用
        refinement_mode = kwargs.get("refinement_mode", False)
        if not refinement_mode and len(self.working_memory.observations) > self._reflection_threshold:
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
                logger.info("[%s] 主动决定发动猎手技能: target=%s suspicion=%.2f", self.name, target_id, suspicion)
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
            retrieved_text = "\n【相关的历史记忆回溯】\n" + "\n".join([f"- {it['text']}" for it in retrieved_items])

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
            tier_text_blocks.append("【绝对客观事实 (OBJECTIVE - 100%可信)】\n" + "\n".join([f"- {m}" for m in objective_memories]))
        if high_confidence_memories:
            tier_text_blocks.append("【高可信度线索 (HIGH_CONFIDENCE - 夜晚结果或私密信息)】\n" + "\n".join([f"- {m}" for m in high_confidence_memories]))
        if public_memories:
            # 去重：过滤掉与社交图谱自报身份重复的公开记忆
            graph_claims = set()
            for pid, prof in self.social_graph.profiles.items():
                if prof.current_self_claim:
                    graph_claims.add(f"{prof.name} 公开跳身份为 {get_role_name(prof.current_self_claim)}")
            filtered_public = [m for m in public_memories if m not in graph_claims] if graph_claims else public_memories
            # 限制公开记忆的条数避免刷屏
            tier_text_blocks.append("【公开讨论与声明 (PUBLIC - 可能存在欺骗与伪装)】\n" + "\n".join([f"- {m}" for m in filtered_public[-15:]]))
        
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
        if cached_speech_draft and action_type in {"speak", "defense_speech"}:
            action_context = (
                f"{action_context}\n【预思考草稿】{cached_speech_draft}\n"
                "请基于最新局势修正这份草稿，不要原样照抄，也不要引用你不可公开的信息。"
            )
        persona_block = self._build_persona_prompt_block(action_type, visible_state)

        system_prompt = f"""你是一名正在玩《血染钟楼》(Blood on the Clocktower) 的真实玩家。
你的名字是 {self.name}，你认知的角色是 {perceived_role}，阵营是 {self.team}。

【核心原则：玩家优先级】
1. **你是玩家，不是 AI**：表现得像一个人在和朋友社交。会有犹豫、怀疑、幽默或偶尔的强势。
2. **社交推演**：除了规则和技能，更要关注别人的发言逻辑以及过往行为的一致性。
3. **保密与欺骗 (CRITICAL)**：
   - 如果你是邪恶阵营：**绝对不可**在公开频道（speak）中直接承认你的真实身份或泄露队友、真实技能结果。你必须伪装成一个好人。**严禁直接背诵你的私密信息或队友名单**。
   - 如果你是正义阵营：也要保护好你的关键信息，除非你认为说出来对正义方更有利。
   - 所有的【高可信度线索】和【绝对客观事实】都是你的私人底牌，**严禁**直接照抄到 content 中。你必须经过拟人化的加工。
4. **沉浸式对话**：发言要自然，像在群聊或面杀现场。禁止使用"我更信的一条线"、"根据事实记录"等生硬开场。
5. **拒绝机械复述**：如果场上有公开信息（如死亡、提名），不要单纯复述——这些每个人都知道。关注的是这些信息背后的意义，或者别人没发现的疑点。
5a. **发言多样性**：每次发言的内容、措辞和角度必须与之前不同。不要重复同一句话或同一种开场白。即使是相似的观点，也要换一种说法来表达。
6. **长线记忆**：不要只看眼前，要结合你在"往期回忆"和"社交图谱"中记录的线索。
7. **记忆权重**：【绝对客观事实】与【高可信度线索】是你推演的基石。如果公开说法和高可信信息冲突，请更偏向高可信信息。

{persona_block}
{self._deception_budget_prompt(visible_state)}

【你的记忆与档案】
{episodic_text}

{social_text}

【你可见的局势摘要】
{visible_state_text}

当前需要执行的动作类型：{action_type}
当前动作补充要求：{action_context}

【你的目标】
{"作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。" if self.team == "evil" else "作为正义阵营，通过逻辑与沟通找出恶魔并处决。"}

【核心分层记忆】
{tiered_memory_text}

【JSON 格式规范】
请务必返回如下结构的 JSON，不要包含任何多余文字：
{self._json_schema_for_action(action_type)}"""

        action_started = time.perf_counter()
        response = None
        self._pending_fallback_reason = None
        try:
            from src.llm.base_backend import Message
            backend_call = self.backend.generate(
                system_prompt=system_prompt,
                messages=[Message(role="user", content=f"请只返回适用于动作 `{action_type}` 的 JSON 决策，不要输出任何额外说明。")],
                temperature=self.difficulty_preset.temperature,
            )
            if self._should_wait_without_game_timeout(action_type):
                response = await backend_call
            else:
                response = await asyncio.wait_for(
                    backend_call,
                    timeout=self._action_timeout_seconds(action_type),
                )
            response_text = response.content or ""
            decision = self._parse_llm_decision_json(response_text)
            decision = self._normalize_decision(visible_state, legal_context, action_type, decision)
            fallback_reason = self._pending_fallback_reason
            
            # 记录到数据仓库 (Task C)
            if self.data_collector:
                thought = decision.get("reasoning", "")
                self.data_collector.record_thought_trace(
                    player_id=self.player_id,
                    role_id=self.role_id,
                    phase=str(visible_state.phase),
                    round_number=visible_state.round_number,
                    thought=thought,
                    action=decision,
                    context={"retrieved_text_len": len(retrieved_text) if 'retrieved_text' in locals() else 0},
                    usage=response.usage
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
            decision = self._fallback_decision(visible_state, legal_context, action_type, reason=reason)
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

        perceived_role = self.perceived_role_id or self.role_id

        # Tiered memory (fast — pure data access)
        objective_memories = self.working_memory.get_objective_memory_summaries()
        high_confidence_memories = self.working_memory.get_private_memory_summaries()
        public_memories = self.working_memory.get_public_memory_summaries()

        tier_text_blocks = []
        if objective_memories:
            tier_text_blocks.append("【绝对客观事实】\n" + "\n".join([f"- {m}" for m in objective_memories]))
        if high_confidence_memories:
            tier_text_blocks.append("【高可信度线索】\n" + "\n".join([f"- {m}" for m in high_confidence_memories]))
        if public_memories:
            tier_text_blocks.append("【公开讨论与声明】\n" + "\n".join([f"- {m}" for m in public_memories[-10:]]))

        tiered_memory_text = "\n\n".join(tier_text_blocks) if tier_text_blocks else "暂无记忆。"
        social_text = self.social_graph.get_graph_summary()
        visible_state_text = self._build_visible_state_summary(visible_state)
        persona_block = self._build_persona_prompt_block("speak", visible_state)
        action_context = self._build_action_context(visible_state, legal_context, "speak")

        # Token budget: cap memory sections
        tiered_memory_text = self._cap_memory_section(tiered_memory_text, 600)
        social_text = self._cap_memory_section(social_text, 200)

        system_prompt = f"""你是一名正在玩《血染钟楼》的真实玩家。
你的名字是 {self.name}，你认知的角色是 {perceived_role}，阵营是 {self.team}。
你的个性是：{self.persona.description}，表达风格是：{self.persona.speaking_style}。

{persona_block}
{self._deception_budget_prompt(visible_state)}

{social_text}

【你可见的局势摘要】
{visible_state_text}

当前需要执行的动作类型：speak

{tiered_memory_text}

{action_context}

【你的目标】
{"作为邪恶阵营，隐藏恶魔，混淆视听，剪除正义之士。" if self.team == "evil" else "作为正义阵营，通过逻辑与沟通找出恶魔并处决。"}

请返回一个 JSON 对象，格式如下：
{{
  "action": "speak",
  "content": "你作为玩家的公开发言内容（口语化，不要照抄记忆）",
  "tone": "calm/suspicious/confused/assertive/emotional",
  "reasoning": "你的内部推理（不公开）"
}}
只返回 JSON，不要输出任何额外说明。"""

        try:
            from src.llm.base_backend import Message
            response = await asyncio.wait_for(
                self.backend.generate(
                    system_prompt=system_prompt,
                    messages=[Message(role="user", content="请只返回 speak 的 JSON 决策。")],
                    temperature=self.difficulty_preset.temperature,
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

    def _local_low_value_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str) -> dict[str, Any]:
        return self._decision_engine.local_low_value_decision(visible_state, legal_context, action_type)

    async def think(self, prompt: str, visible_state: AgentVisibleState) -> str:
        return await self._memory_controller.think(prompt, visible_state)

    async def archive_phase_memory(self, visible_state: AgentVisibleState) -> None:
        return await self._memory_controller.archive_phase_memory(visible_state)

    def build_data_snapshot_summary(self) -> dict[str, Any]:
        return self._memory_controller.build_data_snapshot_summary()

    def _player_name_from_visible_state(self, player_id: str | None, visible_state: AgentVisibleState) -> str:
        if not player_id:
            return "某个目标"
        if visible_state.self_view and player_id == visible_state.self_view.player_id:
            return visible_state.self_view.name
        for player in visible_state.players:
            if player.player_id == player_id:
                return player.name
        return player_id

    def _format_event_to_text(self, event: GameEvent, visible_state: AgentVisibleState) -> str:
        return self._event_observer.format_event_to_text(event, visible_state)

    def _iter_role_terms(self) -> list[tuple[str, str, str]]:
        return self._event_observer._iter_role_terms()

    def _extract_role_statements(self, content: str, speaker_id: str, visible_state: AgentVisibleState) -> list[ParsedRoleStatement]:
        return self._event_observer.extract_role_statements(content, speaker_id, visible_state)

    def _build_action_context(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str) -> str:
        return self._prompt_factory.build_action_context(visible_state, legal_context, action_type)

    def _build_memory_signal_brief(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_memory_signal_brief(visible_state)

    @staticmethod
    def _profile_claimed_role_id(profile: Any) -> str | None:
        if not profile:
            return None
        return getattr(profile, "current_self_claim", getattr(profile, "claimed_role_id", None))

    def _build_speech_priority_brief(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_speech_priority_brief(visible_state)

    def _empath_neighbor_ids(self, visible_state: AgentVisibleState) -> tuple[str, ...]:
        me = visible_state.self_view
        if not me or me.perceived_role_id != "empath":
            return ()
        seat_order = list(visible_state.seat_order or tuple(player.player_id for player in visible_state.players))
        if me.player_id not in seat_order:
            return ()
        alive_lookup = {player.player_id: player.is_alive for player in visible_state.players}
        my_idx = seat_order.index(me.player_id)
        n = len(seat_order)
        if n <= 1:
            return ()

        def find_neighbor(step: int) -> str | None:
            idx = my_idx
            for _ in range(n - 1):
                idx = (idx + step) % n
                pid = seat_order[idx]
                if alive_lookup.get(pid, True):
                    return pid
            return None

        left = find_neighbor(-1)
        right = find_neighbor(1)
        result: list[str] = []
        for pid in (left, right):
            if pid and pid not in result:
                result.append(pid)
        return tuple(result)

    def _empath_neighbor_signal_summary(self, visible_state: AgentVisibleState) -> str:
        if not visible_state.self_view or visible_state.self_view.perceived_role_id != "empath":
            return ""
        summaries = self.working_memory.get_private_memory_summaries("empath_info")
        if not summaries:
            return ""
        latest = summaries[-1]
        neighbor_names = [self._player_name_from_visible_state(pid, visible_state) for pid in self._empath_neighbor_ids(visible_state)]
        if neighbor_names:
            return f"作为共情者，你当前活着的邻座是：{', '.join(neighbor_names)}。最近结果：{latest}"
        return f"作为共情者，你最近的结果是：{latest}"

    def _chef_signal_summary(self) -> str:
        summaries = self.working_memory.get_private_memory_summaries("chef_info")
        if not summaries:
            return ""
        return f"作为厨师，你的高可信首夜结果是：{summaries[-1]}"

    def _latest_numeric_value(self, category: str, patterns: tuple[str, ...]) -> int | None:
        summaries = self.working_memory.get_private_memory_summaries(category)
        if not summaries:
            return None
        summary = summaries[-1]
        for pattern in patterns:
            match = re.search(pattern, summary)
            if match:
                try:
                    return int(match.group(1))
                except Exception:
                    return None
        return None

    def _build_legal_action_context(self, game_state: GameState, visible_state: AgentVisibleState) -> AgentActionLegalContext:
        from src.engine.rule_engine import RuleEngine
        from src.engine.roles.base_role import get_role_class

        nomination_targets: list[str] = []
        for player in game_state.players:
            if player.player_id == self.player_id:
                continue
            can_nominate, _ = RuleEngine.can_nominate(game_state, self.player_id, player.player_id)
            if can_nominate:
                nomination_targets.append(player.player_id)

        night_targets = [
            player.player_id
            for player in game_state.get_alive_players()
            if player.player_id != self.player_id
        ]
        voters_so_far = set(game_state.votes_today.keys())
        seat_order = visible_state.seat_order or tuple(player.player_id for player in visible_state.players)
        remaining_voters = [pid for pid in seat_order if pid not in voters_so_far]
        required_targets = 1
        can_target_self = False
        player = game_state.get_player(self.player_id)
        if player:
            role_cls = get_role_class(player.true_role_id or player.role_id)
            if role_cls:
                role_instance = role_cls()
                try:
                    required_targets = max(0, int(role_instance.get_required_targets(game_state, game_state.phase) or 0))
                except Exception:
                    required_targets = 1
                try:
                    can_target_self = bool(role_instance.can_target_self())
                except Exception:
                    can_target_self = False
        return AgentActionLegalContext(
            legal_nomination_targets=tuple(nomination_targets),
            legal_night_targets=tuple(night_targets),
            votes_required=RuleEngine.votes_required(game_state),
            remaining_voters=tuple(remaining_voters),
            required_targets=required_targets,
            can_target_self=can_target_self,
        )

    def _is_event_visible_to_self(self, event: GameEvent) -> bool:
        if event.visibility == Visibility.PUBLIC:
            return True
        if event.visibility == Visibility.STORYTELLER_ONLY:
            return self.player_id in {event.actor, event.target}
        if event.visibility == Visibility.PRIVATE:
            return event.actor == self.player_id or event.target == self.player_id
        if event.visibility == Visibility.TEAM_EVIL:
            return self.team == Team.EVIL.value
        if event.visibility == Visibility.TEAM_GOOD:
            return self.team == Team.GOOD.value
        return False

    def _is_chat_visible_to_self(self, message) -> bool:
        if message.speaker == self.player_id:
            return True
        recipients = getattr(message, "recipient_ids", None)
        if not recipients:
            return True
        return self.player_id in recipients

    def _build_visible_state(self, game_state: GameState) -> AgentVisibleState:
        return AgentVisibleState(
            game_id=game_state.game_id,
            phase=game_state.phase,
            round_number=game_state.round_number,
            day_number=game_state.day_number,
            self_view=self.private_view if isinstance(self.private_view, PrivatePlayerView) else None,
            players=tuple(
                VisiblePlayerInfo(
                    player_id=player.player_id,
                    name=player.name,
                    is_alive=player.is_alive,
                )
                for player in game_state.players
            ),
            current_nominee=game_state.current_nominee,
            current_nominator=game_state.current_nominator,
            seat_order=game_state.seat_order or tuple(player.player_id for player in game_state.players),
            nominations_today=game_state.nominations_today,
            nominees_today=game_state.nominees_today,
            yes_votes=sum(1 for vote in game_state.votes_today.values() if vote is True),
            voted_player_ids=tuple(game_state.votes_today.keys()),
            public_chat_history=tuple(
                message for message in game_state.chat_history if self._is_chat_visible_to_self(message)
            ),
            visible_event_log=tuple(
                event for event in game_state.event_log if self._is_event_visible_to_self(event)
            ),
        )

    def _json_schema_for_action(self, action_type: str) -> str:
        schemas = {
            "speak": (
                '{\n'
                '  "action": "speak",\n'
                '  "content": "你的中文发言内容",\n'
                '  "tone": "calm/passionate/accusatory/defensive",\n'
                '  "reasoning": "你的内部推理（不公开）",\n'
                f'  "extracted_claims": [ // 可选：声明身份时提取，格式如 {{"role_id": "mayor", "claim_type": "self_claim", "subject_player_ids": ["{self.player_id}"]}}'
                '\n  ]\n'
                '}'
            ),
            "defense_speech": (
                '{\n'
                '  "action": "speak",\n'
                '  "content": "你的辩解内容",\n'
                '  "tone": "calm/passionate/defensive",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
            "vote": (
                '{\n'
                '  "action": "vote",\n'
                '  "decision": true/false,\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
            "nominate": (
                '{\n'
                '  "action": "nominate/none",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
            "nomination_intent": (
                '{\n'
                '  "action": "nominate/none",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
            "night_action": (
                '{\n'
                '  "action": "night_action",\n'
                '  "target": "player_id 或 [id1, id2]",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
            "slayer_shot": (
                '{\n'
                '  "action": "slayer_shot",\n'
                '  "target": "player_id",\n'
                '  "reasoning": "你的内部推理（不公开）"\n'
                '}'
            ),
        }
        return schemas.get(action_type, (
            '{\n'
            '  "action": "speak/nominate/vote/night_action/slayer_shot/skip_discussion/none",\n'
            '  "content": "发言内容（仅 speak 时）",\n'
            '  "target": "player_id（提名/射击时）",\n'
            '  "decision": true/false（仅 vote 时）,\n'
            '  "reasoning": "你的内部推理（不公开）"\n'
            '}'
        ))

    def _build_visible_state_summary(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.build_visible_state_summary(visible_state)

    async def build_evil_night_coordination_message(self, action: dict[str, Any], visible_state: AgentVisibleState, legal_context: AgentActionLegalContext | None = None) -> str:
        return await self._evil_strategy.build_evil_night_coordination_message(action, visible_state, legal_context)

    async def generate_first_night_coordination(self, visible_state: AgentVisibleState) -> str:
        return await self._evil_strategy.generate_first_night_coordination(visible_state)

    def _visible_alive_count(self, visible_state: AgentVisibleState) -> int:
        return sum(1 for player in visible_state.players if player.is_alive)

    def _sync_social_graph(self, game_state: GameState) -> None:
        return self._memory_controller.sync_social_graph(game_state)

    def _prime_social_graph_from_state(self, visible_state: AgentVisibleState) -> None:
        return self._memory_controller.prime_social_graph_from_state(visible_state)

    def _recent_context_texts(self, visible_state: AgentVisibleState, limit: int = 12) -> list[str]:
        texts: list[str] = []
        for obs in self.working_memory.observations[-limit:]:
            if obs.content:
                texts.append(obs.content)
        for message in visible_state.public_chat_history[-limit:]:
            speaker = next((player for player in visible_state.players if player.player_id == message.speaker), None)
            speaker_name = speaker.name if speaker else message.speaker
            target_name = ""
            if message.target_player:
                target_player = next((player for player in visible_state.players if player.player_id == message.target_player), None)
                target_name = f" -> {target_player.name}" if target_player else f" -> {message.target_player}"
            texts.append(f"{speaker_name}{target_name}: {message.content}")
        for event in visible_state.visible_event_log[-limit:]:
            if event.event_type in {"player_speaks", "nomination_started", "vote_cast", "voting_resolved", "execution_resolved", "player_death", "private_info_delivered"}:
                texts.append(self._format_event_to_text(event, visible_state))
        return texts

    def _count_mentions(self, texts: list[str], keyword: str) -> int:
        if not keyword:
            return 0
        lowered = keyword.lower()
        count = 0
        for text in texts:
            haystack = text.lower()
            if lowered in haystack:
                count += haystack.count(lowered)
        return count

    def _persona_modifier(self, key: str, mapping: dict[str, float], default: float = 0.0) -> float:
        profile = self.persona_profile or {}
        return mapping.get(str(profile.get(key, "")), default)

    def _nomination_threshold(self, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.nomination_threshold(visible_state)

    def _nomination_margin(self) -> float:
        return self._decision_engine.nomination_margin()

    def _vote_threshold(self, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.vote_threshold(visible_state)

    def _target_signal_score(self, target_id: str, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.target_signal_score(target_id, visible_state)

    def _select_nomination_target(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, intent_mode: bool = False) -> tuple[str, float, float] | None:
        return self._decision_engine.select_nomination_target(visible_state, legal_context, intent_mode)

    def _nomination_candidate_band(self, legal_targets: list[str], visible_state: AgentVisibleState, tolerance: float = 0.04) -> tuple[list[str], float]:
        return self._decision_engine.nomination_candidate_band(legal_targets, visible_state, tolerance)

    def _choose_nomination_target_from_band(self, legal_targets: list[str], visible_state: AgentVisibleState, action_type: str, salt: str, tolerance: float = 0.04) -> tuple[str | None, float]:
        return self._decision_engine.choose_nomination_target_from_band(legal_targets, visible_state, action_type, salt, tolerance)

    def _select_night_targets(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext) -> list[str]:
        return self._decision_engine.select_night_targets(visible_state, legal_context)

    def _known_evil_teammate_ids(self, visible_state: AgentVisibleState) -> set[str]:
        return self._decision_engine.known_evil_teammate_ids(visible_state)

    def _poisoner_priority_for_target(self, target_id: str, visible_state: AgentVisibleState) -> float:
        return self._decision_engine.poisoner_priority_for_target(target_id, visible_state)

    def _rank_poisoner_targets(self, ordered_targets: list[str], visible_state: AgentVisibleState) -> list[str]:
        return self._decision_engine._rank_poisoner_targets(ordered_targets, visible_state)

    def _coerce_target_values(self, raw_target: Any) -> list[str]:
        return self._decision_engine.coerce_target_values(raw_target)

    def _select_vote_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, model_vote: bool | None = None) -> tuple[bool, float, float]:
        return self._decision_engine.select_vote_decision(visible_state, legal_context, model_vote)

    def _can_attempt_slayer_shot(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str) -> bool:
        return self._decision_engine.can_attempt_slayer_shot(visible_state, legal_context, action_type)

    def _select_slayer_shot_target(self, visible_state: AgentVisibleState) -> tuple[str, float] | None:
        return self._decision_engine.select_slayer_shot_target(visible_state)

    def _reasoning_evidence_candidates(self, target_id: str | None, visible_state: AgentVisibleState) -> list[str]:
        return self._decision_engine.reasoning_evidence_candidates(target_id, visible_state)

    def _best_reasoning_evidence(self, target_id: str | None, visible_state: AgentVisibleState) -> str:
        return self._decision_engine.best_reasoning_evidence(target_id, visible_state)

    def _augment_reasoning_with_evidence(self, reasoning: str, *, action_type: str, target_id: str | None, visible_state: AgentVisibleState, suspicion: float | None = None, threshold: float | None = None) -> str:
        return self._decision_engine.augment_reasoning_with_evidence(reasoning, action_type=action_type, target_id=target_id, visible_state=visible_state, suspicion=suspicion, threshold=threshold)

    def _stable_choice(self, options: list[str], round_number: int, day_number: int, action_type: str, salt: str = "") -> str:
        return self._decision_engine.stable_choice(options, round_number, day_number, action_type, salt)

    def _persona_vote_bias(self, visible_state: AgentVisibleState) -> bool:
        return self._decision_engine.persona_vote_bias(visible_state)

    def _persona_fallback_speech(self, action_type: str, reason: str, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext) -> dict[str, Any]:
        return self._decision_engine.persona_fallback_speech(action_type, reason, visible_state, legal_context)

    def _find_most_suspicious_player(self, visible_state: AgentVisibleState) -> str | None:
        return self._decision_engine.find_most_suspicious_player(visible_state)

    def _evil_coordination_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer._evil_coordination_line(visible_state)

    def _mentioned_visible_names(self, summary: str, visible_state: AgentVisibleState) -> list[str]:
        return self._speech_sanitizer._mentioned_visible_names(summary, visible_state)

    def _private_info_public_paraphrase(self, summary: str, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer._private_info_public_paraphrase(summary, visible_state)

    def _public_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer.public_speech_anchor_line(visible_state)

    def _preferred_speech_anchor_line(self, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer.preferred_speech_anchor_line(visible_state)

    def _hidden_memory_summaries_for_public_filter(self) -> list[str]:
        return self._speech_sanitizer._hidden_memory_summaries_for_public_filter()

    def _sanitize_public_speech_content(self, content: str, visible_state: AgentVisibleState) -> str:
        return self._speech_sanitizer.sanitize_public_speech_content(content, visible_state)

    def _deception_budget_prompt(self, visible_state: AgentVisibleState) -> str:
        return self._prompt_factory.deception_budget_prompt(visible_state)

    def _track_own_claims_from_decision(self, decision: dict[str, Any], visible_state: AgentVisibleState) -> None:
        return self._decision_engine.track_own_claims_from_decision(decision, visible_state)

    def _stabilize_speech_content_with_memory(
        self,
        content: str,
        visible_state: AgentVisibleState,
        action_type: str,
    ) -> str:
        return self._speech_sanitizer.stabilize_speech_content_with_memory(content, visible_state, action_type)

    def _normalize_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str, decision: dict[str, Any]) -> dict[str, Any]:
        return self._decision_engine.normalize_decision(visible_state, legal_context, action_type, decision)

    def _fallback_decision(self, visible_state: AgentVisibleState, legal_context: AgentActionLegalContext, action_type: str, reason: str) -> dict[str, Any]:
        return self._decision_engine.fallback_decision(visible_state, legal_context, action_type, reason)