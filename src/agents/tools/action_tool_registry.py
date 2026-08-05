"""
行动工具注册表 (GameActionToolRegistry)

将 AI 玩家的行动（speak / vote / nominate / night_action / defense_speech /
slayer_shot）标准化为 LLM tool calling 的工具定义（ToolDef）。

设计目标（见 `docs/plans/agent-native-redesign-plan.md` PLN-038 阶段 A）：
`act()` 以工具调用为主导路径，JSON 解析作为 fallback。

工具 schema 是稳定字符串，可作公共缓存前缀（协同 PLN-037 P1）。
"""

from __future__ import annotations

from typing import Any

from src.llm.base_backend import ToolDef

# 动作 → 工具描述映射（集中维护，供注册与调试）
_ACTION_TOOL_DESCRIPTIONS: dict[str, str] = {
    "speak": "在白天讨论环节向所有玩家发出你的公开发言（不能泄露你的私密身份与队友信息）。",
    "defense_speech": "你正在被提名，向全场发出你的辩解发言。",
    "vote": "对当前提名进行处决投票。",
    "nominate": "决定是否提名一名玩家为嫌疑人（跳过则选 none）。",
    "nomination_intent": "表达你今天是否打算提名某名玩家。",
    "night_action": "夜晚行动：选择你今晚的行动目标（无目标可选时 target 可为 null）。",
    "slayer_shot": "白天主动发动猎手技能：向一名玩家开枪。",
    "private_message": "私下给某名玩家发一条消息（仅该玩家可见）。",
}

_TONE_ENUM = ["calm", "passionate", "accusatory", "defensive", "hesitant"]


def _reasoning_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "description": "你的内部推理（不公开）。≤30 字，只写关键结论。",
    }


class GameActionToolRegistry:
    """行动工具注册表：提供各动作对应的 ToolDef 列表。"""

    # 每个动作的主工具参数 schema（参数名与旧 JSON decision 键一致，便于归一化）
    _TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
        "speak": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "你的中文发言内容（口语化，不要照抄记忆，不要复述人尽皆知的公开信息）。",
                },
                "tone": {"type": "string", "enum": _TONE_ENUM, "description": "发言语气。"},
                "reasoning": _reasoning_schema(),
            },
            "required": ["content", "tone"],
        },
        "defense_speech": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "你的中文辩解内容。"},
                "tone": {"type": "string", "enum": _TONE_ENUM, "description": "发言语气。"},
                "reasoning": _reasoning_schema(),
            },
            "required": ["content", "tone"],
        },
        "vote": {
            "type": "object",
            "properties": {
                "decision": {
                    "type": "boolean",
                    "description": "true=赞成处决当前被提名者，false=反对。",
                },
                "reasoning": _reasoning_schema(),
            },
            "required": ["decision"],
        },
        "nominate": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["nominate", "none"],
                    "description": "是否发起提名。",
                },
                "target": {
                    "type": ["string", "null"],
                    "description": "被提名玩家的 player_id（action=none 时为 null）。",
                },
                "reasoning": _reasoning_schema(),
            },
            "required": ["action"],
        },
        "nomination_intent": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["nominate", "none"],
                    "description": "是否计划提名。",
                },
                "target": {
                    "type": ["string", "null"],
                    "description": "计划提名玩家的 player_id（action=none 时为 null）。",
                },
                "reasoning": _reasoning_schema(),
            },
            "required": ["action"],
        },
        "night_action": {
            "type": "object",
            "properties": {
                "target": {
                    "type": ["string", "null"],
                    "description": "行动目标 player_id；需要多目标时传目标 id 数组。",
                },
                "reasoning": _reasoning_schema(),
            },
            "required": ["target"],
        },
        "slayer_shot": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "被射击玩家的 player_id。"},
                "reasoning": _reasoning_schema(),
            },
            "required": ["target"],
        },
        "private_message": {
            "type": "object",
            "properties": {
                "target_player": {"type": "string", "description": "私聊对象 player_id。"},
                "content": {"type": "string", "description": "私聊内容。"},
                "reasoning": _reasoning_schema(),
            },
            "required": ["target_player", "content"],
        },
    }

    # 工具名 → 映射回 JSON decision 的 action 值（speak 与 defense_speech 都返回 action=speak）
    _TOOL_TO_ACTION: dict[str, str] = {
        "speak": "speak",
        "defense_speech": "speak",
        "vote": "vote",
        "nominate": "nominate",
        "nomination_intent": "nominate",
        "night_action": "night_action",
        "slayer_shot": "slayer_shot",
        "private_message": "private_message",
    }

    @classmethod
    def _build_tool_def(cls, name: str) -> ToolDef:
        return ToolDef(
            name=name,
            description=_ACTION_TOOL_DESCRIPTIONS.get(name, f"执行动作 {name}"),
            parameters=cls._TOOL_SCHEMAS[name],
        )

    @classmethod
    def tool_defs_for_action(cls, action_type: str) -> list[ToolDef]:
        """返回某动作主导的工具列表（含 JSON 兜底保留原 fallback）。"""
        if action_type in cls._TOOL_SCHEMAS:
            return [cls._build_tool_def(action_type)]
        if action_type in {"speak", "defense_speech"}:
            return [cls._build_tool_def("speak"), cls._build_tool_def("defense_speech")]
        # 未知动作：给出 speak/vote/nominate/night_action 的通用选择
        return [cls._build_tool_def(name) for name in ("speak", "vote", "nominate", "night_action")]

    @classmethod
    def all_tool_defs(cls) -> list[ToolDef]:
        return [cls._build_tool_def(name) for name in cls._TOOL_SCHEMAS]

    @classmethod
    def known_tool_names(cls) -> set[str]:
        """返回所有可识别的工具名集合（用于从 thinking 文本 scavenge tool call）。"""
        return set(cls._TOOL_SCHEMAS)

    @classmethod
    def tool_schema_text(cls) -> str:
        """8 个 Action 工具的一句话用途（稳定字符串，供全局静态层使用）。

        精简版（PLN-039 RPT-014 优化）：只保留工具名与用途，参数细节交由
        tools 参数（全量 JSON schema）提供，避免 system 文本与 tools 参数
        重复描述导致每请求输入膨胀。
        """
        lines = ["【可用行动工具】"]
        for name in cls._TOOL_SCHEMAS:
            desc = _ACTION_TOOL_DESCRIPTIONS.get(name, f"执行动作 {name}")
            lines.append(f"- {name}：{desc}")
        return "\n".join(lines)

    @classmethod
    def _tool_matches_action(cls, function_name: str, action_type: str) -> bool:
        """判断某工具是否与当前动作类型对应（tools 全量后优先匹配，防误调）。"""
        mapped = cls._TOOL_TO_ACTION.get(function_name)
        if mapped == action_type:
            return True
        # speak / defense_speech 都可映射到 speak；nomination_intent/nominate 映射到 nominate
        if mapped in {"speak", "defense_speech"} and action_type in {"speak", "defense_speech"}:
            return True
        return mapped in {"nominate", "nomination_intent"} and action_type in {
            "nominate",
            "nomination_intent",
        }

    @classmethod
    def decision_from_tool_calls(
        cls, tool_calls: list[Any], action_type: str
    ) -> dict[str, Any] | None:
        """将 LLM 返回的 tool_calls 解析为与旧 JSON decision 结构兼容的 dict。

        仅接受与当前动作类型语义兼容的工具调用（REV-008 F3 收严：tools 全量后
        模型误调 speak/night_action 等不兼容工具的概率上升，无条件接受会被
        normalize_decision 判缺参后静默走本地启发式，丢弃 LLM 决策）。
        无兼容工具调用时返回 None（交由 JSON fallback 兜底）。
        """
        if not tool_calls:
            return None

        def _build(tc: Any) -> dict[str, Any] | None:
            function_name = getattr(tc, "function_name", None)
            if not function_name or function_name not in cls._TOOL_TO_ACTION:
                return None
            args = dict(getattr(tc, "arguments", {}) or {})
            decision: dict[str, Any] = {"action": cls._TOOL_TO_ACTION[function_name]}
            decision.update(args)
            # 兼容旧字段：nomination_intent/nominate 的 action 直接透传
            if function_name in {"nominate", "nomination_intent"}:
                decision["action"] = args.get("action", "none")
                if args.get("action") == "none":
                    decision["target"] = None
            return decision

        # 仅接受与 action_type 语义兼容的工具调用（speak/defense_speech、
        # nominate/nomination_intent 视为同类；不兼容工具一律返回 None）
        for tc in tool_calls:
            function_name = getattr(tc, "function_name", None)
            if function_name and cls._tool_matches_action(function_name, action_type):
                decision = _build(tc)
                if decision is not None:
                    return decision
        return None

    @classmethod
    def describe_action(cls, action_type: str) -> str:
        return _ACTION_TOOL_DESCRIPTIONS.get(action_type, f"执行动作 {action_type}")
