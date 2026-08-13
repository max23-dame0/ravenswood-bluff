"""
OpenAI LLM 后端实现

通过 OpenAI API（兼容 GPT-4o、GPT-4o-mini 等）调用 LLM。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import uuid
from typing import Any

from src.debug.game_debug_logger import game_debug_logger
from src.llm.base_backend import (
    LLMBackend,
    LLMResponse,
    Message,
    ToolCall,
    ToolDef,
)

logger = logging.getLogger(__name__)


class OpenAIBackend(LLMBackend):
    """
    OpenAI API 后端

    使用 openai Python SDK 调用 GPT 系列模型。
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        from dotenv import load_dotenv

        load_dotenv()  # Load variables from .env if present

        self._model = os.getenv("DEFAULT_MODEL") or model
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self._embedding_api_key = os.getenv("EMBEDDING_API_KEY") or self._api_key
        self._embedding_base_url = os.getenv("EMBEDDING_BASE_URL") or self._base_url
        self._embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self._request_timeout_seconds = float(os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "300"))
        self._client = None
        self._embedding_client = None
        self._embeddings_disabled = False
        self._embeddings_disable_reason: str | None = None

    def _get_client(self):
        """懒加载 OpenAI 客户端"""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required. Install with: pip install openai"
                ) from None
            kwargs = {}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = AsyncOpenAI(**kwargs, timeout=self._request_timeout_seconds)
        return self._client

    def _get_embedding_client(self):
        """懒加载 Embeddings 客户端，允许与聊天模型分离配置。"""
        if self._embedding_client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError:
                raise ImportError(
                    "openai package is required. Install with: pip install openai"
                ) from None
            kwargs = {}
            if self._embedding_api_key:
                kwargs["api_key"] = self._embedding_api_key
            if self._embedding_base_url:
                kwargs["base_url"] = self._embedding_base_url
            self._embedding_client = AsyncOpenAI(**kwargs)
        return self._embedding_client

    async def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: list[ToolDef] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """通过 OpenAI API 生成响应"""
        client = self._get_client()

        # 构建消息列表
        api_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            api_msg = {"role": msg.role, "content": msg.content}
            if msg.name:
                api_msg["name"] = msg.name
            if msg.tool_call_id:
                api_msg["tool_call_id"] = msg.tool_call_id
            api_messages.append(api_msg)

        # 构建 API 参数
        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        # 思考模式 / 推理强度透传（OpenAI 兼容 extra_body）
        if thinking in {"enabled", "disabled"}:
            kwargs.setdefault("extra_body", {})["thinking"] = {"type": thinking}
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        # 构建工具定义
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]

        # 调用 API
        request_id = uuid.uuid4().hex[:12]
        game_debug_logger.log_llm_request(
            request_id=request_id,
            model=self._model,
            base_url=self._base_url,
            system_prompt=system_prompt,
            messages=api_messages,
            parameters={
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tools": [tool.name for tool in tools] if tools else [],
            },
        )
        logger.info(f"Sending LLM request to {self._model} (base_url: {self._base_url})")
        try:
            response = await client.chat.completions.create(
                **kwargs, timeout=self._request_timeout_seconds
            )
            logger.info("Received LLM response successfully.")
        except Exception as e:
            game_debug_logger.log_llm_response(
                request_id=request_id,
                model=self._model,
                content=None,
                tool_calls=[],
                usage={},
                finish_reason=None,
                error=f"{type(e).__name__}: {e}",
            )
            logger.error(f"OpenAI API error: {type(e).__name__}: {e}")
            raise

        # 解析响应
        choice = response.choices[0]
        message = choice.message
        content = message.content
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    parts.append(str(part.get("text") or part.get("content") or ""))
                else:
                    parts.append(
                        str(getattr(part, "text", "") or getattr(part, "content", "") or "")
                    )
            content = "".join(parts).strip()
        if not str(content or "").strip():
            diagnostic_fields = {
                "finish_reason": getattr(choice, "finish_reason", None),
                "model": getattr(response, "model", self._model),
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
                "tool_call_count": len(message.tool_calls or []),
                "refusal": str(getattr(message, "refusal", "") or "")[:300],
                "reasoning_content_preview": str(getattr(message, "reasoning_content", "") or "")[
                    :300
                ],
                "reasoning_preview": str(getattr(message, "reasoning", "") or "")[:300],
            }
            # 工具调用路径（finish_reason=tool_calls）content 为空是预期现象：
            # 动作参数从 tool_calls[].arguments 解析，此时不应作为异常告警（PLN-038 阶段 A）。
            if getattr(choice, "finish_reason", None) == "tool_calls" and (
                message.tool_calls or []
            ):
                logger.debug(
                    "LLM response content is empty (tool_calls path): %s", diagnostic_fields
                )
            else:
                logger.warning("LLM response content is empty: %s", diagnostic_fields)
        else:
            diagnostic_fields = {}

        # 解析 tool calls
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": tc.function.arguments}
                tool_calls.append(
                    ToolCall(
                        tool_call_id=tc.id,
                        function_name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # Scavenge 兜底（2026-08-05）：DeepSeek 开启 thinking 后偶发把 tool call JSON
        # 写进 reasoning_content/thinking 块或 content 文本而非标准 tool_calls 字段，
        # 标准字段为空时尝试从文本中正则恢复（社区已知适配问题）。
        if not tool_calls:
            scavenge_text = str(getattr(message, "reasoning_content", "") or "")
            if not scavenge_text:
                scavenge_text = str(content or "")
            if scavenge_text:
                try:
                    from src.agents.tools.action_tool_registry import GameActionToolRegistry
                except ImportError:  # pragma: no cover - 防御性
                    GameActionToolRegistry = None  # type: ignore[assignment]
                if GameActionToolRegistry is not None:
                    scavenged = self._scavenge_tool_calls_from_text(
                        scavenge_text, GameActionToolRegistry.known_tool_names()
                    )
                    if scavenged:
                        tool_calls = scavenged
                        logger.info(
                            "[Scavenge] 从 thinking/content 文本恢复 %d 个 tool call",
                            len(scavenged),
                        )

        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        if response.usage:
            cached_hit = getattr(response.usage, "prompt_cache_hit_tokens", None)
            cached_miss = getattr(response.usage, "prompt_cache_miss_tokens", None)
            usage["prompt_cache_hit_tokens"] = cached_hit if cached_hit is not None else 0
            usage["prompt_cache_miss_tokens"] = cached_miss if cached_miss is not None else 0
            completion_details = getattr(response.usage, "completion_tokens_details", None)
            reasoning_tokens = getattr(completion_details, "reasoning_tokens", None)
            usage["reasoning_tokens"] = reasoning_tokens if reasoning_tokens is not None else 0
        game_debug_logger.log_llm_response(
            request_id=request_id,
            model=response.model,
            content=content,
            tool_calls=[
                tc.model_dump() if hasattr(tc, "model_dump") else dict(tc) for tc in tool_calls
            ],
            usage=usage,
            finish_reason=getattr(choice, "finish_reason", None),
            diagnostics=diagnostic_fields,
        )

        reasoning_content = str(getattr(message, "reasoning_content", "") or "").strip()
        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            model=response.model,
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def get_model_name(self) -> str:
        return self._model

    @staticmethod
    def _extract_json_objects(text: str) -> list[Any]:
        """用平衡括号扫描提取文本中的顶层 JSON 对象（跳过字符串内的括号/转义）。"""
        results: list[Any] = []
        stack: list[str] = []
        start: int | None = None
        in_str = False
        escape = False
        for i, ch in enumerate(text):
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                if not stack:
                    start = i
                stack.append(ch)
            elif ch == "}" and stack:
                stack.pop()
                if not stack and start is not None:
                    candidate = text[start : i + 1]
                    with contextlib.suppress(json.JSONDecodeError, ValueError):
                        results.append(json.loads(candidate))
                    start = None
        return results

    @staticmethod
    def _scavenge_tool_calls_from_text(text: str, known_names: set[str]) -> list[ToolCall]:
        """从 thinking/content 文本中恢复被写成 JSON 的 tool call。

        支持两种形态：
        - 标准：{"id": "...", "function": {"name": "speak", "arguments": "{...}"}}
        - 简化：{"name": "speak", "arguments": {"content": "..."}}
        arguments 既可能是字符串（再 json.loads）也可能是对象。
        """
        tool_calls: list[ToolCall] = []
        if not text:
            return tool_calls
        for candidate in OpenAIBackend._extract_json_objects(text):
            if not isinstance(candidate, dict):
                continue
            name: Any = None
            arguments: Any = None
            func = candidate.get("function")
            if isinstance(func, dict):
                name = func.get("name")
                arguments = func.get("arguments")
            else:
                name = candidate.get("name")
                arguments = candidate.get("arguments")
            if not isinstance(name, str) or name not in known_names:
                continue
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except (json.JSONDecodeError, ValueError):
                    arguments = {"raw": arguments}
            if not isinstance(arguments, dict):
                continue
            tool_calls.append(
                ToolCall(
                    tool_call_id=str(
                        candidate.get("id") or candidate.get("tool_call_id") or "scavenged"
                    ),
                    function_name=name,
                    arguments=arguments,
                )
            )
        return tool_calls

    @staticmethod
    def _is_embedding_unsupported_error(error: Exception) -> bool:
        status_code = getattr(error, "status_code", None)
        if status_code == 404:
            return True

        message = str(error).lower()
        unsupported_markers = (
            "404",
            "not found",
            "embeddings",
            "does not exist",
            "unsupported",
        )
        return "embedding" in message and any(marker in message for marker in unsupported_markers)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """通过 OpenAI API 获取向量嵌入"""
        if not texts:
            return []

        if self._embeddings_disabled:
            return []

        client = self._get_embedding_client()
        logger.info(
            "Generating embeddings for %s texts using %s (base_url=%s)",
            len(texts),
            self._embedding_model,
            self._embedding_base_url,
        )
        try:
            response = await client.embeddings.create(
                model=self._embedding_model, input=texts, timeout=15.0
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            if self._is_embedding_unsupported_error(e):
                self._embeddings_disabled = True
                self._embeddings_disable_reason = str(e)
                logger.warning(
                    "Embeddings endpoint/model is unavailable for base_url=%s model=%s; "
                    "disabling embeddings and continuing without vector retrieval. reason=%s",
                    self._embedding_base_url,
                    self._embedding_model,
                    e,
                )
                return []

            logger.error(f"OpenAI Embeddings API error: {e}")
            return []

    def get_embedding_status(self) -> dict[str, object]:
        """返回 embeddings 通道的轻量状态，供数据快照与调试使用。"""
        return {
            "enabled": not self._embeddings_disabled,
            "model": self._embedding_model,
            "base_url": self._embedding_base_url,
            "disabled_reason": self._embeddings_disable_reason,
        }
