"""Alpha 1.0 M5 AI player experience acceptance and sample report."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
REPORT_PATH = REPO_ROOT / "docs" / "alpha-1.0-ai-behavior-sample.md"


def _run_pytest() -> None:
    result = subprocess.run(
        [
            str(PYTHON),
            "-m",
            "pytest",
            "tests/test_agents/test_ai_persona.py",
            "tests/test_agents/test_agent_reasoning.py",
            "-q",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=240,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)


def _fmt_rate(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _sample_rounds(metrics: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for game in metrics.get("games", []):
        for record in game.get("round_records", []):
            samples.append(record)
            if len(samples) >= limit:
                return samples
    return samples


def _build_report(metrics: dict[str, Any]) -> str:
    vote_profiles = metrics.get("archetype_vote_profiles", {})
    level_breakdown = metrics.get("level_breakdown", {})
    fallback_probe = metrics.get("fallback_probe", {})
    samples = _sample_rounds(metrics)
    lines = [
        "# Alpha 1.0 M5 AI 行为样本",
        "",
        "## 摘要",
        "",
        f"- 评估局数：{metrics.get('game_count')}",
        f"- 每局压力档位：{metrics.get('rounds_per_game')}",
        f"- 记录总数：{metrics.get('records_total')}",
        f"- Persona 差异分：{_fmt_rate(metrics.get('persona_diversity_score'))}",
        f"- 多局稳定分：{_fmt_rate(metrics.get('multi_game_stability_score'))}",
        f"- 社交信任响应分：{_fmt_rate(metrics.get('social_trust_responsiveness_score'))}",
        f"- 弱信号不提名率：{_fmt_rate(metrics.get('weak_nomination_none_rate'))}",
        f"- 强信号提名率：{_fmt_rate(metrics.get('ai_strong_nomination_rate'))}",
        f"- 强信号赞成票率：{_fmt_rate(metrics.get('strong_vote_yes_rate'))}",
        f"- Fallback 探针动作数：{fallback_probe.get('action_count')}",
        f"- Fallback 探针触发数：{fallback_probe.get('fallback_count')}",
        "",
        "## Persona 投票画像",
        "",
        "| Persona | Yes Rate | Weak No Rate | Medium/Strong Yes Rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, profile in sorted(vote_profiles.items()):
        lines.append(
            f"| {name} | {_fmt_rate(profile.get('yes_rate'))} | "
            f"{_fmt_rate(profile.get('weak_no_rate'))} | "
            f"{_fmt_rate(profile.get('medium_strong_yes_rate'))} |"
        )

    lines.extend(
        [
            "",
            "## 行为分布",
            "",
            "```json",
            json.dumps(level_breakdown, ensure_ascii=False, indent=2),
            "```",
            "",
            "## Fallback 统计",
            "",
            "```json",
            json.dumps(fallback_probe, ensure_ascii=False, indent=2),
            "```",
            "",
            "## 样本记录",
            "",
            "| Game | Persona | Pressure | Nomination | Target | Vote |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
    )
    for record in samples:
        lines.append(
            f"| {record.get('game_index')} | {record.get('archetype')} | "
            f"{record.get('pressure')} | {record.get('nomination_action')} | "
            f"{record.get('nomination_target')} | {record.get('vote_decision')} |"
        )

    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- AI 在弱信号下保留意见、强信号下推动提名与投票，趋势门禁通过。",
            "- Persona 间的投票画像可区分，且同一 persona 多局表现保持稳定。",
            "- 公开发言回归覆盖私密信息与邪恶队友信息的防泄露边界。",
        ]
    )
    return "\n".join(lines) + "\n"


async def _fallback_probe_metrics() -> dict[str, Any]:
    from scripts.ai_evaluation import InvalidJSONBackend
    from src.agents.ai_agent import AIAgent, Persona
    from src.state.game_state import GamePhase, GameState, PlayerState, Team

    backend = InvalidJSONBackend()
    agent = AIAgent(
        player_id="p1",
        name="Fallback-Probe",
        backend=backend,
        persona=Persona(description="稳定兜底测试", speaking_style="平稳"),
    )
    players = (
        PlayerState(player_id="p1", name="Alice", role_id="washerwoman", team=Team.GOOD),
        PlayerState(player_id="p2", name="Bob", role_id="imp", team=Team.EVIL),
        PlayerState(player_id="p3", name="Cathy", role_id="chef", team=Team.GOOD),
    )
    agent.synchronize_role(players[0])

    day_state = GameState(
        game_id="m5-fallback-probe",
        players=players,
        phase=GamePhase.DAY_DISCUSSION,
        round_number=1,
        day_number=1,
        seat_order=("p1", "p2", "p3"),
    )
    nomination_state = day_state.with_update(phase=GamePhase.NOMINATION)
    vote_state = day_state.with_update(
        phase=GamePhase.VOTING,
        current_nominator="p3",
        current_nominee="p2",
    )
    for state, action_type in (
        (day_state, "speak"),
        (nomination_state, "nomination_intent"),
        (vote_state, "vote"),
    ):
        visible_state = agent._build_visible_state(state)
        legal_context = agent._build_legal_action_context(state, visible_state)
        await agent.act(visible_state, action_type, legal_context=legal_context)

    records = agent.export_action_metrics()
    fallback_records = [record for record in records if record.get("fallback_used")]
    return {
        "action_count": len(records),
        "fallback_count": len(fallback_records),
        "fallback_rate": round(len(fallback_records) / (len(records) or 1), 3),
        "fallback_by_action_type": {
            action_type: sum(1 for record in fallback_records if record.get("action_type") == action_type)
            for action_type in sorted({str(record.get("action_type")) for record in records})
        },
        "fallback_reasons": sorted({str(record.get("fallback_reason")) for record in fallback_records}),
    }


def main() -> int:
    if not PYTHON.exists():
        raise SystemExit(f"missing Python interpreter: {PYTHON}")

    _run_pytest()

    from scripts.ai_evaluation import _validate, evaluate_agents

    metrics = asyncio.run(evaluate_agents())
    _validate(metrics)
    metrics["fallback_probe"] = asyncio.run(_fallback_probe_metrics())
    REPORT_PATH.write_text(_build_report(metrics), encoding="utf-8")
    print(f"m5 ai player experience acceptance: ok")
    print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
