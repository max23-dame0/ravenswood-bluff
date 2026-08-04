r"""Token 预算基准（PLN-037 P2-4.9）。

离线验证 PLN-037 P0/P1 的 token 控制效果，无需 API key：

1. **策略表检查**：`LLM_STRATEGY_BY_ACTION` 覆盖全部动作，简单动作关闭思考，
   发言类降 effort 且限 max_tokens。
2. **三层前缀稳定**：同一 agent 在相同轮次内连续调用 `act()`，
   system_prompt（稳定规则层）与首条 user 消息（稳定长上下文）逐 token 一致。
3. **公共前缀共享**：两个不同 agent 的 system_prompt 共享同一公共规则前缀开头。
4. **草稿复用**：`cached_speech_draft` 存在时 `act("speak")` 跳过二次 LLM
   （backend 调用次数 = 0），token 输出减半。

输出 JSON 到 `--json-output`（默认打印控制台）。

Examples:
  .\.venv\Scripts\python.exe scripts\benchmark\token_budget_benchmark.py
  .\.venv\Scripts\python.exe scripts\benchmark\token_budget_benchmark.py --json-output docs/plans/token-budget-benchmark.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.ai_agent import AIAgent
from src.agents.persona.persona import Persona
from src.state.game_state import GamePhase, GameState, PlayerState, Team
from tests.doubles import CapturingBackend


class _CountingBackend(CapturingBackend):
    """记录调用次数与 system 前缀，返回可控 JSON。"""

    def __init__(
        self, content: str = '{"action":"speak","content":"ok","tone":"calm","reasoning":"ok"}'
    ) -> None:
        super().__init__(content=content)
        self.call_count = 0
        self.systems: list[str] = []
        self.first_messages: list[str] = []

    async def generate(self, system_prompt: str, messages: list[Any], **kwargs: Any):
        from src.llm.base_backend import LLMResponse

        self.call_count += 1
        self.systems.append(system_prompt)
        if messages:
            self.first_messages.append(messages[0].content)
        return LLMResponse(content=self.content, tool_calls=[])


def _make_state(day: int = 1, round_no: int = 1) -> GameState:
    return GameState(
        game_id="bench-game",
        phase=GamePhase.DAY_DISCUSSION,
        round_number=round_no,
        day_number=day,
        players=(
            PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
            PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
            PlayerState(player_id="p3", name="Charlie", role_id="chef", team=Team.GOOD),
        ),
    )


async def _check_strategy_table() -> dict[str, Any]:
    missing = [a for a in AIAgent.LLM_STRATEGY_BY_ACTION if not a]
    simple = AIAgent._llm_strategy_for_action("vote")
    speak = AIAgent._llm_strategy_for_action("speak")
    return {
        "ok": True,
        "strategy_actions": sorted(AIAgent.LLM_STRATEGY_BY_ACTION.keys()),
        "simple_vote_thinking": simple["thinking"],
        "speak_reasoning_effort": speak["reasoning_effort"],
        "speak_max_tokens": speak["max_tokens"],
        "missing_actions": missing,
    }


async def _check_three_tier_prefix() -> dict[str, Any]:
    backend = _CountingBackend()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    state = _make_state()
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)
    await agent.act(visible_state, "speak")
    await agent.act(visible_state, "speak")
    system_stable = backend.systems[0] == backend.systems[1]
    first_msg_stable = (
        len(backend.first_messages) >= 2 and backend.first_messages[0] == backend.first_messages[1]
    )
    return {
        "ok": system_stable and first_msg_stable,
        "system_stable": system_stable,
        "first_user_msg_stable": first_msg_stable,
        "system_prefix_chars": len(backend.systems[0]) if backend.systems else 0,
    }


async def _check_common_prefix() -> dict[str, Any]:
    from src.agents.prompt.common_rules import build_global_static_layer

    b1 = _CountingBackend()
    b2 = _CountingBackend()
    a1 = AIAgent(
        player_id="p1",
        name="Alice",
        backend=b1,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    a2 = AIAgent(
        player_id="p2",
        name="Bob",
        backend=b2,
        persona=Persona(description="激进", speaking_style="快人快语"),
    )
    state = _make_state()
    a1.synchronize_role(state.get_player("p1"))
    a2.synchronize_role(state.get_player("p2"))
    vs1 = a1._build_visible_state(state)
    vs2 = a2._build_visible_state(state)
    await a1.act(vs1, "speak")
    await a2.act(vs2, "speak")
    # PLN-039 T1：层1 全局静态层跨 Agent 100% 逐 token 一致（不再仅比较基础规则段）。
    global_layer = build_global_static_layer()
    share1 = b1.systems[0].startswith(global_layer)
    share2 = b2.systems[0].startswith(global_layer)
    identical = b1.systems[0][: len(global_layer)] == b2.systems[0][: len(global_layer)]
    return {
        "ok": share1 and share2 and identical,
        "both_share_global_layer": share1 and share2,
        "global_layer_identical_across_agents": identical,
        "global_layer_chars": len(global_layer),
    }


async def _check_draft_reuse() -> dict[str, Any]:
    backend = _CountingBackend()
    agent = AIAgent(
        player_id="p1",
        name="Alice",
        backend=backend,
        persona=Persona(description="谨慎", speaking_style="平稳"),
    )
    state = _make_state()
    agent.synchronize_role(state.get_player("p1"))
    visible_state = agent._build_visible_state(state)
    # 无草稿：1 次 LLM
    await agent.act(visible_state, "speak")
    calls_without_draft = backend.call_count
    # 有草稿：0 次 LLM（直接复用）
    backend.call_count = 0
    await agent.act(visible_state, "speak", cached_speech_draft="我怀疑 Bob，需要更多人聊聊。")
    calls_with_draft = backend.call_count
    return {
        "ok": calls_without_draft == 1 and calls_with_draft == 0,
        "calls_without_draft": calls_without_draft,
        "calls_with_draft": calls_with_draft,
    }


async def main_async(args: argparse.Namespace) -> int:
    from src.agents.tools.action_tool_registry import GameActionToolRegistry

    print("Token budget benchmark (offline, no API key)")
    print("=" * 72)

    results: dict[str, Any] = {}
    results["strategy_table"] = await _check_strategy_table()
    results["three_tier_prefix"] = await _check_three_tier_prefix()
    results["common_prefix"] = await _check_common_prefix()
    results["draft_reuse"] = await _check_draft_reuse()
    results["registry"] = {
        "all_tool_names": [d.name for d in GameActionToolRegistry.all_tool_defs()],
        "tool_count": len(GameActionToolRegistry.all_tool_defs()),
    }

    ok = True
    for name, item in results.items():
        if isinstance(item, dict) and item.get("ok") is False:
            ok = False
        print(f"[{name}] ok={item.get('ok', '-')} {json.dumps(item, ensure_ascii=False)}")

    print("=" * 72)
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")

    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote JSON: {output_path}")
    return 0 if ok else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", default="", help="Optional path to write JSON results.")
    return parser.parse_args()


def main() -> int:
    import asyncio

    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
