"""Agent 工具包测试（PLN-038 阶段 A/C/D + PLN-037 策略表）。

覆盖：GameActionToolRegistry、MemoryTools、WorldTools、
LLM 策略表（LLM_STRATEGY_BY_ACTION）、三层前缀稳定。
"""

from __future__ import annotations

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from src.agents.prompt.common_rules import build_common_rules_prefix
from src.agents.tools.action_tool_registry import GameActionToolRegistry
from src.agents.tools.memory_tools import MemoryTools
from src.agents.tools.world_tools import WorldTools
from src.llm.base_backend import Message, ToolCall
from src.state.game_state import (
    AgentVisibleState,
    GamePhase,
    GameState,
    PlayerState,
    Team,
)
from tests.doubles import CapturingBackend

# ---------------------------------------------------------------------------
# GameActionToolRegistry（阶段 A）
# ---------------------------------------------------------------------------


def test_registry_provides_tool_defs_for_all_actions():
    for action in ("speak", "defense_speech", "vote", "nominate", "night_action", "slayer_shot"):
        defs = GameActionToolRegistry.tool_defs_for_action(action)
        assert defs, f"{action} 应有工具定义"


def test_registry_tool_defs_have_stable_schema():
    # 工具 schema 为稳定字符串，可作缓存前缀（PLN-037 P1）
    s1 = GameActionToolRegistry._build_tool_def("speak").parameters
    s2 = GameActionToolRegistry._build_tool_def("speak").parameters
    assert s1 == s2


def test_decision_from_tool_calls_speak():
    calls = [
        ToolCall(
            tool_call_id="call_1",
            function_name="speak",
            arguments={"content": "大家好", "tone": "calm", "reasoning": "关键结论"},
        )
    ]
    decision = GameActionToolRegistry.decision_from_tool_calls(calls, "speak")
    assert decision is not None
    assert decision["action"] == "speak"
    assert decision["content"] == "大家好"


def test_decision_from_tool_calls_vote():
    calls = [
        ToolCall(
            tool_call_id="call_1",
            function_name="vote",
            arguments={"decision": True},
        )
    ]
    decision = GameActionToolRegistry.decision_from_tool_calls(calls, "vote")
    assert decision["action"] == "vote"
    assert decision["decision"] is True


def test_decision_from_tool_calls_nominate_none():
    calls = [
        ToolCall(
            tool_call_id="call_1",
            function_name="nominate",
            arguments={"action": "none", "reasoning": "放弃"},
        )
    ]
    decision = GameActionToolRegistry.decision_from_tool_calls(calls, "nominate")
    assert decision["action"] == "none"
    assert decision["target"] is None


def test_decision_from_tool_calls_empty_returns_none():
    assert GameActionToolRegistry.decision_from_tool_calls([], "speak") is None
    assert GameActionToolRegistry.decision_from_tool_calls(None, "speak") is None


def test_decision_from_tool_calls_unknown_tool_returns_none():
    calls = [ToolCall(tool_call_id="1", function_name="nope", arguments={})]
    assert GameActionToolRegistry.decision_from_tool_calls(calls, "speak") is None


def test_decision_from_tool_calls_prefers_action_matching_tool():
    # PLN-039 T2：tools 全量后优先匹配与当前动作类型对应的工具，防误调
    calls = [
        ToolCall(
            tool_call_id="call_1",
            function_name="speak",
            arguments={"content": "先说的内容", "tone": "calm", "reasoning": "x"},
        ),
        ToolCall(
            tool_call_id="call_2",
            function_name="vote",
            arguments={"decision": True, "reasoning": "y"},
        ),
    ]
    decision = GameActionToolRegistry.decision_from_tool_calls(calls, "vote")
    assert decision is not None
    assert decision["action"] == "vote"
    assert decision["decision"] is True


def test_decision_from_tool_calls_fallback_known_tool():
    # REV-008 F3：无匹配动作类型且无兼容工具时返回 None（走 JSON fallback），
    # 不再静默接受错误动作工具（如 night_action 时调用 speak 会被本地启发式覆盖 LLM 决策）
    calls = [
        ToolCall(
            tool_call_id="call_1",
            function_name="speak",
            arguments={"content": "hi", "tone": "calm", "reasoning": "x"},
        )
    ]
    decision = GameActionToolRegistry.decision_from_tool_calls(calls, "night_action")
    assert decision is None


def test_global_static_layer_is_pure_static_and_shared_across_agents():
    # PLN-039 T1：全局静态层为纯静态字符串，跨 Agent 逐 token 一致
    from src.agents.prompt.common_rules import build_global_static_layer

    layer = build_global_static_layer()
    assert len(layer) >= 1500  # T1 目标长度
    assert "【可用行动工具】" in layer
    assert "【输出格式要求】" in layer
    assert build_global_static_layer() == layer


# ---------------------------------------------------------------------------
# LLM 策略表（PLN-037 P0-4.1）
# ---------------------------------------------------------------------------


def _make_strategy_agent(difficulty: str = "standard") -> AIAgent:
    return AIAgent(
        player_id="p1",
        name="Alice",
        backend=CapturingBackend(),
        persona=Persona(description="谨慎", speaking_style="平稳"),
        difficulty=difficulty,
    )


def test_llm_strategy_table_thinking_levels_by_difficulty(monkeypatch: pytest.MonkeyPatch):
    # 用户决策 2026-08-05：casual=off / standard=medium / master=high / chaos=high
    monkeypatch.delenv("AI_THINKING_LEVEL", raising=False)
    casual = _make_strategy_agent("casual")
    assert casual._llm_strategy_for_action("vote")["thinking"] == "disabled"
    assert casual._llm_strategy_for_action("night_action")["thinking"] == "disabled"
    assert casual._llm_strategy_for_action("nominate")["thinking"] == "disabled"

    standard = _make_strategy_agent("standard")
    assert standard._llm_strategy_for_action("vote")["thinking"] == "enabled"
    assert standard._llm_strategy_for_action("vote")["reasoning_effort"] == "medium"
    assert standard._llm_strategy_for_action("night_action")["thinking"] == "enabled"
    assert standard._llm_strategy_for_action("nominate")["reasoning_effort"] == "medium"

    master = _make_strategy_agent("master")
    assert master._llm_strategy_for_action("vote")["thinking"] == "enabled"
    assert master._llm_strategy_for_action("vote")["reasoning_effort"] == "high"


def test_llm_strategy_table_speaks_use_difficulty_effort(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AI_THINKING_LEVEL", raising=False)
    strategy = _make_strategy_agent("standard")._llm_strategy_for_action("speak")
    assert strategy["thinking"] == "enabled"
    assert strategy["reasoning_effort"] == "medium"
    # 2026-08-05 调大：为 thinking 预留空间（DeepSeek reasoning 波动可达 1000+），避免 finish=length 无输出
    assert strategy["max_tokens"] == 2000


def test_llm_strategy_table_unknown_action_falls_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AI_THINKING_LEVEL", raising=False)
    strategy = _make_strategy_agent()._llm_strategy_for_action("unknown_action")
    assert strategy["thinking"] == "disabled"
    assert strategy["reasoning_effort"] is None
    assert strategy["max_tokens"] == 400


def test_llm_strategy_table_env_override_forces_level(monkeypatch: pytest.MonkeyPatch):
    # AI_THINKING_LEVEL 环境变量可全局覆盖难度默认值
    monkeypatch.setenv("AI_THINKING_LEVEL", "high")
    casual = _make_strategy_agent("casual")
    assert casual._llm_strategy_for_action("vote")["thinking"] == "enabled"
    assert casual._llm_strategy_for_action("vote")["reasoning_effort"] == "high"

    monkeypatch.setenv("AI_THINKING_LEVEL", "off")
    master = _make_strategy_agent("master")
    assert master._llm_strategy_for_action("vote")["thinking"] == "disabled"


# ---------------------------------------------------------------------------
# 三层前缀稳定（PLN-037 P1-4.6）
# ---------------------------------------------------------------------------


def test_common_rules_prefix_is_static():
    a = build_common_rules_prefix()
    b = build_common_rules_prefix()
    assert a == b
    assert "血染钟楼" in a


@pytest.mark.asyncio
async def test_act_three_tier_prefix_is_stable_across_calls():
    # 同一 agent 两次 speak：稳定规则层（system）应逐 token 相同
    class DoubleCapture(CapturingBackend):
        def __init__(self) -> None:
            super().__init__(
                content='{"action":"speak","content":"hi","tone":"calm","reasoning":"ok"}'
            )
            self.systems: list[str] = []
            self.first_msgs: list[str] = []

        async def generate(self, system_prompt: str, messages: list[Message], **kwargs):
            self.systems.append(system_prompt)
            if messages:
                self.first_msgs.append(messages[0].content)
            from src.llm.base_backend import LLMResponse

            return LLMResponse(content=self.content, tool_calls=[])

    backend = DoubleCapture()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    state = GameState(
        game_id="fixed-game-id-1",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)
    await agent.act(visible_state, "speak")
    await agent.act(visible_state, "speak")
    assert backend.systems[0] == backend.systems[1]
    # 首条 user 消息为稳定长上下文，也应一致（同一轮内）
    assert backend.first_msgs[0] == backend.first_msgs[1]


@pytest.mark.asyncio
async def test_act_system_prompt_contains_player_names_and_action():
    class Capture(CapturingBackend):
        def __init__(self) -> None:
            super().__init__(content='{"action":"vote","decision":true,"reasoning":"ok"}')
            self.systems: list[str] = []
            self.message_lists: list[list[Message]] = []

        async def generate(self, system_prompt: str, messages: list[Message], **kwargs):
            self.systems.append(system_prompt)
            self.message_lists.append(messages)
            from src.llm.base_backend import LLMResponse

            return LLMResponse(content=self.content, tool_calls=[])

    backend = Capture()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    state = GameState(
        game_id="fixed-game-id-2",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)
    await agent.act(visible_state, "vote")
    prompt = backend.systems[-1]
    assert "Alice" in prompt
    assert "p1" in prompt
    # PLN-039 T1：system 含全局静态层（工具 schema 文本化），action_type 动态指令仍后置到 user 末条
    assert "【可用行动工具】" in prompt
    assert "当前需要执行的动作类型" not in prompt
    user_msgs = "".join(m.content for m in backend.message_lists[-1])
    assert "当前需要执行的动作类型" in user_msgs
    assert "vote" in user_msgs


# ---------------------------------------------------------------------------
# WorldTools（阶段 D）
# ---------------------------------------------------------------------------


def _make_visible_state() -> AgentVisibleState:
    from src.orchestrator.information_broker import InformationBroker

    state = GameState(
        game_id="fixed-game-id-w",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    return InformationBroker().get_visible_state(game_state=state, player_id="p1")


def test_world_tools_observe_state():
    vs = _make_visible_state()
    obs = WorldTools.observe_state(None, vs)
    assert obs["day_number"] == 1
    assert obs["alive_count"] == 2


def test_world_tools_query_players():
    vs = _make_visible_state()
    players = WorldTools.query_players(None, vs)
    assert len(players) == 2
    assert players[0]["player_id"] == "p1"


def test_world_tools_query_legal_context_default():
    vs = _make_visible_state()
    ctx = WorldTools.query_legal_context(None, vs)
    assert "legal_nomination_targets" in ctx


def test_world_tools_query_public_log_returns_texts():
    class AgentLike:
        def _format_event_to_text(self, event, visible_state):
            return f"[event] {event.event_type}"

    vs = _make_visible_state()
    logs = WorldTools.query_public_log(AgentLike(), vs)
    assert isinstance(logs, list)


# ---------------------------------------------------------------------------
# MemoryTools（阶段 C）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_tools_append_and_read(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    vs = _make_visible_state()
    result = MemoryTools.append_memory(
        agent, vs, "我看到 Bob 昨晚表现可疑", tier="objective", category="suspect"
    )
    assert result["ok"] is True
    read = MemoryTools.read_memory(agent, tier="objective", category="suspect")
    assert any("Bob" in item for item in read["items"])
    # 落盘文件存在
    disk = MemoryTools._read_disk_entries(agent.player_id)
    assert disk and disk[-1]["content"].startswith("我看到 Bob")


@pytest.mark.asyncio
async def test_memory_tools_block_sensitive_content(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    vs = _make_visible_state()
    with pytest.raises(ValueError):
        MemoryTools.append_memory(agent, vs, "邪恶队友名单：p2", tier="private")
    with pytest.raises(ValueError):
        MemoryTools.append_memory(agent, vs, "正常内容", tier="TEAM_EVIL")


@pytest.mark.asyncio
async def test_memory_tools_reflect_and_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="我觉得局势对我有利")
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    vs = _make_visible_state()
    # 先用 mock 后端填充一条观察，使反思非空
    MemoryTools.append_memory(agent, vs, "Bob 昨晚行为可疑", tier="objective", category="suspect")
    result = await MemoryTools.reflect(agent, vs)
    assert result["ok"] is True
    archive = await MemoryTools.archive_phase(agent, vs)
    assert archive["ok"] is True
