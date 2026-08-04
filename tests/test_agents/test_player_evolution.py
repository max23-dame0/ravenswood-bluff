"""玩家进化机制测试（PLN-038 阶段 E）。

覆盖：
- 对局隔离：MemoryTools 落盘到 games/{game_id}/，不同对局目录独立
- 跨局档案：PlayerProfileStore 战绩统计 + 长期经验教训持久化
- 玩家进化闭环：finalize_game_lesson → build_long_term_summary → prompt 注入
- 说书人进化：StorytellerProfileStore + StorytellerAgent.finalize_game_profile
- 信息隔离：敏感内容不会进入跨局经验
"""

from __future__ import annotations

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.memory.player_profile import PlayerProfileStore
from src.agents.persona.persona import Persona
from src.agents.storyteller_agent import StorytellerAgent
from src.agents.storyteller_tools import StorytellerProfileStore
from src.agents.tools.memory_tools import MemoryTools
from src.state.game_state import (
    GamePhase,
    GameState,
    PlayerState,
    Team,
)
from tests.doubles import CapturingBackend


def _make_agent(tmp_path, monkeypatch, player_id: str = "p1") -> AIAgent:
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    agent = AIAgent(
        player_id=player_id,
        name=f"Agent{player_id}",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-A")
    return agent


def _make_state(game_id: str = "game-A") -> GameState:
    return GameState(
        game_id=game_id,
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )


# ---------------------------------------------------------------------------
# 对局隔离（MemoryTools 目录）
# ---------------------------------------------------------------------------


def test_game_dir_is_per_game(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    d1 = MemoryTools.game_dir("p1", "game-A")
    d2 = MemoryTools.game_dir("p1", "game-B")
    assert d1 != d2
    assert d1.name == "game-A"
    assert d2.name == "game-B"
    assert d1.parent.name == "games"
    # 无 game_id 回退到玩家根目录
    d0 = MemoryTools.game_dir("p1", None)
    assert d0.name == "p1"


@pytest.mark.asyncio
async def test_memory_tools_writes_to_game_dir(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    state = _make_state("game-A")
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)

    MemoryTools.append_memory(agent, visible_state, "观察：Bob 跳厨师", tier="public")

    game_dir = MemoryTools.game_dir("p1", "game-A")
    assert (game_dir / "memory.jsonl").exists()
    # 其他对局目录不应有该记忆
    other_dir = MemoryTools.game_dir("p1", "game-B")
    assert not (other_dir / "memory.jsonl").exists()


# ---------------------------------------------------------------------------
# 跨局玩家档案
# ---------------------------------------------------------------------------


def test_player_profile_record_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = PlayerProfileStore("p1", "Alice")
    store.record_game_result(won=True, role_id="imp", team="evil")
    store.record_game_result(won=False, role_id="washerwoman", team="good")

    profile = store.load_profile()
    assert profile["games_played"] == 2
    assert profile["wins"] == 1
    assert profile["losses"] == 1
    assert profile["role_stats"]["imp"]["played"] == 1
    assert profile["role_stats"]["washerwoman"]["wins"] == 0
    assert profile["team_stats"]["evil"]["wins"] == 1

    # 持久化：新实例读取同一份档案
    store2 = PlayerProfileStore("p1", "Alice")
    assert store2.load_profile()["games_played"] == 2


def test_player_profile_lessons_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = PlayerProfileStore("p1", "Alice")
    store.record_game_result(won=True, role_id="imp", team="evil")
    store.append_lesson({"lesson": "首夜保持低调，不要过早暴露身份", "won": True})
    store.append_lesson({"lesson": "多观察发言矛盾，不轻易站边", "won": False})

    lessons = store.read_lessons()
    assert len(lessons) == 2
    assert "低调" in lessons[-1]["lesson"]
    summary = store.build_long_term_summary()
    assert "低调" in summary
    assert "局" in summary
    assert "胜率" in summary


def test_player_profile_lesson_blocks_sensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = PlayerProfileStore("p1", "Alice")
    store.append_lesson({"lesson": "邪恶队友名单：p2 是恶魔", "won": True})
    store.append_lesson({"lesson": "正常经验：不要照抄私密信息", "won": False})

    summary = store.build_long_term_summary()
    # 敏感 lesson 不会注入 prompt
    assert "恶魔" not in summary
    assert "队友名单" not in summary
    assert "正常经验" in summary


# ---------------------------------------------------------------------------
# 玩家进化闭环（AIAgent）
# ---------------------------------------------------------------------------


def test_agent_finalize_lesson_and_evolve(tmp_path, monkeypatch):
    agent = _make_agent(tmp_path, monkeypatch)
    # 模拟两局
    agent.finalize_game_lesson(won=True, role_id="imp", team="evil", lesson="伪装要一致")
    agent.finalize_game_lesson(won=False, role_id="chef", team="good", lesson="信息位要早点报")

    agent.load_player_profile()
    long_term = agent.build_long_term_context()
    assert "伪装要一致" in long_term
    assert "信息位要早点报" in long_term
    assert "2 局" in long_term or "2局" in long_term


def test_agent_long_term_injected_into_stable_context(tmp_path, monkeypatch):
    class Capture(CapturingBackend):
        def __init__(self) -> None:
            super().__init__(
                content='{"action":"speak","content":"hi","tone":"calm","reasoning":"ok"}'
            )
            self.first_msgs: list[str] = []

        async def generate(self, system_prompt, messages, **kwargs):
            from src.llm.base_backend import LLMResponse

            if messages:
                self.first_msgs.append(messages[0].content)
            return LLMResponse(content=self.content, tool_calls=[])

    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = Capture()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    agent.set_game_context("game-A")
    agent.finalize_game_lesson(won=True, role_id="imp", team="evil", lesson="伪装要一致")
    agent.load_player_profile()

    state = _make_state("game-A")
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)
    import asyncio

    asyncio.run(agent.act(visible_state, "speak"))
    assert "跨局玩家记忆" in backend.first_msgs[0]
    assert "伪装要一致" in backend.first_msgs[0]


# ---------------------------------------------------------------------------
# 说书人进化机制
# ---------------------------------------------------------------------------


def test_storyteller_profile_record_and_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    store = StorytellerProfileStore()
    store.record_game_summary(
        game_id="g1",
        judgement_count=10,
        distortion_events=3,
        lesson="首夜扭曲要克制",
    )
    profile = store.load_profile()
    assert profile["games_conducted"] == 1
    assert profile["total_judgements"] == 10
    assert profile["distortion_events"] == 3
    assert profile["distortion_rate"] == 0.3

    store2 = StorytellerProfileStore()
    assert store2.load_profile()["games_conducted"] == 1
    summary = store2.build_long_term_summary()
    assert "1 局" in summary
    assert "首夜扭曲要克制" in summary


def test_storyteller_agent_finalize_game_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    st = StorytellerAgent(mode="auto")
    st.record_judgement(
        "night_info",
        "distort",
        "平衡",
        distortion_strategy="chef_pairs_offset.help_evil",
    )
    st.record_judgement("execution", "normal", "正常")
    result = st.finalize_game_profile(game_id="g1", lesson="本局裁决完成")
    assert result["judgement_count"] == 2
    assert result["distortion_events"] == 1
    assert result["profile"]["games_conducted"] == 1


# ---------------------------------------------------------------------------
# 拟人化进化：局中反思 / 局后复盘 / 学习他人 / 调整策略
# ---------------------------------------------------------------------------


def test_in_game_reflection_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.add_in_game_reflection("刚才提名太冲动了，下次应多观察一轮", phase="DAY_DISCUSSION")
    agent.add_in_game_reflection("Bob 的发言有矛盾，值得盯住")

    reflections = agent._player_profile.read_reflections()
    assert len(reflections) == 2
    # read 最新在前：reflections[1] 是最早写入的那条（含"冲动"）
    assert "冲动" in reflections[1]["reflection"]
    assert "矛盾" in reflections[0]["reflection"]
    assert agent.player_profile["evolution"]["reflections_done"] == 2


def test_finalize_game_review_records_and_evolves(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    result = agent.finalize_game_review(
        won=True,
        role_id="imp",
        team="evil",
        takeaway="伪装一致且节奏主动是恶魔获胜关键",
    )
    assert result["reviewed"] is True
    assert result["evolved"] is True
    # 复盘落盘
    reviews = agent._player_profile.read_game_reviews()
    assert len(reviews) == 1
    assert "伪装一致" in reviews[0]["takeaway"]
    # 策略调整落盘：赢局默认强化攻击/冒险
    strategies = agent._player_profile.read_strategies()
    assert len(strategies) == 1
    assert strategies[0]["tendency_delta"]["aggression"] > 0
    assert agent.player_profile["evolution"]["reviews_done"] == 1
    assert agent.player_profile["evolution"]["strategy_adjustments"] == 1


def test_learn_play_style_from_others(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.learn_play_style("chef", "厨师要尽快建立可信信息位并公开分享")
    learned = agent._player_profile.read_lessons_learned()
    assert len(learned) == 1
    assert "厨师" in learned[0]["lesson"]
    assert agent.player_profile["evolution"]["lessons_learned"] == 1


def test_evolved_tendency_changes_with_wins_and_losses(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    # 初始倾向均衡
    agent.finalize_game_review(won=True, role_id="imp", team="evil", takeaway="赢一局")
    agent.finalize_game_review(won=False, role_id="chef", team="good", takeaway="输一局")
    tendency = agent.player_profile["tendency"]
    # 赢 evil：caution 上升；输 good：talkativeness 上升
    assert tendency["caution"] > 0.5
    assert tendency["talkativeness"] > 0.5
    # 进化倾向摘要可注入
    summary = agent.build_evolved_tendency()
    assert "打法倾向" in summary


def test_long_term_summary_includes_learned_and_tendency(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.finalize_game_review(won=False, role_id="chef", team="good", takeaway="信息位要早报")
    agent.learn_play_style("chef", "厨师要公开分享信息")
    agent.load_player_profile()
    summary = agent.build_long_term_context()
    assert "信息位要早报" in summary
    assert "厨师要公开分享信息" in summary
    assert "打法倾向" in summary
