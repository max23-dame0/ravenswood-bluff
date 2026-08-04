"""LLM 策略透传与 usage 解析扩展测试（PLN-037 P0-4.1 / P2-4.8）。

覆盖：
- OpenAIBackend.generate 透传 thinking / reasoning_effort
- usage 扩展字段（prompt_cache_hit_tokens / prompt_cache_miss_tokens / reasoning_tokens）解析
- MockBackend.generate 签名兼容 thinking / reasoning_effort
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from src.llm.base_backend import Message, ToolDef
from src.llm.mock_backend import MockBackend
from src.llm.openai_backend import OpenAIBackend


class _EchoChatClient:
    def __init__(self) -> None:
        self.instances = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    async def create(self, **kwargs):
        self.instances.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=20,
                total_tokens=120,
                prompt_cache_hit_tokens=60,
                prompt_cache_miss_tokens=40,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=5),
            ),
            model="dummy",
        )


@pytest.mark.asyncio
async def test_openai_generate_passes_thinking_and_reasoning_effort(monkeypatch) -> None:
    _EchoChatClient.instances = []
    client = _EchoChatClient()
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(AsyncOpenAI=lambda **kwargs: SimpleNamespace(**client.__dict__)),
    )
    backend = OpenAIBackend(model="dummy")
    backend._client = client  # 直接用 echo client 替换

    await backend.generate(
        "sys",
        [Message(role="user", content="hi")],
        thinking="enabled",
        reasoning_effort="low",
        max_tokens=120,
    )

    call = client.instances[-1]
    assert call["extra_body"]["thinking"] == {"type": "enabled"}
    assert call["reasoning_effort"] == "low"
    assert call["max_tokens"] == 120


@pytest.mark.asyncio
async def test_openai_generate_ignores_thinking_when_invalid() -> None:
    client = _EchoChatClient()
    backend = OpenAIBackend(model="dummy")
    backend._client = client

    await backend.generate(
        "sys",
        [Message(role="user", content="hi")],
        thinking="weird-value",
        reasoning_effort=None,
    )

    call = client.instances[-1]
    assert "extra_body" not in call or "thinking" not in call["extra_body"]
    assert "reasoning_effort" not in call


@pytest.mark.asyncio
async def test_openai_generate_parses_extended_usage(monkeypatch) -> None:
    client = _EchoChatClient()
    backend = OpenAIBackend(model="dummy")
    backend._client = client

    response = await backend.generate("sys", [Message(role="user", content="hi")])

    usage = response.usage
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 120
    assert usage["prompt_cache_hit_tokens"] == 60
    assert usage["prompt_cache_miss_tokens"] == 40
    assert usage["reasoning_tokens"] == 5


@pytest.mark.asyncio
async def test_openai_generate_passes_tools() -> None:
    client = _EchoChatClient()
    backend = OpenAIBackend(model="dummy")
    backend._client = client

    await backend.generate(
        "sys",
        [Message(role="user", content="hi")],
        tools=[ToolDef(name="speak", description="d", parameters={"type": "object"})],
    )

    call = client.instances[-1]
    assert call["tools"][0]["function"]["name"] == "speak"


@pytest.mark.asyncio
async def test_mock_backend_accepts_thinking_and_reasoning_effort() -> None:
    backend = MockBackend()
    response = await backend.generate(
        "sys",
        [Message(role="user", content="请返回 speak 决策")],
        thinking="disabled",
        reasoning_effort=None,
        max_tokens=200,
    )
    assert response.content is not None
