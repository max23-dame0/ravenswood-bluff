"""NominationVotingHandler — nomination, voting, execution mechanics."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from src.engine.nomination import NominationManager
from src.engine.rule_engine import RuleEngine
from src.engine.roles.base_role import get_role_class
from src.state.game_state import (
    AgentActionLegalContext,
    AgentVisibleState,
    GameEvent,
    GamePhase,
    RoleType,
    Visibility,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class NominationVotingHandler:
    """Nomination and voting logic extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    async def _run_nomination_phase(self) -> None:
        # [A3-DATA-2] 提名前快照
        self._o._record_data_snapshot("before_nomination")

        self._o._set_nomination_state(
            stage="window_open",
            result_phase="window_open",
            current_nominator=None,
            current_nominee=None,
            votes_cast=0,
            yes_votes=0,
        )
        self._o._record_data_snapshot(
            "nomination_window_open",
            threshold=RuleEngine.votes_required(self._o.state),
        )
        max_rounds = self._o.state.config.max_nomination_rounds if self._o.state.config and self._o.state.config.max_nomination_rounds else max(1, self._o.state.alive_count)
        nomination_round = 0
        had_any_nomination = False
        self._o._log_storyteller("nomination_phase_open", max_rounds=max_rounds, alive=self._o.state.alive_count)
        self._o._record_storyteller_judgement(
            "nomination_started",
            decision="open",
            max_rounds=max_rounds,
            alive=self._o.state.alive_count,
        )

        while nomination_round < max_rounds:
            nomination_round += 1
            self._o._mark_progress(f"nomination_intents:round:{nomination_round}")
            intents = await self._collect_nomination_intents(nomination_round)

            # [FIX] 优先处理猎手技能发动
            for intent_pid, intent_data in intents.items():
                if intent_data.get("action") == "slayer_shot":
                    target_id = intent_data.get("target")
                    if target_id:
                        await self._o._execute_slayer_shot(intent_pid, target_id)

            chosen = self._select_nomination_intent(intents)
            if not chosen:
                self._o._set_nomination_state(
                    stage="no_nomination" if not had_any_nomination else "resolved",
                    result_phase="no_nomination" if not had_any_nomination else "vote_resolved",
                    current_nominator=None,
                    current_nominee=None,
                    votes_cast=0,
                    yes_votes=0,
                    round=nomination_round,
                    last_result={"executed": None, "reason": "no_nomination"} if not had_any_nomination else self._o.state.payload.get("nomination_state", {}).get("last_result", {"executed": None}),
                )
                if not had_any_nomination:
                    self._o._append_nomination_history({
                        "kind": "no_nomination",
                        "round": nomination_round,
                        "reason": "no_legal_intent",
                        "trace_id": self._o._make_trace_id("BOTC-FLOW-NOM-NONE"),
                    })
                self._o._log_storyteller(
                    "nomination_round_no_nomination",
                    round=nomination_round,
                    had_any_nomination=had_any_nomination,
                )
                self._o._record_storyteller_judgement(
                    "nomination_choice",
                    decision="none",
                    reason="no_legal_intent",
                    round=nomination_round,
                    intents={pid: intent.get("target") if intent else None for pid, intent in intents.items()},
                )
                break

            had_any_nomination = True
            nominator_id, target_id = chosen
            self._o._record_storyteller_judgement(
                "nomination_choice",
                decision="choose",
                reason="first_legal_intent",
                round=nomination_round,
                nominator=nominator_id,
                nominee=target_id,
            )
            trace_id = self._o._make_trace_id("BOTC-FLOW-NOM")
            try:
                self._o._ensure_player_alive(nominator_id, "nomination_actor")
                self._o._ensure_player_alive(target_id, "nomination_target")
                self._o.state, events = NominationManager.nominate(self._o.state, nominator_id, target_id, trace_id)
                # [FIX] 如果由于特殊技能（如圣女）导致了即时处决，处决事件会修改 phase 为非提名且非投票状态（如直接进入结算或回退讨论）
                if self._o.state.phase not in [GamePhase.NOMINATION, GamePhase.VOTING]:
                    logger.info("提名阶段被特殊技能(如圣女)中断，或已直接进入处决结算。")
                    break
            except ValueError as exc:
                logger.warning("无效提名: %s", exc)
                self._o._set_nomination_state(
                    stage="invalid_nomination",
                    result_phase="invalid_nomination",
                    reason=str(exc),
                    round=nomination_round,
                    last_result={"executed": None, "reason": "invalid_nomination"},
                )
                self._o._append_nomination_history({
                    "kind": "invalid_nomination",
                    "round": nomination_round,
                    "nominator": nominator_id,
                    "nominee": target_id,
                    "reason": str(exc),
                    "trace_id": trace_id,
                })
                self._o._log_storyteller(
                    "nomination_invalid",
                    round=nomination_round,
                    nominator=nominator_id,
                    nominee=target_id,
                    reason=str(exc),
                )
                self._o._record_storyteller_judgement(
                    "nomination_choice",
                    decision="invalid",
                    reason=str(exc),
                    round=nomination_round,
                    nominator=nominator_id,
                    nominee=target_id,
                )
                continue

            await self._o._publish_event(GameEvent(
                event_type="nomination_attempted",
                phase=GamePhase.NOMINATION,
                round_number=self._o.state.round_number,
                trace_id=trace_id,
                actor=nominator_id,
                target=target_id,
                visibility=Visibility.STORYTELLER_ONLY,
                payload={"accepted": True, "round": nomination_round},
            ))
            for event in events:
                await self._o.event_bus.publish(event)
            self._o._set_nomination_state(
                stage="defense",
                result_phase="nomination_started",
                current_nominator=nominator_id,
                current_nominee=target_id,
                votes_cast=0,
                yes_votes=0,
                threshold=RuleEngine.votes_required(self._o.state),
                round=nomination_round,
                trace_id=trace_id,
                defense_text=None,
                votes={},
            )
            self._o._log_storyteller(
                "nomination_started",
                round=nomination_round,
                nominator=nominator_id,
                nominee=target_id,
                threshold=RuleEngine.votes_required(self._o.state),
            )
            self._o._append_nomination_history({
                "kind": "nomination_started",
                "round": nomination_round,
                "nominator": nominator_id,
                "nominee": target_id,
                "threshold": RuleEngine.votes_required(self._o.state),
                "trace_id": trace_id,
            })
            self._o._record_storyteller_judgement(
                "nomination_started",
                decision="start",
                round=nomination_round,
                nominator=nominator_id,
                nominee=target_id,
                threshold=RuleEngine.votes_required(self._o.state),
                trace_id=trace_id,
            )
            if await self._handle_virgin_trigger(nominator_id, target_id, trace_id):
                self._o._update_payload(skip_execution_finalize=True)
                self._o._set_nomination_state(
                    stage="executed",
                    result_phase="execution_resolved",
                    current_nominator=nominator_id,
                    current_nominee=target_id,
                    round=nomination_round,
                    last_result={"executed": nominator_id, "reason": "virgin"},
                )
                self._o._append_nomination_history({
                    "kind": "execution_resolved",
                    "round": nomination_round,
                    "executed": nominator_id,
                    "reason": "virgin",
                    "trace_id": trace_id,
                })
                self._o._log_storyteller(
                    "virgin_trigger",
                    round=nomination_round,
                    nominator=nominator_id,
                    nominee=target_id,
                )
                self._o._record_storyteller_judgement(
                    "execution",
                    decision="virgin_trigger",
                    round=nomination_round,
                    nominator=nominator_id,
                    nominee=target_id,
                    trace_id=trace_id,
                )
                break

            await self._run_defense_and_voting(target_id, trace_id)
            self._o._log_storyteller(
                "nomination_round_resolved",
                round=nomination_round,
                nominee=target_id,
                votes=self._o.state.votes_today,
            )
            self._o._record_storyteller_judgement(
                "voting_resolution",
                decision="resolved",
                round=nomination_round,
                nominee=target_id,
                votes=self._o.state.votes_today,
                trace_id=trace_id,
            )
            if not self._can_continue_nomination_rounds(nomination_round, max_rounds):
                break

        if self._o.state.payload.get("skip_execution_finalize"):
            payload = dict(self._o.state.payload)
            payload.pop("skip_execution_finalize", None)
            self._o.state = self._o.state.with_update(payload=payload)
            self._o._sync_all_agents("BOTC-FLOW-EXEC-SKIP")
            return

        trace_id = self._o._make_trace_id("BOTC-FLOW-EXEC")
        self._o.state, events = NominationManager.finalize_execution(self._o.state, trace_id)
        for event in events:
            await self._o.event_bus.publish(event)
        final_payload = events[0].payload if events else {"executed": None}
        self._o._set_nomination_state(
            stage="executed",
            result_phase="execution_resolved",
            current_nominator=None,
            current_nominee=None,
            votes={},
            votes_cast=0,
            yes_votes=0,
            defense_text=None,
            last_result=final_payload,
            round=nomination_round,
        )
        self._o._append_nomination_history({
            "kind": "execution_resolved",
            "round": nomination_round,
            "executed": final_payload.get("executed"),
            "votes": final_payload.get("votes"),
            "trace_id": trace_id,
        })
        self._o._sync_all_agents(trace_id)
        self._o._log_storyteller(
            "execution_finalized",
            round=nomination_round,
            executed=final_payload.get("executed"),
            votes=final_payload.get("votes"),
            trace_id=trace_id,
        )
        self._o._record_storyteller_judgement(
            "execution",
            decision="finalize",
            round=nomination_round,
            executed=final_payload.get("executed"),
            votes=final_payload.get("votes"),
            trace_id=trace_id,
        )

        # [A3-DATA-2] 投票与处决后快照
        self._o._record_data_snapshot("after_execution")

    def _select_nomination_intent(self, intents: dict[str, dict[str, Any]]) -> tuple[str, str] | None:
        for player_id in self._o.state.seat_order or tuple(p.player_id for p in self._o.state.players):
            intent = intents.get(player_id)
            if not intent:
                continue
            target_id = intent.get("target")
            if intent.get("action") == "nominate" and target_id and target_id != "not_nominating":
                return player_id, target_id
        if self._o.state.config and self._o.state.config.audit_mode:
            return self._select_audit_nomination_fallback()
        return None

    def _select_audit_nomination_fallback(self) -> tuple[str, str] | None:
        seat_order = self._o.state.seat_order or tuple(p.player_id for p in self._o.state.players)
        for nominator_id in seat_order:
            nominator = self._o.state.get_player(nominator_id)
            if not nominator or not nominator.is_alive:
                continue
            if nominator_id in self._o.state.nominations_today:
                continue
            for target_id in seat_order:
                if target_id == nominator_id:
                    continue
                target = self._o.state.get_player(target_id)
                if not target or not target.is_alive:
                    continue
                if target_id in self._o.state.nominees_today:
                    continue
                allowed, _ = RuleEngine.can_nominate(self._o.state, nominator_id, target_id)
                if allowed:
                    self._o._log_storyteller(
                        "nomination_audit_fallback",
                        nominator=nominator_id,
                        nominee=target_id,
                    )
                    self._o._record_storyteller_judgement(
                        "nomination_choice",
                        decision="audit_fallback",
                        reason="no_agent_crossed_threshold",
                        nominator=nominator_id,
                        nominee=target_id,
                    )
                    return nominator_id, target_id
        return None

    def _can_continue_nomination_rounds(self, nomination_round: int, max_rounds: int) -> bool:
        if nomination_round >= max_rounds:
            return False
        alive_players = [player for player in self._o.state.players if player.is_alive]
        remaining_nominators = [player for player in alive_players if player.player_id not in self._o.state.nominations_today]
        remaining_nominees = [player for player in alive_players if player.player_id not in self._o.state.nominees_today]
        return bool(remaining_nominators and remaining_nominees)

    async def _collect_nomination_intents(self, nomination_round: int) -> dict[str, dict[str, Any]]:
        await self._o._publish_event(GameEvent(
            event_type="nomination_window_opened",
            phase=GamePhase.NOMINATION,
            round_number=self._o.state.round_number,
            trace_id=self._o._make_trace_id("BOTC-FLOW-NOMWIN"),
            visibility=Visibility.PUBLIC,
            payload={"round": nomination_round},
        ))
        self._o._set_nomination_state(
            stage="nomination",
            current_nominator=None,
            current_nominee=None,
            votes_cast=0,
            yes_votes=0,
            threshold=RuleEngine.votes_required(self._o.state),
            round=nomination_round,
        )
        self._o._log_storyteller(
            "nomination_window_opened",
            round=nomination_round,
            alive=self._o.state.alive_count,
        )
        ordered_players = [
            self._o.state.get_player(pid)
            for pid in (self._o.state.seat_order or tuple(p.player_id for p in self._o.state.players))
        ]
        eligible_players = [
            player for player in ordered_players
            if player and player.is_alive and player.player_id not in self._o.state.nominations_today
        ]
        tasks: list[tuple[str, asyncio.Task]] = []
        human_ids = set(self._o.state.config.human_player_ids if self._o.state.config else [])
        for player in eligible_players:
            agent = self._o.broker.agents.get(player.player_id)
            if not agent:
                continue
            action_type = "nominate" if player.player_id in human_ids else "nomination_intent"
            visible_state = self._o._get_agent_visible_state(player.player_id)
            if not visible_state:
                continue
            legal_context = self._o._get_agent_legal_context(player.player_id, visible_state)

            # 为人类玩家增加强制选择校验
            if player.player_id in human_ids:
                async def human_nomination_loop(v_state, a_type, l_ctx, a_agent):
                    trying_empty = False
                    retry_count = 0
                    while retry_count < self._o.MAX_AGENT_RETRIES:
                        retry_count += 1
                        # 发送请求并等待
                        self._o._mark_progress(f"human_action:{player.player_id}:nominate")
                        act_res = await a_agent.act(
                            v_state,
                            a_type,
                            legal_context=l_ctx,
                            reminder="请做出选择（提名玩家或选择'不提名'）。不可空选。" if trying_empty else None,
                            retry_count=retry_count,
                            last_error="必须明确选择提名对象或不提名" if trying_empty else None,
                        )
                        # 校验：必须有 target，且不得为空。合法的可以是 "not_nominating" 或 玩家 ID
                        tgt = act_res.get("target")
                        if tgt or act_res.get("action") == "none":
                            return act_res
                        logger.warning(f"[Nomination] 玩家 {player.player_id} 提交了空提名意图，重试 ({retry_count}/{self._o.MAX_AGENT_RETRIES})。")
                        trying_empty = True

                    # 达到最大重试次数，返回兜底跳过
                    return {"action": "not_nominating", "target": "not_nominating", "reason": "max_retries_reached"}

                tasks.append((player.player_id, asyncio.create_task(human_nomination_loop(visible_state, action_type, legal_context, agent))))
            else:
                self._o._mark_progress(f"ai_action:{player.player_id}:nomination_intent")
                async def _nomination_intent_task(pid=player.player_id, agt=agent, vs=visible_state, lc=legal_context):
                    return await self._o._timed_act(
                        agt, vs, action_type,
                        legal_context=lc,
                        player_id=pid,
                        phase="nomination",
                    )
                tasks.append((player.player_id, asyncio.create_task(_nomination_intent_task())))

        results: dict[str, dict[str, Any]] = {}
        for player_id, task in tasks:
            trace_id = self._o._make_trace_id("BOTC-FLOW-NOMINTENT")
            try:
                action = await task
            except Exception as exc:
                self._o._record_recent_exception(f"nomination_intent:{player_id}", exc)
                action = {"action": "none", "reasoning": f"nomination_intent_error:{type(exc).__name__}"}

            # 统一处理结果：如果结果依然为空（AI 异常等），给予默认值，防止卡死
            if not action.get("target"):
                action["target"] = "not_nominating"
                action["action"] = "not_nominating"

            await self._o._publish_event(GameEvent(
                event_type="nomination_intent_submitted",
                phase=GamePhase.NOMINATION,
                round_number=self._o.state.round_number,
                trace_id=trace_id,
                actor=player_id,
                target=action.get("target"),
                visibility=Visibility.STORYTELLER_ONLY,
                payload={"action": action.get("action"), "round": nomination_round},
            ))
            results[player_id] = action
            self._o._log_storyteller(
                "nomination_intent_submitted",
                round=nomination_round,
                actor=player_id,
                action=action.get("action"),
                target=action.get("target"),
            )
        return results

    async def _handle_virgin_trigger(self, nominator_id: str, nominee_id: str, trace_id: str) -> bool:
        nominee = self._o.state.get_player(nominee_id)
        nominator = self._o.state.get_player(nominator_id)
        if not nominee or not nominator:
            return False
        if nominee.true_role_id != "virgin" or "virgin_used" in nominee.storyteller_notes:
            return False
        role_cls = get_role_class(nominator.true_role_id or nominator.role_id)
        if not role_cls or role_cls.get_definition().role_type != RoleType.TOWNSFOLK:
            self._o.state = self._o.state.with_player_update(nominee_id, storyteller_notes=nominee.storyteller_notes + ("virgin_used",))
            return False
        self._o.state = self._o.state.with_player_update(nominator_id, is_alive=False)
        self._o.state = self._o.state.with_player_update(nominee_id, storyteller_notes=nominee.storyteller_notes + ("virgin_used",))
        await self._o._publish_event(GameEvent(
            event_type="execution_resolved",
            phase=GamePhase.EXECUTION,
            round_number=self._o.state.round_number,
            trace_id=trace_id,
            target=nominator_id,
            visibility=Visibility.PUBLIC,
            payload={"executed": nominator_id, "reason": "virgin"},
        ))
        self._o._log_storyteller(
            "virgin_resolved",
            nominator=nominator_id,
            nominee=nominee_id,
            executed=nominator_id,
            trace_id=trace_id,
        )
        return True

    async def _run_defense_and_voting(self, nominee_id: str, trace_id: str) -> None:
        # [GAME-1.2] 二次存活检查：防范提名发起后、进入防御前目标死亡（如特殊技能或圣女导致被提名人离场）
        nominee_player = self._o.state.get_player(nominee_id)
        if not nominee_player or not nominee_player.is_alive:
            logger.info("被提名人 %s 已死亡，取消防御和投票阶段", nominee_id)
            self._o._set_nomination_state(stage="resolved", result_phase="nominee_dead_abort")
            return

        agent = self._o.broker.agents.get(nominee_id)
        defense_text = "我无告可陈。"
        if agent:
            self._o._record_storyteller_judgement(
                "defense",
                decision="request",
                nominee=nominee_id,
                trace_id=trace_id,
            )
            visible_state = self._o._get_agent_visible_state(nominee_id)
            if not visible_state:
                visible_state = self._o.broker.get_visible_state(nominee_id, self._o.state)
            legal_context = self._o._get_agent_legal_context(nominee_id, visible_state) if visible_state else AgentActionLegalContext()
            self._o._mark_progress(f"ai_action:{nominee_id}:defense_speech")
            if visible_state:
                defense = await self._o._timed_act(
                    agent, visible_state, "defense_speech",
                    legal_context=legal_context,
                    player_id=nominee_id,
                    phase="defense",
                )
            else:
                defense = {"action": "speak", "content": defense_text}
            defense_text = defense.get("content", defense_text)
            self._o._set_nomination_state(stage="defense", defense_text=defense_text)
            self._o._log_storyteller(
                "defense_started",
                nominee=nominee_id,
                trace_id=trace_id,
                content=defense_text,
            )
            self._o._record_storyteller_judgement(
                "defense",
                decision="deliver",
                nominee=nominee_id,
                trace_id=trace_id,
                content=defense_text,
            )
            payload = {"content": defense_text}
            await self._o._publish_event(GameEvent(
                event_type="defense_started",
                phase=GamePhase.NOMINATION,
                round_number=self._o.state.round_number,
                trace_id=trace_id,
                actor=nominee_id,
                target=nominee_id,
                visibility=Visibility.PUBLIC,
                payload=payload,
            ))
        else:
            self._o._record_storyteller_judgement(
                "defense",
                decision="skip",
                reason="no_agent",
                nominee=nominee_id,
                trace_id=trace_id,
            )
        self._o._set_nomination_state(stage="voting", result_phase="defense_started")
        self._o._log_storyteller("voting_opened", nominee=nominee_id, trace_id=trace_id)
        self._o._record_storyteller_judgement(
            "voting_resolution",
            decision="open",
            nominee=nominee_id,
            trace_id=trace_id,
            defense_text=defense_text,
            threshold=RuleEngine.votes_required(self._o.state),
        )

        vote_details: dict[str, bool] = {}
        votes_cast = 0
        yes_votes = 0
        human_ids = set(self._o.state.config.human_player_ids if self._o.state.config else [])

        async def _ai_vote_task(voter_id: str) -> tuple[str, bool]:
            """并发执行单个 AI 玩家的投票决策，返回 (voter_id, decision)。"""
            vote_agent = self._o.broker.agents.get(voter_id)
            try:
                visible_state = self._o._get_agent_visible_state(voter_id)
                if not visible_state:
                    return voter_id, False
                legal_context = self._o._get_agent_legal_context(voter_id, visible_state)
                action = await self._o._timed_act(
                    vote_agent, visible_state, "vote",
                    legal_context=legal_context,
                    player_id=voter_id,
                    phase="voting",
                )
                return voter_id, bool(action.get("decision", False))
            except Exception as e:
                self._o._record_recent_exception(f"vote:{voter_id}", e)
                logger.error(f"Voter {voter_id} action error: {e}")
                return voter_id, False

        # 先并发收集所有 AI 投票决策，人类玩家串行处理
        vote_decisions: dict[str, bool] = {}
        ai_vote_tasks: list[tuple[str, asyncio.Task]] = []

        for voter in self._o.state.players:
            voter_id = voter.player_id
            vote_agent = self._o.broker.agents.get(voter_id)
            if not vote_agent:
                continue
            if voter_id in human_ids:
                # 人类玩家：串行处理
                try:
                    visible_state = self._o._get_agent_visible_state(voter_id)
                    if not visible_state:
                        continue
                    legal_context = self._o._get_agent_legal_context(voter_id, visible_state)
                    trying_empty = False
                    retry_count = 0
                    action: dict[str, Any] = {"action": "vote", "decision": False}
                    while retry_count < self._o.MAX_AGENT_RETRIES:
                        retry_count += 1
                        self._o._mark_progress(f"human_action:{voter_id}:vote")
                        action = await vote_agent.act(
                            visible_state,
                            "vote",
                            legal_context=legal_context,
                            reminder="请做出明确选择（同意或不赞成）。不可直接跳过。" if trying_empty else None,
                            retry_count=retry_count,
                            last_error="必须明确选择同意或不赞成" if trying_empty else None,
                        )
                        if action.get("decision") is not None:
                            break
                        logger.warning(f"[Voting] 玩家 {voter_id} 提交了空投票意图，重试 ({retry_count}/{self._o.MAX_AGENT_RETRIES})。")
                        trying_empty = True
                    if action.get("decision") is None:
                        action = {"action": "vote", "decision": False, "reason": "max_retries_reached"}
                    vote_decisions[voter_id] = bool(action.get("decision", False))
                except Exception as e:
                    self._o._record_recent_exception(f"vote:{voter_id}", e)
                    vote_decisions[voter_id] = False
            else:
                self._o._mark_progress(f"ai_action:{voter_id}:vote")
                ai_vote_tasks.append((voter_id, asyncio.create_task(_ai_vote_task(voter_id))))

        # 等待所有 AI 投票完成
        for voter_id, task in ai_vote_tasks:
            pid, decision = await task
            vote_decisions[pid] = decision

        # 按座位顺序应用投票到状态
        for voter in self._o.state.players:
            voter_id = voter.player_id
            if voter_id not in vote_decisions:
                continue
            decision = vote_decisions[voter_id]
            try:
                self._o.state, events = NominationManager.cast_vote(self._o.state, voter_id, decision, trace_id)
                for event in events:
                    await self._o.event_bus.publish(event)
            except ValueError:
                continue

            vote_details[voter_id] = decision
            votes_cast += 1
            yes_votes += 1 if decision else 0
            self._o._set_nomination_state(
                votes_cast=votes_cast,
                yes_votes=yes_votes,
                threshold=RuleEngine.votes_required(self._o.state),
                votes=vote_details,
            )
            self._o._log_storyteller(
                "vote_cast",
                voter=voter_id,
                decision=decision,
                nominee=nominee_id,
                yes_votes=yes_votes,
                votes_cast=votes_cast,
                trace_id=trace_id,
            )
            self._o._record_storyteller_judgement(
                "voting_resolution",
                decision="cast_vote",
                voter=voter_id,
                nominee=nominee_id,
                vote=decision,
                yes_votes=yes_votes,
                votes_cast=votes_cast,
                trace_id=trace_id,
            )
            for event in events:
                await self._o.event_bus.publish(event)

        self._o.state, events = NominationManager.resolve_voting_round(self._o.state, trace_id)
        for event in events:
            await self._o.event_bus.publish(event)
        if events:
            result_payload = dict(events[0].payload)
            result_payload["target"] = nominee_id
            self._o._set_nomination_state(
                stage="resolved",
                result_phase="vote_resolved",
                last_result=result_payload,
                current_nominee=nominee_id,
                votes=vote_details,
                votes_cast=votes_cast,
                yes_votes=yes_votes,
                defense_text=defense_text,
            )
            self._o._append_nomination_history({
                "kind": "voting_resolved",
                "round": self._o.state.payload.get("nomination_state", {}).get("round"),
                "nominee": nominee_id,
                "passed": result_payload.get("passed"),
                "votes": result_payload.get("votes"),
                "needed": result_payload.get("needed"),
                "voters": vote_details,
                "trace_id": trace_id,
            })
            self._o._log_storyteller(
                "voting_resolved",
                nominee=nominee_id,
                passed=result_payload.get("passed"),
                votes=result_payload.get("votes"),
                needed=result_payload.get("needed"),
                trace_id=trace_id,
            )
            self._o._record_storyteller_judgement(
                "voting_resolution",
                decision="resolve",
                nominee=nominee_id,
                passed=result_payload.get("passed"),
                votes=result_payload.get("votes"),
                needed=result_payload.get("needed"),
                yes_votes=yes_votes,
                votes_cast=votes_cast,
                trace_id=trace_id,
            )
            self._o._record_data_snapshot(
                "voting_resolved",
                nominee=nominee_id,
                passed=result_payload.get("passed"),
                votes=result_payload.get("votes"),
                needed=result_payload.get("needed"),
            )
