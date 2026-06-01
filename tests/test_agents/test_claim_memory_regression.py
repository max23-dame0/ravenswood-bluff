import pytest

from src.agents.ai_agent import AIAgent, Persona
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.state.game_state import GameEvent, GamePhase, GameState, PlayerState, Team, Visibility


class DummyBackend(LLMBackend):
    async def generate(self, system_prompt: str, messages: list[Message], **kwargs) -> LLMResponse:
        return LLMResponse(content="{}", tool_calls=[])

    def get_model_name(self) -> str:
        return "dummy"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


def _agent_ctx(agent: AIAgent, state: GameState):
    visible_state = agent._build_visible_state(state)
    legal_context = agent._build_legal_action_context(state, visible_state)
    return visible_state, legal_context


@pytest.mark.asyncio
async def test_claim_history_tracks_self_claim_then_denial_across_multiple_days():
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "我跳预言家。"},
        ),
        visible_state,
    )

    day2 = state.model_copy(update={"day_number": 2, "round_number": 2})
    visible_day2, _ = _agent_ctx(agent, day2)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=2,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "我什么时候说我是预言家了？"},
        ),
        visible_day2,
    )

    bob = agent.social_graph.get_profile("p2")
    assert bob is not None
    assert len(bob.claim_history) == 2
    assert bob.claim_history[0].claim_type == "self_claim"
    assert bob.claim_history[1].claim_type == "denial"


@pytest.mark.asyncio
async def test_self_claim_with_named_players_does_not_assign_claimed_role_to_mentioned_players():
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="h1", name="Human", role_id="investigator", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p3", name="Charlie", role_id="librarian", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="h1",
            visibility=Visibility.PUBLIC,
            payload={"content": "我跳调查员，我怀疑 Bob 和 Charlie 里有问题。"},
        ),
        visible_state,
    )

    human = agent.social_graph.get_profile("h1")
    bob = agent.social_graph.get_profile("p2")
    charlie = agent.social_graph.get_profile("p3")
    assert human is not None and human.claimed_role_id == "investigator"
    assert bob is None or bob.claimed_role_id is None
    assert charlie is None or charlie.claimed_role_id is None


@pytest.mark.asyncio
async def test_public_claim_remains_visible_in_summary_after_phase_archive():
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="fortune_teller", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "我跳预言家。"},
        ),
        visible_state,
    )
    await agent.archive_phase_memory(visible_state)

    context = agent.working_memory.get_recent_context()
    assert "公开场上的普通信息" in context
    assert "Bob 公开跳身份为 占卜师" in context
    assert "身份发言记录" in agent.social_graph.get_graph_summary()


@pytest.mark.asyncio
async def test_cross_sentence_text_does_not_create_false_relay():
    """Regression: greedy regex must not match across sentence boundaries.
    'P4 说他觉得可疑。P6 跳了陌客' should NOT create P4→陌客 relay."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p4", name="David", role_id="investigator", team=Team.GOOD),
            PlayerState(player_id="p6", name="Frank", role_id="recluse", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p6",
            visibility=Visibility.PUBLIC,
            payload={"content": "David 说他觉得大家都很可疑。我是陌客，我的技能容易干扰侦测。"},
        ),
        visible_state,
    )

    # p6 should have a self_claim for recluse
    frank = agent.social_graph.get_profile("p6")
    assert frank is not None
    assert frank.current_self_claim == "recluse"

    # p4 should NOT have a relay claim for recluse
    david = agent.social_graph.get_profile("p4")
    # David should either not exist or have no claim about recluse
    if david is not None:
        for record in david.claim_history:
            assert not (record.role_id == "recluse" and record.claim_type == "self_claim")


@pytest.mark.asyncio
async def test_single_sentence_relay_still_works():
    """Ensure legitimate single-sentence relay claims still extract correctly.
    Relay claims are stored in the speaker's claims_about_others."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p4", name="David", role_id="investigator", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "David 说他跳了调查员。"},
        ),
        visible_state,
    )

    # Relay claim is stored in speaker's (p2's) claims_about_others
    bob = agent.social_graph.get_profile("p2")
    assert bob is not None
    assert "p4" in bob.claims_about_others
    relay_records = [r for r in bob.claims_about_others["p4"] if r.claim_type == "relay" and r.role_id == "investigator"]
    assert len(relay_records) > 0

    # David should have a note about the relay
    david = agent.social_graph.get_profile("p4")
    assert david is not None
    assert any("调查员" in n for n in david.notes)


@pytest.mark.asyncio
async def test_self_claim_with_say_keyword_not_blocked():
    """Regression: '我想说的是，我是陌客' should match as self_claim.
    The (?<!说) lookbehind was too aggressive."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="recluse", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "我想说的是，我是陌客。"},
        ),
        visible_state,
    )

    bob = agent.social_graph.get_profile("p2")
    assert bob is not None
    assert bob.current_self_claim == "recluse"


@pytest.mark.asyncio
async def test_relay_note_has_distinctive_prefix():
    """Relay notes in social graph should be prefixed to distinguish from self-claims."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p4", name="David", role_id="investigator", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "David 说他跳了调查员。"},
        ),
        visible_state,
    )

    david = agent.social_graph.get_profile("p4")
    assert david is not None
    # Notes should contain the relay prefix
    relay_notes = [n for n in david.notes if "转述" in n]
    assert any("[转述-非自报]" in n for n in relay_notes), f"Expected [转述-非自报] prefix in notes: {david.notes}"


@pytest.mark.asyncio
async def test_cross_sentence_accusation_does_not_false_match():
    """Regression: 'P4 很可疑。P6 像陌客' should NOT accuse P4 of being recluse."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p4", name="David", role_id="investigator", team=Team.GOOD),
            PlayerState(player_id="p6", name="Frank", role_id="recluse", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p1",
            visibility=Visibility.PUBLIC,
            payload={"content": "我觉得 David 很可疑。不过 Frank 像 陌客。"},
        ),
        visible_state,
    )

    # David should NOT be accused of being recluse
    david = agent.social_graph.get_profile("p4")
    if david is not None:
        accusation_records = [r for r in david.claim_history if r.role_id == "recluse" and r.claim_type in {"accusation", "question"}]
        assert len(accusation_records) == 0, f"David should not be accused of recluse: {accusation_records}"


@pytest.mark.asyncio
async def test_defense_speech_discussing_baron_does_not_create_false_self_claim():
    """Regression: A defense speech that discusses Baron in relay/hypothetical/denial
    contexts must NOT register the speaker as claiming Baron.

    Real-world example from user report: Player 4's defense mentions Baron multiple
    times (relay: "你说3号或者我是男爵", hypothetical: "要是真有男爵",
    denial: "根本没有男爵") but is NOT claiming to be Baron.
    """
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.NOMINATION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p3", name="Charlie", role_id="investigator", team=Team.GOOD),
            PlayerState(player_id="p4", name="David", role_id="empath", team=Team.GOOD),
            PlayerState(player_id="p5", name="Eve", role_id="imp", team=Team.EVIL),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)

    defense_text = (
        "P1，你这一直盯着我不放，是不是剧本拿错了？"
        "你说 3 号或者我是男爵，现在 3 号都走了，你还非要拉我陪葬？"
        "7 号提的那个'外来者坑位'可是个硬伤，要是真有男爵，"
        "场上那另外两个外来者是集体掉线了吗？还是说根本就没有男爵，"
        "只是有人在编故事？"
    )
    await agent.observe_event(
        GameEvent(
            event_type="defense_started",
            phase=GamePhase.NOMINATION,
            round_number=1,
            actor="p4",
            visibility=Visibility.PUBLIC,
            payload={"content": defense_text},
        ),
        visible_state,
    )

    david = agent.social_graph.get_profile("p4")
    # David should NOT have a self_claim for baron
    assert david is None or david.current_self_claim != "baron", (
        f"Defense speech discussing Baron should not create self_claim. "
        f"current_self_claim={david.current_self_claim if david else None}, "
        f"history={david.claim_history if david else []}"
    )
    # No self_claim records for baron at all
    if david is not None:
        self_claims = [r for r in david.claim_history if r.role_id == "baron" and r.claim_type == "self_claim"]
        assert len(self_claims) == 0, f"Defense speech should not produce baron self_claim: {self_claims}"


@pytest.mark.asyncio
async def test_player_speaks_with_relay_context_does_not_create_false_self_claim():
    """Regression: 'Alice 一直说我是男爵' in player_speaks should NOT
    produce a self_claim for baron due to the relay attribution context."""
    agent = AIAgent("p1", "Alice", DummyBackend(), Persona("谨慎村民", "平稳"))
    state = GameState(
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="chef", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="washerwoman", team=Team.GOOD),
        ),
    )
    visible_state, _ = _agent_ctx(agent, state)
    await agent.observe_event(
        GameEvent(
            event_type="player_speaks",
            phase=GamePhase.DAY_DISCUSSION,
            round_number=1,
            actor="p2",
            visibility=Visibility.PUBLIC,
            payload={"content": "Alice 一直说我是男爵，但我不是。"},
        ),
        visible_state,
    )

    bob = agent.social_graph.get_profile("p2")
    assert bob is not None
    # Bob should NOT have a self_claim for baron — the relay context is detected
    baron_self_claims = [r for r in bob.claim_history if r.role_id == "baron" and r.claim_type == "self_claim"]
    assert len(baron_self_claims) == 0, f"Relay context should not produce baron self_claim: {baron_self_claims}"
