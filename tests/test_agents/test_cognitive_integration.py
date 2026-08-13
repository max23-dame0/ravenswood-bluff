"""T4: 认知工作流 AIAgent 集成测试 — PLN-042。

覆盖：
- `cognitive_speak_enabled()` 开关（BOTC_COGNITIVE_SPEAK 默认 off）；
- AIAgent 初始化 viewpoint store（仅 live/强制开启）；
- act_with_strategy 在开关开启时 speak 走认知路径并注入观点摘要；
- 开关关闭时行为与现状完全一致（零回归）；
- mock 默认零污染（无 viewpoints.jsonl）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.memory.working_memory import Observation
from src.agents.persona.persona import Persona
from src.agents.workflow.cognitive_workflow import cognitive_speak_enabled
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import DummyBackend

_SPEECH_JSON = '{"action":"speak","content":"我怀疑 P2 有问题","reasoning":"基于线索"}'


def _make_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, force: str = "0") -> AIAgent:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.setenv("BOTC_COGNITIVE_SPEAK", force)
    return AIAgent(
        player_id="p1",
        name="Alice",
        backend=DummyBackend(content=_SPEECH_JSON),
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )


def test_cognitive_switch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOTC_COGNITIVE_SPEAK", raising=False)
    assert not cognitive_speak_enabled()


def test_cognitive_switch_forced_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOTC_COGNITIVE_SPEAK", "1")
    assert cognitive_speak_enabled()


def test_agent_store_absent_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch)
    assert agent.get_viewpoint_store() is None


def test_agent_store_created_when_forced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch, force="1")
    store = agent.get_viewpoint_store()
    assert store is not None
    assert store.enabled
    assert store.path is None  # game_id 未绑定前不落盘


def test_agent_store_created_by_viewpoints_env_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-3 修复：仅 BOTC_VIEWPOINTS=1（不设认知开关）也创建 store。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.setenv("BOTC_VIEWPOINTS", "1")
    monkeypatch.delenv("BOTC_COGNITIVE_SPEAK", raising=False)
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=DummyBackend(content=_SPEECH_JSON),
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    store = agent.get_viewpoint_store()
    assert store is not None
    assert store.enabled


def test_agent_store_binds_game_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = _make_agent(tmp_path, monkeypatch, force="1")
    agent.set_game_context("game-cog")
    store = agent.get_viewpoint_store()
    assert store is not None
    assert store.path is not None
    assert "game-cog" in str(store.path)


@pytest.mark.asyncio
async def test_speak_with_cognitive_off_behavior_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关关闭：speak 走原路径（不产生 viewpoint 文件、不注入认知摘要）。"""
    agent = _make_agent(tmp_path, monkeypatch)  # force="0"
    agent.set_game_context("game-cog")
    state = GameState(
        game_id="game-cog",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    decision = await agent.act_with_strategy(visible, "speak")
    assert decision["action"] == "speak"
    # 零污染
    assert not list(Path(tmp_path).rglob("viewpoints.jsonl"))


@pytest.mark.asyncio
async def test_speak_with_cognitive_on_injects_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """开关开启：speak 走认知路径，strategic_thought 含观点链摘要。"""
    agent = _make_agent(tmp_path, monkeypatch, force="1")
    agent.set_game_context("game-cog")
    # 预置记忆（hard 证据 → high_confidence 记忆）
    agent.working_memory.add_observation(
        Observation(
            observation_id="obs-1",
            content="高可信信息：P2 可能是恶魔（占卜师指出）",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
        )
    )
    agent.working_memory.remember_private_info(
        "fortune_teller_info", "高可信信息：P2 可能是恶魔（占卜师指出）"
    )
    state = GameState(
        game_id="game-cog",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    decision = await agent.act_with_strategy(visible, "speak")
    assert decision["action"] == "speak"
    # 观点落盘
    store = agent.get_viewpoint_store()
    assert store is not None and store.path is not None and store.path.exists()


class _RecordingBackend(DummyBackend):
    """记录每次 generate 的 messages（验证 user 段注入）。"""

    def __init__(self) -> None:
        super().__init__(content=_SPEECH_JSON)
        self.user_texts: list[str] = []

    async def generate(self, system_prompt, messages, **kwargs):
        self.user_texts.extend(str(m.content) for m in messages if getattr(m, "content", None))
        return await super().generate(system_prompt, messages, **kwargs)


@pytest.mark.asyncio
async def test_cognitive_summary_injected_into_llm_user_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """观点链必须进入 LLM 的 user 段（dynamic_context），驱动发言论证。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BOTC_BACKEND", "mock")
    monkeypatch.setenv("BOTC_COGNITIVE_SPEAK", "1")
    backend = _RecordingBackend()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-cog")
    agent.working_memory.remember_private_info(
        "fortune_teller_info", "高可信信息：P2 可能是恶魔（占卜师指出）"
    )
    state = GameState(
        game_id="game-cog",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    await agent.act(visible, "speak")
    combined = "\n".join(backend.user_texts)
    assert "【你的观点链】" in combined
    assert "P2 可能是恶魔" in combined
    assert "置信度" in combined


@pytest.mark.asyncio
async def test_draft_reuse_still_records_viewpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """草稿复用路径（0 次 LLM）也必须先形成观点并落盘。"""
    agent = _make_agent(tmp_path, monkeypatch, force="1")
    agent.set_game_context("game-cog")
    agent.working_memory.remember_private_info(
        "fortune_teller_info", "高可信信息：P2 可能是恶魔（占卜师指出）"
    )
    state = GameState(
        game_id="game-cog",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    # orchestrator 实际路径：直接调 act()（带 cached_speech_draft）
    decision = await agent.act(visible, "speak", cached_speech_draft="我怀疑 P2，线索指向他。")
    assert decision["action"] == "speak"
    assert decision["speech_source"] == "cache_finalized_draft_reuse"
    # 观点已落盘（草稿复用路径不跳过认知）
    store = agent.get_viewpoint_store()
    assert store is not None and store.path is not None and store.path.exists()


@pytest.mark.asyncio
async def test_cognitive_path_no_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """认知路径下 decision 仍为合法 speak，不触发 fallback。"""
    agent = _make_agent(tmp_path, monkeypatch, force="1")
    agent.set_game_context("game-cog")
    agent.working_memory.remember_private_info(
        "fortune_teller_info", "高可信信息：P2 可能是恶魔（占卜师指出）"
    )
    state = GameState(
        game_id="game-cog",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )
    visible = agent._build_visible_state(state)
    decision = await agent.act_with_strategy(visible, "speak")
    assert decision["action"] == "speak"
    assert decision.get("content")
    # 未走 fallback（DummyBackend 返回合法发言决策）
    assert "兜底" not in str(decision.get("reasoning", ""))
    # 观点库已落盘
    store = agent.get_viewpoint_store()
    assert store is not None and store.path is not None and store.path.exists()
