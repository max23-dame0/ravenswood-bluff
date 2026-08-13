"""共享经验池测试（PLN-040 T2）。

覆盖：
- 沉淀（deposit）：去私密化、敏感过滤、非空约束
- 检索（retrieve）：角色优先 + 阵营 + 新鲜度排序
- 注入摘要（build_shared_context）：纯文本、无敏感、空池返回空串
- AIAgent.load_player_profile 合并共享池到 _long_term_summary
- game_loop._finalize_agent_player_profiles 沉淀钩子
"""

from __future__ import annotations

import pytest

from src.agents.ai_agent import AIAgent
from src.agents.memory.shared_pool import SharedExperiencePool
from src.agents.persona.persona import Persona
from src.state.game_state import GamePhase, GameState, PlayerState, Team
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
        phase=GamePhase.GAME_OVER,
        round_number=1,
        day_number=2,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        ),
    )


# ---------------------------------------------------------------------------
# deposit（沉淀）
# ---------------------------------------------------------------------------


def test_deposit_writes_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    path = pool.deposit(
        role_id="washerwoman",
        team="good",
        won=True,
        lesson="作为洗衣妇要尽早公布信息位。",
    )
    assert path is not None
    assert path.exists()
    records = pool._read_all()
    assert len(records) == 1
    assert records[0]["role_id"] == "washerwoman"
    assert records[0]["team"] == "good"
    assert records[0]["won"] is True


def test_deposit_rejects_sensitive_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    path = pool.deposit(
        role_id="imp",
        team="evil",
        won=True,
        lesson="作为恶魔要隐藏身份，队友名单是 p3。",
    )
    assert path is None  # 含"恶魔"/"队友名单" → 拒绝入池
    assert not pool._read_all()


def test_deposit_requires_role_and_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    assert pool.deposit(role_id=None, team="good", won=True, lesson="x") is None
    assert pool.deposit(role_id="imp", team="evil", won=True, lesson="") is None
    assert not pool._read_all()


# ---------------------------------------------------------------------------
# retrieve（检索）
# ---------------------------------------------------------------------------


def test_retrieve_prefers_same_role(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    pool.deposit(role_id="chef", team="good", won=True, lesson="厨师看相邻。")
    pool.deposit(role_id="washerwoman", team="good", won=True, lesson="洗衣妇报信息位。")
    pool.deposit(role_id="washerwoman", team="evil", won=False, lesson="洗衣妇输了要反省。")
    items = pool.retrieve(role_id="washerwoman", team="good", top_k=5)
    assert len(items) >= 2
    # 同角色条目应排在最前
    assert items[0]["role_id"] == "washerwoman"
    assert items[1]["role_id"] == "washerwoman"


def test_retrieve_top_k_and_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    assert pool.retrieve(role_id="imp", team="evil") == []
    pool.deposit(role_id="imp", team="evil", won=True, lesson="A。")
    pool.deposit(role_id="imp", team="evil", won=True, lesson="B。")
    pool.deposit(role_id="imp", team="evil", won=True, lesson="C。")
    assert len(pool.retrieve(role_id="imp", team="evil", top_k=2)) == 2


def test_retrieve_unknown_role_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    pool.deposit(role_id="imp", team="evil", won=True, lesson="A。")
    assert pool.retrieve(role_id=None, team="evil") == []


# ---------------------------------------------------------------------------
# build_shared_context（注入摘要）
# ---------------------------------------------------------------------------


def test_build_shared_context_empty_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    assert pool.build_shared_context(role_id="imp", team="evil") == ""


def test_build_shared_context_formats_text(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    # 注意：含"恶魔/队友名单"等敏感词的经验会被 is_sensitive 拒绝入池（信息隔离）
    pool.deposit(
        role_id="imp", team="evil", won=True, lesson="要控制信息释放节奏，避免过早暴露意图。"
    )
    ctx = pool.build_shared_context(role_id="imp", team="evil")
    assert "共享经验池" in ctx
    assert "控制信息释放节奏" in ctx
    assert "队友名单" not in ctx


def test_build_shared_context_filters_sensitive_at_read(tmp_path, monkeypatch):
    """即使池中有敏感残留（异常写入），注入时也应过滤。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    pool.deposit(role_id="imp", team="evil", won=True, lesson="正常经验。")
    # 手工写入一条敏感记录（模拟历史污染）
    pool._pool_dir.mkdir(parents=True, exist_ok=True)
    with open(pool._lessons_path, "a", encoding="utf-8") as f:
        import json

        f.write(json.dumps({"role_id": "imp", "team": "evil", "lesson": "队友名单是 p2"}) + "\n")
    ctx = pool.build_shared_context(role_id="imp", team="evil")
    assert "队友名单" not in ctx
    assert "正常经验" in ctx


# ---------------------------------------------------------------------------
# AIAgent.load_player_profile 注入合并
# ---------------------------------------------------------------------------


def test_load_player_profile_merges_shared_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    pool = SharedExperiencePool()
    pool.deposit(role_id="washerwoman", team="good", won=True, lesson="洗衣妇报信息位要趁早。")

    agent = _make_agent(tmp_path, monkeypatch)
    agent.role_id = "washerwoman"
    from src.state.game_state import Team as _T

    agent.team = _T.GOOD
    agent.load_player_profile()
    summary = agent.build_long_term_context()
    assert "共享经验池" in summary
    assert "洗衣妇报信息位要趁早" in summary


def test_load_player_profile_keeps_own_when_pool_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.role_id = "imp"
    from src.state.game_state import Team as _T

    agent.team = _T.EVIL
    # 先写一条个人经验，池为空
    agent._player_profile.append_lesson({"lesson": "我的个人经验。", "won": True})
    agent.load_player_profile()
    summary = agent.build_long_term_context()
    assert "我的个人经验" in summary
    assert "共享经验池" not in summary


# ---------------------------------------------------------------------------
# PLN-041 T9：规则书注入（setup 期静态注入）
# ---------------------------------------------------------------------------


def test_load_player_profile_injects_rulebook(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.role_id = "washerwoman"
    from src.state.game_state import Team as _T

    agent.team = _T.GOOD
    agent.load_player_profile()
    assert agent._rulebook_context
    assert "洗衣妇" in agent._rulebook_context
    assert "村民" in agent._rulebook_context


def test_load_player_profile_rulebook_evil_red_line(tmp_path, monkeypatch):
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.role_id = "imp"
    from src.state.game_state import Team as _T

    agent.team = _T.EVIL
    agent.load_player_profile()
    assert "伪装" in agent._rulebook_context or "保密" in agent._rulebook_context


def test_rulebook_context_stable_within_game(tmp_path, monkeypatch):
    """规则书注入同局内稳定：多次调用结果一致（前缀缓存安全）。"""
    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    agent = _make_agent(tmp_path, monkeypatch)
    agent.role_id = "empath"
    from src.state.game_state import Team as _T

    agent.team = _T.GOOD
    agent.load_player_profile()
    first = agent._rulebook_context
    agent.load_player_profile()
    assert agent._rulebook_context == first


# ---------------------------------------------------------------------------
# game_loop 沉淀钩子（_finalize_agent_player_profiles）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_agent_player_profiles_deposits_to_pool(tmp_path, monkeypatch):
    from src.orchestrator.game_loop import GameOrchestrator

    monkeypatch.setenv("BOTC_DATA_DIR", str(tmp_path))
    backend = CapturingBackend(content="{}")
    state = _make_state("game-profile-test")
    orch = GameOrchestrator(state)
    orch.default_agent_backend = backend
    from src.agents.storyteller_agent import StorytellerAgent

    orch.storyteller_agent = StorytellerAgent(backend)

    agent = _make_agent(tmp_path, monkeypatch, player_id="p1")
    agent.synchronize_role(state.get_player("p1"))
    orch.broker.agents["p1"] = agent

    orch.settlement_report = {
        "winning_team": "good",
        "players": [
            {"player_id": "p1", "team": "good", "true_role_id": "washerwoman"},
            {"player_id": "p2", "team": "evil", "true_role_id": "imp"},
        ],
    }
    await orch._finalize_agent_player_profiles()

    pool = SharedExperiencePool()
    records = pool._read_all()
    assert len(records) == 1  # 仅 p1（p2 是 broker 未注册的 AI？——broker 只有 p1）
    assert records[0]["role_id"] == "washerwoman"
    assert records[0]["won"] is True
