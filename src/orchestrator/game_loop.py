"""游戏主循环 (Game Orchestrator)。

本文件为 facade：仅负责顶层编排与路由，行为逻辑下沉到子模块
（agents/claims/grimoire/info/metrics/phases/settlement）与委托层
`game_loop_delegation.py`（见 `DECISIONS.md` D006）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
from typing import Any

from src.debug.game_debug_logger import game_debug_logger
from src.engine.data_collector import GameDataCollector
from src.engine.phase_manager import PhaseManager
from src.engine.roles.base_role import get_role_class
from src.engine.victory_checker import VictoryChecker
from src.orchestrator.agents import AgentManager
from src.orchestrator.claims import ClaimExtractor
from src.orchestrator.event_bus import EventBus
from src.orchestrator.game_loop_delegation import GameOrchestratorDelegation
from src.orchestrator.grimoire import GrimoireManager
from src.orchestrator.info import PrivateInfoNormalizer
from src.orchestrator.information_broker import InformationBroker
from src.orchestrator.metrics import MetricsCollector
from src.orchestrator.phases import DayDiscussionHandler, NightPhaseHandler, NominationVotingHandler
from src.orchestrator.settlement import SettlementBuilder
from src.state.event_log import EventLog
from src.state.game_record import GameRecordStore
from src.state.game_state import (
    ChatMessage,
    DifficultyLevel,
    GameConfig,
    GameEvent,
    GamePhase,
    GameState,
    PlayerState,
    PlayerStatus,
    Team,
    Visibility,
)
from src.state.snapshot import SnapshotManager

logger = logging.getLogger(__name__)
storyteller_logger = logging.getLogger("storyteller")


class GameOrchestrator(GameOrchestratorDelegation):
    """顶级容器，协调规则、Agent 和状态（facade：编排 + 路由）。"""

    MAX_AGENT_RETRIES = 5  # 最大重试次数，防止 AI/人类玩家意图异常导致卡死

    def __init__(self, initial_state: GameState):
        self.state = initial_state
        self.phase_manager = PhaseManager()
        self.event_bus = EventBus()
        self.event_log = EventLog()
        self.snapshot_manager = SnapshotManager()
        self.broker = InformationBroker()
        self.storyteller_agent = None
        self.default_agent_backend = None
        self.winner: Team | None = None
        self.settlement_report: dict[str, Any] | None = None
        self.record_store = GameRecordStore()
        self.data_collector = GameDataCollector()
        self._setup_done: asyncio.Future | None = None
        self._setup_started = False
        self._pending_night_action: dict[str, Any] | None = (
            None  # { "player_id": str, "action_type": str, "legal_context": dict }
        )
        self._loop_started_at: float | None = None
        self._last_progress_at: float | None = None
        self._current_waiting_for: str | None = None
        self._recent_exception: dict[str, Any] | None = None
        self._current_night_steps: list[dict[str, Any]] | None = None
        self._current_night_step_index: int = -1
        self._phase_started_at: float | None = None
        self._phase_started_action_positions: dict[str, int] = {}
        self._phase_duration_history: list[dict[str, Any]] = []
        self._action_latencies: list[dict[str, Any]] = []
        # Orchestrator 预算必须大于 agent 内部预算，让 agent 的智能 fallback 优先执行。
        # Agent 预算: speak=2.0s, defense_speech=2.5s, vote=0.8s, nomination_intent=1.0s, night_action=1.5s
        # vote/nomination_intent 预算提高到 2500ms，确保 agent 的智能 fallback 有足够时间执行。
        self._action_latency_budgets: dict[str, int] = {
            "vote": 2500,
            "nomination_intent": 2500,
            "night_action": 2500,
            "speak": 3500,
            "defense_speech": 4000,
        }
        # Speech pre-generation cache: created per round in _run_day_discussion
        self._claim_extraction_tasks: set[asyncio.Task] = set()
        self._claim_extraction_failures: dict[str, int] = {}
        self.agent_manager = AgentManager(self)
        self.claim_extractor = ClaimExtractor(self)
        self.grimoire_manager = GrimoireManager(self)
        self.metrics_collector = MetricsCollector(self)
        self.private_info_normalizer = PrivateInfoNormalizer(self)
        self.settlement_builder = SettlementBuilder(self)
        self.night_phase_handler = NightPhaseHandler(self)
        self.day_discussion_handler = DayDiscussionHandler(self)
        self.nomination_voting_handler = NominationVotingHandler(self)
        self.event_bus.subscribe("*", self._on_any_event, priority=0)

    def _mark_progress(self, waiting_for: str | None = None) -> None:
        self._last_progress_at = time.time()
        self._current_waiting_for = waiting_for

    async def run_setup(self, player_count: int, host_id: str, is_human: bool = True):
        if self._setup_started or self.phase_manager.current_phase != GamePhase.SETUP:
            raise RuntimeError("BOTC-FLOW-SETUP: 当前对局已开始或已配置，不能重复 setup")
        await self.run_setup_with_options(player_count, host_id, is_human)

    async def run_setup_with_options(
        self,
        player_count: int,
        host_id: str,
        is_human: bool = True,
        discussion_rounds: int | None = None,
        storyteller_mode: str | None = None,
        audit_mode: bool = False,
        max_nomination_rounds: int | None = None,
        ai_discussion_message_limit: int | None = None,
        backend_mode: str = "auto",
        human_mode: str | None = None,
        human_client_id: str | None = None,
        storyteller_client_id: str | None = None,
        storyteller_delegated: bool = False,
        difficulty: str = "standard",
    ) -> None:
        logger.info(
            f"[run_setup_with_options] Starting setup for {player_count} players. host_id={host_id} mode={human_mode}"
        )
        if self._setup_started or self.phase_manager.current_phase != GamePhase.SETUP:
            logger.warning(
                "[run_setup_with_options] Setup already started or not in SETUP phase. phase=%s",
                self.phase_manager.current_phase,
            )
            raise RuntimeError("BOTC-FLOW-SETUP: 当前对局已开始或已配置，不能重复 setup")

        self._setup_started = True
        debug_dir = game_debug_logger.start_game(
            self.state.game_id,
            {
                "player_count": player_count,
                "host_id": host_id,
                "human_mode": human_mode or ("player" if is_human else "none"),
                "backend_mode": backend_mode,
                "difficulty": difficulty,
            },
        )
        if debug_dir:
            logger.info("[run_setup_with_options] Debug logs for this game: %s", debug_dir)
        from src.engine.scripts import SCRIPTS, distribute_roles

        script = SCRIPTS["trouble_brewing"]
        role_ids, bluffs = distribute_roles(script, player_count)
        resolved_human_mode = human_mode or ("player" if is_human else "none")
        resolved_human_client_id = human_client_id or (
            host_id if resolved_human_mode == "player" else None
        )
        resolved_storyteller_client_id = storyteller_client_id or (
            host_id if resolved_human_mode == "storyteller" else None
        )
        human_seat = (
            random.randint(0, player_count - 1)
            if resolved_human_mode == "player" and resolved_human_client_id
            else -1
        )
        players: list[PlayerState] = []
        seat_order: list[str] = []

        for seat_index, role_id in enumerate(role_ids):
            player_id = (
                resolved_human_client_id if seat_index == human_seat else f"p{seat_index + 1}"
            )
            role_cls = get_role_class(role_id)
            team = role_cls.get_definition().team if role_cls else Team.GOOD
            fake_role = None
            statuses = (PlayerStatus.ALIVE,)
            if role_id == "drunken":
                fake_role = (
                    await self.storyteller_agent.decide_drunk_role(script, role_ids)
                    if self._should_storyteller_auto_act()
                    else "washerwoman"
                )
                statuses = (PlayerStatus.ALIVE, PlayerStatus.DRUNK)
            players.append(
                PlayerState(
                    player_id=player_id,
                    name="Human Player"
                    if player_id == resolved_human_client_id
                    else f"Player {seat_index + 1}",
                    role_id=role_id,
                    team=team,
                    true_role_id=role_id,
                    perceived_role_id=fake_role or role_id,
                    current_team=team,
                    fake_role=fake_role,
                    statuses=statuses,
                )
            )
            seat_order.append(player_id)

        payload = dict(self.state.payload)
        if "fortune_teller" in role_ids:
            goods = [
                p
                for p in players
                if p.current_team == Team.GOOD and p.true_role_id != "fortune_teller"
            ]
            if goods:
                payload["fortune_teller_red_herring"] = random.choice(goods).player_id

        self.state = self.state.with_update(
            players=tuple(players),
            seat_order=tuple(seat_order),
            bluffs=tuple(bluffs),
            payload=payload,
            config=GameConfig(
                player_count=player_count,
                script=script,
                script_id=script.script_id,
                human_client_id=resolved_human_client_id,
                human_mode=resolved_human_mode,
                storyteller_client_id=resolved_storyteller_client_id,
                human_player_ids=[resolved_human_client_id]
                if resolved_human_mode == "player" and resolved_human_client_id
                else [],
                is_human_participant=resolved_human_mode == "player",
                storyteller_mode=storyteller_mode
                or (
                    "human"
                    if resolved_human_mode == "storyteller"
                    else getattr(self.storyteller_agent, "mode", "auto")
                ),
                storyteller_delegated=storyteller_delegated,
                backend_mode=backend_mode,
                audit_mode=audit_mode,
                discussion_rounds=discussion_rounds or 3,
                ai_discussion_message_limit=ai_discussion_message_limit,
                max_nomination_rounds=max_nomination_rounds,
                difficulty=DifficultyLevel(difficulty),
            ),
        )
        if self.storyteller_agent:
            new_mode = self.state.config.storyteller_mode
            logger.info(
                f"[run_setup_with_options] Updating storyteller_agent mode to {new_mode}, delegated={storyteller_delegated}"
            )
            self.storyteller_agent.mode = new_mode
            if hasattr(self.storyteller_agent, "delegated"):
                self.storyteller_agent.delegated = storyteller_delegated
        self._update_payload(nomination_state={"stage": "idle"}, nomination_history=[])
        self._update_grimoire()

        from src.agents.ai_agent import AIAgent, Persona
        from src.agents.persona.persona_registry import ARCHETYPES
        from src.llm.openai_backend import OpenAIBackend

        backend = (
            self.default_agent_backend
            or (getattr(self.storyteller_agent, "backend", None))
            or OpenAIBackend()
        )
        player_count = len(self.state.players)
        archetype_keys = list(ARCHETYPES.keys())
        rng = random.Random(self.state.game_id)
        rng.shuffle(archetype_keys)

        self.data_collector.start_game(self.state.game_id)
        for i, player in enumerate(self.state.players):
            if player.player_id not in self.broker.agents:
                # 轮询分配不同的性格原型
                arch_key = archetype_keys[i % len(archetype_keys)]
                arch = ARCHETYPES[arch_key]
                persona = Persona(
                    description=arch.description,
                    speaking_style=arch.speaking_style,
                    archetype=arch_key,
                )

                difficulty = self.state.config.difficulty.value if self.state.config else "standard"
                self.register_agent(
                    AIAgent(
                        player.player_id,
                        player.name,
                        backend,
                        persona,
                        player_count=player_count,
                        data_collector=self.data_collector,
                        difficulty=difficulty,
                    )
                )

        logger.info("[run_setup_with_options] Syncing all agents")
        self._sync_all_agents("BOTC-FLOW-SETUP")
        # PLN-038 阶段 E：绑定对局 + 加载玩家跨局档案（进化记忆注入）
        self._bind_agent_game_context()
        if not self._setup_done:
            self._setup_done = asyncio.get_running_loop().create_future()
        if not self._setup_done.done():
            logger.info("[run_setup_with_options] Setting _setup_done result to True")
            self._setup_done.set_result(True)
        logger.info("[run_setup_with_options] Setup completed successfully")

    def _bind_agent_game_context(self) -> None:
        """为所有 AI 玩家绑定 game_id 并加载跨局玩家档案（进化机制）。"""
        from src.agents.ai_agent import AIAgent

        for agent in self.broker.agents.values():
            if not isinstance(agent, AIAgent):
                continue
            try:
                agent.set_game_context(self.state.game_id)
                agent.load_player_profile()
            except Exception as exc:
                logger.warning("[player-profile] 绑定对局上下文失败 %s: %s", agent.name, exc)

    async def run_game_loop(self) -> Team | None:
        try:
            if not self._setup_done:
                self._setup_done = asyncio.get_running_loop().create_future()
            self._loop_started_at = time.time()
            self._mark_progress("setup")
            logger.info("=== 游戏开始 ===")
            self.snapshot_manager.take_snapshot(self.state)
            await self._transition_and_run(GamePhase.SETUP)

            while not self.winner:
                self.winner = self.state.winning_team or VictoryChecker.check_victory(self.state)
                if self.winner:
                    await self._transition_and_run(GamePhase.GAME_OVER)
                    break

                phase = self.phase_manager.current_phase
                if phase == GamePhase.SETUP:
                    self._mark_progress("setup_done")
                    logger.info("[run_game_loop] Waiting for _setup_done...")
                    await self._setup_done
                    logger.info(
                        "[run_game_loop] _setup_done received. Transitioning to FIRST_NIGHT"
                    )
                    await self._transition_and_run(GamePhase.FIRST_NIGHT)
                elif phase in (GamePhase.FIRST_NIGHT, GamePhase.NIGHT):
                    await self._transition_and_run(GamePhase.DAY_DISCUSSION)
                elif phase == GamePhase.DAY_DISCUSSION:
                    await self._transition_and_run(GamePhase.NOMINATION)
                elif phase in (GamePhase.NOMINATION, GamePhase.EXECUTION):
                    await self._transition_and_run(GamePhase.NIGHT)
                else:
                    break
            return self.winner
        finally:
            if game_debug_logger.game_id == self.state.game_id:
                logger.info("Ending debug logs for game %s", self.state.game_id)
                game_debug_logger.end_game()

    async def _transition_and_run(self, target_phase: GamePhase) -> None:
        phase_start = time.perf_counter()
        self._phase_started_at = time.time()
        self._phase_started_action_positions = self._snapshot_ai_action_positions()
        self._mark_progress(f"phase:{target_phase.value}")
        if target_phase != self.phase_manager.current_phase:
            await self._archive_agent_phase_memories()
        if target_phase != self.phase_manager.current_phase or target_phase == GamePhase.SETUP:
            self.phase_manager.transition_to(target_phase)
        self.state = self.state.with_update(
            phase=target_phase,
            round_number=self.phase_manager.round_number,
            day_number=self.phase_manager.day_number,
        )
        if target_phase == GamePhase.GAME_OVER:
            self._set_nomination_state(
                stage="idle",
                result_phase="game_over",
                current_nominator=None,
                current_nominee=None,
                votes_cast=0,
                yes_votes=0,
                threshold=(self.state.alive_count // 2) + 1 if self.state.alive_count else 0,
                votes={},
                defense_text=None,
                last_result=None,
            )
            # 结算报告生成与持久化
            self.settlement_report = self._build_settlement_report()
            self.state = self.state.with_update(winning_team=self.winner)
            await self._publish_event(
                GameEvent(
                    event_type="game_settlement",
                    phase=GamePhase.GAME_OVER,
                    round_number=self.phase_manager.round_number,
                    trace_id=self._make_trace_id("BOTC-SETTLEMENT"),
                    visibility=Visibility.PUBLIC,
                    payload=self.settlement_report,
                )
            )
            try:
                await self.record_store.save_game(
                    self.state.game_id, self.state, self.settlement_report
                )
            except Exception as exc:
                logger.error("Failed to persist game record: %s", exc)
            self._record_data_snapshot(
                "game_settlement_ready",
                winning_team=self.winner.value if self.winner else None,
                timeline_items=len(self.settlement_report.get("timeline", []))
                if self.settlement_report
                else 0,
            )
            # PLN-038 阶段 E：局末玩家进化（战绩 + 经验教训写入跨局档案）
            await self._finalize_agent_player_profiles()

        phase_event = GameEvent(
            event_type="phase_changed",
            phase=target_phase,
            round_number=self.phase_manager.round_number,
            trace_id=self._make_trace_id("BOTC-FLOW-PHASE"),
            visibility=Visibility.PUBLIC,
            payload={"day_number": self.phase_manager.day_number},
        )
        await self._publish_event(phase_event)
        self.snapshot_manager.take_snapshot(self.state)

        if self._should_storyteller_auto_act():
            narration = await self.storyteller_agent.narrate_phase(self.state)
            if narration:
                self.state = self.state.with_message(
                    ChatMessage(
                        speaker="storyteller",
                        content=narration,
                        phase=target_phase,
                        round_number=self.phase_manager.day_number,
                    )
                )

        # [A3-ST-6] 如果开启了 AI 说书人自动动作，在每个阶段开始时进行局势分析
        if self.storyteller_agent and self._should_storyteller_auto_act():
            try:
                await self.storyteller_agent.analyze_game_situation(self.state)
            except Exception as exc:
                logger.warning("Storyteller analysis failed: %s", exc)

        if target_phase == GamePhase.SETUP:
            await self._run_setup_phase()
        elif target_phase == GamePhase.FIRST_NIGHT:
            await self._run_first_night()
        elif target_phase == GamePhase.NIGHT:
            await self._run_night()
        elif target_phase == GamePhase.DAY_DISCUSSION:
            await self._run_day_discussion()
        elif target_phase == GamePhase.NOMINATION:
            await self._run_nomination_phase()
        duration_ms = int((time.perf_counter() - phase_start) * 1000)
        phase_action_summary = self._summarize_ai_action_records(
            self._collect_ai_action_records_since(self._phase_started_action_positions)
        )
        self._phase_duration_history.append(
            {
                "phase": target_phase.value,
                "day_number": self.state.day_number,
                "round_number": self.state.round_number,
                "duration_ms": duration_ms,
                "ai_action_count": phase_action_summary["action_count"],
                "ai_total_tokens": phase_action_summary["total_tokens"],
                "ai_average_tokens_per_action": phase_action_summary["average_tokens_per_action"],
                "ai_fallback_count": phase_action_summary["fallback_count"],
                "ai_fallback_token_share": phase_action_summary["fallback_token_share"],
                "ai_top_token_action": phase_action_summary["top_token_actions"][0]
                if phase_action_summary["top_token_actions"]
                else None,
                "ai_tokens_by_action_type": phase_action_summary["tokens_by_action_type"],
                "ai_fallback_by_action_type": phase_action_summary["fallback_by_action_type"],
            }
        )
        self._phase_duration_history = self._phase_duration_history[-50:]
        self._mark_progress(None)

    async def _finalize_agent_player_profiles(self) -> None:
        """局末提炼：为每个 AI 玩家记录战绩、复盘并调整策略（拟人化进化）。

        真实角色/阵营/胜负来自 settlement_report（确定性）。
        拟人化四维：
        1. 局后复盘（finalize_game_review：战绩 + 复盘要点 + 倾向微调）；
        2. 学习他人经验（learn_play_style：从胜方 MVP / 表现好的玩家身上提炼打法）；
        3. 经验教训沉淀（legacy append_lesson，保留兼容）。
        均不含私密信息。
        """
        from src.agents.ai_agent import AIAgent

        report = self.settlement_report or {}
        winning_team = (report.get("winning_team") or "").lower()
        player_reveal: dict[str, dict[str, Any]] = {}
        for entry in report.get("players", []):
            player_reveal[entry.get("player_id", "")] = entry

        for agent in self.broker.agents.values():
            if not isinstance(agent, AIAgent):
                continue
            reveal = player_reveal.get(agent.player_id, {})
            team = (reveal.get("team") or "").lower()
            won = bool(winning_team) and team == winning_team
            role_id = reveal.get("true_role_id")
            takeaway = self._build_player_takeaway(agent, reveal, won)
            lesson = self._build_player_lesson(agent, reveal, won)
            try:
                # 1) 局后复盘 + 调整策略（拟人化进化核心）
                agent.finalize_game_review(
                    won=won,
                    role_id=role_id,
                    team=team,
                    takeaway=takeaway,
                )
                # 2) 经验教训沉淀（兼容）
                agent.finalize_game_lesson(
                    won=won,
                    role_id=role_id,
                    team=team,
                    lesson=lesson,
                )
            except Exception as exc:
                logger.warning("[player-profile] 玩家进化落盘失败 %s: %s", agent.player_id, exc)

        # 3) 学习他人经验：从胜方 MVP / 表现好的玩家提炼打法
        await self._learn_from_strong_players(winning_team, player_reveal)

        # 说书人跨局档案（进化机制）
        if self.storyteller_agent is not None and hasattr(
            self.storyteller_agent, "finalize_game_profile"
        ):
            try:
                await self.storyteller_agent.finalize_game_profile(
                    game_id=self.state.game_id,
                    lesson="本局已主持并记录裁决；如需复盘可调用 review_balance。",
                )
            except Exception as exc:
                logger.warning("[storyteller-profile] 说书人进化落盘失败: %s", exc)

    def _build_player_takeaway(self, agent: Any, reveal: dict[str, Any], won: bool) -> str:
        """构造局后复盘的『本局收获』（规则模板，无私密信息）。

        拟人化：赢局提炼"我做了什么对的"，输局提炼"下次该改什么"。
        """
        role_id = reveal.get("true_role_id") or agent.role_id or "unknown"
        team = (reveal.get("team") or agent.team or "unknown").lower()
        if won:
            # 赢局：强调可复制的打法
            return (
                f"作为{role_id}（{team}）获胜，"
                "本局有效打法可复用：控制信息节奏、团结可信队友、按可信线索行动。"
            )
        # 输局：反思可改进点（按角色/阵营给出方向，无私密）
        if team == "evil":
            return (
                f"作为{role_id}（{team}）落败，复盘提示：避免过早暴露、"
                "发言与行动要保持一致性、留好烟雾弹。"
            )
        return (
            f"作为{role_id}（{team}）落败，复盘提示：更早梳理信息位、"
            "公开表达关键判断、避免被误导站错边。"
        )

    async def _learn_from_strong_players(
        self, winning_team: str, player_reveal: dict[str, dict[str, Any]]
    ) -> None:
        """学习他人经验：从胜方表现好的玩家提炼打法，让所有 AI 玩家借鉴。

        拟人化：人类玩家会观察高手（通常是胜方阵营）的打法并模仿。
        这里从胜方中选出"局内表现活跃"的玩家，把其角色/阵营打法定式为
        可复用经验，写入每个 AI 玩家的 lessons_learned。
        """
        from src.agents.ai_agent import AIAgent

        if not winning_team:
            return
        # 胜方候选人：胜方存活 / 表现活跃者（用统计数据近似）
        candidates: list[dict[str, Any]] = []
        for _pid, reveal in player_reveal.items():
            if (reveal.get("team") or "").lower() != winning_team:
                continue
            stats = reveal.get("stats") or {}
            activity = int(stats.get("speech_count", 0) or 0) + int(stats.get("votes_cast", 0) or 0)
            candidates.append({**reveal, "_activity": activity})
        if not candidates:
            return
        # 取表现最好（活跃度最高）的玩家作为学习对象
        candidates.sort(key=lambda c: c["_activity"], reverse=True)
        role = candidates[0].get("true_role_id") or "unknown"
        role_style = {
            "imp": "恶魔要伪装成好人并主导夜间刀人，发言保持中立不引怀疑",
            "minion": "爪牙要保护恶魔，主动制造误导、替恶魔挡刀",
            "washerwoman": "洗衣妇要在首日快速建立可信信息位并分享",
            "fortune_teller": "占卜师要谨慎公开调查结果，避免过早暴露",
            "chef": "厨师要用当晚邻近恶魔数辅助首日推演",
            "hunter": "猎手要选择合适的开枪时机，别浪费技能",
        }.get(role, f"{role} 要保持信息位节奏与发言一致性")
        lesson = f"本局胜方{role}打法：{role_style}"

        for agent in self.broker.agents.values():
            if not isinstance(agent, AIAgent):
                continue
            try:
                agent.learn_play_style(role, lesson)
            except Exception as exc:
                logger.warning("[player-profile] 学习他人经验失败 %s: %s", agent.player_id, exc)

    def _build_player_lesson(self, agent: Any, reveal: dict[str, Any], won: bool) -> str:
        """构造一条可复用的局末经验（规则模板，无私密信息）。"""
        role_id = reveal.get("true_role_id") or agent.role_id or "unknown"
        team = (reveal.get("team") or agent.team or "unknown").lower()
        result_text = "获胜" if won else "落败"
        # 从本局记忆提取亮点（最多两条，自动截断）
        highlights: list[str] = []
        if hasattr(agent, "working_memory") and agent.working_memory.observations:
            for obs in agent.working_memory.observations[-2:]:
                text = (obs.content or "").strip()
                if text and not self._player_lesson_sensitive(text):
                    highlights.append(text[:60])
        detail = "；".join(highlights) if highlights else "本局主要推演过程已归档"
        return f"作为{role_id}（{team}阵营）{result_text}。{detail}"

    @staticmethod
    def _player_lesson_sensitive(text: str) -> bool:
        from src.agents.memory.player_profile import MemoryToolsLike

        return MemoryToolsLike.is_sensitive(text)

    async def _archive_agent_phase_memories(self) -> None:
        tasks = []
        for player_id, agent in self.broker.agents.items():
            try:
                visible_state = self._get_agent_visible_state(player_id)
                if visible_state:
                    tasks.append(agent.archive_phase_memory(visible_state))
            except Exception as exc:
                logger.warning("archive_phase_memory setup failed for %s: %s", player_id, exc)
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=10.0)
            except TimeoutError:
                logger.warning("[archive] phase memory archiving timed out after 10s")

    def export_game_record(self, export_dir: str) -> None:
        """持久化输出事件日志和系统快照到外部文件系统，用于前端回放或调试"""

        os.makedirs(export_dir, exist_ok=True)
        # 导出快照
        snapshot_path = os.path.join(export_dir, "snapshots.json")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(self.snapshot_manager.export_to_json())

        # 导出事件
        event_path = os.path.join(export_dir, "events.json")
        events_data = [e.model_dump(mode="json") for e in self.event_log.events]
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump(events_data, f, ensure_ascii=False, indent=2)

        logger.info(f"游戏记录已持久化到目录: {export_dir}")
