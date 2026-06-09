"""
Mock LLM 后端实现

用于在没有 API Key 的环境下进行逻辑模拟与自动化测试。
"""

from __future__ import annotations
import json
import os
import random
import re
from typing import Optional

from src.llm.base_backend import (
    LLMBackend,
    LLMResponse,
    Message,
    ToolDef,
)

class MockBackend(LLMBackend):
    """
    Mock 后端
    根据 action_type 返回预定义的或随机的行为。
    """

    def __init__(self) -> None:
        self._response_queue: list[str] = []

    def set_response(self, content: str) -> None:
        """预设下一次 generate 的返回内容"""
        self._response_queue.append(content)

    def _extract_player_ids(self, text: str) -> list[str]:
        matches = re.findall(r"\b([aph]\d+)\b", text.lower())
        seen: list[str] = []
        for match in matches:
            if match not in seen:
                seen.append(match)
        return seen

    def _extract_action_type(self, text: str) -> Optional[str]:
        match = re.search(r"当前需要执行的动作类型[:：]\s*([a-z_]+)", text.lower())
        return match.group(1) if match else None

    async def generate(
        self,
        system_prompt: str,
        messages: list[Message],
        tools: Optional[list[ToolDef]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        
        # W3-C: 优先使用预设回复
        if self._response_queue:
            content = self._response_queue.pop(0)
            return LLMResponse(
                content=content,
                tool_calls=[],
                model="mock-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            )
        
        # 默认响应框架
        decision = {
            "action": "speak",
            "content": "我是一个 Mock AI。",
            "tone": "calm",
            "reasoning": "保持流程畅通。"
        }
        
        # 根据系统提示词中的关键词判定当前请求的行为类型
        prompt_lower = system_prompt.lower()
        player_ids = self._extract_player_ids(system_prompt)
        action_type = self._extract_action_type(system_prompt)

        # Check for evil night coordination message prompts (plain text)
        if "邪恶频道" in prompt_lower or "coordination" in prompt_lower or "协调" in prompt_lower:
            if "爪牙" in prompt_lower or "minion" in prompt_lower:
                content = "收到恶魔的分配，我白天会配合这个方向进行伪装发言，并引导投票和提名方向。"
            else:
                content = "我来分配一下首夜的伪装：我准备跳洗衣妇，队友A跳共情者，队友B跳厨师。白天我们互相回应，把逻辑理顺，吸引好人注意力。"
            return LLMResponse(
                content=content,
                tool_calls=[],
                model="mock-model",
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            )

        if action_type == "night_action":
            decision["action"] = "night_action"
            decision["target"] = player_ids[1] if len(player_ids) > 1 else (player_ids[0] if player_ids else None)
            decision["reasoning"] = "夜晚行动模拟。"
        elif action_type in {"nominate", "nomination_intent"}:
            possible_targets = player_ids[1:] if len(player_ids) > 1 else player_ids
            if random.random() < 0.7 and possible_targets:
                decision["action"] = "nominate"
                decision["target"] = possible_targets[0]
                decision["reasoning"] = "我想推动一次有效提名。"
            else:
                decision["action"] = "none"
                decision["reasoning"] = "目前没有怀疑对象。"
        elif action_type == "defense_speech":
            decision["action"] = "speak"
            decision["content"] = random.choice([
                "我是好人，请不要处决我！",
                "我能理解大家的怀疑，但我真的是好人阵营的。",
                "如果你们投我出去，明天会后悔的。",
                "我有我的理由，给我一点时间解释。",
            ])
            decision["reasoning"] = "辩解中。"
        elif action_type == "vote":
            decision["action"] = "vote"
            decision["decision"] = True
            decision["reasoning"] = "赞成处决可疑人员。"
        elif action_type == "speak":
            decision["action"] = "speak"
            decision["content"] = random.choice([
                "今天天气不错，大家有什么线索吗？我先表态，我会重点关注票型走向。",
                "我觉得我们需要仔细分析一下目前的信息，特别是发言中的逻辑矛盾。",
                "我有一些想法，但还需要再观察一下。不过我更想先听听提名环节怎么说。",
                "场上局势比较复杂，我先听听大家怎么说，然后再决定我的投票方向。",
                "我对目前的讨论有几个疑点想提出来，尤其是关于线索的逻辑链。",
                "大家的发言我都看了，有些地方值得深挖，我会在投票前把方向理清楚。",
                "我注意到有几个人的逻辑不太一致，我更想看看他们后续怎么解释。",
                "目前我比较关注的是票型走向，这能帮我判断谁在带节奏。",
                "我觉得我们应该把注意力集中在几个关键节点上，线索指向的方向很重要。",
                "有些发言我觉得值得再推敲一下，特别是关于立场变化的部分。",
                "今天的信息量比较大，我需要消化一下。不过我对发言方向有些初步判断。",
                "我对场上某些人的态度变化有些疑问，尤其是他前后发言的逻辑。",
                "有几个人的立场我觉得需要再确认，线索对不上的话问题就大了。",
                "目前的信息还不够下定论，我再等等看，但提名环节我会积极投票。",
                "我觉得有人在带节奏，但我不确定是谁。我会追踪发言中的矛盾点。",
                "从目前的发言来看，有些矛盾点值得追，我更想看看票型怎么走。",
                "我的直觉告诉我事情没那么简单，线索指向的方向需要进一步确认。",
                "我想看看接下来的提名环节会怎么发展，然后再决定我的投票方向。",
                "有些人的解释我觉得说服力不够，我会在投票时表达我的立场。",
                "今天的讨论有几个方向可以继续追，我会重点关注逻辑链最完整的那条线。",
            ])
        elif "night_action" in prompt_lower:
            decision["action"] = "night_action"
            decision["target"] = player_ids[1] if len(player_ids) > 1 else (player_ids[0] if player_ids else None)
            decision["reasoning"] = "夜晚行动模拟。"
            
        content = json.dumps(decision, ensure_ascii=False)

        return LLMResponse(
            content=content,
            tool_calls=[],
            model="mock-model",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )

    def get_model_name(self) -> str:
        return "mock-model"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Mock implementation of get_embeddings."""
        dimension = int(os.getenv("EMBEDDING_DIMENSION", "1536"))
        return [[0.0] * dimension for _ in texts]
