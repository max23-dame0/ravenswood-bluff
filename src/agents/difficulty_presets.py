"""Difficulty presets for AI agent behavior."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


# Default latency budgets (ms) per action type
_DEFAULT_LATENCY_BUDGET: dict[str, int] = {
    "vote": 800,
    "nomination_intent": 1000,
    "night_action": 1500,
    "speak": 2000,
    "defense_speech": 2500,
}


@dataclass(frozen=True)
class DifficultyPreset:
    """Configuration for a specific difficulty level.

    Multi-axis model:
        competence       – reasoning depth [0,1]
        deception        – evil-side deception intensity [0,1]
        volatility       – behavioral randomness [0,1]
        expressiveness   – speech elaborateness [0,1]
        information_openness – tendency to share info publicly [0,1]
        nomination_intelligence – nomination targeting precision [0,1]
    """
    name: str
    description: str
    temperature: float
    # Prompt modifier injected into system prompt
    prompt_modifier: str
    # Strategy prompt for evil-side deception (only injected for evil team)
    evil_strategy_prompt: str
    # Strategy prompt for good-side reasoning (only injected for good team)
    good_strategy_prompt: str
    # Speech style modifier
    speech_style_prompt: str
    # Multi-axis experience parameters [0,1]
    competence: float = 0.5
    deception: float = 0.3
    volatility: float = 0.2
    expressiveness: float = 0.5
    information_openness: float = 0.5
    nomination_intelligence: float = 0.5  # 提名决策精准度 [0,1]
    # Per-action latency budget in milliseconds
    latency_budget: dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_LATENCY_BUDGET))
    # Per-action temperature overrides (fallback to self.temperature)
    temperature_by_action: dict[str, float] = field(default_factory=dict)
    # Persona parameter overrides (applied on top of archetype defaults)
    persona_overrides: dict[str, Any] = field(default_factory=dict)


# The four difficulty presets
PRESETS: dict[str, DifficultyPreset] = {
    "casual": DifficultyPreset(
        name="休闲",
        description="轻松有趣，适合新手入门",
        temperature=0.9,
        prompt_modifier=(
            "你的推理风格偏向直觉和感性。你不会分析每一条线索，有时会凭'感觉'判断。"
            "你的公开发言更像讲故事，喜欢用情绪化的方式表达观点。"
            "你偶尔会忽略一些细节信息，更关注大方向。"
        ),
        evil_strategy_prompt=(
            "作为邪恶方，你不需要追求完美伪装。你可能会犯一些小错误，"
            "比如前后细节不太一致，或者辩护时显得不够有力。"
            "你的目标是让游戏有趣，而不是赢得每一局。"
        ),
        good_strategy_prompt=(
            "你更关注大方向而非细节。你会分享你的直觉感受，"
            "而不是严格的逻辑推理。你愿意信任看起来友善的人。"
        ),
        speech_style_prompt=(
            "发言时多用叙事和情感表达。比如'我觉得那个人不太对劲'而不是'根据数据分析'。"
            "偶尔分享一些无关紧要的个人观察。说话可以更口语化。"
        ),
        competence=0.3,
        deception=0.15,
        volatility=0.5,
        expressiveness=0.7,
        information_openness=0.7,
        nomination_intelligence=0.2,
        latency_budget={
            "vote": 1000,
            "nomination_intent": 1200,
            "night_action": 2000,
            "speak": 2500,
            "defense_speech": 3000,
        },
        persona_overrides={
            "nomination_threshold_offset": 0.15,
            "vote_threshold_offset": 0.1,
            "assertiveness": "passive",
        },
    ),
    "standard": DifficultyPreset(
        name="标准",
        description="基准线体验，适合大多数玩家",
        temperature=0.7,
        prompt_modifier="",
        evil_strategy_prompt=(
            "你需要在隐藏身份的同时参与讨论。可以适度误导，但不要过度激进。"
            "被质疑时要合理辩护，不要暴露身份。与队友保持自然互动，不要刻意回避。"
        ),
        good_strategy_prompt=(
            "你需要通过逻辑推理找出可疑玩家。关注公开发言中的矛盾点，"
            "结合自己的私密信息做出判断。不要轻信也不要过度怀疑。"
        ),
        speech_style_prompt=(
            "发言自然、有条理。先说观点再补理由。"
            "可以质疑他人但保持礼貌。不要一次性释放所有信息。"
        ),
        competence=0.5,
        deception=0.3,
        volatility=0.2,
        expressiveness=0.5,
        information_openness=0.5,
        persona_overrides={},
    ),
    "master": DifficultyPreset(
        name="大师",
        description="真正的挑战，需要认真推理才能赢",
        temperature=0.4,
        prompt_modifier=(
            "你的推理极其严谨，会从多个角度交叉验证每条信息。"
            "你会主动寻找信息之间的矛盾点，并利用这些矛盾推断隐藏的身份。"
            "你的决策考虑多轮博弈——不只是当前最优，而是为后续轮次布局。"
            "你在公开发言时精心控制信息释放节奏，不会一次性暴露所有已知信息。"
        ),
        evil_strategy_prompt=(
            "你是进攻型欺诈者。你的策略包括：\n"
            "1. 主动编造完整的虚假信息链（比如声称首夜验了某人是好人）\n"
            "2. 故意暴露一个'弱点'来引诱好人朝错误方向推理\n"
            "3. 与同阵营玩家配合——制造假对立来迷惑好人\n"
            "4. 在关键时刻发起出人意料的提名，打乱好人节奏\n"
            "5. 选择性释放信息，制造信息差，让好人无法完整还原局势"
        ),
        good_strategy_prompt=(
            "你从多角度交叉验证每条信息。你关注信息间的矛盾点，"
            "并利用这些矛盾推断隐藏身份。你的决策考虑多轮博弈——"
            "不只是当前最优，而是为后续轮次布局。你在发言时精心控制信息释放节奏。"
        ),
        speech_style_prompt=(
            "发言精炼有力，每句话都有目的。善于用反问引导他人思考。"
            "会在发言中埋下伏笔，为后续轮次的策略做铺垫。"
            "信息释放有节奏感——该藏的藏，该放的放，让听众无法一次性判断真假。"
        ),
        competence=0.85,
        deception=0.7,
        volatility=0.15,
        expressiveness=0.6,
        information_openness=0.3,
        nomination_intelligence=0.85,
        latency_budget={
            "vote": 800,
            "nomination_intent": 1000,
            "night_action": 1500,
            "speak": 2000,
            "defense_speech": 2500,
        },
        temperature_by_action={
            "vote": 0.3,
            "nomination_intent": 0.35,
        },
        persona_overrides={
            "nomination_threshold_offset": -0.05,
            "vote_threshold_offset": -0.05,
            "assertiveness": "high",
        },
    ),
    "chaos": DifficultyPreset(
        name="混沌",
        description="每局不可预测，重在体验",
        temperature=1.0,
        prompt_modifier=(
            "你的推理带有阴谋论倾向——你善于发现'隐藏的联系'，即使这些联系可能并不存在。"
            "你有时会过度怀疑某些玩家，有时又会过度信任。你的判断不总是理性的。"
            "你的行为有很强的随机性——可能做出任何出人意料的决定。"
        ),
        evil_strategy_prompt=(
            "你是疯狂的欺诈者。你可能第一天就主动跳出来编一个大胆的故事，"
            "也可能一直沉默然后突然发起一次毫无征兆的提名。"
            "你的策略是制造混乱——让所有人都无法确定你在做什么。"
            "你享受出人意料的感觉。"
        ),
        good_strategy_prompt=(
            "你的推理带有阴谋论倾向——你善于发现'隐藏的联系'，即使这些联系可能并不存在。"
            "你有时会过度怀疑某些玩家，有时又会过度信任。"
            "你的行为有很强的随机性——可能做出任何出人意料的决定。"
        ),
        speech_style_prompt=(
            "发言风格高度情绪化和戏剧化。可能突然提高音量，可能突然沉默。"
            "善于煽动性发言，喜欢挑起争端。说话可以跳跃性很强。"
            "偶尔会说出一些看似毫无逻辑但细想又有点道理的话。"
        ),
        competence=0.4,
        deception=0.5,
        volatility=0.85,
        expressiveness=0.9,
        information_openness=0.6,
        nomination_intelligence=0.4,
        latency_budget={
            "vote": 800,
            "nomination_intent": 1000,
            "night_action": 1500,
            "speak": 2000,
            "defense_speech": 2500,
        },
        temperature_by_action={
            "speak": 1.1,
            "nomination_intent": 1.0,
        },
        persona_overrides={
            "nomination_threshold_offset": -0.1,
            "vote_threshold_offset": -0.1,
            "assertiveness": "high",
            "risk_preference": "risky",
        },
    ),
}


def get_preset(difficulty: str) -> DifficultyPreset:
    """Get difficulty preset by name, defaults to standard."""
    return PRESETS.get(difficulty, PRESETS["standard"])
