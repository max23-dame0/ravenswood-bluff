"""ClaimExtractor — async LLM-based claim extraction from speech events."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Any

from src.state.game_state import GameEvent, Visibility

if TYPE_CHECKING:
    from src.orchestrator.game_loop import GameOrchestrator

logger = logging.getLogger(__name__)


class ClaimExtractor:
    """Async claim extraction from speech events, extracted from GameOrchestrator."""

    def __init__(self, orchestrator: GameOrchestrator) -> None:
        self._o = orchestrator

    def _schedule_claim_extraction(self, event: GameEvent) -> None:
        content = event.payload.get("content", "")
        if not content:
            return
        task = asyncio.create_task(self._extract_claims_background(event))
        self._o._claim_extraction_tasks.add(task)
        task.add_done_callback(self._o._claim_extraction_tasks.discard)

    async def _extract_claims_background(self, event: GameEvent) -> None:
        claims = await self._extract_claims_via_llm(event)
        if not claims:
            return
        claim_event = GameEvent(
            event_type="claims_extracted",
            phase=event.phase,
            round_number=event.round_number,
            trace_id=self._o._make_trace_id("BOTC-CLAIMS"),
            actor=event.actor,
            visibility=Visibility.STORYTELLER_ONLY,
            payload={
                "source_event_id": event.event_id,
                "claims": claims,
                "async": True,
            },
        )
        self._o.state = self._o.state.with_event(claim_event)
        await self._o.event_bus.publish(claim_event)

    async def _extract_claims_via_llm(self, event: GameEvent) -> list[dict[str, Any]]:
        from src.llm.openai_backend import OpenAIBackend
        from src.llm.base_backend import Message

        backend = self._o.default_agent_backend or (getattr(self._o.storyteller_agent, "backend", None)) or OpenAIBackend()
        content = event.payload.get("content", "")
        if not content:
            return []

        prompt = f"""分析以下《血染钟楼》对局发言，提取发言者({event.actor})对身份的声明、否认或指控。
可用角色(Role ID)：washerwoman, librarian, investigator, chef, empath, fortune_teller, undertaker, monk, ravenkeeper, virgin, slayer, soldier, mayor, butler, drunken, recluse, saint, poisoner, spy, scarlet_woman, baron, imp。
注意：
1. self_claim: 发言者明确以第一人称声明自己的身份。例："我是市长"，"我跳调查员"，"我明牌女巫"。
   排除以下情况（不算self_claim）：
   - 假设/条件："如果我是市长"，"要是我是毒师"，"就算我是恶魔"
   - 转述他人说自己："你说我是男爵"，"P1说我是间谍"，"他觉得我是恶魔"
   - 讨论/质疑角色存在："要是真有男爵"，"根本没有男爵"，"男爵存在吗"
   - 否认语境中的提及："我什么时候说我是男爵"
2. denial: 发言者否认自己是某角色。例："我不是毒师"，"我没跳过市长"。
3. accusation: 发言者指控他人是某角色。例："我觉得他(P2)是毒师"，"7号像间谍"。
4. relay: 发言者转述他人对第三方的身份声明。例："P2说他是调查员"，"P1声称3号是市长"。
发言内容："{content}"

必须以严格的 JSON 对象格式返回，包含一个 "claims" 数组。格式示例：
{{
    "claims": [
        {{"role_id": "mayor", "claim_type": "self_claim", "subject_player_ids": ["{event.actor}"]}}
    ]
}}
如果未提及任何角色或没有明确声明，返回 {{"claims": []}}。
"""
        try:
            response = await asyncio.wait_for(
                backend.generate("", [Message(role="user", content=prompt)]),
                timeout=float(os.getenv("CLAIM_EXTRACTION_TIMEOUT_SECONDS", "2.0")),
            )
            text = (response.content or "").strip()
            if not text:
                return []
            data = json.loads(text)
            return data.get("claims", [])
        except Exception as e:
            key = type(e).__name__
            count = self._o._claim_extraction_failures.get(key, 0) + 1
            self._o._claim_extraction_failures[key] = count
            if count <= 3 or count in {10, 25, 50}:
                logger.debug("LLM 提取身份声明失败(%s/%s)，已异步跳过: %s", key, count, e)
            return []
