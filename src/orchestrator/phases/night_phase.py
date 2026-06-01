"""NightPhaseHandler — first night, night actions, death triggers, slayer shots."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Any

from src.engine.roles.base_role import get_all_role_ids, get_role_class
from src.state.game_state import (
    AbilityTrigger,
    GameEvent,
    GamePhase,
    PlayerStatus,
    Team,
    Visibility,
)

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class NightPhaseHandler:
    """Night phase logic extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    async def _run_first_night(self) -> None:
        self._o._update_grimoire()
        evil_players = [p for p in self._o.state.players if (p.current_team or p.team) == Team.EVIL]

        # --- Parallel: evil reveal + storyteller initial setup ---

        async def _reveal_evil():
            """Publish evil team membership to all evil players."""
            for player in evil_players:
                teammates = [p.name for p in evil_players if p.player_id != player.player_id]
                bluffs = list(self._o.state.bluffs)
                await self._o._publish_private_info(
                    phase=GamePhase.FIRST_NIGHT,
                    target=player.player_id,
                    trace_id=self._o._make_trace_id("BOTC-ST-EVIL"),
                    payload={
                        "type": "evil_reveal",
                        "title": "邪恶阵营互认",
                        "teammates": teammates,
                        "bluffs": bluffs,
                    },
                )
                self._o._record_storyteller_judgement(
                    "evil_reveal",
                    decision="deliver",
                    phase="first_night",
                    player_id=player.player_id,
                    teammates=teammates,
                    bluffs=bluffs,
                )

        async def _storyteller_setup():
            """Let the storyteller decide initial setup info (drunk, washerwoman, etc.)."""
            if self._o._should_storyteller_auto_act():
                return await self._o.storyteller_agent.decide_initial_setup_info(self._o.state)
            return None

        # 在首夜开始时，邪恶阵营互认与说书人初始配置可并行执行
        results = await asyncio.gather(
            _reveal_evil(),
            _storyteller_setup(),
            return_exceptions=True,
        )
        # Apply storyteller setup result (returns a new GameState)
        if len(results) > 1 and results[1] is not None and not isinstance(results[1], Exception):
            self._o.state = results[1]
        # Log any exceptions from parallel tasks
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error("[first_night] parallel task %d failed: %s", i, r)

        # --- Evil team first-night coordination window ---
        await self._run_evil_first_night_coordination(evil_players)

        # --- Sequential: night actions (depend on setup being complete) ---
        await self._execute_night_actions(GamePhase.FIRST_NIGHT)
        await self._distribute_night_info(GamePhase.FIRST_NIGHT)
        self._o._sync_all_agents("BOTC-FLOW-NIGHT")
        self._o._update_grimoire()
        await self._o._batch_reflect_agents(GamePhase.FIRST_NIGHT)
        self._o._record_data_snapshot(
            "first_night_complete",
            private_info_events=sum(1 for e in self._o.state.event_log if e.event_type == "private_info_delivered"),
        )

    async def _run_evil_first_night_coordination(self, evil_players: list) -> None:
        """Allow evil players to coordinate claims before first-night actions.

        The demon speaks first (proposes claim assignments), then minions
        respond in order.  Each later speaker sees earlier messages in
        their visible_state.public_chat_history.
        """
        # Sort so the demon (imp) goes first
        sorted_players = sorted(evil_players, key=lambda p: 0 if (p.true_role_id or p.role_id) == "imp" else 1)
        for player in sorted_players:
            agent = self._o.broker.agents.get(player.player_id)
            if not agent or not hasattr(agent, "generate_first_night_coordination"):
                continue
            visible_state = self._o._get_agent_visible_state(player.player_id)
            if not visible_state:
                continue
            try:
                msg = await agent.generate_first_night_coordination(visible_state)
                if msg:
                    await self._o.handle_chat(player.player_id, msg, is_private=True)
            except Exception as exc:
                logger.warning("First-night coordination failed for %s: %s", player.player_id, exc)

    async def _run_night(self) -> None:
        pre_alive = {p.player_id for p in self._o.state.get_alive_players()}
        self._clear_transient_statuses()
        # 在每晚行动开始前，说书人可以做出一些全局性决策（如间谍/隐士是否误报）
        if self._o._should_storyteller_auto_act():
            self._o.state = await self._o.storyteller_agent.decide_misregistration(self._o.state)

        await self._execute_night_actions(GamePhase.NIGHT)
        await self._distribute_night_info(GamePhase.NIGHT)
        await self._resolve_on_death_triggers(pre_alive)
        self._o._sync_all_agents("BOTC-FLOW-NIGHT")
        self._o._update_grimoire()
        for dead_id in sorted(pre_alive - {p.player_id for p in self._o.state.get_alive_players()}):
            await self._o._publish_event(GameEvent(
                event_type="player_death",
                phase=GamePhase.NIGHT,
                round_number=self._o.state.round_number,
                trace_id=self._o._make_trace_id("BOTC-RULE-DEATH"),
                target=dead_id,
                visibility=Visibility.PUBLIC,
                payload={"reason": "night"},
            ))

    async def _resolve_on_death_triggers(self, pre_alive: set[str]) -> None:
        newly_dead_ids = sorted(pre_alive - {p.player_id for p in self._o.state.get_alive_players()})
        for dead_id in newly_dead_ids:
            player = self._o.state.get_player(dead_id)
            if not player:
                continue
            role_id = player.true_role_id or player.role_id
            role_cls = get_role_class(role_id)
            if not role_cls or role_cls.get_definition().ability.trigger != AbilityTrigger.ON_DEATH:
                continue
            agent = self._o.broker.agents.get(dead_id)
            if not agent:
                continue
            trace_id = self._o._make_trace_id("BOTC-ST-DEATH")
            await self._o._publish_event(GameEvent(
                event_type="death_trigger_requested",
                phase=GamePhase.NIGHT,
                round_number=self._o.state.round_number,
                trace_id=trace_id,
                actor=dead_id,
                visibility=Visibility.STORYTELLER_ONLY,
                payload={"role_id": role_id},
            ))
            self._o._log_storyteller(
                "death_trigger_requested",
                actor=dead_id,
                role=role_id,
                trace_id=trace_id,
            )
            self._o._record_storyteller_judgement(
                "death_trigger",
                decision="request",
                actor=dead_id,
                role=role_id,
                trace_id=trace_id,
            )
            try:
                visible_state = self._o._get_agent_visible_state(player.player_id)
                if not visible_state:
                    continue
                legal_context = self._o._get_agent_legal_context(player.player_id, visible_state)
                self._o._mark_progress(f"ai_action:{player.player_id}:death_trigger")
                action = await self._o._timed_act(
                    agent, visible_state, "death_trigger",
                    legal_context=legal_context,
                    player_id=player.player_id,
                    phase="death_trigger",
                )
            except Exception as exc:
                self._o._record_recent_exception(f"death_trigger:{dead_id}", exc)
                logger.warning("死亡触发决策失败: %s", exc)
                action = {"action": "death_trigger", "target": None, "reasoning": f"death_trigger_error:{type(exc).__name__}"}
            target = action.get("target")
            role = role_cls()
            new_state, events = role.execute_ability(self._o.state, player, target)
            self._o.state = new_state
            for event in events:
                if event.event_type == "night_info" and event.visibility == Visibility.PRIVATE:
                    payload = dict(event.payload)
                    payload.setdefault("type", f"{role_id}_info")
                    await self._o._publish_private_info(
                        phase=GamePhase.NIGHT,
                        target=dead_id,
                        trace_id=trace_id,
                        payload=payload,
                    )
                    continue
                await self._o.event_bus.publish(event)
            self._o._log_storyteller(
                "death_trigger_resolved",
                actor=dead_id,
                role=role_id,
                target=target,
                trace_id=trace_id,
            )
            self._o._record_storyteller_judgement(
                "death_trigger",
                decision="resolved",
                actor=dead_id,
                role=role_id,
                target=target,
                trace_id=trace_id,
            )

    async def _execute_slayer_shot(self, actor_id: str, target_id: str) -> None:
        """执行猎手技能"""
        try:
            actor = self._o._ensure_player_alive(actor_id, "slayer_shot_actor")
            target = self._o._ensure_player_alive(target_id, "slayer_shot_target")
        except ValueError as e:
            logger.warning("猎手技能校验失败: %s", e)
            return

        from src.engine.roles.townsfolk import SlayerRole
        role = SlayerRole()

        trace_id = self._o._make_trace_id("BOTC-FLOW-SLAYER")
        await self._o._publish_event(GameEvent(
            event_type="slayer_shot_announced",
            phase=self._o.phase_manager.current_phase,
            round_number=self._o.state.round_number,
            trace_id=trace_id,
            actor=actor_id,
            target=target_id,
            visibility=Visibility.PUBLIC,
            payload={"message": f"{actor.name} 对 {target.name} 发动了猎手技能！"}
        ))

        # 执行技能
        try:
            self._o.state, events = role.execute_ability(self._o.state, actor, target_id)
            for event in events:
                # 确保 trace_id 一致
                event_dict = event.model_dump()
                event_dict["trace_id"] = trace_id
                #重新封装以通过 event_bus
                new_event = GameEvent(**event_dict)
                await self._o._publish_event(new_event)

            self._o._record_storyteller_judgement(
                "slayer_shot",
                decision="execute",
                actor=actor_id,
                target=target_id,
                trace_id=trace_id,
            )
        except Exception as e:
            logger.error(f"Slayer shot execution failed: {e}")

    async def _execute_night_actions(self, phase: GamePhase) -> None:
        steps = await self._o.storyteller_agent.build_night_order(self._o.state, phase) if self._o._should_storyteller_auto_act() else []
        self._o._log_storyteller("night_action_queue", phase=phase.value, steps=len(steps))
        self._o._record_storyteller_judgement(
            "night_queue",
            decision="queue",
            phase=phase.value,
            steps=[{"player_id": step["player_id"], "role_id": step["role_id"], "night_order": step["night_order"]} for step in steps],
        )
        self._o._current_night_steps = steps
        for i, step in enumerate(steps):
            self._o._current_night_step_index = i
            player = self._o.state.get_player(step["player_id"])
            agent = self._o.broker.agents.get(step["player_id"])
            if not player or not agent:
                continue

            self._o._mark_progress(f"night_action:{player.player_id}:{step['role_id']}")
            # [FIX] 夜晚行动顺序校验：如果玩家已死亡且不是守鸦人（ON_DEATH 触发），则跳过
            if not player.is_alive:
                role_cls = get_role_class(player.true_role_id or player.role_id)
                if role_cls:
                    role_def = role_cls.get_definition()
                    # 守鸦人等 ON_DEATH 角色允许在当晚死后行动一次
                    if role_def.ability.trigger != AbilityTrigger.ON_DEATH:
                        logger.info(f"BOTC-FLOW-NIGHT: 跳过已死亡玩家 {player.player_id} ({player.role_id}) 的行动")
                        continue
                else:
                    continue
            trace_id = self._o._make_trace_id("BOTC-ST-ACT")

            visible_state = self._o._get_agent_visible_state(player.player_id)
            if not visible_state:
                continue
            legal_context = self._o._get_agent_legal_context(player.player_id, visible_state)

            # 持久化当前待办动作，供 API 查询
            self._o._pending_night_action = {
                "player_id": player.player_id,
                "action_type": "night_action",
                "legal_context": legal_context.model_dump(mode="json"),
                "role_id": player.true_role_id or player.role_id,
            }

            trying_empty = False
            retry_count = 0
            last_error = None
            while retry_count < self._o.MAX_AGENT_RETRIES:
                retry_count += 1
                reminder_msg = ""
                if trying_empty:
                    reminder_msg = "请选择目标后再提交，不可空跳。"
                elif last_error:
                    reminder_msg = f"操作失败: {last_error}。由于规则或格式限制，请修正后重新提交。"

                await self._o._publish_event(GameEvent(
                    event_type="night_action_requested",
                    phase=phase,
                    round_number=self._o.state.round_number,
                    trace_id=trace_id,
                    actor=player.player_id,
                    visibility=Visibility.STORYTELLER_ONLY,
                    payload={
                        "role_id": player.true_role_id or player.role_id,
                        "requires_choice": True,
                        "required_targets": legal_context.required_targets,
                        "can_target_self": legal_context.can_target_self,
                        "reminder": reminder_msg if reminder_msg else None
                    },
                ))
                self._o._log_storyteller(
                    "night_action_requested",
                    phase=phase.value,
                    actor=player.player_id,
                    role=player.true_role_id or player.role_id,
                    trace_id=trace_id,
                )
                self._o._record_storyteller_judgement(
                    "night_action",
                    decision="request",
                    phase=phase.value,
                    actor=player.player_id,
                    role=player.true_role_id or player.role_id,
                    trace_id=trace_id,
                )

                try:
                    self._o._mark_progress(f"ai_action:{player.player_id}:night_action")
                    action = await self._o._timed_act(
                        agent, visible_state, "night_action",
                        legal_context=legal_context,
                        player_id=player.player_id,
                        phase=phase.value,
                        reminder=reminder_msg if reminder_msg else None,
                        retry_count=retry_count,
                        last_error=last_error,
                    )
                except Exception as exc:
                    self._o._record_recent_exception(f"night_action:{player.player_id}", exc)
                    logger.warning("夜晚行动决策失败: %s", exc)
                    action = {"action": "night_action", "target": None, "targets": [], "reasoning": f"night_action_error:{type(exc).__name__}"}

                if (
                    player
                    and (player.current_team or player.team) == Team.EVIL
                    and hasattr(agent, "build_evil_night_coordination_message")
                ):
                    try:
                        coordination_msg = await agent.build_evil_night_coordination_message(action, visible_state, legal_context)
                    except Exception:
                        coordination_msg = ""
                    if coordination_msg:
                        await self._o.handle_chat(player.player_id, coordination_msg, is_private=True)

                role_cls = get_role_class(player.true_role_id or player.role_id)

                # 鲁棒性：解析 targets 并处理可能的嵌套列表
                raw_targets = action.get("targets") or ([action["target"]] if action.get("target") else [])

                def flatten_targets(items):
                    """递归展平列表并过滤非字符串"""
                    res = []
                    if isinstance(items, (list, tuple)):
                        for item in items:
                            res.extend(flatten_targets(item))
                    elif isinstance(items, str):
                        res.append(items)
                    return res

                targets = flatten_targets(raw_targets)

                # 校验：如果不允许空选（required_targets > 0）但玩家空选了，则重试
                if legal_context.required_targets > 0 and not targets:
                    logger.warning(f"[GameLoop] 玩家 {player.player_id} ({player.role_id}) 尝试空选，重新请求。")
                    trying_empty = True
                    last_error = "必须选择目标"
                    continue

                if role_cls and action.get("action") == "night_action":
                    try:
                        primary_target = targets[0] if targets else None
                        self._o.state, events = role_cls().execute_ability(
                            self._o.state,
                            player,
                            target=primary_target,
                            targets=targets,
                        )

                        # 成功执行，发布事件并记录
                        for event in events:
                            await self._o.event_bus.publish(event)
                            if (
                                event.event_type == "night_kill"
                                and event.payload.get("redirected_from")
                            ):
                                self._o._record_storyteller_judgement(
                                    "mayor_redirect",
                                    decision="redirect",
                                    reason="mayor_night_death_redirect",
                                    actor=event.actor,
                                    original_target=event.payload.get("redirected_from"),
                                    target=event.target,
                                    killer_role=event.payload.get("killer_role"),
                                    resolved_target_role=event.payload.get("resolved_target_role"),
                                    trace_id=trace_id,
                                )

                        self._o._log_storyteller(
                            "night_action_executed",
                            phase=phase.value,
                            actor=player.player_id,
                            role=player.true_role_id or player.role_id,
                            targets=",".join(targets) if targets else "none",
                            trace_id=trace_id,
                        )
                        self._o._record_storyteller_judgement(
                            "night_action",
                            decision="execute",
                            phase=phase.value,
                            actor=player.player_id,
                            role=player.true_role_id or player.role_id,
                            targets=targets,
                            trace_id=trace_id,
                        )
                        break  # 执行成功，跳出重试循环
                    except Exception as exc:
                        logger.warning("夜晚行动无效: actor=%s role=%s targets=%s error=%s. 重新请求。",
                                       player.player_id, player.true_role_id or player.role_id, targets, exc)
                        last_error = str(exc)
                        # 执行失败（如校验不通过），继续循环重试
                        continue
                else:
                    # 如果不是目标行动或解析失败，也认为需要重试（或根据逻辑跳过，但这里我们偏向严格）
                    break

            # 清除待办
            self._o._pending_night_action = None

            await self._o._publish_event(GameEvent(
                event_type="night_action_resolved",
                phase=phase,
                round_number=self._o.state.round_number,
                trace_id=trace_id,
                actor=player.player_id,
                target=action.get("target"),
                visibility=Visibility.STORYTELLER_ONLY,
                payload={"role_id": player.true_role_id or player.role_id, "targets": targets},
            ))
            self._o._log_storyteller(
                "night_action_resolved",
                phase=phase.value,
                actor=player.player_id,
                role=player.true_role_id or player.role_id,
                targets=",".join(targets) if targets else "none",
                trace_id=trace_id,
            )
            self._o._record_storyteller_judgement(
                "night_action",
                decision="resolved",
                phase=phase.value,
                actor=player.player_id,
                role=player.true_role_id or player.role_id,
                targets=targets,
                trace_id=trace_id,
            )

    async def _distribute_night_info(self, phase: GamePhase) -> None:
        players_needing_info = [
            p for p in self._o.state.get_alive_players()
            if self._o.storyteller_agent and self._o.storyteller_agent.role_receives_storyteller_info(p.true_role_id or p.role_id)
        ]
        self._o._current_night_steps = [
            {"player_id": p.player_id, "role_id": p.true_role_id or p.role_id, "type": "info"}
            for p in players_needing_info
        ]

        async def _decide_single(player: "PlayerState") -> tuple["PlayerState", str, dict]:
            """并发执行单个角色的夜晚信息分发，返回 (player, role_id, info)。"""
            role_id = player.true_role_id or player.role_id
            info = await self._o.storyteller_agent.decide_night_info(self._o.state, player.player_id, role_id) if self._o._should_storyteller_auto_act() else {}
            if not info:
                active_role_id = role_id
                if active_role_id == "drunken" and player.perceived_role_id:
                    active_role_id = player.perceived_role_id
                role_cls = get_role_class(active_role_id)
                role = role_cls() if role_cls else None
                info = role.build_storyteller_info(self._o.state, player) if role else {}
                if info and player.ability_suppressed:
                    info = self._scramble_info(info)
            return player, role_id, info

        # 所有角色的夜晚信息并发生成
        if players_needing_info:
            results = await asyncio.gather(*(_decide_single(p) for p in players_needing_info))
            # 按原始顺序发布
            for i, (player, role_id, info) in enumerate(results):
                self._o._current_night_step_index = i
                if not info:
                    if self._o._should_storyteller_auto_act():
                        self._o._record_storyteller_judgement(
                            "night_info",
                            decision="fallback",
                            reason="storyteller_returned_empty",
                            phase=phase.value,
                            actor=player.player_id,
                            role=role_id,
                            info_type="unknown",
                        )
                    continue
                await self._o._publish_private_info(
                    phase=phase,
                    target=player.player_id,
                    trace_id=self._o._make_trace_id("BOTC-ST-INFO"),
                    payload=info,
                )
                self._o._log_storyteller(
                    "night_info_distributed",
                    phase=phase.value,
                    actor=player.player_id,
                    role=role_id,
                    info_type=info.get("type", "unknown"),
                )
                self._o._record_storyteller_judgement(
                    "night_info",
                    decision="deliver",
                    phase=phase.value,
                    actor=player.player_id,
                    role=role_id,
                    info_type=info.get("type", "unknown"),
                )
        # 移除立即重置，由 _run_day_discussion 负责在进入白天时清空
        # self._current_night_steps = None
        # self._current_night_step_index = -1

    def _scramble_info(self, info: dict) -> dict:
        scrambled = dict(info)
        info_type = scrambled.get("type", "")

        if info_type == "empath_info":
            options = [0, 1, 2]
            if "evil_count" in scrambled and scrambled["evil_count"] in options:
                options.remove(scrambled["evil_count"])
            scrambled["evil_count"] = random.choice(options) if options else 0
        elif info_type == "chef_info":
            scrambled["pairs"] = (scrambled.get("pairs", 0) + random.randint(1, 2)) % 4
        elif info_type == "fortune_teller_info":
            scrambled["has_demon"] = not scrambled.get("has_demon", False)
        elif info_type in ["investigator_info", "librarian_info", "washerwoman_info", "undertaker_info", "ravenkeeper_info"]:
            scrambled["role_seen"] = random.choice(list(get_all_role_ids()))

        return scrambled

    def _clear_transient_statuses(self) -> None:
        """清理夜晚开始时的瞬时状态（如僧侣保护、中毒、醉酒等）"""
        players = []
        for player in self._o.state.players:
            # 清理状态列表
            # 只清理 POISONED 和 PROTECTED。
            # 注意：DRUNK (醉酒) 通常是持久的 (如酒鬼角色)，不应在每晚结束时自动清除。
            statuses = tuple(status for status in player.statuses if status not in {PlayerStatus.PROTECTED, PlayerStatus.POISONED})
            if not statuses:
                statuses = (PlayerStatus.ALIVE,) if player.is_alive else (PlayerStatus.DEAD,)

            # botc 标准逻辑：中毒通常持续一个昼夜 cycle。
            # 这里我们简单清理，后续可根据具体角色技能持续时间细化。
            players.append(player.with_update(statuses=statuses))

        self._o.state = self._o.state.with_update(players=tuple(players))
        self._o._log_storyteller("transient_statuses_cleared")
