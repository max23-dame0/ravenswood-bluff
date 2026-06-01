"""Difficulty behavior acceptance: proves different difficulties produce different actions.

Tests that difficulty differences manifest in actual agent behavior, not just
static configuration fields. Covers prompt injection, temperature, decision
noise, and threshold offsets.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.ai_agent import AIAgent, Persona
from src.agents.decision_noise import DecisionNoise, _NOISE_MAGNITUDE, _BOLD_MOVE_PROB
from src.agents.difficulty_presets import PRESETS
from src.llm.base_backend import LLMBackend, LLMResponse, Message
from src.state.game_state import Team


_pass_count = 0
_fail_count = 0


def _check(label: str, condition: bool) -> None:
    global _pass_count, _fail_count
    if condition:
        _pass_count += 1
        print(f"  PASS  {label}")
    else:
        _fail_count += 1
        print(f"  FAIL  {label}")


class _StubBackend(LLMBackend):
    async def generate(self, system_prompt: str, messages: list[Message], **kwargs) -> LLMResponse:
        return LLMResponse(content="stub", tool_calls=[])

    def get_model_name(self) -> str:
        return "stub"

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 1536 for _ in texts]


def _make_agent(team: str, difficulty: str) -> AIAgent:
    backend = _StubBackend()
    persona = Persona(description="测试人格", speaking_style="测试风格")
    agent = AIAgent(
        player_id="p_test",
        name="TestAgent",
        backend=backend,
        persona=persona,
        difficulty=difficulty,
    )
    agent.team = team
    return agent


# ------------------------------------------------------------------
# 1. Prompt block differences across difficulties
# ------------------------------------------------------------------


def check_prompt_block_differences() -> None:
    print("[1] Prompt block differences across difficulties")
    difficulties = ("casual", "standard", "master", "chaos")

    # Good team: should see good_strategy_prompt on all difficulties now
    good_blocks = {}
    for d in difficulties:
        agent = _make_agent(Team.GOOD.value, d)
        block = agent._build_persona_prompt_block("speak")
        good_blocks[d] = block
        _check(f"good/{d} contains 【正义策略】", "【正义策略】" in block)
        _check(f"good/{d} does NOT contain 【邪恶策略】", "【邪恶策略】" not in block)

    # Evil team: should see evil_strategy_prompt
    evil_blocks = {}
    for d in difficulties:
        agent = _make_agent(Team.EVIL.value, d)
        block = agent._build_persona_prompt_block("speak")
        evil_blocks[d] = block
        _check(f"evil/{d} contains 【邪恶策略】", "【邪恶策略】" in block)
        _check(f"evil/{d} does NOT contain 【正义策略】", "【正义策略】" not in block)

    # Verify prompts are meaningfully different across difficulties
    _check("casual good block != master good block",
           good_blocks["casual"] != good_blocks["master"])
    _check("standard good block != master good block",
           good_blocks["standard"] != good_blocks["master"])
    _check("casual evil block != master evil block",
           evil_blocks["casual"] != evil_blocks["master"])
    _check("master evil block longer than standard evil block",
           len(evil_blocks["master"]) > len(evil_blocks["standard"]))


# ------------------------------------------------------------------
# 2. Temperature differences
# ------------------------------------------------------------------


def check_temperature_differences() -> None:
    print("[2] Temperature differences across difficulties")
    difficulties = ("casual", "standard", "master", "chaos")
    temps = {d: PRESETS[d].temperature for d in difficulties}

    _check("casual (0.9) > standard (0.7)", temps["casual"] > temps["standard"])
    _check("standard (0.7) > master (0.4)", temps["standard"] > temps["master"])
    _check("chaos (1.0) > standard (0.7)", temps["chaos"] > temps["standard"])
    _check("all four temperatures distinct", len(set(temps.values())) == 4)

    # Verify temperature_by_action exists for master and chaos
    _check("master has temperature_by_action", len(PRESETS["master"].temperature_by_action) > 0)
    _check("chaos has temperature_by_action", len(PRESETS["chaos"].temperature_by_action) > 0)


# ------------------------------------------------------------------
# 3. Decision noise differences
# ------------------------------------------------------------------


def check_decision_noise_differences() -> None:
    print("[3] Decision noise differences across difficulties")
    difficulties = ("casual", "standard", "master", "chaos")

    # Noise magnitude ordering
    magnitudes = {d: _NOISE_MAGNITUDE[d] for d in difficulties}
    _check("chaos magnitude (0.18) > casual (0.12)", magnitudes["chaos"] > magnitudes["casual"])
    _check("casual magnitude (0.12) > standard (0.05)", magnitudes["casual"] > magnitudes["standard"])
    _check("standard magnitude (0.05) > master (0.02)", magnitudes["standard"] > magnitudes["master"])

    # Bold move probability ordering
    bold_probs = {d: _BOLD_MOVE_PROB[d] for d in difficulties}
    _check("chaos bold_prob (0.15) > casual (0.08)", bold_probs["chaos"] > bold_probs["casual"])
    _check("casual bold_prob (0.08) > standard (0.03)", bold_probs["casual"] > bold_probs["standard"])
    _check("standard bold_prob (0.03) > master (0.01)", bold_probs["standard"] > bold_probs["master"])

    # Verify noise actually varies across difficulties for same context
    context_key = "vote_day3_nominee_p5"
    noises = {}
    for d in difficulties:
        dn = DecisionNoise(difficulty=d, player_id="p_test")
        noises[d] = dn.threshold_noise(context_key)

    # Chaos noise should have larger absolute value than master on average
    # (single sample may not differ due to hash, so test multiple contexts)
    chaos_bigger_count = 0
    for i in range(20):
        ctx = f"vote_day{i}_nominee_p5"
        chaos_noise = abs(DecisionNoise(difficulty="chaos", player_id="p1").threshold_noise(ctx))
        master_noise = abs(DecisionNoise(difficulty="master", player_id="p1").threshold_noise(ctx))
        if chaos_noise >= master_noise:
            chaos_bigger_count += 1
    _check("chaos noise >= master noise in most contexts (>=15/20)", chaos_bigger_count >= 15)


# ------------------------------------------------------------------
# 4. Persona override differences
# ------------------------------------------------------------------


def check_persona_override_differences() -> None:
    print("[4] Persona override differences across difficulties")

    # Nomination threshold offsets
    casual_offset = PRESETS["casual"].persona_overrides.get("nomination_threshold_offset", 0.0)
    standard_offset = PRESETS["standard"].persona_overrides.get("nomination_threshold_offset", 0.0)
    master_offset = PRESETS["master"].persona_overrides.get("nomination_threshold_offset", 0.0)
    chaos_offset = PRESETS["chaos"].persona_overrides.get("nomination_threshold_offset", 0.0)

    _check("casual nomination_threshold_offset > 0 (more conservative)", casual_offset > 0)
    _check("standard nomination_threshold_offset == 0 (baseline)", standard_offset == 0)
    _check("master nomination_threshold_offset < 0 (more aggressive)", master_offset < 0)
    _check("chaos nomination_threshold_offset < 0 (more aggressive)", chaos_offset < 0)

    # Assertiveness
    _check("casual assertiveness is passive",
           PRESETS["casual"].persona_overrides.get("assertiveness") == "passive")
    _check("master assertiveness is high",
           PRESETS["master"].persona_overrides.get("assertiveness") == "high")
    _check("chaos assertiveness is high",
           PRESETS["chaos"].persona_overrides.get("assertiveness") == "high")


# ------------------------------------------------------------------
# 5. Multi-axis parameter ordering
# ------------------------------------------------------------------


def check_multi_axis_ordering() -> None:
    print("[5] Multi-axis parameter ordering")

    # Master should have highest competence
    _check("master competence (0.85) > standard (0.5)",
           PRESETS["master"].competence > PRESETS["standard"].competence)
    _check("standard competence (0.5) > casual (0.3)",
           PRESETS["standard"].competence > PRESETS["casual"].competence)

    # Chaos should have highest volatility
    _check("chaos volatility (0.85) > casual (0.5)",
           PRESETS["chaos"].volatility > PRESETS["casual"].volatility)
    _check("casual volatility (0.5) > standard (0.2)",
           PRESETS["casual"].volatility > PRESETS["standard"].volatility)

    # Master should have highest deception
    _check("master deception (0.7) > chaos (0.5)",
           PRESETS["master"].deception > PRESETS["chaos"].deception)

    # Casual should have highest information_openness
    _check("casual information_openness (0.7) > standard (0.5)",
           PRESETS["casual"].information_openness > PRESETS["standard"].information_openness)
    _check("standard information_openness (0.5) > master (0.3)",
           PRESETS["standard"].information_openness > PRESETS["master"].information_openness)


# ------------------------------------------------------------------
# 6. Latency budget differences
# ------------------------------------------------------------------


def check_latency_budget_differences() -> None:
    print("[6] Latency budget differences")
    # Casual should have more relaxed budgets than master
    for action in ("vote", "speak", "nomination_intent"):
        casual_budget = PRESETS["casual"].latency_budget[action]
        master_budget = PRESETS["master"].latency_budget[action]
        _check(f"casual {action} budget ({casual_budget}ms) >= master ({master_budget}ms)",
               casual_budget >= master_budget)


# ------------------------------------------------------------------
# 7. Nomination intelligence differences
# ------------------------------------------------------------------


def check_nomination_intelligence_differences() -> None:
    print("[7] Nomination intelligence differences")

    # 7a. Axis ordering
    _check("master nomination_intelligence (0.85) > standard (0.5)",
           PRESETS["master"].nomination_intelligence > PRESETS["standard"].nomination_intelligence)
    _check("standard nomination_intelligence (0.5) > casual (0.2)",
           PRESETS["standard"].nomination_intelligence > PRESETS["casual"].nomination_intelligence)
    _check("chaos nomination_intelligence (0.4) in [0.2, 0.5]",
           0.2 <= PRESETS["chaos"].nomination_intelligence <= 0.5)
    _check("all nomination_intelligence in [0,1]",
           all(0.0 <= PRESETS[k].nomination_intelligence <= 1.0 for k in ("casual", "standard", "master", "chaos")))

    # 7b. Margin ordering: casual (low intel) needs bigger gap than master (high intel)
    from src.agents.decision.decision_engine import DecisionEngine

    agents = {}
    for d in ("casual", "standard", "master", "chaos"):
        agent = _make_agent(Team.GOOD.value, d)
        # Need a minimal persona_profile for DecisionEngine
        agent.persona_profile = {"archetype": None, "risk_tolerance": "均衡", "assertiveness": "中性"}
        agents[d] = DecisionEngine(agent)

    casual_margin = agents["casual"].nomination_margin()
    master_margin = agents["master"].nomination_margin()
    _check(f"casual margin ({casual_margin:.3f}) > master margin ({master_margin:.3f})",
           casual_margin > master_margin)

    # 7c. Evil protection scaling: master evil protects teammates more than casual evil
    # Use a mock visible_state with a target that is a confirmed evil teammate
    from unittest.mock import MagicMock
    from src.agents.memory.social_graph import PlayerProfile

    for d in ("casual", "master"):
        agent = _make_agent(Team.EVIL.value, d)
        agent.persona_profile = {"archetype": None, "social_style": "独立"}

        # Set up social graph with a profile for the target
        profile = PlayerProfile(player_id="p_target", name="TeammateTarget")
        agent.social_graph.profiles["p_target"] = profile

        # Set up working memory with evil teammate info
        agent.working_memory.remember_objective_info("evil_teammates", "TeammateTarget 是你的邪恶队友")

        # Create minimal visible_state
        mock_player = MagicMock()
        mock_player.player_id = "p_target"
        mock_player.name = "TeammateTarget"
        mock_state = MagicMock()
        mock_state.players = [mock_player]
        mock_state.nominees_today = ()
        mock_state.current_nominee = None
        mock_state.current_nominator = None
        mock_state.day_number = 1

        engine = DecisionEngine(agent)
        score = engine.target_signal_score("p_target", mock_state)

        if d == "casual":
            casual_evil_score = score
        else:
            master_evil_score = score

    _check(f"master evil teammate score ({master_evil_score:.3f}) < casual evil teammate score ({casual_evil_score:.3f})",
           master_evil_score < casual_evil_score)

    # 7d. High-value target identification: master evil targets info roles more
    for d in ("casual", "master"):
        agent = _make_agent(Team.EVIL.value, d)
        agent.persona_profile = {"archetype": None, "social_style": "独立"}

        profile = PlayerProfile(player_id="p_ft", name="FortuneTellerPlayer")
        profile.current_self_claim = "fortune_teller"
        agent.social_graph.profiles["p_ft"] = profile

        mock_player = MagicMock()
        mock_player.player_id = "p_ft"
        mock_player.name = "FortuneTellerPlayer"
        mock_state = MagicMock()
        mock_state.players = [mock_player]
        mock_state.nominees_today = ()
        mock_state.current_nominee = None
        mock_state.current_nominator = None
        mock_state.day_number = 1

        engine = DecisionEngine(agent)
        score = engine.target_signal_score("p_ft", mock_state)

        if d == "casual":
            casual_ft_score = score
        else:
            master_ft_score = score

    _check(f"master evil FT target score ({master_ft_score:.3f}) > casual ({casual_ft_score:.3f})",
           master_ft_score > casual_ft_score)

    # 7e. Bold move probability: chaos > master
    chaos_bmp = _BOLD_MOVE_PROB["chaos"]
    master_bmp = _BOLD_MOVE_PROB["master"]
    _check(f"chaos bold_move_prob ({chaos_bmp}) > master ({master_bmp})",
           chaos_bmp > master_bmp)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main() -> int:
    print("=" * 60)
    print("Difficulty behavior acceptance checks")
    print("=" * 60)

    check_prompt_block_differences()
    check_temperature_differences()
    check_decision_noise_differences()
    check_persona_override_differences()
    check_multi_axis_ordering()
    check_latency_budget_differences()
    check_nomination_intelligence_differences()

    print("=" * 60)
    total = _pass_count + _fail_count
    print(f"Results: {_pass_count}/{total} passed, {_fail_count}/{total} failed")
    print("=" * 60)

    if _fail_count > 0:
        print("difficulty behavior acceptance: FAILED")
        return 1

    print("difficulty behavior acceptance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
