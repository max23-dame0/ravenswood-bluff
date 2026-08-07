"""MockBackend action_type 提取修复测试（PLN-040 T3.5）。

根因：PLN-039 三层前缀把"当前需要执行的动作类型"从 system 移到 user 末条，
MockBackend._extract_action_type 只扫 system_prompt → 提取失败 → 所有动作返回
默认 speak 决策 → normalize_decision 判非法 → vote/nomination 100% fallback。

修复：_extract_action_type 同时扫描 system + messages 拼接文本。
"""

from __future__ import annotations

import pytest

from src.llm.base_backend import Message
from src.llm.mock_backend import MockBackend


async def _mock_respond(action_type: str) -> dict:
    backend = MockBackend()
    system = "【全局静态层】规则...【玩家名单】p1 p2 p3"
    messages = [
        Message(role="user", content="稳定的跨局记忆。"),
        Message(role="user", content=f"当前需要执行的动作类型：{action_type}，请返回 JSON"),
    ]
    import json

    resp = await backend.generate(system_prompt=system, messages=messages)
    return json.loads(resp.content)


@pytest.mark.asyncio
async def test_extract_action_type_from_messages() -> None:
    """从 messages 中能提取到 action_type（修复核心）。"""
    backend = MockBackend()
    system = "【全局静态层】"
    messages = [Message(role="user", content="当前需要执行的动作类型：vote，请返回 JSON")]
    prompt_all = system + "\n" + "".join(m.content for m in messages)
    assert backend._extract_action_type(prompt_all) == "vote"


@pytest.mark.asyncio
async def test_vote_returns_decision_field() -> None:
    """vote 请求返回 decision 字段（修复前是 speak 决策导致 invalid_vote_decision）。"""
    decision = await _mock_respond("vote")
    assert decision["action"] == "vote"
    assert decision["decision"] is True


@pytest.mark.asyncio
async def test_nomination_intent_returns_nominate_or_none() -> None:
    """nomination_intent 返回 nominate（带 target）或 none，不再返回 speak。"""
    decision = await _mock_respond("nomination_intent")
    assert decision["action"] in {"nominate", "none"}
    if decision["action"] == "nominate":
        assert decision.get("target") in {"p1", "p2", "p3"}


@pytest.mark.asyncio
async def test_night_action_returns_night_action() -> None:
    """night_action 请求返回 night_action（修复前可能返回默认 speak）。"""
    decision = await _mock_respond("night_action")
    assert decision["action"] == "night_action"


@pytest.mark.asyncio
async def test_speak_still_returns_speak() -> None:
    """speak 请求行为不变（返回 speak）。"""
    decision = await _mock_respond("speak")
    assert decision["action"] == "speak"


@pytest.mark.asyncio
async def test_defense_speech_returns_speak() -> None:
    """defense_speech 请求返回 speak（辩解文案）。"""
    decision = await _mock_respond("defense_speech")
    assert decision["action"] == "speak"
